import logging
from discord.ext import commands
from discord import app_commands
import discord
import asyncio

logger = logging.getLogger(__name__)

class Resumir(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.genai_model = bot.model
        self.config = bot.generation_config
        self.cliente = bot.client

    class BotoesResumo(discord.ui.View):
        # a view agora recebe a lista de mensagens ja coletada para otimizar o processo
        def __init__(self, bot, mensagens: list[str], autor_id: int, privado: bool = False):
            super().__init__(timeout=150)
            self.bot = bot
            self.mensagens = mensagens
            self.autor_id = autor_id
            self.privado = privado

        @discord.ui.button(label="Mais Detalhes", style=discord.ButtonStyle.primary)
        async def mais_detalhes(self, interacao: discord.Interaction, botao: discord.ui.Button):
            if interacao.user.id != self.autor_id:
                await interacao.response.send_message(
                    "Só quem usou o comando pode clicar neste botão!",
                    ephemeral=True
                )
                return

            try:
                if not self.mensagens:
                    await interacao.response.send_message("Não há mensagens para detalhar :/", ephemeral=True)
                    return

                botao.disabled = True
                await interacao.message.edit(view=self)
                
                is_dm = interacao.guild is None
                await interacao.response.defer(thinking=True, ephemeral=self.privado and not is_dm)

                # prompt refinado para exigir a formatacao de topicos exata que voce pediu
                prompt = (
                    "Sua tarefa é criar um resumo detalhado das mensagens do Discord a seguir. "
                    "Organize a resposta como uma lista de tópicos. Cada tópico deve seguir estritamente este formato: `- **Título do Tópico**: Descrição.` "
                    "Por exemplo:\n- **Assunto Principal**: Discussão sobre o erro X no banco de dados.\n- **Solução Proposta**: Apagar o arquivo para forçar a recriação.\n"
                    "Não use tags como '[resumo]' ou '[detalhes]'. Entregue apenas a lista de tópicos formatada.\n\nmensagens:\n" 
                    + "\n".join(self.mensagens)
                )
                
                # o bot usa a lista de mensagens que ja tinha, sem precisar buscar no canal de novo
                resumo_detalhado = await self.bot.get_cog("Resumir")._fazer_resumo(interacao, prompt)
                await self.bot.get_cog("Resumir")._enviar_resumo(interacao, resumo_detalhado, privado=self.privado and not is_dm)
            
            except Exception as erro:
                logger.error(f"Erro ao gerar resumo detalhado: {erro}", exc_info=True)
                await interacao.followup.send(f"Ocorreu um erro ao gerar os detalhes: {erro}", ephemeral=True)


    async def _fazer_resumo(self, inter: discord.Interaction, prompt: str):
        resposta = await self.cliente.aio.models.generate_content(
            model=f'models/{self.genai_model}',
            contents=prompt,
            config=self.config
        )
        
        try:
            text_parts = [part.text for part in resposta.candidates[0].content.parts if hasattr(part, "text")]
            text = "".join(text_parts)
            return text.strip()
        except (ValueError, IndexError):
            logger.warning("Não foi possível extrair texto da resposta da API em resumir")
            return "Não foi possível gerar o resumo pois a resposta da API estava vazia"

    async def _enviar_resumo(self, inter: discord.Interaction, resumo: str, privado: bool, view: discord.ui.View = None):
        is_dm = inter.guild is None
        ephemeral = privado and not is_dm

        try:
            if len(resumo) > 1900:
                partes = [resumo[i:i + 1900] for i in range(0, len(resumo), 1900)]
                for i, parte in enumerate(partes):
                    kwargs = {'ephemeral': ephemeral}
                    if view and i == len(partes) - 1:
                        kwargs['view'] = view
                    await inter.followup.send(parte, **kwargs)
            else:
                kwargs = {'ephemeral': ephemeral}
                if view:
                    kwargs['view'] = view
                await inter.followup.send(resumo, **kwargs)
        except discord.errors.NotFound:
            kwargs = {'view': view} if view else {}
            await inter.channel.send(resumo, **kwargs)

    @app_commands.command(name="resumir", description="Faz um resumo das mensagens recentes do canal")
    @app_commands.describe(
        limite="Quantas mensagens coletar (máximo 200, padrão 100)",
        usuario="Resumir só mensagens de um usuário (opcional)",
        privado="Enviar o resumo só para você (padrão: não | não é possível usar em dms)"
    )
    async def resumir(self, inter: discord.Interaction, limite: int = 100, usuario: discord.User = None, privado: bool = False):
        try:
            is_dm = inter.guild is None
            if is_dm:
                privado = False

            await inter.response.defer(thinking=True, ephemeral=privado)

            if not is_dm:
                permissoes = inter.channel.permissions_for(inter.guild.me)
                if not permissoes.read_message_history:
                    await inter.followup.send("Não tenho permissão para ler mensagens neste canal", ephemeral=True)
                    return

            if not 1 <= limite <= 200:
                await inter.followup.send("O limite deve ser entre 1 e 200 mensagens", ephemeral=True)
                return

            # as mensagens do historico sao coletadas aqui, e apenas uma vez
            mensagens = []
            async for mensagem in inter.channel.history(limit=limite):
                if not mensagem.author.bot and (usuario is None or mensagem.author == usuario):
                    texto = f"{mensagem.author.display_name}: {mensagem.content}"
                    mensagens.append(texto)

            if not mensagens:
                await inter.followup.send("Não achei mensagens para resumir com esses critérios :/", ephemeral=True)
                return

            # o primeiro prompt agora e focado em um resumo simples e rapido
            prompt_simples = (
                "Sua tarefa é criar um resumo conciso e claro das mensagens do Discord a seguir. "
                "Destaque os principais tópicos de forma breve. Não use títulos nem formatação complexa. "
                "Apenas o texto do resumo.\n\nmensagens:\n" + "\n".join(mensagens)
            )
            resumo_inicial = await self._fazer_resumo(inter, prompt_simples)

            # a lista de mensagens coletadas e passada para a view, otimizando o processo
            view = self.BotoesResumo(self.bot, mensagens, inter.user.id, privado=privado)

            await self._enviar_resumo(inter, resumo_inicial, privado=privado, view=view)

        except Exception as erro:
            logger.error(f"Erro no comando /resumir: {erro}", exc_info=True)
            if not inter.response.is_done():
                await inter.response.send_message(f"Ocorreu um erro: {erro}", ephemeral=True)
            else:
                await inter.followup.send(f"Ocorreu um erro: {erro}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Resumir(bot))