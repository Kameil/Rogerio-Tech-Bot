from discord import app_commands
from discord.ext import commands
import discord

from google.genai import types


class Experimental(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.model = bot.model
        self.generation_config = bot.generation_config
        self.chats = bot.chats
        self.client = bot.client
        self.experimental_generation_config = bot.experimental_generation_config

    @app_commands.command(name="experimental", description="Ativar/desativar modo de pensamente experimental no chat atual.")
    async def resetar(self, inter: discord.Interaction):
        if not inter.channel.id in self.chats["experimental"]:
            channel_id = inter.channel.id

            self.chats["experimental"].append(channel_id)
            self.chats[channel_id] = self.client.aio.chats.create(
                                model="gemini-2.5-flash-lite-preview-06-17",
                                config=self.generation_config,
                            )
            embed = discord.Embed(description=f"Modo experimental ativado no canal atual.", color=discord.Color.green())
            await inter.response.send_message(embed=embed)
        else:
            channel_id = inter.channel.id

            self.chats["experimental"].remove(channel_id)
            del self.chats[channel_id]
            embed = discord.Embed(description="Modo experimental desativado no canal atual.", color=discord.Color.red())
            await inter.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Experimental(bot))