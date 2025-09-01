import discord
from discord.ext import commands
from discord import app_commands
import httpx
import datetime
import textwrap
import traceback
import logging

from google import genai
from google.genai import types
from monitoramento import Tokens

ANALYSIS_TIMEOUT_SECONDS = 180.0
MAX_MESSAGES_PER_CHANNEL = 100

logger = logging.getLogger(__name__)

class AnalysisBlockedError(Exception):
    pass

class Analisar(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.http_client: httpx.AsyncClient = bot.http_client
        self.client: genai.Client = bot.client
        self.tokens_monitor: Tokens = bot.tokens_monitor

    # a view foi redesenhada para o fluxo de duas etapas e otimizada
    class BotoesAnalise(discord.ui.View):
        def __init__(self, cog_instance, user: discord.User, mensagens: list[str], avatar_bytes: bytes, autor_id: int, original_prompt: str | None):
            super().__init__(timeout=ANALYSIS_TIMEOUT_SECONDS)
            self.cog = cog_instance
            self.user = user
            self.autor_id = autor_id
            # armazena os dados coletados para reutilizacao imediata
            self.mensagens = mensagens
            self.avatar_bytes = avatar_bytes
            self.original_prompt = original_prompt

        async def interaction_check(self, interaction: discord.Interaction) -> bool:
            if interaction.user.id != self.autor_id:
                await interaction.response.send_message("Apenas quem executou o comando pode usar este botão.", ephemeral=True)
                return False
            return True

        @discord.ui.button(label="Análise Detalhada", style=discord.ButtonStyle.primary, emoji="🧠")
        async def analise_detalhada(self, interaction: discord.Interaction, button: discord.ui.Button):
            button.disabled = True
            await interaction.message.edit(view=self)
            await interaction.response.defer()

            try:
                # prompt aprimorado para a analise profunda, focando em estrutura e topicos
                prompt_detalhado = (
                    "Faça uma análise de perfil sobre o usuário a seguir ve se ele é desenrolado, baseando-se em seu nome, avatar e, principalmente, em seu histórico de mensagens. "
                    "Seja perspicaz e capture a essência do estilo de comunicação do usuário."
                )
                
                # incorpora o prompt customizado do usuario, se ele tiver fornecido um
                if self.original_prompt:
                    prompt_detalhado += f"\nLeve em consideração também a seguinte pergunta do analista: '{self.original_prompt}'"

                # reutiliza os dados ja coletados para uma resposta muito mais rapida
                contents = [
                    prompt_detalhado,
                    f"Nome do usuário: {self.user.display_name}",
                    "Histórico de Mensagens:\n" + "\n".join(self.mensagens),
                    types.Part.from_bytes(data=self.avatar_bytes, mime_type="image/png")
                ]

                genai_response = await self.cog._generate_analysis(interaction, contents)
                await self.cog._enviar_resposta(interaction, genai_response.text)

            except Exception as e:
                await self.cog._handle_error(interaction, e)

    async def _collect_user_messages(self, inter: discord.Interaction, user: discord.User, mpc: int) -> list[str]:
        messages = []
        for channel in inter.guild.text_channels:
            if not channel.permissions_for(inter.guild.me).read_message_history: continue
            
            try:
                async for message in channel.history(limit=mpc, after=datetime.datetime.now() - datetime.timedelta(days=30)):
                    if message.author == user and message.content:
                        local_time = message.created_at.astimezone(datetime.timezone(datetime.timedelta(hours=-3)))
                        messages.append(f'No canal #{message.channel.name} em {local_time.strftime("%d/%m")}: "{message.content}"')
            except discord.Forbidden:
                continue
        return messages

    # a funcao agora e mais generica, apenas envia para a api
    async def _generate_analysis(self, inter: discord.Interaction, contents: list) -> types.GenerateContentResponse:
        response = await self.client.aio.models.generate_content(
            contents=contents, config=self.bot.generation_config, model=self.bot.model
        )
        
        if not response.candidates:
            reason = response.prompt_feedback.block_reason.name if response.prompt_feedback else "Desconhecida"
            raise AnalysisBlockedError(f"A resposta foi bloqueada pela API por motivo de segurança: {reason}")
        
        if response.usage_metadata:
            self.tokens_monitor.insert_usage(uso=response.usage_metadata.total_token_count, guild_id=inter.guild.id)
            
        if not response.text:
            raise ValueError("A análise gerou uma resposta vazia.")

        return response

    # novo: funcao simplificada para enviar respostas
    async def _enviar_resposta(self, inter: discord.Interaction, response_text: str, view: discord.ui.View = None):
        wrapped_text = textwrap.wrap(response_text, 2000, replace_whitespace=False, drop_whitespace=False)
        for i, chunk in enumerate(wrapped_text):
            is_last_chunk = (i == len(wrapped_text) - 1)
            
            send_kwargs = {"content": chunk, "allowed_mentions": discord.AllowedMentions.none()}
            if is_last_chunk and view:
                send_kwargs["view"] = view
            
            await inter.followup.send(**send_kwargs)

    async def _handle_error(self, inter: discord.Interaction, e: Exception):
        if isinstance(e, AnalysisBlockedError):
            embed = discord.Embed(title="Análise Bloqueada", description=str(e), color=discord.Color.orange())
        else:
            error_trace = traceback.format_exc(limit=1)
            embed = discord.Embed(
                title="Ocorreu um Erro Inesperado",
                description=f"Não foi possível concluir a análise.\n```py\n{error_trace}\n```", color=discord.Color.red()
            )
        
        if inter.response.is_done():
            await inter.followup.send(embed=embed, ephemeral=True)
        else:
            await inter.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="analisar", description="Descobrir se um usuário é desenrolado com base em seu perfil e mensagens.")
    @app_commands.describe(
        user="O usuário a ser analisado.",
        prompt="Um tópico ou pergunta específica para a análise detalhada (opcional).",
        mpc=f"Máximo de mensagens a coletar por canal (Padrão: {MAX_MESSAGES_PER_CHANNEL})."
    )
    async def analisar(self, inter: discord.Interaction, user: discord.User, mpc: int = MAX_MESSAGES_PER_CHANNEL, prompt: str = None):
        if isinstance(inter.channel, discord.DMChannel):
            await inter.response.send_message("Este comando só pode ser executado em um servidor.", ephemeral=True)
            return

        await inter.response.defer()

        try:
            await inter.followup.send(f"🔎 Analisando **{user.display_name}**... Estou bizonhando o servidor em busca de mensagens. Isso pode levar um tempinho, relaxa ai...", ephemeral=True)

            # novo: otimizacao, coleta de dados ocorre apenas uma vez
            messages = await self._collect_user_messages(inter, user, mpc)
            
            response = await self.http_client.get(user.display_avatar.url)
            response.raise_for_status()
            avatar_bytes = await response.aread()

            # novo: logica para a primeira analise, a basica
            prompt_basico = f"Analise este usuário com base em seu nome e avatar. Diga de forma breve e direta se ele parece ser uma pessoa 'desenrolada' ou não. Seja curto e informal."
            contents_basico = [
                prompt_basico,
                f"Nome do usuário: {user.display_name}",
                types.Part.from_bytes(data=avatar_bytes, mime_type="image/png")
            ]

            genai_response = await self._generate_analysis(inter, contents_basico)

            # novo: os dados coletados sao passados para a view para serem reutilizados
            view = self.BotoesAnalise(self, user, messages, avatar_bytes, inter.user.id, prompt)
            
            await self._enviar_resposta(inter, genai_response.text, view=view)

        except Exception as e:
            await self._handle_error(inter, e)


async def setup(bot: commands.Bot):
    await bot.add_cog(Analisar(bot))