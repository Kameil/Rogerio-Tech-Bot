from discord import app_commands
from discord.ext import commands
import discord

class Pessoas(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.model = bot.model
        self.generation_config = bot.generation_config
        self.chats = bot.chats
        self.client = bot.client

    @app_commands.command(name='pessoas', description='Adicionar uma pessoa com nome completo e descrição.')
    @app_commands.describe(
        nome='O nome completo da pessoa',
        descricao='A descrição da pessoa',
        composto='O nome é composto?'
    )
    @app_commands.choices(
        composto=[
            app_commands.Choice(name="Sim", value="sim"),
            app_commands.Choice(name="Não", value="nao")
        ]
    )
    async def pessoas(self, inter: discord.Interaction, nome: str, descricao: str, composto: str):
        try:
            await inter.response.defer(ephemeral=True)
            # divide a string 'nome' em uma lista de palavras
            nomes = nome.split()
            # define o nome exibido com base na escolha de 'composto'
            if composto == "sim" and len(nomes) >= 2:
                nome_exibido = f"{nomes[0]} {nomes[1]}"
            else:
                nome_exibido = nomes[0]
            
            embed = discord.Embed(
                title="Sucesso!",
                description=f"**{nome_exibido.capitalize()}** foi adicionado(a) com êxito.",
                color=discord.Color.green()
            )
            
            await inter.followup.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            embed = discord.Embed(
                title="Ocorreu Um Erro!",
                description=f"\n```py\n{str(e)}\n```",
                color=discord.Color.red()
            )
            await inter.followup.send(embed=embed)
    class MyModal(discord.ui.Modal):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)

            self.add_item(discord.ui.TextInput(label="Nome"))
            self.add_item(discord.ui.TextInput(label="Descricao", style=discord.TextStyle.long))

        async def callback(self, interaction: discord.Interaction):
            embed = discord.Embed(title="tendeu")
            embed.add_field(name="nome", value=self.children[0].value)
            embed.add_field(name="descricao", value=self.children[1].value)
            await interaction.response.send_message(embeds=[embed])
    @app_commands.command(name="pessoas_beta", description="adiciona pessoa ai tendeu")
    async def pessoas_beta(self, inter: discord.Interaction):
        await inter.response.send_modal(self.MyModal(title="Pessoas Beta"))

async def setup(bot):
    await bot.add_cog(Pessoas(bot))