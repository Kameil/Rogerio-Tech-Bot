from discord.ext import commands
import discord
from monitoramento import Tokens

class Monitor(commands.Cog):
    def __init__(self, bot):
        self.tokens_monitor: Tokens = bot.tokens_monitor
    

    @commands.command(name="tokens")
    async def show_tabela_de_uso(self, ctx: commands.Context):
        lista = self.tokens_monitor.get_usage_order_uso()
        
        if lista:
            embed_description = "\n".join(f"`guild: {guild.guild_id} uso:{guild.uso} reqts {guild.requests}`" for guild in lista[:20])
            embed = discord.Embed(title="Lista de Uso", description=embed_description)
            await ctx.send(embed=embed)
        else:
            await ctx.send("Nenhum registro de uso de tokens encontrado pae")

async def setup(bot):
    await bot.add_cog(Monitor(bot))