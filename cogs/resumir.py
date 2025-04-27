from discord.ext import commands
from discord import app_commands
import discord
import asyncio


class Resumir(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.modelo = bot.model
        self.config = bot.generation_config
        self.cliente = bot.client

    class BotoesResumo(discord.ui.View):
        def __init__(self, bot, canal, usuario=None, limite=100, autor_id=None, privado=False):
            super().__init__(timeout=150)  # um tempo ai para os botões funcionarem
            self.bot = bot
            self.canal = canal
            self.usuario = usuario
            self.limite = limite
            self.autor_id = autor_id
            self.privado = privado  # armazena se a interação é privada

        @discord.ui.button(label="Mais Detalhes", style=discord.ButtonStyle.primary)
        async def mais_detalhes(self, interacao: discord.Interaction, botao: discord.ui.Button):
            # verifica se quem clicou é o autor do comando
            if interacao.user.id != self.autor_id:
                await interacao.response.send_message(
                    "Só quem usou o comando pode clicar neste botão!",
                    ephemeral=True
                )
                return

            try:
                mensagens = await self._coletar_mensagens(interacao)
                if not mensagens:
                    await interacao.response.send_message("Não achei mensagens para resumir :/", ephemeral=True)
                    return

                # deferir a resposta para indicar que está processando
                await interacao.response.defer(thinking=True, ephemeral=self.privado)  # respeita a privacidade

                prompt = (
                    "Resuma essas mensagens do canal do Discord com mais detalhes, incluindo exemplos e contexto dos "
                    "principais assuntos:\n\n" + "\n".join(mensagens)
                )
                resumo = await self.bot.get_cog("Resumir")._fazer_resumo(interacao, prompt)
                # corrigido: não passa view no mais_detalhes, resumo detalhado não precisa de botões
                await self.bot.get_cog("Resumir")._enviar_resumo(interacao, resumo, privado=self.privado)
            except Exception as erro:
                try:
                    await interacao.followup.send(embed=discord.Embed(
                        title="Erro",
                        description=f"Deu erro ao fazer resumo detalhado: {str(erro)}\nTipo do erro: {type(erro).__name__}",
                        color=discord.Color.red()
                    ), ephemeral=True)
                except discord.errors.NotFound:
                    # se o webhook estiver inválido, tenta enviar diretamente no canal
                    await interacao.channel.send(embed=discord.Embed(
                        title="Erro",
                        description=f"Deu erro ao fazer resumo detalhado: {str(erro)}\nTipo do erro: {type(erro).__name__}",
                        color=discord.Color.red()
                    ))

        async def _coletar_mensagens(self, interacao: discord.Interaction):
            mensagens = []
            async for mensagem in self.canal.history(limit=self.limite):
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

    async def _enviar_resumo(self, inter: discord.Interaction, resumo: str, privado: bool, view: discord.ui.View = None):
        # envia o resumo, dividindo se for muito longo (limite de 1900 caracteres)
        # corrigido: simplificado para sempre aceitar view=None sem erros
        try:
            if len(resumo) > 1900:
                partes = [resumo[i:i + 1900] for i in range(0, len(resumo), 1900)]
                for i, parte in enumerate(partes):
                    # só passa view na última parte e se view existir
                    kwargs = {'ephemeral': privado}
                    if view and i == len(partes) - 1:
                        kwargs['view'] = view
                    await inter.followup.send(parte, **kwargs)
            else:
                # passa view só se existir
                kwargs = {'ephemeral': privado}
                if view:
                    kwargs['view'] = view
                await inter.followup.send(resumo, **kwargs)
        except discord.errors.NotFound:
            # se o webhook estiver inválido, tenta enviar diretamente no canal
            kwargs = {'view': view} if view else {}
            await inter.channel.send(resumo, **kwargs)

    @app_commands.command(name="resumir", description="Faz um resumo das mensagens recentes do canal.")
    @app_commands.describe(
        limite="Quantas mensagens coletar (máximo 200, padrão 100).",
        usuario="Resumir só mensagens de um usuário (opcional).",
        privado="Enviar o resumo só para você (padrão: não)."
    )
    async def resumir(self, inter: discord.Interaction, limite: int = 100, usuario: discord.User = None, privado: bool = False):
        try:
            # resposta imediata para evitar expiração da interação
            await inter.response.defer(thinking=True, ephemeral=privado)

            # verificar permissões
            permissoes = inter.channel.permissions_for(inter.guild.me)
            if not permissoes.read_message_history:
                try:
                    await inter.followup.send("Não tenho permissão para ler mensagens neste canal.", ephemeral=True)
                except discord.errors.NotFound:
                    await inter.channel.send("Não tenho permissão para ler mensagens neste canal.")
                return

            # validar limite
            if limite < 1 or limite > 200:
                try:
                    await inter.followup.send("O limite deve ser entre 1 e 200 mensagens.", ephemeral=True)
                except discord.errors.NotFound:
                    await inter.channel.send("O limite deve ser entre 1 e 200 mensagens.")
                return

            # coletar mensagens
            mensagens = []
            async for mensagem in inter.channel.history(limit=limite):
                if not mensagem.author.bot and (usuario is None or mensagem.author == usuario):
                    texto = f"{mensagem.author.display_name}: {mensagem.content}"
                    mensagens.append(texto)

            if not mensagens:
                try:
                    await inter.followup.send("Não achei mensagens para resumir com esses critérios :/", ephemeral=True)
                except discord.errors.NotFound:
                    await inter.channel.send("Não achei mensagens para resumir com esses critérios :/")
                return

            # preparar prompt e fazer resumo
            prompt = (
                "Resuma essas mensagens do canal do Discord de forma simples e clara, destacando os principais "
                "assuntos:\n\n" + "\n".join(mensagens)
            )
            resumo = await self._fazer_resumo(inter, prompt)

            # criar view sempre, passando o parâmetro privado
            view = self.BotoesResumo(self.bot, inter.channel, usuario, limite, inter.user.id, privado=privado)

            # enviar resumo
            await self._enviar_resumo(
                inter,
                resumo,
                privado=privado,
                view=view
            )

        except Exception as erro:
            try:
                await inter.followup.send(embed=discord.Embed(
                    title="Erro",
                    description=f"Deu erro ao resumir: {str(erro)}\nTipo do erro: {type(erro).__name__}",
                    color=discord.Color.red()
                ), ephemeral=True)
            except discord.errors.NotFound:
                # se o webhook estiver inválido, envia diretamente no canal
                await inter.channel.send(embed=discord.Embed(
                    title="Erro",
                    description=f"Deu erro ao resumir: {str(erro)}\nTipo do erro: {type(erro).__name__}",
                    color=discord.Color.red()
                ))

async def setup(bot: commands.Bot):
    await bot.add_cog(Resumir(bot))