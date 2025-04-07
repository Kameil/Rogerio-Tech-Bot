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

    class MyModal(discord.ui.Modal):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)

            self.add_item(discord.ui.TextInput(label="Nome", placeholder="Digite o nome da pessoa"))
            self.add_item(discord.ui.TextInput(label="Descrição", style=discord.TextStyle.long, placeholder="Digite a descrição"))
            self.add_item(discord.ui.TextInput(label="Composto? (sim/não)", placeholder="Digite 'sim' ou 'não'"))

        async def callback(self, interaction: discord.Interaction):
            try:
                # pega os valores do modal
                nome = self.children[0].value
                composto = self.children[2].value.lower()
                
                # divide o nome em uma lista de palavras
                nomes = nome.split()
                
                # define o nome exibido com base na escolha de 'composto'
                if composto == "sim" and len(nomes) >= 2:
                    nome_exibido = f"{nomes[0]} {nomes[1]}"
                else:
                    nome_exibido = nomes[0]
                
                # cria o embed de sucesso
                embed = discord.Embed(
                    title="Sucesso!",
                    description=f"**{nome_exibido.capitalize()}** foi adicionado(a) com êxito.",
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
            except Exception as e:
                embed = discord.Embed(
                    title="Ocorreu Um Erro!",
                    description=f"\n```py\n{str(e)}\n```",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=False)

    @app_commands.command(name="pessoas", description="Adiciona uma pessoa anonimamente")
    async def pessoas_beta(self, inter: discord.Interaction):
        await inter.response.send_modal(self.MyModal(title="Adicionar pessoa(s)..."))

async def setup(bot):
    await bot.add_cog(Pessoas(bot))