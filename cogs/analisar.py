import discord
from discord.ext import commands
from discord import app_commands
import httpx
import datetime
import textwrap
import traceback

from google import genai
from google.genai import types
from monitoramento import Tokens

ANALYSIS_TIMEOUT_SECONDS = 180.0
MAX_MESSAGES_PER_CHANNEL = 100

class AnalysisBlockedError(Exception):
    pass

class Analisar(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.http_client: httpx.AsyncClient = bot.http_client
        self.client: genai.Client = bot.client
        self.tokens_monitor: Tokens = bot.tokens_monitor

    class _AnalysisPromptModal(discord.ui.Modal):
        def __init__(self, cog_instance, user: discord.User, mpc: int, original_prompt: str | None):
            super().__init__(title="Refazer Análise com Prompt")
            self.cog = cog_instance
            self.user = user
            self.mpc = mpc
            self.original_prompt = original_prompt
            self.prompt_input = discord.ui.TextInput(
                label="Novo Prompt (opcional)", style=discord.TextStyle.long,
                placeholder="Deixe em branco para usar o prompt original ou digite um novo.",
                default=original_prompt, required=False
            )
            self.add_item(self.prompt_input)
        async def on_submit(self, interaction: discord.Interaction):
            await interaction.response.defer()
            new_prompt = self.prompt_input.value or self.original_prompt
            await self.cog._executar_analise(interaction, self.user, new_prompt, self.mpc, is_rerun=True)

    class _AnalysisActionsView(discord.ui.View):
        def __init__(self, cog_instance, user: discord.User, prompt: str | None, mpc: int, author_id: int):
            super().__init__(timeout=ANALYSIS_TIMEOUT_SECONDS)
            self.cog = cog_instance
            self.user = user
            self.prompt = prompt
            self.mpc = mpc
            self.author_id = author_id
        async def interaction_check(self, interaction: discord.Interaction) -> bool:
            if interaction.user.id != self.author_id:
                await interaction.response.send_message("Apenas quem executou o comando pode usar este botão.", ephemeral=True)
                return False
            return True
        @discord.ui.button(label="Refazer Análise", style=discord.ButtonStyle.secondary, emoji="🔄")
        async def reanalisar(self, interaction: discord.Interaction, button: discord.ui.Button):
            button.disabled = True
            await interaction.message.edit(view=self)
            modal = Analisar._AnalysisPromptModal(self.cog, self.user, self.mpc, self.prompt)
            await interaction.response.send_modal(modal)

    async def _collect_user_messages(self, inter: discord.Interaction, user: discord.User, mpc: int) -> list[str]:
        messages = []
        for channel in inter.guild.text_channels:
            bot_perms = channel.permissions_for(inter.guild.me)
            user_perms = channel.permissions_for(inter.user)
            if not bot_perms.read_message_history or not user_perms.read_messages: continue
            try:
                async for message in channel.history(limit=mpc):
                    if message.author == user:
                        local_time = message.created_at.astimezone(datetime.timezone(datetime.timedelta(hours=-3)))
                        messages.append(f'Em #{message.channel.name}: "{message.content}" às {local_time.strftime("%H:%M:%S de %d/%m/%Y")}')
            except discord.Forbidden: continue
        return messages

    async def _generate_analysis(self, inter: discord.Interaction, user: discord.User, messages: list[str], prompt: str | None, avatar_bytes: bytes) -> types.GenerateContentResponse:
        if prompt:
            prompt_template = f"Analise {prompt} | Nome do usuário: {user.name}, Mensagens do usuário:\n"
        else:
            prompt_template = f"Analise esse usuário com base no seu nome e na sua imagem de perfil e diga se ele é desenrolado ou não. Nome: {user.name}\n"
        
        message_log = "\n".join(messages) if messages else "Nenhuma mensagem encontrada."
        final_prompt = prompt_template + message_log

        contents = [final_prompt, types.Part.from_bytes(data=avatar_bytes, mime_type="image/png")]
        
        response = await self.bot.client.aio.models.generate_content(
            contents=contents, config=self.bot.generation_config, model=self.bot.model
        )
        
        if not response.candidates:
            reason = "Desconhecida"
            if response.prompt_feedback and response.prompt_feedback.block_reason:
                reason = response.prompt_feedback.block_reason.name
            raise AnalysisBlockedError(f"A resposta foi bloqueada pela API por motivo de segurança: {reason}")
        
        if response.usage_metadata:
            self.tokens_monitor.insert_usage(uso=response.usage_metadata.total_token_count, guild_id=inter.guild.id)
            
        return response

    async def _send_analysis_response(self, inter: discord.Interaction, response_text: str, user: discord.User, prompt: str | None, mpc: int, is_rerun: bool):
        wrapped_text = textwrap.wrap(response_text, 2000, replace_whitespace=False, drop_whitespace=False)
        for i, chunk in enumerate(wrapped_text):
            is_last_chunk = (i == len(wrapped_text) - 1)
            
            send_kwargs = {"content": chunk, "allowed_mentions": discord.AllowedMentions.none()}
            if is_last_chunk and not is_rerun:
                send_kwargs["view"] = self._AnalysisActionsView(self, user, prompt, mpc, inter.user.id)
            
            await inter.followup.send(**send_kwargs)

    async def _executar_analise(self, inter: discord.Interaction, user: discord.User, prompt: str | None, mpc: int, is_rerun: bool = False):
        if not is_rerun: 
            await inter.response.defer()

        if not is_rerun:
            await inter.followup.send(
                f"🔎 Análise iniciada para **{user.display_name}**! Estou bizonhando o servidor em busca de mensagens. Isso pode levar um tempinho, relaxa ai...",
                ephemeral=True
            )

        if isinstance(inter.channel, discord.DMChannel):
            await inter.followup.send("Este comando só pode ser executado em um servidor."); return

        try:
            messages = await self._collect_user_messages(inter, user, mpc)
            
            if not messages:
                await inter.followup.send(
                    f"Não achei nenhuma mensagem recente de **{user.display_name}** nos canais onde tenho acesso para fazer a análise, não posso fazer nada :/",
                    ephemeral=True
                )
                return
            
            response = await self.http_client.get(user.display_avatar.url)
            response.raise_for_status()
            avatar_bytes = await response.aread()

            genai_response = await self._generate_analysis(inter, user, messages, prompt, avatar_bytes)
            
            if not genai_response.text:
                await inter.followup.send("A análise gerou uma resposta vazia. Tente novamente ou com um prompt diferente.", ephemeral=True)
                return

            await self._send_analysis_response(inter, genai_response.text, user, prompt, mpc, is_rerun)

        except AnalysisBlockedError as e:
            embed = discord.Embed(
                title="Análise Bloqueada",
                description=f"Não foi possível gerar a análise pois o conteúdo foi bloqueado por políticas de segurança.\n> Motivo: `{e}`",
                color=discord.Color.orange()
            )
            await inter.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            error_trace = traceback.format_exc(limit=2)
            embed = discord.Embed(
                title="Ocorreu um Erro Inesperado",
                description=f"Não foi possível concluir a análise.\n```py\n{error_trace}\n```", color=discord.Color.red()
            )
            embed.set_footer(text="Suporte: https://discord.gg/H77FTb7hwH")
            
            if inter.response.is_done(): await inter.followup.send(embed=embed)
            else:
                try: await inter.response.send_message(embed=embed)
                except discord.InteractionResponded: await inter.followup.send(embed=embed)


    @app_commands.command(name="analisar", description="Descobrir se é desenrolado.")
    @app_commands.describe(
        user="O usuário a ser analisado.",
        prompt="Um tópico ou pergunta específica para guiar a análise.",
        mpc=f"Máximo de mensagens a coletar por canal (Padrão: {MAX_MESSAGES_PER_CHANNEL})."
    )
    async def analisar(self, inter: discord.Interaction, user: discord.User, mpc: int = MAX_MESSAGES_PER_CHANNEL, prompt: str = None):
        await self._executar_analise(inter, user, prompt, mpc)


async def setup(bot: commands.Bot):
    await bot.add_cog(Analisar(bot))
