import discord
from discord import app_commands
from discord.ext import commands
import logging

# logger p/ facilitar a depuracao
logger = logging.getLogger(__name__)

class Experimental(commands.Cog):
    """
    cog que gerencia o comando /experimental para ativar ou desativar
    o modo de pensamento em um canal específico
    funciona como um 'interruptor' para a lógica no cog de eventos
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.chats = bot.chats
        self.client = bot.client

    @app_commands.command(name="experimental", description="Ativar/desativar modo de pensamento experimental no chat atual.")
    @app_commands.checks.has_permissions(administrator=True)
    async def experimental_toggle(self, interaction: discord.Interaction):
        """
        alterna o modo experimental para o canal onde o comando foi executado
        ele não cria uma nova sessão de chat, apenas sinaliza para o event handler qual configuração usar
        """
        await interaction.response.defer(ephemeral=True)

        channel_id = str(interaction.channel.id)

        # verifica se o canal já está na lista de chats experimentais
        if channel_id not in self.chats["experimental"]:
            # ativando o modo experimental
            self.chats["experimental"].append(channel_id)
            
            # força a exclusão da sessão de chat atual, se existir
            # assim, na próxima mensagem, o events.py cria uma nova sessão com a configuração correta
            if channel_id in self.chats:
                del self.chats[channel_id]

            embed = discord.Embed(
                title="🧪 Modo Experimental Ativado",
                description="O bot agora usará um modelo com capacidade de 'pensamento' neste canal. As respostas podem incluir um bloco de depuração.",
                color=discord.Color.green()
            )
        else:
            # desativando o modo experimental
            self.chats["experimental"].remove(channel_id)
            
            # exclui a sessão experimental para forçar a criação de uma sessão padrão na próxima mensagem
            if channel_id in self.chats:
                del self.chats[channel_id]
            
            embed = discord.Embed(
                title="✅ Modo Experimental Desativado",
                description="O bot voltará a usar as configurações padrão neste canal.",
                color=discord.Color.red()
            )
        
        # envia a confirmação
        await interaction.followup.send(embed=embed)

    @experimental_toggle.error
    async def on_experimental_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """tratamento de erro para o comando /experimental"""
        if isinstance(error, app_commands.MissingPermissions):
            message = "Você precisa ser um Administrador para usar este comando."
        else:
            logger.error(f"Erro no comando /experimental: {error}", exc_info=True)
            message = "Ocorreu um erro desconhecido ao tentar executar o comando."
            
        if not interaction.response.is_done():
            await interaction.response.send_message(message, ephemeral=True)
        else:
            await interaction.followup.send(message, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Experimental(bot))