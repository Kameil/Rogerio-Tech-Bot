from discord.ext import commands
from discord import app_commands
import discord
import asyncio
import datetime


class Resumir(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.modelo = bot.model
        self.config = bot.generation_config
        self.cliente = bot.client

    class BotoesResumo(discord.ui.View):
        def __init__(self, bot, canal, usuario=None, limite=100, tempo=None, autor_id=None):
            super().__init__(timeout=300)  # 5 minutos para os botões funcionarem
            self.bot = bot
            self.canal = canal
            self.usuario = usuario
            self.limite = limite
            self.tempo = tempo
            self.autor_id = autor_id

        @discord.ui.button(label="Mais Detalhes", style=discord.ButtonStyle.primary)
        async def mais_detalhes(self, interacao: discord.Interaction, botao: discord.ui.Button):
            # verifica se quem clicou é o autor do comando
            if interacao.user.id != self.autor_id:
                await interacao.response.send_message(
                    "Só quem usou o comando pode clicar neste botão!",
                    ephemeral=True
                )
                return

            if not interacao.response.is_done():
                await interacao.response.defer(thinking=True)
            try:
                mensagens = await self._coletar_mensagens(interacao)
                if not mensagens:
                    await interacao.followup.send("Não achei mensagens para resumir :/", ephemeral=True)
                    return

                prompt = (
                    "Resuma essas mensagens do canal do Discord com mais detalhes, incluindo exemplos e contexto dos "
                    "principais assuntos:\n\n" + "\n".join(mensagens)
                )
                resumo = await self.bot.get_cog("Resumir")._fazer_resumo(interacao, prompt)
                await self.bot.get_cog("Resumir")._enviar_resumo(interacao, resumo, privado=False)
            except Exception as erro:
                await interacao.followup.send(embed=discord.Embed(
                    title="Erro",
                    description=f"Deu erro ao fazer resumo detalhado: {str(erro)}\nTipo do erro: {type(erro).__name__}",
                    color=discord.Color.red()
                ), ephemeral=True)

        @discord.ui.button(label="Novo Resumo", style=discord.ButtonStyle.secondary)
        async def novo_resumo(self, interacao: discord.Interaction, botao: discord.ui.Button):
            # verifica se quem clicou é o autor do comando
            if interacao.user.id != self.autor_id:
                await interacao.response.send_message(
                    "Só quem usou o comando pode clicar neste botão!",
                    ephemeral=True
                )
                return

            await interacao.response.send_message(
                "Use o comando `/resumir` de novo para fazer outro resumo!",
                ephemeral=True
            )

        async def _coletar_mensagens(self, interacao: discord.Interaction):
            mensagens = []
            data_inicio = None
            if self.tempo:
                data_inicio = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=self.tempo)

            async for mensagem in self.canal.history(limit=self.limite, after=data_inicio):
                if not mensagem.author.bot and (self.usuario is None or mensagem.author == self.usuario):
                    texto = f"{mensagem.author.display_name}: {mensagem.content}"
                    mensagens.append(texto)
            return mensagens

    async def _fazer_resumo(self, inter: discord.Interaction, prompt: str):
        # faz o resumo usando o modelo de IA
        resposta = await self.cliente.aio.models.generate_content(
            model=self.modelo,
            contents=prompt,
            config=self.config
        )
        return resposta.text.strip()

    async def _enviar_resumo(self, inter: discord.Interaction, resumo: str, privado: bool, view=None):
        # envia o resumo, dividindo se for muito longo (limite de 1900 caracteres)
        if len(resumo) > 1900:
            partes = [resumo[i:i + 1900] for i in range(0, len(resumo), 1900)]
            for parte in partes:
                await inter.followup.send(parte, ephemeral=privado, view=view if parte == partes[-1] else None)
        else:
            await inter.followup.send(resumo, ephemeral=privado, view=view)

    @app_commands.command(name="resumir", description="Faz um resumo das mensagens recentes do canal.")
    @app_commands.describe(
        limite="Quantas mensagens coletar (máximo 200, padrão 100).",
        tempo="Horas para coletar mensagens (ex.: 24 para últimas 24h).",
        usuario="Resumir só mensagens de um usuário (opcional).",
        privado="Enviar o resumo só para você (padrão: não)."
    )
    async def resumir(self, inter: discord.Interaction, limite: int = 100, tempo: int = None, usuario: discord.User = None, privado: bool = False):
        # adia a resposta imediatamente para evitar timeout
        if not inter.response.is_done():
            await inter.response.defer(thinking=True)

        try:
            # verifica se o bot tem permissão para ler mensagens
            permissoes = inter.channel.permissions_for(inter.guild.me)
            if not permissoes.read_message_history:
                await inter.followup.send(
                    "Não tenho permissão para ler mensagens neste canal!",
                    ephemeral=True
                )
                return

            # verifica se o limite é válido
            if limite < 1 or limite > 200:
                await inter.followup.send(
                    "O limite deve ser entre 1 e 200 mensagens!",
                    ephemeral=True
                )
                return

            # verifica se o tempo é válido
            if tempo is not None and tempo < 1:
                await inter.followup.send(
                    "O tempo deve ser maior que 0 horas!",
                    ephemeral=True
                )
                return

            # avisa que está coletando mensagens
            await inter.followup.send(
                "Coletando mensagens... Aguarde um pouco!",
                ephemeral=True
            )

            # coleta mensagens com base nos parâmetros
            mensagens = []
            data_inicio = None
            if tempo:
                data_inicio = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=tempo)

            async for mensagem in inter.channel.history(limit=limite, after=data_inicio):
                if not mensagem.author.bot and (usuario is None or mensagem.author == usuario):
                    texto = f"{mensagem.author.display_name}: {mensagem.content}"
                    mensagens.append(texto)

            if not mensagens:
                await inter.followup.send(
                    "Não achei mensagens para resumir com esses critérios :/",
                    ephemeral=True
                )
                return

            # avisa que está fazendo o resumo
            await inter.followup.send(
                "Fazendo o resumo... Já, já termino!",
                ephemeral=True
            )

            # prepara o texto para o resumo
            prompt = (
                "Resuma essas mensagens do canal do Discord de forma simples e clara, destacando os principais "
                "assuntos:\n\n" + "\n".join(mensagens)
            )

            # faz e envia o resumo
            resumo = await self._fazer_resumo(inter, prompt)
            await self._enviar_resumo(
                inter,
                resumo,
                privado=privado,
                view=self.BotoesResumo(
                    self.bot,
                    inter.channel,
                    usuario=usuario,
                    limite=limite,
                    tempo=tempo,
                    autor_id=inter.user.id
                ) if not privado else None
            )

        except Exception as erro:
            mensagem_erro = f"Deu erro ao resumir: {str(erro)}\nTipo do erro: {type(erro).__name__}"
            await inter.followup.send(embed=discord.Embed(
                title="Erro",
                description=mensagem_erro,
                color=discord.Color.red()
            ), ephemeral=True)


async def setup(bot: commands.Bot):
    # adiciona o cog ao bot
    await bot.add_cog(Resumir(bot))