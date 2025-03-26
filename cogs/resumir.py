from discord.ext import commands
from discord import app_commands
import discord

class Resumir(commands.Cog):
    def __init__(self, bot):
        self.bot = bot



async def setup(bot: commands.Bot):
    bot.add_cog(Resumir(bot))