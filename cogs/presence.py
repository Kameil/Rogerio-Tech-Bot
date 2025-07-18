import discord
from discord.ext import commands
from config import target_id, channel_id

class Presence(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        if after.id == target_id:
            if before.status == discord.Status.offline and after.status in [
                discord.Status.online,
                discord.Status.idle,
                discord.Status.dnd,
            ]:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    if after.status == discord.Status.dnd:
                        texto = (
                            "O menino volei tá on mas não quer ser perturbado, tropa...\n"
                            "https://tenor.com/view/zesty-cat-niklas-cat-tongue-gif-9842551414196208576"
                        )
                    else:
                        texto = (
                            f"{after.mention} o menino volei ta on tropa!!\n"
                            "https://tenor.com/view/zesty-cat-niklas-cat-tongue-gif-9842551414196208576"
                        )

                    msg = await channel.send(texto)
                    print(f"[PRESENCE] Mensagem enviada para {after.name} e será apagada em 10 minutos.")
                    await msg.delete(delay=600) 

async def setup(bot):
    await bot.add_cog(Presence(bot))
