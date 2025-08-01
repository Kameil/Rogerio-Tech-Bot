import discord
from discord.ext import commands, tasks
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
from collections import deque
import statistics

from typing import Optional, Union

logger = logging.getLogger(__name__)

FALLBACK_MODEL = "gemini-1.5-flash-latest"

# --- anti-flood rigoroso (final) ---
# agora o sistema vai limitar o spam de forma muito mais agressiva
BUCKET_CAPACITY = 6.0
LEAK_RATE_PER_SEC = 0.7  # recuperacao um pouco mais rapida para usuarios legitimos
COST_PER_TEXT = 1.5
COST_PER_ATTACHMENT = 4.0
# matematica:
# - msg com anexo: 1.5 + 4.0 = 5.5 (cabe na capacidade de 6)
# - spam de texto: msg1=1.5, msg2=3.0, msg3=4.5, msg4=6.0. a 5a mensagem sera bloqueada.

ATTACHMENT_SIZE_LIMIT_MB = 20

class DetailsView(discord.ui.View):
    def __init__(self, author: discord.User, full_text: str):
        super().__init__(timeout=300)
        self.author = author
        self.full_text = full_text
        self.message: discord.Message = None

    async def on_timeout(self):
        if self.message:
            try: await self.message.edit(view=None)
            except discord.HTTPException: pass

    @discord.ui.button(label="📄 Ver detalhes", style=discord.ButtonStyle.secondary)
    async def details_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Apenas o autor da mensagem original pode fazer isso.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        button.disabled = True
        await interaction.message.edit(view=self)
        
        logger.info(f"enviando detalhes para o usuário {self.author.id}")
        chunk_size = 1980
        for i in range(0, len(self.full_text), chunk_size):
            chunk = self.full_text[i:i + chunk_size]
            await interaction.followup.send(chunk, ephemeral=False)
        self.stop()

class ContinueView(discord.ui.View):
    def __init__(self, author: Union[discord.User, discord.Member], second_part: str):
        super().__init__(timeout=300)
        self.author = author
        self.second_part = second_part
        self.message: Optional[discord.Message] = None

    async def on_timeout(self):
        if self.message:
            try: await self.message.edit(view=None)
            except discord.HTTPException: pass

    @discord.ui.button(label="➡️ Continuar", style=discord.ButtonStyle.primary)
    async def continue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Apenas o autor da mensagem original pode fazer isso.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        await interaction.message.edit(view=None)
        await interaction.followup.send(self.second_part)
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
        self.user_buckets = {}
        self.user_locks = {}
        self.main_lock = asyncio.Lock()
        self.is_high_traffic_mode = False
        self.hourly_usage_history = deque(maxlen=24)
        self.check_traffic.start()

    def cog_unload(self):
        self.check_traffic.cancel()

    @tasks.loop(minutes=15)
    async def check_traffic(self):
        try:
            records = self.monitor.tokens_monitor.get_usage_order_uso()
            current_hour_usage = sum(r.uso for r in records) if records else 0
            self.hourly_usage_history.append(current_hour_usage)
            if len(self.hourly_usage_history) < 4: return
            usage_list = list(self.hourly_usage_history)
            mean_usage = statistics.mean(usage_list)
            stdev_usage = statistics.stdev(usage_list) if len(usage_list) > 1 else 0
            high_traffic_threshold = mean_usage + (1.5 * stdev_usage)
            normal_traffic_threshold = mean_usage + (0.5 * stdev_usage)
            if current_hour_usage > high_traffic_threshold and not self.is_high_traffic_mode:
                self.is_high_traffic_mode = True
                logger.warning(f"limiar de tráfego alto atingido. modo de economia ativado (usando {FALLBACK_MODEL})")
            elif current_hour_usage < normal_traffic_threshold and self.is_high_traffic_mode:
                self.is_high_traffic_mode = False
                logger.info(f"tráfego normalizado. modo de economia desativado")
        except Exception as e:
            logger.error(f"erro ao verificar o tráfego de tokens: {e}")

    async def _is_rate_limited(self, user_id: int, cost: float) -> bool:
        user_id_str = str(user_id)
        async with self.main_lock:
            if user_id_str not in self.user_locks:
                self.user_locks[user_id_str] = asyncio.Lock()
        user_lock = self.user_locks[user_id_str]
        async with user_lock:
            now = datetime.datetime.now(datetime.timezone.utc)
            if user_id_str not in self.user_buckets:
                self.user_buckets[user_id_str] = {"level": 0.0, "last_update": now}
            bucket = self.user_buckets[user_id_str]
            time_passed = (now - bucket["last_update"]).total_seconds()
            leaked_amount = time_passed * LEAK_RATE_PER_SEC
            bucket["level"] = max(0.0, bucket["level"] - leaked_amount)
            bucket["last_update"] = now
            if bucket["level"] + cost > BUCKET_CAPACITY:
                return True
            bucket["level"] += cost
            return False

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not (self.bot.user.mentioned_in(message) or isinstance(message.channel, discord.DMChannel)):
            return
        perms = message.channel.permissions_for(message.guild.me if message.guild else self.bot.user)
        if not perms.send_messages:
            return
        message_cost = COST_PER_TEXT + (len(message.attachments) * COST_PER_ATTACHMENT)
        if await self._is_rate_limited(message.author.id, message_cost):
            logger.warning(f"usuario {message.author.id} foi limitado por flood. custo: {message_cost}")
            try:
                if perms.add_reactions:
                    await message.add_reaction("⏳")
            except discord.HTTPException:
                pass
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
                error_embed = discord.Embed(title="Ocorreu Um Erro Inesperado!", description=f"Não foi possível processar sua solicitação.\n```py\n{traceback.format_exc(limit=1)}\n```", color=discord.Color.red())
                try: await message.channel.send(embed=error_embed)
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
            if not response: return
        await self._send_reply(response, message)

    async def _build_prompt_parts(self, message: discord.Message) -> list | None:
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
        prompt_parts = [f'informacoes: mensagem de "{message.author.display_name}"{activity_text}: "{clean_message}"{referenced_content}']
        if message.attachments:
            attachment_parts = await self.process_attachments(message)
            if attachment_parts is None: return None
            prompt_parts.extend(attachment_parts)
        return prompt_parts

    async def process_attachments(self, message: discord.Message) -> list | None:
        parts = []
        for attachment in message.attachments:
            if attachment.size > ATTACHMENT_SIZE_LIMIT_MB * 1024 * 1024:
                error_msg = f"O anexo '{attachment.filename}' é muito grande ({attachment.size / 1024 / 1024:.2f} MB). O limite é de {ATTACHMENT_SIZE_LIMIT_MB} MB."
                logger.warning(error_msg)
                await message.reply(error_msg, mention_author=False)
                return None
            try:
                content_bytes = await attachment.read()
                mime_type = attachment.content_type
                if not mime_type:
                    mime_type = "application/octet-stream"
                    logger.warning(f"anexo '{attachment.filename}' sem mime_type, usando fallback.")
                parts.append(types.Part.from_bytes(data=content_bytes, mime_type=mime_type))
            except Exception as e:
                logger.error(f"falha ao processar o anexo {attachment.filename} em memória: {e}")
                await message.reply(f"Não consegui ler o anexo '{attachment.filename}'. Ele pode estar corrompido.", mention_author=False)
                return None
        return parts

    async def _send_to_genai(self, prompt_parts: list, message: discord.Message) -> types.GenerateContentResponse | None:
        channel_id = str(message.channel.id)
        is_experimental = channel_id in self.chats.get("experimental", [])
        if is_experimental:
            model_name = "gemini-1.5-pro-latest"
            gen_config = self.bot.experimental_generation_config
        elif self.is_high_traffic_mode:
            model_name = FALLBACK_MODEL
            gen_config = self.bot.generation_config
        else:
            model_name = self.bot.model
            gen_config = self.bot.generation_config
        chat_session = None
        if channel_id not in self.chats or self.chats[channel_id].get("model") != model_name:
            logger.info(f"criando/trocando sessão para o canal {channel_id} (modelo: {model_name})")
            chat_session = self.client.aio.chats.create(model=f'models/{model_name}', config=gen_config)
            self.chats[channel_id] = {"session": chat_session, "model": model_name}
        else:
            chat_session = self.chats[channel_id]["session"]
        try:
            response: types.GenerateContentResponse = await chat_session.send_message(prompt_parts)
            
            if response.prompt_feedback and response.prompt_feedback.block_reason != 0 :
                reason = response.prompt_feedback.block_reason.name.replace('_', ' ').title()
                logger.warning(f"resposta bloqueada (prompt). razão: {reason}")
                await message.reply(f"minha política de segurança bloqueou sua solicitação. razão: **{reason}**.", mention_author=False)
                return None
            if not response.candidates:
                logger.warning("resposta da api sem candidatos (provavelmente bloqueada).")
                await message.reply("não consegui gerar uma resposta, provavelmente por violar minhas políticas de segurança.", mention_author=False)
                return None
            if response.usage_metadata:
                self.monitor.tokens_monitor.insert_usage(uso=response.usage_metadata.total_token_count, guild_id=message.guild.id if message.guild else "dm",)
            return response
        except (ClientError, ServerError) as e:
            logger.error(f"erro na api do google: {e}")
            await message.reply(f"ocorreu um erro com a api do google: `{e}`", mention_author=False)
        except Exception:
            e_trace = traceback.format_exc()
            logger.error(f"erro ao enviar para a api genai: {e_trace}")
            await message.reply(f"ocorreu um erro ao comunicar com a api.\n```py\n{e_trace.splitlines()[-1]}\n```", mention_author=False)
        return None

    async def _send_reply(self, response: types.GenerateContentResponse, message: discord.Message):
        try: text = response.text
        except (AttributeError, ValueError): text = ""
        clean_text = self.remover_pensamento_da_resposta(text).strip()
        if not clean_text:
            logger.warning("a resposta da api estava vazia.")
            return

        summary_match = re.search(r"\[RESUMO\](.*?)\[DETALHES\]", clean_text, re.DOTALL)
        
        if summary_match:
            summary_text = summary_match.group(1).strip()
            # Pega tudo que vem depois da tag [RESUMO] e seu conteúdo
            details_text = clean_text[summary_match.end(1):].strip()
            # Remove a tag [DETALHES] do início do texto de detalhes
            if details_text.startswith("[DETALHES]"):
                details_text = details_text[len("[DETALHES]"):].strip()

            if not summary_text: summary_text = "Analisei o conteúdo! A resposta é um pouco longa, clique no botão abaixo para ver os detalhes."
            
            logger.info("enviando resposta com resumo e botao de detalhes.")
            view = DetailsView(author=message.author, full_text=details_text)
            reply_message = await message.reply(summary_text, view=view, mention_author=False)
            view.message = reply_message
        else:
            logger.info("resposta sem tags, usando sistema de fallback para dividir se necessario.")
            char_limit = 1950
            if len(clean_text) <= char_limit:
                await message.reply(clean_text, mention_author=False)
            else:
                logger.info("resposta longa, dividindo com o botao 'continuar'.")
                split_delimiters = ['\n\n', '\n', '. ', ' ']
                split_at = -1
                for delimiter in split_delimiters:
                    found_pos = clean_text.rfind(delimiter, 0, char_limit)
                    if found_pos != -1:
                        split_at = found_pos + len(delimiter)
                        break
                if split_at == -1: split_at = char_limit
                part1 = clean_text[:split_at].strip()
                part2 = clean_text[split_at:].strip()
                if not part2:
                    await message.reply(part1, mention_author=False)
                else:
                    view = ContinueView(author=message.author, second_part=part2)
                    reply_message = await message.reply(part1, view=view, mention_author=False)
                    view.message = reply_message

    def remover_pensamento_da_resposta(self, resposta: str) -> str:
        return re.sub(r"```[\r]?\nPensamento:[\r]?\n.*?\n```", "", resposta, flags=re.DOTALL).strip()

async def setup(bot):
    await bot.add_cog(Chat(bot))