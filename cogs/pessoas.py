from discord import app_commands
from discord.ext import commands
import discord

class Pessoas(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.model = bot.model
        self.generation_config = bot.generation_config
        self.chats = bot.chats
        self.client = bot.client

    class MyModal(discord.ui.Modal):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)

            self.add_item(discord.ui.TextInput(label="Nome", style=discord.TextStyle.short, placeholder="Digite o nome da pessoa."))
            self.add_item(discord.ui.TextInput(label="Descrição", style=discord.TextStyle.long, placeholder="Digite a descrição da pessoa."))

        async def on_submit(self, interaction: discord.Interaction):
            try:
                # Pega os valores do modal
                nome: str = self.children[0].value
                descricao: str = self.children[1].value

                # Verifica se o nome está vazio
                if not nome or not nome.strip():
                    raise ValueError("'Nome' não pode estar vazio.")

                # Cria o menu de seleção
                select = discord.ui.Select(
                    placeholder="O nome da pessoa é composto?",
                    min_values=1,
                    max_values=1,
                    options=[
                        discord.SelectOption(label="Sim", value="sim", description="Sim, para nome composto. e.g.: João Victor."),
                        discord.SelectOption(label="Não", value="nao", description="Não, para nome não composto e.g.: João.")
                    ]
                )

                async def select_callback(interaction_select: discord.Interaction):
                    try:
                        composto = select.values[0]  # Pega a escolha do usuário
                        nomes = nome.split()

                        # Define o nome exibido com base na escolha
                        if composto == "sim" and len(nomes) >= 2:
                            nome_exibido = f"{nomes[0]} {nomes[1]}"
                        else:
                            nome_exibido = nomes[0]

                        embed = discord.Embed(
                            description=f"Adicionado **{nome_exibido.capitalize()}** com êxito.",
                            color=discord.Color.green()
                        )
                        await interaction_select.response.send_message(embed=embed, ephemeral=True)

                    except Exception as e:
                        embed = discord.Embed(
                            title="Ocorreu Um Erro!",
                            description=f"\n```py\n{str(e)}\n```",
                            color=discord.Color.red()
                        )
                        await interaction_select.response.send_message(embed=embed, ephemeral=False)

                select.callback = select_callback
                view = discord.ui.View()
                view.add_item(select)

                await interaction.response.send_message(
                    "Por favor, escolha se o nome é composto:", 
                    view=view, 
                    ephemeral=True
                )

            except Exception as e:
                embed = discord.Embed(
                    title="Ocorreu Um Erro!",
                    description=f"\n```py\n{str(e)}\n```",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=False)

    @app_commands.command(name="pessoas", description="Adiciona uma pessoa anonimamente")
    async def pessoas_beta(self, inter: discord.Interaction):
        await inter.response.send_modal(self.MyModal(title="Adicionar pessoa(s)..."))

async def setup(bot):
    await bot.add_cog(Pessoas(bot))