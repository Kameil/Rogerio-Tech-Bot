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

ANALYSIS_TIMEOUT_SECONDS = 300.0
MAX_MESSAGES_PER_CHANNEL = 100

logger = logging.getLogger(__name__)

class AnalysisBlockedError(Exception):
    pass


class ReanaliseView(discord.ui.View):
    def __init__(self, cog_instance, user_data: dict, autor_id: int):
        super().__init__(timeout=ANALYSIS_TIMEOUT_SECONDS)
        self.cog = cog_instance
        self.user_data = user_data
        self.autor_id = autor_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.autor_id:
            await interaction.response.send_message(
                "Apenas quem executou o comando original pode usar este botão",
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Reanalisar", style=discord.ButtonStyle.primary, emoji="🔄")
    async def reanalisar(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.defer(thinking=True)

        await interaction.followup.send("🔄 To bizonhando de novo, pera ai...")

        try:
            self.user_data['prompt'] = (
                "Refaça a análise de perfil do usuário a seguir de forma resumida, divertida e direta. "
                "Baseie-se no nome, avatar e histórico de mensagens. "
                "Não use marcadores, não use tags, não divida em RESUMO/DETALHES. "
                "Escreva em um único parágrafo corrido, objetivo e com tom descontraído. "
                "O texto deve ter entre 900 e 1200 caracteres."
            )

            genai_response = await self.cog._generate_analysis(interaction, self.user_data)
            response_text = self.cog._extract_text_from_response(genai_response)

            if not response_text:
                raise ValueError("A reanálise gerou uma resposta vazia")

            await self.cog._enviar_resposta(
                interaction,
                f"🧠 **Reanálise para {self.user_data['user'].display_name}**:\n\n{response_text}"
            )

        except Exception as e:
            await self.cog._handle_error(interaction, e)


class Analisar(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.http_client: httpx.AsyncClient = bot.http_client
        self.client: genai.Client = bot.client
        self.tokens_monitor: Tokens = bot.tokens_monitor

    def _extract_text_from_response(self, response: types.GenerateContentResponse) -> str:
        if not response.candidates:
            raise ValueError("A resposta da API não contém candidatos")

        candidate = response.candidates[0]
        if not candidate.content or not candidate.content.parts:
            return ""

        try:
            text_parts = [
                part.text for part in candidate.content.parts
                if hasattr(part, "text") and part.text
            ]
            return "".join(text_parts).strip()
        except Exception:
            return ""

    async def _collect_user_messages(
        self, inter: discord.Interaction, user: discord.User, mpc: int
    ) -> list[str]:
        messages = []
        periodo = datetime.datetime.now() - datetime.timedelta(days=30)

        for channel in inter.guild.text_channels:
            if not channel.permissions_for(inter.guild.me).read_message_history:
                continue
            try:
                async for message in channel.history(limit=mpc, after=periodo):
                    if message.author == user and message.content:
                        local_time = message.created_at.astimezone(
                            datetime.timezone(datetime.timedelta(hours=-3))
                        )
                        messages.append(
                            f'No canal #{message.channel.name} em {local_time.strftime("%d/%m")}: "{message.content}"'
                        )
            except discord.Forbidden:
                continue
        return messages

    # a funcao agora e mais generica, apenas envia para a api
    async def _generate_analysis(self, inter: discord.Interaction, contents: list) -> types.GenerateContentResponse:
        generation_config = types.GenerateContentConfig(
            temperature=0.7,
            max_output_tokens=3000,
            system_instruction=self.bot.system_instruction,

        )
        response = await self.client.aio.models.generate_content(
            contents=contents, config=generation_config, model="gemini-2.5-flash-lite"
        )

        
        if not response.candidates:
            reason = response.prompt_feedback.block_reason.name if response.prompt_feedback else "Desconhecida"
            raise AnalysisBlockedError(f"A resposta foi bloqueada pela API por motivo de segurança: {reason}")
        
        for candidate in response.candidates:
                for part in candidate.content.parts:
                    if part.text:
                        if part.thought:
                            print("THOUGHT: ", part.text)
                            continue
                        print("NORMAL PART: ", part.text)

        if response.usage_metadata:
            self.tokens_monitor.insert_usage(
                uso=response.usage_metadata.total_token_count,
                guild_id=inter.guild.id
            )

        return response

    async def _enviar_resposta(
        self, inter: discord.Interaction, response_text: str, view: discord.ui.View = None
    ):
        wrapped_text = textwrap.wrap(
            response_text, 1200, replace_whitespace=False, drop_whitespace=False
        )
        for i, chunk in enumerate(wrapped_text):
            is_last_chunk = (i == len(wrapped_text) - 1)
            send_kwargs = {"content": chunk, "allowed_mentions": discord.AllowedMentions.none()}
            if is_last_chunk and view:
                send_kwargs["view"] = view
            await inter.followup.send(**send_kwargs)

    async def _handle_error(self, inter: discord.Interaction, e: Exception):
        error_trace = traceback.format_exc(limit=1)

        error_embed = discord.Embed(
            title="Ocorreu um erro inesperado!",
            description=(
                f"Não foi possivel processar sua solicitação\n```py\n{error_trace}\n```\n"
                f"[🆘 Suporte](https://discord.gg/H77FTb7hwH)"
            ),
            color=discord.Color.red(),
        )

        if isinstance(e, AnalysisBlockedError):
            embed = discord.Embed(
                title="Análise Bloqueada",
                description=str(e),
                color=discord.Color.orange()
            )
            embed.add_field(
                name="Precisa de ajuda?",
                value="[🆘 Suporte](https://discord.gg/H77FTb7hwH)",
                inline=False
            )
            if inter.response.is_done():
                await inter.followup.send(embed=embed)
            else:
                await inter.response.send_message(embed=embed)
            return

        if inter.response.is_done():
            await inter.followup.send(embed=error_embed)
        else:
            await inter.response.send_message(embed=error_embed)

    @app_commands.command(
        name="analisar",
        description="Descobrir se um usuário é desenrolado com base em seu perfil e mensagens"
    )
    @app_commands.describe(
        user="O usuário a ser analisado",
        mpc=f"Máximo de mensagens a coletar por canal (Padrão: {MAX_MESSAGES_PER_CHANNEL})"
    )
    async def analisar(
        self, inter: discord.Interaction, user: discord.User, mpc: int = MAX_MESSAGES_PER_CHANNEL
    ):
        if isinstance(inter.channel, discord.DMChannel):
            await inter.response.send_message(
                "Este comando só pode ser executado em um servidor"
            )
            return

        await inter.response.defer(thinking=True)

        try:
            await inter.followup.send(
                f"🔎 Analisando **{user.display_name}**... To bizonhando o servidor em busca de mensagens. Segura ai..."
            )

            messages = await self._collect_user_messages(inter, user, mpc)

            async with self.http_client as client:
                response = await client.get(user.display_avatar.url)
                response.raise_for_status()
                avatar_bytes = response.content

            user_data = {
                "user": user,
                "messages": messages,
                "avatar_bytes": avatar_bytes,
                "prompt": (
                    "Faça uma análise de perfil resumida e divertida sobre o usuário a seguir para ver se ele é 'desenrolado'. "
                    "Use nome, avatar e histórico de mensagens. "
                    "Escreva em um único parágrafo corrido, direto, informal, sem tags ou subtítulos. "
                    "O texto deve ter entre 900 e 1200 caracteres."
                )
            }

            genai_response = await self._generate_analysis(inter, user_data)
            response_text = self._extract_text_from_response(genai_response)

            if not response_text:
                raise ValueError("A análise inicial gerou uma resposta vazia")

            view = ReanaliseView(self, user_data, inter.user.id)
            await self._enviar_resposta(inter, response_text, view=view)

        except Exception as e:
            await self._handle_error(inter, e)


async def setup(bot: commands.Bot):
    await bot.add_cog(Analisar(bot))
