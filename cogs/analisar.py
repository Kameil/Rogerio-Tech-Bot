from discord.ext import commands
from discord import app_commands
import discord
import httpx
import base64
import datetime
import textwrap
from google import genai
from google.genai import types
from monitoramento import Tokens


class Analisar(commands.Cog):
    def __init__(self, bot):
        self.bot: commands.Bot = bot
        self.model: str = bot.model
        self.generation_config: types.GenerationConfig = bot.generation_config
        self.httpClient: httpx.AsyncClient = bot.httpclient
        self.client: genai.Client = bot.client
        self.tokens_monitor: Tokens = bot.tokens_monitor

    def mencao(self, content: str, guild: discord.Guild) -> str:
        for member in guild.members:
            mention = f"<@!{member.id}>"
            if mention in content:
                content = content.replace(mention, f"@{member.name}")
            mention = f"<@{member.id}>"
            if mention in content:
                content = content.replace(mention, f"@{member.name}")
        return content

    async def _executar_analise(self, inter: discord.Interaction, user, prompt=None, mpc=100, janalisado=False):
        # verifica se a interação ainda é válida antes de deferir
        if not inter.response.is_done():
            await inter.response.defer()

        if isinstance(inter.channel, discord.DMChannel):
            return await inter.followup.send("Esse comando só pode ser executado em um servidor.")

        try:
            # lista para armazenar mensagens coletadas
            messages = []

            # itera sobre os canais de texto do servidor
            for channel in inter.guild.text_channels:
                bot_permissions = channel.permissions_for(inter.guild.me)
                user_permissions = channel.permissions_for(inter.user)
                # ignora canais sem permissão de leitura de histórico para o bot ou sem acesso para o usuário
                if not bot_permissions.read_message_history or not user_permissions.read_messages:
                    continue

                # coleta até 'mpc' mensagens do canal
                async for message in channel.history(limit=mpc):
                    if message.author == user:
                        horario_utc = message.created_at
                        horario_local = horario_utc.astimezone(datetime.timezone(datetime.timedelta(hours=-3)))
                        sanitized_content = self.mencao(message.content, inter.guild)
                        messages.append(
                            f'Mensagem de {user.name} em #{message.channel.name}: "{sanitized_content}" às '
                            f'{horario_local.strftime("%H:%M:%S %d/%m/%Y")}'
                        )

            prompt_probot = f"Analise esse usuário com base no seu nome e na sua imagem de perfil e diga se ele é desenrolado ou não. Nome: {user.name}\n"
            if prompt is not None:
                prompt_probot = f"Analise {prompt} | Nome do usuário: {user.name}, Mensagens do usuário:\n"
            print(prompt_probot)

            prompt_probot += "\n".join(messages)

            # obtém a imagem de perfil do usuário
            response = await self.httpClient.get(user.avatar.url)
            avatar = response.content if response.status_code == 200 else None

            if avatar:
                # envia o prompt e a imagem para o modelo de IA
                response = await self.client.aio.models.generate_content(
                    contents=[prompt_probot, types.Part.from_bytes(data=avatar, mime_type="image/png")],
                    config=self.generation_config,
                    model=self.model
                )
                # adiciona o uso de tokens no banco de dados 
                usage_metadata = response.usage_metadata
                self.tokens_monitor.insert_usage(
                        uso=(usage_metadata.prompt_token_count + usage_metadata.candidates_token_count),
                        guild_id=message.guild.id,
                    )

                # divide a resposta em partes menores para respeitar o limite do Discord
                textos = textwrap.wrap(response.text, 2000)
                for text in textos:
                    # sanitiza a resposta do modelo para evitar menções ativas
                    sanitized_text = self.mencao(text, inter.guild)
                    if text == textos[-1] and not janalisado:
                        # envia a última parte com botões, desativando menções
                        await inter.followup.send(
                            sanitized_text,
                            view=self.Botoes(self.bot, user, prompt, mpc, author=inter.user.id),
                            allowed_mentions=discord.AllowedMentions.none()
                        )
                    else:
                        # envia as partes anteriores, desativando menções
                        await inter.followup.send(
                            sanitized_text,
                            allowed_mentions=discord.AllowedMentions.none()
                        )
            else:
                # envia mensagem de erro se a imagem não pôde ser obtida
                await inter.followup.send("Não foi possível obter a imagem do perfil do usuário.")
        except Exception as e:
            # envia um embed com detalhes do erro, caso ocorra
            embed = discord.Embed(
                title="Ocorreu Um Erro!",
                description=f"Erro ao analisar usuário: {str(e)}\nTipo do erro: {type(e).__name__}",
                color=discord.Color.red()
            )
            await inter.followup.send(
                embed=embed,
                view=self.Botoes(self.bot, user, prompt, mpc, author=inter.user.id)
            )
            print(f"Erro ao analisar usuário em: {inter.guild.name}")

    class PromptModal(discord.ui.Modal):
        def __init__(self, bot, user, mpc, author, original_prompt):
            super().__init__(title="Novo Prompt para Análise")
            self.bot = bot
            self.user = user
            self.mpc = mpc
            self.author = author
            self.original_prompt = original_prompt
            self.add_item(discord.ui.TextInput(
                label="Novo Prompt",
                style=discord.TextStyle.long,
                placeholder="Digite o novo prompt para análise...",
                required=False
            ))

        async def on_submit(self, interaction: discord.Interaction):
            try:
                # usa o novo prompt se tiver, se não usa o original
                new_prompt = self.children[0].value if self.children[0].value else self.original_prompt
                # verifica se a interação ainda é válida antes de prosseguir
                if not interaction.response.is_done():
                    await interaction.response.defer()
                await self.bot.get_cog("Analisar")._executar_analise(
                    interaction, self.user, new_prompt, self.mpc, janalisado=True
                )
            except Exception as e:
                # garante que a mensagem de erro seja clara e bem formatada
                error_message = f"Erro ao processar o novo prompt: {str(e)}\nTipo do erro: {type(e).__name__}"
                embed = discord.Embed(
                    title="Ocorreu Um Erro!",
                    description=error_message,
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed, ephemeral=False)

    class Botoes(discord.ui.View):
        def __init__(self, bot, user, prompt, mpc, author=None):
            super().__init__(timeout=60)
            self.bot = bot
            self.user = user
            self.prompt = prompt
            self.mpc = mpc
            self.janalisado = False
            self.author = author

        @discord.ui.button(label="Re:Analisar", style=discord.ButtonStyle.secondary)
        async def analisar(self, interaction: discord.Interaction, button: discord.ui.Button):
            # verifica se o usuário clicando é o autor do comando
            if interaction.user.id != self.author:
                return await interaction.response.send_message(
                    "Apenas o usuário que executou o comando pode usar esse botão.",
                    ephemeral=True
                )
            if not self.janalisado:
                self.janalisado = True
                # cria um menu de seleção para escolher entre novo prompt ou original
                select = discord.ui.Select(
                    placeholder="Usar um novo prompt?",
                    min_values=1,
                    max_values=1,
                    options=[
                        discord.SelectOption(label="Sim", value="sim", description="Usar um novo prompt para análise."),
                        discord.SelectOption(label="Não", value="nao", description="Usar o prompt original.")
                    ]
                )

                async def select_callback(interaction_select: discord.Interaction):
                    try:
                        if select.values[0] == "sim":
                            # exibe o modal p/ colocar um novo prompt
                            await interaction_select.response.send_modal(
                                Analisar.PromptModal(self.bot, self.user, self.mpc, self.author, self.prompt)
                            )
                        else:
                            # faz a análise com o prompt original
                            if not interaction_select.response.is_done():
                                await interaction_select.response.defer()
                            await self.bot.get_cog("Analisar")._executar_analise(
                                interaction_select, self.user, self.prompt, self.mpc, janalisado=True
                            )
                    except Exception as e:
                        # garante que a mensagem de erro seja clara e bem formatada
                        error_message = f"Erro ao processar a seleção: {str(e)}\nTipo do erro: {type(e).__name__}"
                        embed = discord.Embed(
                            title="Ocorreu Um Erro!",
                            description=error_message,
                            color=discord.Color.red()
                        )
                        await interaction_select.followup.send(embed=embed, ephemeral=False)

                select.callback = select_callback
                view = discord.ui.View()
                view.add_item(select)

                await interaction.response.send_message(
                    "Deseja usar um novo prompt para a análise?",
                    view=view,
                    ephemeral=True
                )
            else:
                # informa que o usuário já foi analisado
                await interaction.response.send_message("Usuário já analisado.", ephemeral=True)

    @app_commands.command(name="analisar", description="Descobrir se é desenrolado.")
    @app_commands.describe(
        user="Usuário a ser analisado",
        mpc="Mensagens por canal. Padrão: 100",
        prompt="Analise + prompt | nome do usuário + mensagens do usuário"
    )
    async def analisar(self, inter: discord.Interaction, user: discord.User, prompt: str = None, mpc: int = 100):
        # executa a análise inicial
        await self._executar_analise(inter, user, prompt, mpc)


async def setup(bot):
    # adiciona o cog ao bot
    await bot.add_cog(Analisar(bot))