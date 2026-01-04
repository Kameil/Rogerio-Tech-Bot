import discord
from discord.ext import commands
from config import target_id, channel_id
from typing import Optional
import time

class Presence(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.last_alert_time = 0  # timestamp da última notificação
        self.cooldown = 600       # 10 minutos de cooldown

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        if after.id != target_id:
            return

        before_status = before.status
        after_status = after.status

        if before_status == discord.Status.offline and after_status in {
            discord.Status.online,
            discord.Status.idle,
            discord.Status.dnd,
        }:
            now = time.monotonic()
            if now - self.last_alert_time < self.cooldown:
                return  # ignora se ainda estiver no cooldown

            self.last_alert_time = now  # atualiza o timestamp

            channel: Optional[discord.TextChannel] = self.bot.get_channel(channel_id)
            if not channel:
                print(f"[ERRO] Canal com ID {channel_id} não encontrado. Verifique se o ID está correto e se o bot tem acesso.")
                return

            gif_url = "https://tenor.com/view/zesty-cat-niklas-cat-tongue-gif-9842551414196208576"

            if after_status == discord.Status.dnd:
                texto = (
                    "O menino volei tá on mas não quer ser perturbado, tropa...\n"
                    f"{gif_url}"
                )
            else:
                texto = (
                    f"{after.mention} o menino volei ta on tropa!!\n"
                    f"{gif_url}"
                )

            msg = await channel.send(texto)
            await msg.delete(delay=600)

async def setup(bot: commands.Bot):
    await bot.add_cog(Presence(bot))
