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

from google.genai import types

class Chat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.model = bot.model
        self.generation_config = bot.generation_config
        self.chats = bot.chats
        self.httpClient = bot.httpclient
        self.processing = {}
        self.message_queue = {}
        self.client = bot.client

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):

        if not message.flags.ephemeral and not message.author.bot:

            if message.guild is None:
                rogerioPermissoes = message.channel.permissions_for(self.bot.user)
            else:
                rogerioPermissoes = message.channel.permissions_for(message.guild.me)

            channel_id = str(message.channel.id)

            if (f"<@{self.bot.user.id}>" in message.content or 
                isinstance(message.channel, discord.DMChannel) or 
                self.bot.user in message.mentions) and rogerioPermissoes.send_messages:

                if self.message_queue.get(channel_id) is None:
                    self.message_queue[channel_id] = Queue()

                await self.message_queue[channel_id].put(message)

                if not self.processing.get(channel_id, False):
                    self.processing[channel_id] = True
                    await self.process_queue(channel_id)

    async def process_queue(self, channel_id: str):
        while not self.message_queue[channel_id].empty():
            message: discord.Message = await self.message_queue[channel_id].get()
            channel_id = str(message.channel.id)

            try:
                self.processing[channel_id] = True

                if channel_id not in self.chats:
                    self.chats[channel_id] = self.client.aio.chats.create(model=self.model, config=self.generation_config)
                chat = self.chats[channel_id]

                atividades = [atividade.name for atividade in message.author.activities] if not isinstance(message.channel, discord.DMChannel) and message.author.activities else []

                referenced_content = ""
                if message.reference:
                    referenced_message = await message.channel.fetch_message(message.reference.message_id)
                    if referenced_message.author.id == self.bot.user.id:
                        referenced_content = f" (em resposta a uma solicitação anterior: '{referenced_message.content}' de {referenced_message.author.name})"
                    else:
                        referenced_content = f" (em resposta a: '{referenced_message.content}' de {referenced_message.author.name})"

                prompt = f'Informaçoes: Mensagem de "{message.author.display_name}"'
                if atividades:
                    prompt += f", ativo agora em: discord(aqui), {', '.join(atividades)}"
                prompt += f": {message.content.replace(f'<@{self.bot.user.id}>', 'Rogerio Tech')}{referenced_content}"

                async with message.channel.typing():
                    images = []
                    text_file_content = None
                    if message.attachments:
                        for attachment in message.attachments:
                            print(f"Anexo detectado: {attachment.filename}, Tipo: {attachment.content_type}")  # log temp
                            if attachment.content_type.startswith("image/"):
                                response = await self.httpClient.get(attachment.url)
                                response.raise_for_status()
                                image = types.Part.from_bytes(data=response.content, mime_type=attachment.content_type)
                                images.append(image)
                            if attachment.content_type == "application/pdf":
                                # for attachment in message.attachments:
                                #     response = await self.httpClient.get(attachment.url)
                                #     response.raise_for_status()
                                #     pdf_document = fitz.open(stream=response.content, filetype="pdf")
                                #     for page in pdf_document:
                                #         pixmap = page.get_pixmap()
                                #         img = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
                                #         img_buffer = BytesIO()
                                #         img.save(img_buffer, format="PNG")
                                #         b64_encoded = base64.b64encode(img_buffer.getvalue()).decode('utf-8')
                                #         images.append({'mime_type': 'image/png', 'data': b64_encoded})
                                raise("Leitor de pdf desativado por enquanto.")
                            elif attachment.content_type.startswith("text/plain"): 
                                response = await self.httpClient.get(attachment.url)
                                response.raise_for_status()
                                try:
                                    text_file_content = response.content.decode('utf-8')
                                    print(f"Conteúdo do arquivo .txt lido com sucesso: {text_file_content}")  # log temp
                                except UnicodeDecodeError as e:
                                    print(f"Erro ao decodificar o arquivo .txt: {e}")  # log temp
                                    text_file_content = "Erro: Não foi possível decodificar o conteúdo do arquivo .txt."

                        if images:
                            prompt = [prompt] + images
                        if text_file_content:
                            prompt += f"\n\nInstruções: Analise o conteúdo do arquivo .txt anexado e responda à mensagem do usuário com base nesse conteúdo. Se o usuário não fornecer uma instrução clara, descreva o conteúdo do arquivo de forma natural, engraçada e irônica.\n\nConteúdo do arquivo .txt anexado:\n```text\n{text_file_content}\n```"

                    # fodase o stream 

                    print(f"Prompt enviado ao modelo: {prompt}")  # log temp
                    _response = await chat.send_message(message=prompt)
                    print(f"Resposta do modelo: {_response.text}")  # log temp

                # dividir tb
                def split_message(text, max_length=1900):
                    lines = text.split('\n')  # dividir p quebrar a linha
                    messages = []
                    current_message = ""
                    
                    for line in lines:
                        # veriica se passou o limite
                        if len(current_message) + len(line) + 1 <= max_length:
                            current_message += line + '\n'
                        else:
                            # se a msg n tiver vazia adiciona a lista
                            if current_message:
                                messages.append(current_message.rstrip('\n'))
                            # inicia  aconversa na linha atual
                            current_message = line + '\n'
                    
                    # add a ultima mensagem, se tiver
                    if current_message:
                        messages.append(current_message.rstrip('\n'))
                    
                    return messages

                _responseDividida = split_message(_response.text)

                for _m in _responseDividida:
                    mensagem_enviada = await message.reply(_m, mention_author=False)

                self.message_queue[channel_id].task_done()

            except Exception as e:
                self.message_queue[channel_id].task_done()
                if isinstance(e, discord.HTTPException) and e.status == 429:
                    await asyncio.sleep(2)
                    embed = discord.Embed(title="Rate Limit Excedido", description="Aguarde um momento, estou enviando muitas mensagens rápido demais!", color=discord.Color.yellow())
                    await message.channel.send(embed=embed)
                else:
                    embed = discord.Embed(title="Ocorreu Um Erro!", description=f"\n```py\n{str(e)}\n```", color=discord.Color.red())
                    await message.channel.send(embed=embed)

            finally:
                self.processing[channel_id] = False
                if not self.message_queue[channel_id].empty():
                    await self.process_queue(channel_id)

async def setup(bot):
    await bot.add_cog(Chat(bot))