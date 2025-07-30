import discord
from discord import app_commands
from discord.ext import commands
import logging

# logger p/ facilitar a depuracao no futuro
logger = logging.getLogger(__name__)

class Experimental(commands.Cog):
    """
    cog que gerencia o comando /experimental para ativar ou desativar
    o modo de pensamento em um canal específico
    Funciona como um 'interruptor' para a lógica no events.py
    """
    def __init__(self, bot):
        self.bot = bot
        self.chats = bot.chats
        self.client = bot.client

    @app_commands.command(name="experimental", description="Ativar/desativar modo de pensamento experimental no chat atual.")
    @app_commands.checks.has_permissions(administrator=True)
    async def experimental_toggle(self, interaction: discord.Interaction):
        """
        alterna o modo experimental para o canal onde o comando foi executado
        """
        await interaction.response.defer(ephemeral=True)

        channel_id = str(interaction.channel.id)

        if channel_id not in self.chats["experimental"]:
            # ativando modo experimental
            self.chats["experimental"].append(channel_id)
            
            # forçca a exclusão da sessão de chat atual
            # assim, na próxima mensagem, o events.py cria uma nova sessão com a configuração experimental
            if channel_id in self.chats:
                del self.chats[channel_id]

            embed = discord.Embed(
                title="🧪 Modo Experimental Ativado",
                description="O bot agora usará um modelo e configurações experimentais neste canal.",
                color=discord.Color.green()
            )
        else:
            # desativando modo experimental
            self.chats["experimental"].remove(channel_id)
            
            # exclui a sessão experimental p/ forçar a criação de uma sessão padrão na próxima mensagem
            if channel_id in self.chats:
                del self.chats[channel_id]
            
            embed = discord.Embed(
                title="✅ Modo Experimental Desativado",
                description="O bot voltará a usar as configurações padrão neste canal.",
                color=discord.Color.red()
            )
        
        # envia a confirmação como uma mensagem de acompanhamento
        await interaction.followup.send(embed=embed)

    @experimental_toggle.error
    async def on_experimental_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """tratamento de erro para o comando /experimental"""
        message = "Ocorreu um erro desconhecido."
        if isinstance(error, app_commands.MissingPermissions):
            message = "Você precisa ser Administrador para usar este comando."
        else:
            logger.error(f"Erro no comando /experimental: {error}", exc_info=True)
            
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            # fallback caso o defer falhe por algum motivo
            await interaction.response.send_message(message, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Experimental(bot))