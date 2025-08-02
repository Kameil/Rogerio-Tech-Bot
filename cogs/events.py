import asyncio
import logging
import re
import traceback
from asyncio import Queue
from typing import Union

import discord
import httpx
from discord.ext import commands
from google import genai
from google.genai import types
from google.genai.errors import ClientError, ServerError

from .security import Security

logger = logging.getLogger(__name__)

ATTACHMENT_SIZE_LIMIT_MB = 20
CHARACTER_LIMIT = 1950


class DetailsView(discord.ui.View):
    """
    uma view que mostra um botao 'ver detalhes'. quando clicado, envia o texto completo
    em uma ou mais mensagens para o autor da interacao
    """
    def __init__(self, author: discord.User, full_text: str):
        super().__init__(timeout=300)
        self.author = author
        self.full_text = full_text
        self.message: discord.Message = None

    async def on_timeout(self):
        if self.message:
            try:
                self.message.edit(view=None)
            except discord.HTTPException:
                pass # ignora erros se a mensagem original for apagada

    @discord.ui.button(label="📄 Ver detalhes", style=discord.ButtonStyle.secondary)
    async def details_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                "Apenas o autor da mensagem original pode fazer isso.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True) # confirma o recebimento da interacao
        button.disabled = True
        await interaction.message.edit(view=self)

        # envia o texto completo em pedacos, caso exceda o limite por mensagem
        for i in range(0, len(self.full_text), CHARACTER_LIMIT):
            chunk = self.full_text[i : i + CHARACTER_LIMIT]
            await interaction.followup.send(chunk, ephemeral=False)
        self.stop()


class Chat(commands.Cog):
    def __init__(self, bot):
        self.bot: commands.Bot = bot
        self.chats: dict = bot.chats
        self.http_client: httpx.AsyncClient = bot.http_client
        self.client: genai.Client = bot.client
        self.monitor = bot.monitor
        self.processing = {}
        self.message_queue = {}
        self.security_cog: Security = None

    async def cog_load(self):
        self.security_cog = self.bot.get_cog("Security")
        if self.security_cog:
            logger.info("Cog 'Security' referenciado com sucesso em 'Chat'.")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if self.security_cog is None:
            self.security_cog = self.bot.get_cog("Security")
            if self.security_cog is None:
                logger.error("Cog 'Security' não encontrado. As mensagens não serão processadas.")
                return 
        
        if message.author.bot or not (
            self.bot.user.mentioned_in(message) or isinstance(message.channel, discord.DMChannel)
        ):
            return
            
        perms = message.channel.permissions_for(message.guild.me if message.guild else self.bot.user)
        if not perms.send_messages:
            return

        message_cost = self.security_cog.COST_PER_TEXT + (len(message.attachments) * self.security_cog.COST_PER_ATTACHMENT)
        if await self.security_cog.is_rate_limited(message.author.id, message_cost):
            logger.warning(f"usuario {message.author.id} foi limitado por flood. custo: {message_cost}")
            try:
                if perms.add_reactions: await message.add_reaction("⏳")
            except discord.HTTPException: pass
            return

        channel_id = str(message.channel.id)
        if channel_id not in self.message_queue:
            self.message_queue[channel_id] = Queue()
        await self.message_queue[channel_id].put(message)
        
        if not self.processing.get(channel_id, False):
            self.processing[channel_id] = True
            asyncio.create_task(self.process_queue(channel_id))

    async def process_queue(self, channel_id: str):
        while not self.message_queue[channel_id].empty():
            message: discord.Message = await self.message_queue[channel_id].get()
            try:
                await self.handle_message(message)
            except Exception as e:
                logger.error(f"erro crítico ao processar a mensagem {message.id}: {e}", exc_info=True)
                error_embed = discord.Embed(
                    title="Ocorreu Um Erro Inesperado!",
                    description=f"Não foi possível processar sua solicitação.\n```py\n{traceback.format_exc(limit=1)}\n```",
                    color=discord.Color.red(),
                )
                error_embed.set_footer(text="Suporte: https://discord.gg/H77FTb7hwH")
                try:
                    await message.channel.send(embed=error_embed)
                except discord.HTTPException: pass
            finally:
                self.message_queue[channel_id].task_done()
        self.processing[channel_id] = False

    async def handle_message(self, message: discord.Message):
        self.monitor.messages.insert_message(message)
        async with message.channel.typing():
            prompt_parts = await self._build_prompt_parts(message)
            if prompt_parts is None:
                return
            response = await self._send_to_genai(prompt_parts, message)
            if not response:
                return
        await self._send_reply(response, message)

    async def _build_prompt_parts(self, message: discord.Message) -> list | None:
        if isinstance(message.channel, discord.DMChannel):
            context = f'Voce esta em uma conversa privada com "{message.author.display_name}".'
        else:
            context = f'Voce esta no canal #{message.channel.name} do servidor "{message.guild.name}".'

        clean_message = message.content.replace(f"<@{self.bot.user.id}>", "Rogerio Tech").strip()
        prompt_parts = [f'Contexto: {context}\nMensagem de "{message.author.display_name}": "{clean_message}"']
        
        if message.attachments:
            attachment_parts = await self._process_attachments(message)
            if attachment_parts is None: return None
            prompt_parts.extend(attachment_parts)
            
        return prompt_parts

    async def _process_attachments(self, message: discord.Message) -> list | None:
        parts = []
        for attachment in message.attachments:
            if attachment.size > ATTACHMENT_SIZE_LIMIT_MB * 1024 * 1024:
                error_msg = f"O anexo '{attachment.filename}' é muito grande ({attachment.size / 1024 / 1024:.2f} MB). O limite é de {ATTACHMENT_SIZE_LIMIT_MB} MB."
                logger.warning(error_msg)
                await message.reply(error_msg, mention_author=False)
                return None
            try:
                content_bytes = await attachment.read()
                mime_type = attachment.content_type or "application/octet-stream"
                parts.append(types.Part.from_bytes(data=content_bytes, mime_type=mime_type))
            except Exception as e:
                logger.error(f"falha ao processar o anexo {attachment.filename} em memória: {e}")
                await message.reply(f"Não consegui ler o anexo '{attachment.filename}'.", mention_author=False)
                return None
        return parts

    async def _send_to_genai(self, prompt_parts: list, message: discord.Message) -> types.GenerateContentResponse | None:
        channel_id = str(message.channel.id)
        is_experimental = channel_id in self.chats.get("experimental", [])
        
        model_name, gen_config = (
            ("gemini-1.5-pro-latest", self.bot.experimental_generation_config) if is_experimental
            else (self.security_cog.FALLBACK_MODEL, self.bot.generation_config) if self.security_cog.is_high_traffic_mode
            else (self.bot.model, self.bot.generation_config)
        )
        
        logger.info(f"Criando sessão de chat sem memória para o canal {channel_id} (modelo: {model_name})")
        chat_session = self.client.aio.chats.create(model=f'models/{model_name}', config=gen_config)
            
        try:
            response = await chat_session.send_message(prompt_parts)
            if response.prompt_feedback and response.prompt_feedback.block_reason != 0:
                reason = response.prompt_feedback.block_reason.name.replace('_', ' ').title()
                logger.warning(f"resposta bloqueada (prompt). razão: {reason}")
                await message.reply(f"minha política de segurança bloqueou sua solicitação. razão: **{reason}**.", mention_author=False)
                return None
            if not response.candidates:
                logger.warning("resposta da api sem candidatos (provavelmente bloqueada por segurança).")
                await message.reply("não consegui gerar uma resposta, provavelmente por violar minhas políticas de segurança.", mention_author=False)
                return None
            if response.usage_metadata:
                self.monitor.tokens_monitor.insert_usage(
                    uso=response.usage_metadata.total_token_count,
                    guild_id=message.guild.id if message.guild else "dm",
                )
            return response
        except (ClientError, ServerError) as e:
            logger.error(f"erro na api do google: {e}")
            await message.reply(f"ocorreu um erro com a api do google: `{e}`", mention_author=False)
        except Exception as e:
            logger.error(f"erro inesperado ao enviar para a api genai: {e}")
            await message.reply(f"ocorreu um erro ao comunicar com a api.", mention_author=False)
        return None

    async def _send_reply(self, response: types.GenerateContentResponse, message: discord.Message):
        try:
            text = response.text
        except ValueError:
            text = ""
            
        clean_text = self.remover_pensamento_da_resposta(text).strip()
        if not clean_text:
            logger.warning("a resposta da api estava vazia após a limpeza.")
            return

        match = re.search(r"\[RESUMO\](.*?)\[DETALHES\](.*)", clean_text, re.DOTALL)
        
        full_reply_text = ""
        summary_text = ""
        details_text = ""

        if match:
            summary_text = match.group(1).strip()
            details_text = match.group(2).strip()
            full_reply_text = f"{summary_text}\n\n{details_text}".strip()
        else:
            full_reply_text = clean_text

        if len(full_reply_text) <= CHARACTER_LIMIT:
            await message.reply(full_reply_text, mention_author=False)
        else:
            if not summary_text:
                summary_text = "A resposta é um pouco longa, clique no botão abaixo para ver os detalhes."
            if not details_text:
                details_text = full_reply_text

            view = DetailsView(author=message.author, full_text=details_text)
            reply_message = await message.reply(summary_text, view=view, mention_author=False)
            view.message = reply_message

    def remover_pensamento_da_resposta(self, resposta: str) -> str:
        return re.sub(r"```[\r]?\nPensamento:[\r]?\n.*?\n```", "", resposta, flags=re.DOTALL).strip()


async def setup(bot):
    await bot.add_cog(Chat(bot))