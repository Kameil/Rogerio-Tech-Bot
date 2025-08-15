# import discord
# from discord import app_commands
# from discord.ext import commands
# import logging

# # logger p/ facilitar a depuracao
# logger = logging.getLogger(__name__)

# class Experimental(commands.Cog):
#     """
#     cog que gerencia o comando /experimental para ativar ou desativar
#     o modo de pensamento em um canal específico
#     funciona como um 'interruptor' para a lógica no cog de eventos
#     """
#     def __init__(self, bot: commands.Bot):
#         self.bot = bot
#         self.chats = bot.chats
#         self.client = bot.client

#     @app_commands.command(name="experimental", description="Ativar/desativar modo de pensamento experimental no chat atual.")
#     @app_commands.checks.has_permissions(manage_messages=True)
#     async def experimental_toggle(self, interaction: discord.Interaction):
#         """
#         alterna o modo experimental para o canal onde o comando foi executado.
#         """
#         # defer público para que todos vejam a confirmação
#         await interaction.response.defer()

#         channel_id = str(interaction.channel.id)

#         if channel_id not in self.chats["experimental"]:
#             # ativando o modo experimental
#             self.chats["experimental"].append(channel_id)
            
#             if channel_id in self.chats:
#                 del self.chats[channel_id]

#             embed = discord.Embed(
#                 title="🧪 Modo Experimental Ativado",
#                 description=f"O bot agora usará um modelo com capacidade de 'pensamento' neste canal.\n*Ativado por {interaction.user.mention}*",
#                 color=discord.Color.green()
#             )
#         else:
#             # desativando o modo experimental
#             self.chats["experimental"].remove(channel_id)
            
#             if channel_id in self.chats:
#                 del self.chats[channel_id]
            
#             embed = discord.Embed(
#                 title="✅ Modo Experimental Desativado",
#                 description=f"O bot voltará a usar as configurações padrão neste canal.\n*Desativado por {interaction.user.mention}*",
#                 color=discord.Color.red()
#             )
        
#         await interaction.followup.send(embed=embed)

#     @experimental_toggle.error
#     async def on_experimental_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
#         """tratamento de erro para o comando /experimental."""
#         # mensagem de erro atualizada para a nova permissão
#         if isinstance(error, app_commands.MissingPermissions):
#             message = "Você precisa da permissão de 'Gerenciar Mensagens' para usar este comando."
#         else:
#             logger.error(f"Erro no comando /experimental: {error}", exc_info=True)
#             message = "Ocorreu um erro desconhecido ao tentar executar o comando."
            
#         # as mensagens de erro continuam efêmeras para não poluir o chat
#         if not interaction.response.is_done():
#             await interaction.response.send_message(message, ephemeral=True)
#         else:
#             await interaction.followup.send(message, ephemeral=True)


# async def setup(bot):
#     await bot.add_cog(Experimental(bot))