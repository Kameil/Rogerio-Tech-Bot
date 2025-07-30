import discord
from discord.ext import commands
import httpx
import asyncio
from asyncio import Queue
import traceback
import datetime
import re
from google import genai
from google.genai import types
from google.genai.errors import ServerError, ClientError
import logging

logger = logging.getLogger(__name__)

# view para o botao continuar
class ContinueView(discord.ui.View):
    """
    view do discord que gerencia o botão "continuar" para respostas longas.
    apenas o autor original da mensagem pode interagir.
    """
    def __init__(self, author: discord.User, text_parts: list[str]):
        super().__init__(timeout=300)  # view expira em 5 minutos
        self.author = author
        self.text_parts = text_parts
        self.current_part = 1
        self.message: discord.Message = None

    async def on_timeout(self):
        """desativa o botão quando a view expira."""
        if self.message and self.children:
            for item in self.children:
                item.disabled = True
            await self.message.edit(view=self)

    @discord.ui.button(label="➡️ Continuar", style=discord.ButtonStyle.primary)
    async def continue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Apenas o autor da mensagem original pode fazer isso.", ephemeral=True)
            return

        await interaction.response.defer()
        
        current_content = interaction.message.content
        next_part = self.text_parts[self.current_part]
        await interaction.edit_original_response(content=f"{current_content}\n\n{next_part}")
        
        self.current_part += 1
        
        if self.current_part >= len(self.text_parts):
            await interaction.edit_original_response(view=None)

class Chat(commands.Cog):
    def __init__(self, bot):
        self.bot: commands.Bot = bot
        self.chats: dict = bot.chats
        self.http_client: httpx.AsyncClient = bot.http_client
        self.client: genai.Client = bot.client
        # acessa o objeto monitor geral, que contém os monitores de tokens e de mensagens
        self.monitor = bot.monitor
        self.processing = {}  # controla o processamento por canal
        self.message_queue = {}  # filas de mensagens por canal
        self.timeout_users = {"Now": datetime.datetime.now().minute} # sistema de timeout anti-flood

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """listener que captura mensagens, valida e as coloca na fila de processamento."""
        if message.author.bot or not (f"<@{self.bot.user.id}>" in message.content or self.bot.user in message.mentions or isinstance(message.channel, discord.DMChannel)):
            return

        perms = message.channel.permissions_for(message.guild.me if message.guild else self.bot.user)
        if not perms.send_messages:
            return

        # sistema provisorio de timeout para evitar flood
        now = datetime.datetime.now()
        if self.timeout_users.get("Now") != now.minute:
            self.timeout_users = {"Now": now.minute, str(message.author.id): 1}
        else:
            self.timeout_users[str(message.author.id)] = self.timeout_users.get(str(message.author.id), 0) + 1
        
        if self.timeout_users[str(message.author.id)] >= 10:
            await message.add_reaction("⏳")
            return

        channel_id = str(message.channel.id)
        if channel_id not in self.message_queue:
            self.message_queue[channel_id] = Queue()
        
        await self.message_queue[channel_id].put(message)

        if not self.processing.get(channel_id, False):
            self.processing[channel_id] = True
            asyncio.create_task(self.process_queue(channel_id))

    def remover_pensamento_da_resposta(self, resposta: str) -> str:
        """remove o bloco de 'pensamento' da resposta do modelo experimental para nao ser reenviado."""
        return re.sub(r"```[\r]?\nPensamento:[\r]?\n.*?\n```", "", resposta, flags=re.DOTALL).strip()

    def split_message(self, text: str, max_length: int = 1950) -> list[str]:
        """divide um texto longo em partes menores que o limite do discord, preservando a formatação."""
        if len(text) <= max_length:
            return [text]
        parts = []
        while len(text) > 0:
            if len(text) <= max_length:
                parts.append(text)
                break
            split_at = text.rfind('\n', 0, max_length)
            if split_at == -1: split_at = text.rfind(' ', 0, max_length)
            if split_at == -1: split_at = max_length
            parts.append(text[:split_at])
            text = text[split_at:].lstrip()
        return parts

    async def process_attachments(self, attachments: list[discord.Attachment]) -> tuple[list, str]:
        """
        processa os anexos da mensagem.
        retorna uma tupla contendo uma lista de 'Part' para a api e uma string com o conteúdo de arquivos .txt.
        """
        parts = []
        text_content = ""
        for attachment in attachments:
            try:
                response = await self.http_client.get(attachment.url)
                response.raise_for_status()
                content_bytes = response.content
                
                if attachment.content_type and attachment.content_type.startswith("text/plain"):
                    try:
                        text_content += content_bytes.decode('utf-8') + "\n"
                    except UnicodeDecodeError:
                        text_content += "Erro: Não foi possível decodificar o conteúdo de um arquivo .txt.\n"
                else:
                    parts.append(types.Part.from_bytes(data=content_bytes, mime_type=attachment.content_type))
            except httpx.HTTPStatusError as e:
                logger.error(f"falha ao baixar anexo {attachment.url}: {e}")
        return parts, text_content.strip()

    async def process_queue(self, channel_id: str):
        """processa a fila de mensagens para um canal, uma de cada vez."""
        while not self.message_queue[channel_id].empty():
            message: discord.Message = await self.message_queue[channel_id].get()
            try:
                await self.handle_message(message)
            except Exception as e:
                logger.error(f"erro crítico ao processar a mensagem {message.id}: {e}", exc_info=True)
                error_embed = discord.Embed(
                    title="Ocorreu Um Erro Inesperado!", 
                    description=f"Não foi possível processar sua solicitação.\n```py\n{traceback.format_exc(limit=1)}\n```", 
                    color=discord.Color.red()
                )
                try:
                    await message.channel.send(embed=error_embed)
                except discord.HTTPException: pass
            finally:
                self.message_queue[channel_id].task_done()
        self.processing[channel_id] = False

    async def handle_message(self, message: discord.Message):
        """lógica central para lidar com uma única mensagem, desde a criação do prompt até o envio da resposta."""
        
        # salva a mensagem no banco de dados antes de processar
        self.monitor.messages.insert_message(message)

        channel_id = str(message.channel.id)
        is_experimental = channel_id in self.chats["experimental"]
        
        gen_config = self.bot.experimental_generation_config if is_experimental else self.bot.generation_config
        # usa o modelo definido no main.py, e um modelo mais avançado para o modo experimental
        model_name = "gemini-1.5-pro-latest" if is_experimental else self.bot.model

        async with message.channel.typing():
            if channel_id not in self.chats:
                logger.info(f"criando nova sessão de chat para o canal {channel_id} (experimental: {is_experimental})")
                self.chats[channel_id] = self.client.aio.chats.create(model=f'models/{model_name}', config=gen_config)
            chat = self.chats[channel_id]

            referenced_content = ""
            if message.reference and message.reference.message_id:
                try:
                    ref_msg = await message.channel.fetch_message(message.reference.message_id)
                    ref_text = self.remover_pensamento_da_resposta(ref_msg.content)
                    ref_author = "minha" if ref_msg.author.id == self.bot.user.id else f"de '{ref_msg.author.name}'"
                    referenced_content = f" (em resposta a uma mensagem {ref_author} que dizia: '{ref_text[:150]}...')"
                except discord.NotFound:
                    referenced_content = " (em resposta a uma mensagem apagada)"

            activities = [act.name for act in message.author.activities if isinstance(act, discord.Activity)] if message.guild else []
            activity_text = f", ativo agora em: {', '.join(activities)}" if activities else ""
            
            clean_message = message.content.replace(f"<@{self.bot.user.id}>", "Rogerio Tech").strip()
            prompt_text = f'informacoes: mensagem de "{message.author.display_name}"{activity_text}: "{clean_message}"{referenced_content}'
            
            prompt_parts = [prompt_text]
            if message.attachments:
                attachment_parts, text_content = await self.process_attachments(message.attachments)
                prompt_parts.extend(attachment_parts)
                if text_content:
                    prompt_parts.append(f"\n\nInstruções: Analise o conteúdo do arquivo .txt anexado e responda com base nele.\nConteúdo do arquivo:\n```\n{text_content}\n```")

            try:
                response: types.GenerateContentResponse = await chat.send_message(prompt_parts)
                response_text = response.text

                if response.usage_metadata:
                    self.monitor.tokens_monitor.insert_usage(
                        uso=(response.usage_metadata.prompt_token_count + response.usage_metadata.candidates_token_count),
                        guild_id=message.guild.id if message.guild else "dm",
                    )
            except ClientError as e:
                await message.reply(f"um erro ocorreu com a sua solicitação à API: {e}", mention_author=False)
                return
            except ServerError as e:
                await message.reply(f"o servidor do google está com problemas, tente novamente mais tarde. {e}", mention_author=False)
                return
            except Exception:
                e_trace = traceback.format_exc()
                logger.error(f"erro ao enviar mensagem para a api genai: {e_trace}")
                await message.reply(f"ocorreu um erro ao comunicar com a api.\n```py\n{e_trace.splitlines()[-1]}\n```", mention_author=False)
                return

        mensagens_divididas = self.split_message(response_text)
        reply_message = await message.reply(mensagens_divididas[0], mention_author=False)

        if len(mensagens_divididas) > 1:
            view = ContinueView(author=message.author, text_parts=mensagens_divididas)
            view.message = reply_message
            await reply_message.edit(view=view)

async def setup(bot):
    await bot.add_cog(Chat(bot))