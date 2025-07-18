import discord
from discord.ext import commands
from config import target_id, channel_id

class Presence(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        if after.id == target_id:
            if before.status == discord.Status.offline and after.status in [discord.Status.online, discord.Status.idle, discord.Status.dnd]:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    await channel.send(
                        f"{after.mention} o menino volei tá on!! tropa\nhttps://tenor.com/view/zesty-cat-niklas-cat-tongue-gif-9842551414196208576"
                    )

async def setup(bot):
    await bot.add_cog(Presence(bot))