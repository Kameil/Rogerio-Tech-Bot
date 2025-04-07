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
            # pega o primeiro nome da string 'nome'
            primeiro_nome = nome.split()[0]
            
            embed = discord.Embed(
                title="Sucesso!",
                description=f"**{primeiro_nome.capitalize()}** foi adicionado(a) com êxito.",
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