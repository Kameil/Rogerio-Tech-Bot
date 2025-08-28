import discord
from discord import app_commands
from discord.ext import commands

class Resetar(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="resetar", description="Resetar a conversa com o bot no canal atual.")
    async def resetar(self, inter: discord.Interaction):
        await inter.response.defer()
        try:
            channel_id = str(inter.channel.id)

            if channel_id in self.bot.chats:
                del self.bot.chats[channel_id]
                
                # se o canal estava no modo experimental, remove de lá também
                if inter.channel.id in self.bot.chats.get("experimental", []):
                    self.bot.chats["experimental"].remove(inter.channel.id)

                embed = discord.Embed(
                    title="✅ Conversa resetada",
                    description="O histórico de conversa deste canal foi apagado. A próxima mensagem iniciará uma nova conversa.",
                    color=discord.Color.green()
                )
            else:
                embed = discord.Embed(
                    title="ℹ️ Nada para resetar",
                    description="Nenhuma conversa existente foi encontrada para este canal.",
                    color=discord.Color.orange()
                )

            embed.set_footer(text=f"Ação executada por: {inter.user.name}")
            await inter.followup.send(embed=embed)

        except Exception as e:
            print(f"[ERRO] Falha ao resetar conversa no canal {inter.channel.id}: {e}")

            embed = discord.Embed(
                title="❌ Ocorreu um erro!",
                description="Não foi possível resetar a conversa. Tente novamente mais tarde.",
                color=discord.Color.red()
            )
            embed.set_footer(text=f"Erro técnico: {type(e).__name__}")
            await inter.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Resetar(bot))