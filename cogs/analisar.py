from discord.ext import commands 
from discord import app_commands
import discord

import httpx
import base64
import datetime
import textwrap

from google.genai import types


class Analisar(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.model = bot.model
        self.generation_config = bot.generation_config
        self.chats = bot.chats
        self.httpClient = bot.httpclient
        self.client = bot.client

        
    async def _executar_analise(self, inter: discord.Interaction, user, prompt=None, mpc=100, janalisado=False):
        await inter.response.defer()
        if isinstance(inter.channel, discord.DMChannel):
            return await inter.followup.send("Esse comando so pode ser executado em um servidor.")
        try:
            messages = []
            for channel in inter.guild.text_channels:
                bot_permissions = channel.permissions_for(inter.guild.me)
                if not bot_permissions.read_message_history:
                    continue
                async for message in channel.history(limit=mpc):
                    if message.author == user:
                        horario_utc = message.created_at 
                        horario_local = horario_utc.astimezone(datetime.timezone(datetime.timedelta(hours=-3)))
                        messages.append(f'Mensagem de {user.name} em #{message.channel.name}: "{message.content}" às {horario_local.strftime("%H:%M:%S %d/%m/%Y")}')
            prompt_probot = f"analise esse usuario com base no seu nome e na sua imagem de perfil e diga se ele e desenrolado ou nao. Nome:{user.name}\n"
            if prompt is not None:
                prompt_probot = "analise " + prompt + f" | Nome do usuario: {user.name}, Mensagens do usuario:\n"
            print(prompt_probot)
            prompt_probot += "\n".join(messages)

            response = await self.httpClient.get(user.avatar.url)
            if response.status_code == 200:
                avatar = response.content
            else:
                avatar = None

            if avatar:
                response = await self.client.aio.models.generate_content(
                    contents = [prompt_probot, types.Part.from_bytes(data=avatar, mime_type="image/png")],
                    config=self.generation_config,
                    model=self.model
                )
                textos = textwrap.wrap(response.text, 2000)
                for text in textos:
                    if text == textos[-1] and janalisado is False:
                        await inter.followup.send(text, view=self.Botoes(self.bot, user, prompt, mpc, author=inter.user.id))
                    else:
                        await inter.followup.send(text)

            else:
                await inter.followup.send("Nao foi possivel obter a imagem do perfil do usuario.")
        except Exception as e:
            embed = discord.Embed(title="Ocorreu Um Erro!", description=f"\n```py\n{str(e)}\n```", color=discord.Color.red())
            await inter.followup.send(embed=embed, view=self.Botoes(self.bot, user, prompt, mpc, author=inter.user.id))
            print(f"Erro ao analisar usuario em: {inter.guild.name}")



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
            if not interaction.user.id == self.author:
                return await interaction.response.send_message("Apenas o usuario que executou o comando pode usar esse botao.", ephemeral=True)
            elif not self.janalisado:
                self.janalisado = True
                await self.bot.get_cog("Analisar")._executar_analise(interaction, self.user, self.prompt, self.mpc, janalisado=True)
            else:
                await interaction.response.send_message("Usuario ja analisado.", ephemeral=True)
    

    

    @app_commands.command(name='analisar', description='descobrir se e desenrolado.')
    @app_commands.describe(user="Usuario a ser analisado", mpc="Mensagens por canal. Padrao:100", prompt="Analise + prompt | nome do usuario + mensagens do usuario")    
    async def Jokenpo(self, inter: discord.Interaction, user: discord.User, prompt: str=None, mpc: int=100):
        await self._executar_analise(inter, user, prompt, mpc)
        
    
    

async def setup(bot):
    await bot.add_cog(Analisar(bot))