import discord
from discord import app_commands
from discord.ext import commands

class Urgente(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.modelo = bot.model
        self.config = bot.generation_config
        self.cliente = bot.client

    @app_commands.command(name="urgente", description="URGENTE EVERYONE!!")
    async def urgente(self, inter: discord.Interaction):
        try:
            if inter.guild is None:
                return await inter.response.send_message("Vai dizer que algo é urgente pra quem? Não da pra usar em DMs.", ephemeral=True)

            if not inter.channel.permissions_for(inter.user).mention_everyone:
                return await inter.response.send_message("Você não tem permissão de usar isso.", ephemeral=True)

            imagem_url = "https://images-ext-1.discordapp.net/external/L7Dwzb_qoJ7Qbe7TagF9GWoXQsgPpgh1bYqUUlCNnyY/%3Falt%3Dmedia%26token%3Df1d9b282-e51a-42b4-84ee-dc138a997900/https/firebasestorage.googleapis.com/v0/b/st2022.appspot.com/o/Screenshot_20221118-130810_YouTube.jpg?format=webp&width=115&height=115"
            embed = discord.Embed()
            embed.set_image(url=imagem_url)

            await inter.response.send_message(
                content="@everyone !!!!!!!!",
                embed=embed,
                allowed_mentions=discord.AllowedMentions(everyone=True)
            )

        except Exception as erro:
            embed_erro = discord.Embed(
                title="Erro",
                description=f"Deu erro ao enviar a mensagem urgente: {str(erro)}\nTipo do erro: {type(erro).__name__}",
                colour=discord.Colour.red()
            )

            try:
                if inter.response.is_done():
                    await inter.followup.send(embed=embed_erro, ephemeral=True)
                else:
                    await inter.response.send_message(embed=embed_erro, ephemeral=True)
            except discord.errors.NotFound:
                await inter.channel.send(embed=embed_erro)

async def setup(bot: commands.Bot):
    await bot.add_cog(Urgente(bot))
