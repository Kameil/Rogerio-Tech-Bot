import asyncio
import datetime
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
from tools.extract_url_text import get_url_text

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
                await self.message.edit(view=None)
            except discord.HTTPException:
                pass # ignora erros se a mensagem original for apagada

    @discord.ui.button(label="📄 Ver detalhes", style=discord.ButtonStyle.secondary)
    async def details_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                "Apenas o autor da mensagem original pode fazer isso", ephemeral=True
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
        self.global_cooldown_until = None # para o controle de erro de cota (429)

    async def cog_load(self):
        self.security_cog = self.bot.get_cog("Security")
        if self.security_cog:
            logger.info("Cog 'Security' referenciado com sucesso em 'Chat'")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if self.security_cog is None:
            self.security_cog = self.bot.get_cog("Security")
            if self.security_cog is None:
                logger.error("Cog 'Security' não encontrado. As mensagens não serão processadas")
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
            logger.warning(f"Usuário {message.author.id} foi limitado por flood. Custo: {message_cost}")
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
                logger.error(f"Erro crítico ao processar a mensagem {message.id}: {e}", exc_info=True)
                error_embed = discord.Embed(
                    title="Ocorreu um erro inesperado!",
                    description=f"Não foi possivel processar sua solicitacao\n```py\n{traceback.format_exc(limit=1)}\n```",
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
            context = f'você está em uma conversa privada com "{message.author.display_name}"'
        else:
            context = f'você está no canal #{message.channel.name} do servidor "{message.guild.name}"'

        clean_message = message.content.replace(f"<@{self.bot.user.id}>", "Rogerio Tech").strip()
        prompt_parts = [f'contexto: {context}\nmensagem de "{message.author.display_name}": "{clean_message}"']
        
        if message.attachments:
            attachment_parts = await self._process_attachments(message)
            if attachment_parts is None: return None
            prompt_parts.extend(attachment_parts)
            
        return prompt_parts

    async def _process_attachments(self, message: discord.Message) -> list | None:
        parts = []
        for attachment in message.attachments:
            if attachment.size > ATTACHMENT_SIZE_LIMIT_MB * 1024 * 1024:
                error_msg = f"O anexo '{attachment.filename}' é muito grande ({attachment.size / 1024 / 1024:.2f} MB). O limite e de {ATTACHMENT_SIZE_LIMIT_MB} MB"
                logger.warning(error_msg)
                await message.reply(error_msg, mention_author=False)
                return None
            try:
                content_bytes = await attachment.read()
                mime_type = attachment.content_type or "application/octet-stream"
                parts.append(types.Part.from_bytes(data=content_bytes, mime_type=mime_type))
            except Exception as e:
                logger.error(f"Falha ao processar o anexo {attachment.filename} em memória: {e}")
                await message.reply(f"Não consegui ler o anexo '{attachment.filename}'", mention_author=False)
                return None
        return parts

    async def check_tools_in_response(self, response: str, message: discord.Message) -> bool:
        padrao = r"```openlink\n(\S*?)\n```"
        result = re.search(padrao, response)
        if not result:
            return False
        try:
            url_text = await get_url_text(result.group(1))
        except Exception as e:
            url_text = f"Não consegui extrair o texto da URL {result.group(1)}. Erro: {e}"
        
        prompt_parts = [f'contexto: Voce abriu a url "{result.group(1)}" e extraiu o seguinte texto: {url_text}',]
        response = await self._send_to_genai(prompt_parts=prompt_parts, message=message)
        await self._send_reply(response, message)
        return True


    async def _send_to_genai(self, prompt_parts: list, message: discord.Message) -> types.GenerateContentResponse | None:
        # verifica se o "disjuntor" (circuit breaker) global está ativo
        if self.global_cooldown_until and datetime.datetime.now(datetime.timezone.utc) < self.global_cooldown_until:
            wait_seconds = (self.global_cooldown_until - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
            logger.warning("Requisição bloqueada pelo cooldown global da API")
            await message.reply(f"O sistema está sobrecarregado. Por favor, tente novamente em **{int(wait_seconds) + 1} segundos**", mention_author=False)
            return None
        
        channel_id = str(message.channel.id)
        
        # lógica de seleção de modelo atualizada
        model_name, gen_config = (
            (self.security_cog.FALLBACK_MODEL, self.bot.generation_config) if self.security_cog.is_high_traffic_mode
            else (self.bot.model, self.bot.generation_config)
        )
        
        logger.info(f"Criando sessão de chat sem memória para o canal {channel_id} (modelo: {model_name})")
        if self.chats.get(channel_id):
            chat_session = self.chats[channel_id]
        else:
            chat_session = self.client.aio.chats.create(model=f'models/{model_name}', config=gen_config)
            self.chats[channel_id] = chat_session
            
        try:
            response = await chat_session.send_message(prompt_parts)
            if response.prompt_feedback and response.prompt_feedback.block_reason != 0:
                reason = response.prompt_feedback.block_reason.name.replace('_', ' ').title()
                logger.warning(f"Resposta bloqueada (prompt). Razão: {reason}")
                await message.reply(f"Minha política de segurança bloqueou sua solicitação. Razão: **{reason}**", mention_author=False)
                return None
            if not response.candidates:
                logger.warning("Resposta da API sem candidatos (provavelmente bloqueada por segurança)")
                await message.reply("Não consegui gerar uma resposta, provavelmente por violar minhas políticas de segurança", mention_author=False)
                return None
            if response.usage_metadata:
                self.monitor.tokens_monitor.insert_usage(
                    uso=response.usage_metadata.total_token_count,
                    guild_id=message.guild.id if message.guild else "dm",
                )
            return response
        except ServerError as e: # captura erros de servidor (como 5xx e 429)
            # implementa o "disjuntor" se o erro for de cota
            if "429" in str(e):
                logger.error(f"Erro de cota (429) detectado. Ativando cooldown global de 30 segundos")
                self.global_cooldown_until = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=30)
                await message.reply("Estamos com um volume muito alto de requisições. Por favor, tente novamente em alguns instantes", mention_author=False)
            else:
                logger.error(f"Erro na API do Google (servidor): {e}")
                await message.reply(f"Ocorreu um erro com a api do google: `{e}`", mention_author=False)
        except ClientError as e: # captura erros do lado do cliente (como requisição mal formatada)
            logger.error(f"Erro na API do Google (cliente): {e}")
            await message.reply(f"Ocorreu um erro com a API do Google: `{e}`", mention_author=False)
        except Exception as e:
            logger.exception(f"Erro inesperado ao enviar para a API GenAI")
            await message.reply(f"Ocorreu um erro ao comunicar com a API", mention_author=False)
        return None

    async def _send_reply(self, response: types.GenerateContentResponse, message: discord.Message):
        # extrai o texto de forma segura para evitar o aviso "non-text parts"
        try:
            text_parts = [part.text for part in response.candidates[0].content.parts if hasattr(part, "text")]
            text = "".join(text_parts)
        except (ValueError, IndexError):
            logger.warning("Não foi possível extrair texto da resposta da API")
            text = ""
            
        clean_text = self.remover_pensamento_da_resposta(text).strip()
        if not clean_text:
            logger.warning("A resposta da API estava vazia após a limpeza")
            await message.reply("Recebi uma resposta vazia e não pude processá-la", mention_author=False)
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
                summary_text = "A resposta é um pouco longa, clique no botão abaixo para ver os detalhes"
            if not details_text:
                details_text = full_reply_text

            view = DetailsView(author=message.author, full_text=details_text)
            reply_message = await message.reply(summary_text, view=view, mention_author=False)
            view.message = reply_message
        print(full_reply_text)
        await self.check_tools_in_response(full_reply_text, message)

    def remover_pensamento_da_resposta(self, resposta: str) -> str:
        return re.sub(r"```[\r]?\nPensamento:[\r]?\n.*?\n```", "", resposta, flags=re.DOTALL).strip()


async def setup(bot):
    await bot.add_cog(Chat(bot))