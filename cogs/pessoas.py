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

    @app_commands.command(name='pessoas', description='Adicionar uma pessoa com nome e descrição.')
    @app_commands.describe(
        nome='O nome da pessoa',
        descricao='A descrição da pessoa'
    )
    async def pessoas(self, inter: discord.Interaction, nome: str, descricao: str):
        try:
            await inter.response.defer()
            # divide a string 'nome' em uma lista de palavras
            nomes = nome.split()
            # pega os dois primeiros nomes, se existirem. Se não existirem, pega o primeiro nome.
            nome_exibido = " ".join(nomes[:2]) if len(nomes) > 1 else nomes[0]
            
            embed = discord.Embed(
                title="Sucesso!",
                description=f"**{nome_exibido.capitalize()}** foi adicionado(a) com êxito.",
                color=discord.Color.green()
            )
            
            await inter.followup.send(embed=embed)
            
        except Exception as e:
            embed = discord.Embed(
                title="Ocorreu Um Erro!",
                description=f"\n```py\n{str(e)}\n```",
                color=discord.Color.red()
            )
            await inter.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Pessoas(bot))