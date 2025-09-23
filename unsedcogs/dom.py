from discord import app_commands
from discord.ext import commands
import discord
import asyncio

class Dom(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.model = bot.model
        self.generation_config = bot.generation_config
        self.chats = bot.chats
        self.client = bot.client

    @app_commands.command(name="dom", description="Encare o dom por 10 segundos (sem rir)!")
    async def dom(self, inter: discord.Interaction):
        try:
            await inter.response.send_message('https://has-autism.lol/W7vv7\nEncare o dom por 10 segundos...')
            await asyncio.sleep(10)
            await inter.followup.send("boa pedro, to gostando de ver, nao riu :clap:\nOu riu...?")
        except Exception as e:
            embed = discord.Embed(
                title="Ocorreu um erro!",
                description=f"```py\n{str(e)}\n```",
                color=discord.Color.red()
            )
            await inter.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Dom(bot))
