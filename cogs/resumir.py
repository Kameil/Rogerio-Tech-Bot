from discord.ext import commands
from discord import app_commands
import discord
import asyncio

class Resumir(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.model = bot.model
        self.generation_config = bot.generation_config
        self.client = bot.client

    @app_commands.command(name="resumir", description="Resume as mensagens recentes do canal atual.")
    async def resumir(self, inter: discord.Interaction):
        await inter.response.defer(thinking=True)  # adia a resposta p/ processamento

        try:
            # verifica se o bot tem permissão para ler mensagens
            permissoes = inter.channel.permissions_for(inter.guild.me)
            if not permissoes.read_message_history:
                await inter.followup.send("Não tenho permissão para ler o histórico de mensagens neste canal!", ephemeral=True)
                return

            # coleta as últimas 100 mensagens do canal
            mensagens = []
            async for mensagem in inter.channel.history(limit=100):
                if not mensagem.author.bot:  # n pode ser d bots
                    conteudo = f"{mensagem.author.display_name}: {mensagem.content}"
                    mensagens.append(conteudo)

            if not mensagens:
                await inter.followup.send("Não encontrei mensagens recentes para resumir :/", ephemeral=True)
                return

            # prepara o prompt para o resumo
            prompt = (
                "Resuma as seguintes mensagens do canal do Discord de forma concisa e clara, destacando os principais tópicos discutidos:\n\n"
                + "\n".join(mensagens)
            )

            # gera o resumo diretamente, sem sessão
            async with inter.channel.typing():
                resposta = await self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    generation_config=self.generation_config
                )

            # envia o resumo
            resumo = resposta.text.strip()
            if len(resumo) > 1900:  # lida com resumos longos
                partes = [resumo[i:i+1900] for i in range(0, len(resumo), 1900)]
                for parte in partes:
                    await inter.followup.send(parte)
            else:
                await inter.followup.send(resumo)

        except Exception as e:
            mensagem_erro = f"Ocorreu um erro ao resumir as mensagens: {str(e)}"
            await inter.followup.send(embed=discord.Embed(
                title="Erro",
                description=mensagem_erro,
                color=discord.Color.red()
            ), ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Resumir(bot))