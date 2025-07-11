import discord
from discord.ext import commands
from discord import app_commands
import httpx
import base64
import fitz
from PIL import Image
from io import BytesIO
import asyncio
from asyncio import Queue
import textwrap
from google import genai
from google.genai import types
from monitoramento import Tokens
import traceback
import datetime
import os

from google.genai.errors import ServerError
from google.genai.errors import ClientError

class Chat(commands.Cog):
    def __init__(self, bot):
        self.bot: commands.Bot = bot
        self.model: str = bot.model
        self.generation_config: types.GenerateContentConfig = bot.generation_config
        self.chats: dict = bot.chats
        self.http_client: httpx.AsyncClient = bot.http_client
        self.processing = {}
        self.message_queue = {}
        self.client: genai.Client = bot.client
        self.tokens_monitor: Tokens = bot.tokens_monitor
        self.timeout_users = {"Now": f"{datetime.datetime.now().minute}"} # so provisioriamente esse timeout ai




    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):

        # ignora mensagens efêmeras e de bots
        if not message.flags.ephemeral and not message.author.bot:
            if message.guild is None:
                rogerio_permissions = message.channel.permissions_for(self.bot.user)
            else:
                rogerio_permissions = message.channel.permissions_for(message.guild.me)

            channel_id = str(message.channel.id)

            if (f"<@{self.bot.user.id}>" in message.content or
                    isinstance(message.channel, discord.DMChannel) or
                    self.bot.user in message.mentions) and rogerio_permissions.send_messages:
                

                 # sitema provisorio de timeout para evitar flood
                now = datetime.datetime.now()
                if self.timeout_users.get("Now") != f"{now.minute}":
                    self.timeout_users = {"Now": f"{now.minute}"}
                    self.timeout_users[f"{message.author.id}"] = 1
                else:
                    if self.timeout_users.get(f"{message.author.id}") is None:
                        self.timeout_users[f"{message.author.id}"] = 1
                    else:
                        self.timeout_users[f"{message.author.id}"] += 1
                
                if self.timeout_users[f"{message.author.id}"] >= 10:
                    return await message.add_reaction("⏳")
                
                # segmento normal
                if self.message_queue.get(channel_id) is None:
                    self.message_queue[channel_id] = Queue()

                await self.message_queue[channel_id].put(message)

                if not self.processing.get(channel_id, False):
                    self.processing[channel_id] = True
                    await self.process_queue(channel_id)

    async def process_attachments(self, attachments):
        images = []
        text_file_content = None
        pdfs = []

        for attachment in attachments:
            if attachment.content_type.startswith("image/"):
                response = await self.http_client.get(attachment.url)
                response.raise_for_status()
                image = types.Part.from_bytes(data=response.content, mime_type=attachment.content_type)
                images.append(image)


            if attachment.content_type == "application/pdf":
                """LER PDF AQUI"""
                pdf_content = await self.http_client.get(attachment.url)
                pdf_content.raise_for_status()
                pdf_part = types.Part.from_bytes(
                    data=pdf_content.content,
                    mime_type=attachment.content_type
                )
                pdfs.append(pdf_part)


            elif attachment.content_type.startswith("text/plain"):
                response = await self.http_client.get(attachment.url)
                response.raise_for_status()
                try:
                    text_file_content = response.content.decode('utf-8')
                except UnicodeDecodeError:
                    text_file_content = "Erro: Não foi possível decodificar o conteúdo do arquivo .txt."

        return images, text_file_content, pdfs

    async def process_queue(self, channel_id: str):
        while not self.message_queue[channel_id].empty():
            message: discord.Message = await self.message_queue[channel_id].get()
            channel_id = str(message.channel.id)

            try:
                self.processing[channel_id] = True

                if channel_id not in self.chats:
                    # creando chat ai
                    self.chats[channel_id] = self.client.aio.chats.create(
                        model=self.model,
                        config=self.generation_config,
                    )
                chat = self.chats[channel_id]

                atividades = [atividade.name for atividade in message.author.activities] if not isinstance(
                    message.channel, discord.DMChannel) and message.author.activities else []

                referenced_content = ""
                if message.reference:
                    referenced_message = await message.channel.fetch_message(message.reference.message_id)
                    if referenced_message.author.id == self.bot.user.id:
                        referenced_content = (
                            f" (em resposta a uma solicitação anterior: '{referenced_message.content}' de "
                            f"{referenced_message.author.name})"
                        )
                    else:
                        referenced_content = (
                            f" (em resposta a: '{referenced_message.content}' de {referenced_message.author.name})"
                        )

                prompt = f'Informaçoes: Mensagem de "{message.author.display_name}"'
                if atividades:
                    prompt += f", ativo agora em: discord(aqui), {', '.join(atividades)}"
                prompt += f": {message.content.replace(f'<@{self.bot.user.id}>', 'Rogerio Tech')}{referenced_content}"

                async with message.channel.typing():
                    images = []
                    text_file_content = None
                    pdfs = []
                    if message.attachments:
                        images, text_file_content, pdfs = await self.process_attachments(message.attachments)
                    if text_file_content:
                        prompt += (
                            f"\n\nInstruções: Analise o conteúdo do arquivo .txt anexado e responda à mensagem do "
                            f"usuário com base nesse conteúdo. Se o usuário não fornecer uma instrução clara, descreva "
                            f"o conteúdo do arquivo de forma natural, engraçada e irônica.\n\n"
                            f"Conteúdo do arquivo .txt anexado:\n```text\n{text_file_content}\n```"
                        )
                    if pdfs:
                        prompt = [prompt] + pdfs
                    if images:
                        prompt = [prompt] + images
                    

                    # fodase o stream

                    
                    _response: types.GenerateContentResponse = await chat.send_message(message=prompt)
                    usage_metadata = _response.usage_metadata
                    
                    self.tokens_monitor.insert_usage(
                        uso=(usage_metadata.prompt_token_count + usage_metadata.candidates_token_count),
                        guild_id=message.guild.id if message.guild else "dm",
                    ) # adicionando no banco de dados ne 

                # dividir tb
                def split_message(text, max_length=1900):
                    lines = text.split('\n')  # dividir p quebrar a linha
                    messages = []
                    current_message = ""

                    for line in lines:
                        # verifica se passou o limite
                        if len(current_message) + len(line) + 1 <= max_length:
                            current_message += line + '\n'
                        else:
                            # se a msg n tiver vazia adiciona a lista
                            if current_message:
                                messages.append(current_message.rstrip('\n'))
                            # inicia a conversa na linha atual
                            current_message = line + '\n'

                    # add a ultima mensagem, se tiver
                    if current_message:
                        messages.append(current_message.rstrip('\n'))

                    return messages

                mensagens_divididas = split_message(_response.text)

                for mensagem_dividida in mensagens_divididas:
                    await message.reply(mensagem_dividida, mention_author=False)

            except discord.HTTPException as e:
                if e.status == 429:
                    await asyncio.sleep(2)
                    embed = discord.Embed(
                        title="Rate Limit Excedido",
                        description="Aguarde um momento, estou enviando muitas mensagens rápido demais!",
                        color=discord.Color.yellow()
                    )
                    await message.channel.send(embed=embed)
                else:
                    traceback.print_exc()
            except ClientError as e:
                if e.status == 429:
                    await message.add_reaction("⏳")
                    # reagir se exceder o limite de requisições
            except ServerError:
                embed = discord.Embed(
                    title="Erro do Servidor",
                    description="Ocorreu um erro de Comunicação com o servidor.",
                    color=discord.Color.red()
                )
                await message.channel.send(embed=embed)
            except Exception:
                    e = traceback.format_exc()
                    embed = discord.Embed(
                        title="Ocorreu Um Erro!",
                        description=f"\n```py\n{e[:4000]}\n```",
                        color=discord.Color.red()
                    )
                    embed.set_footer(text="Suporte: https://discord.gg/H77FTb7hwH")
                    try:
                        await message.channel.send(embed=embed)
                    except Exception as send_erro:
                        print("Erro ao tentar enviar mensagem de erro:")
                        traceback.print_exc()

            finally:
                self.message_queue[channel_id].task_done()
                self.processing[channel_id] = False
                if not self.message_queue[channel_id].empty():
                    await self.process_queue(channel_id)



async def setup(bot):
    # adiciona o cog ao bot
    await bot.add_cog(Chat(bot))