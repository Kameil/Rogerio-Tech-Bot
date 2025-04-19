from discord import app_commands
from discord.ext import commands
import discord

class Resetar(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.model = bot.model
        self.generation_config = bot.generation_config
        self.chats = bot.chats
        self.client = bot.client

    @app_commands.command(name='resetar', description='Resetar a conversa com o bot no canal atual.')
    async def pedra(self, inter: discord.Interaction):
        try:
            await inter.response.defer()
            channel_id = str(inter.channel.id)
            if channel_id in self.chats:
                self.chats[channel_id] = self.client.aio.chats.create(model=self.model, config=self.generation_config)
                embed = discord.Embed(title="Conversa resetada", description="A conversa com o bot foi resetada com sucesso.", color=discord.Color.green())

                embed.set_footer(text=f"{inter.user.name}")
                await inter.followup.send(embed=embed)


            else:
                await inter.followup.send("Nao ha conversa para resetar.")
        except Exception as e:
            embed = discord.Embed(title="Ocorreu Um Erro!", description=f"\n```py\n{str(e)}\n```", color=discord.Color.red())
            await inter.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Resetar(bot))