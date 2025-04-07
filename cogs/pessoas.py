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

            self.add_item(discord.ui.TextInput(label="Nome", style=discord.TextStyle.short, placeholder="Digite o nome"))
            self.add_item(discord.ui.TextInput(label="Descrição", style=discord.TextStyle.long, placeholder="Digite a descrição"))


        async def on_submit(self, interaction: discord.Interaction):
            try:
                # pega os valores do modal
                nome: str = self.children[0].value
                descricao: str = self.children[1].value

                # verifica se o nome está vazio
                if not nome or not nome.strip():
                    raise ValueError("O campo 'Nome' não pode estar vazio!")

                #cria o menu de seleção
                select = discord.ui.Select(
                    placeholder="O nome é composto?",
                    options=[
                        discord.SelectOption(label="Sim", value="sim"),
                        discord.SelectOption(label="Não", value="nao")
                    ]
                )

                async def select_callback(interaction_select: discord.Interaction):
                    try:
                        composto = select.values[0]  # pega a escolha do usuário
                        nomes = nome.split()

                        # define o nome exibido com base na escolha
                        if composto == "sim" and len(nomes) >= 2:
                            nome_exibido = f"{nomes[0]} {nomes[1]}"
                        else:
                            nome_exibido = nomes[0]

                        embed = discord.Embed(
                            title="Sucesso!",
                            description=f"**{nome_exibido.capitalize()}** foi adicionado(a) com êxito.",
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

                class Composto(discord.ui.View):
                    @discord.ui.select( # the decorator that lets you specify the properties of the select menu
                        placeholder = "E nome composto?", # the placeholder text that will be displayed if nothing is selected
                        min_values = 1, # the minimum number of values that must be selected by the users
                        max_values = 1, # the maximum number of values that can be selected by the users
                        options = [ # the list of options from which users can choose, a required field
                            discord.SelectOption(
                                label="Vanilla",
                                description="Sim para nome composto ex: Joao victor"
                            ),
                            discord.SelectOption(
                                label="Chocolate",
                                description="Nao para nome nao composto ex: Joao"
                            ),
                        ]
                    )
                    async def select_callback(self, select, interaction: discord.Interaction): # the function called when the user is done selecting options
                        await interaction.response.send_message(f"Awesome! I like {select.values[0]} too!")

                await interaction.response.send_message(
                    "Por favor, escolha se o nome é composto:", 
                    view=Composto(), 
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