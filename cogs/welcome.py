import discord
from discord.ext import commands

class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.CHANNEL_ID = 1410710808572198942

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        channel = member.guild.get_channel(self.CHANNEL_ID) or await self.bot.fetch_channel(self.CHANNEL_ID)
        
        if not channel:
            print(f"Erro: Canal {self.CHANNEL_ID} não encontrado.")
            return

        total_membros = member.guild.member_count

        embed = discord.Embed(
            title="🎉 EITA, NOVO ZOEIRO NAS ÁREAS 🎉",
            description=(
                f"Slg, {member.mention}, encostou na moralzinha...\n"
                f"Você é o **{total_membros}º** a brotar por aqui! :0\n"
                f"Agora somos **{total_membros}** loucos no servidor!"
            ),
            color=discord.Color.green()
        )
        
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text="Rogério Tech dá as boas-vindas!!! :D")

        try:
            await channel.send(content=f"{member.mention}", embed=embed)
        except discord.Forbidden:
            print("Erro: Sem permissão para enviar mensagens ou embutir links.")
        except Exception as e:
            print(f"Erro inesperado: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))
