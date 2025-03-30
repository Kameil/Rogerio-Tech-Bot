from discord.ext import commands
from discord import app_commands
import discord

class Resumir(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.model = bot.model
        self.generation_config = bot.generation_config

    @commands.Cog.listener(name="resumir")
    async def rogeriootechpro(self, inter: discord.Interaction):
        await inter.response.send_message("Rogerio Tech")
    


async def setup(bot: commands.Bot):
    bot.add_cog(Resumir(bot))