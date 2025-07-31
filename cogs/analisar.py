import asyncio

from discord.ext import commands
from discord import app_commands
import discord
import httpx
import datetime
import textwrap

from google import genai
from google.genai import types as genai_types
from google.genai import errors as genai_errors

from monitoramento import Tokens
from typing import List, Optional
import traceback
import re
import logging

from discord.utils import MISSING
from tools.pastebin import pastebin_send_text as _pastebin_send

class Analisar(commands.Cog):
    def __init__(self, bot):
        self.bot: commands.Bot = bot
        self.model: str = bot.model
        self.generation_config: genai_types.GenerateContentConfig = bot.generation_config # type: ignore
        self.http_client: httpx.AsyncClient = bot.http_client
        self.client: genai.Client = bot.client
        self.tokens_monitor: Tokens = bot.tokens_monitor
        self._mention_re = re.compile(r"<@(\d+)>")
        self.logger = logging.getLogger(__name__)

    @app_commands.command(name="analisar", description="Descobrir se é desenrolado.")
    @app_commands.describe(
        user="Usuário a ser analisado",
        mpc="Mensagens por canal. Padrão: 100",
        prompt="Analise + prompt | nome do usuário + mensagens do usuário"
    )
    async def analisar(self, inter: discord.Interaction, user: discord.Member, prompt: None | str = None, mpc: int = 100):
        # executa a análise inicial
        await self.executar_analise(inter, user, prompt, mpc)

    # analisar
    def _remover_mencao(self, message: str) -> str:
        return self._mention_re.sub(lambda m: f"@<{m.group(1)}!>", message)

    async def _pegar_mensagens(self, inter: discord.Interaction, user: discord.Member, mpc: int) -> List[str]:
        messages = []

        # itera sobre os canais de texto do servidor
        if inter.guild:
            for channel in inter.guild.text_channels :
                bot_permissions = channel.permissions_for(inter.guild.me)
                user_permissions = channel.permissions_for(inter.user) if isinstance(inter.user, discord.Member) else False
                # ignora canais sem permissão de leitura de histórico para o bot ou sem acesso para o usuário
                if not bot_permissions.read_message_history or not user_permissions or not user_permissions.read_messages:
                    continue

                # coleta até 'mpc' mensagens do canal
                async for message in channel.history(limit=mpc):
                    if message.author == user:
                        horario_utc = message.created_at
                        horario_local = horario_utc.astimezone(datetime.timezone(datetime.timedelta(hours=-3)))
                        sanitized_content = self._remover_mencao(message.content)
                        messages.append(
                            f'Mensagem de {user.name} em #{message.channel.name}: "{sanitized_content}" às ' # type: ignore | ignorar o tipo do message.channel pois isso só sera executado em discord.Textchannnel | se por acaso algum erro de tipo, adicionar uma verificacao aí
                            f'{horario_local.strftime("%H:%M:%S %d/%m/%Y")}'
                        )
            
        return messages

    def _criar_o_prompt(self, user: discord.Member, prompt: None | str, messages: list[str]) -> str:
        default_response_prompt = (f"Analise esse usuário com base nas suas mensagens, nome e foto de perfil e diga se ele é "
                         f"desenrolado ou não.")
        params = [
            default_response_prompt if prompt is None else prompt, # prompt do analisar
            f"Nome do usuário: {user.name}",
            f"Mensagens Do Usuario:" + "\n".join(messages),
        ]
        response_prompt = "\n".join(params)
        return response_prompt

    async def _obter_imagem_do_usuario(self, user: discord.Member) -> Optional[bytes]:
        # obtém a imagem de perfil do usuário
        if user.avatar:
            response = await self.http_client.get(user.avatar.url)
            avatar = response.content if response.status_code == 200 else None
            return avatar
        return None

    def _organizar_mensagem(self, textos: List[str]) -> List[str]:
        mensagens_coisadas = []
        for texto in textos:
            self.logger.info(texto)
            coisado = self._remover_mencao(texto)
            self.logger.info(coisado)
            mensagens_coisadas.append(coisado)
        return mensagens_coisadas

    def _contar_os_tokens(self, response: genai_types.GenerateContentResponse, inter: discord.Interaction):
        if response.usage_metadata and inter.guild:
            usage_metadata = response.usage_metadata
            if usage_metadata.total_token_count is not None:
                self.tokens_monitor.insert_usage(
                uso=usage_metadata.total_token_count,

                guild_id = inter.guild.id,
                )
                return 0
            self.logger.info("/analisar - tokens count - total_token_count is None")
            return 1
        self.logger.info("/analisar - tokens count - usage_metadata or inter.guild is None")
        return 1

    async def _send_error(
            self,
            inter: discord.Interaction,
            description: str | None,
            title: str = "Ocorreu um erro!",
            color: int | discord.Color | None = discord.Color.red()
    ):
        embed = discord.Embed(
            title=title,
            description=description if description is not None else "",
            color=color
        )
        embed.set_footer(text="Suporte: https://discord.gg/H77FTb7hwH")
        try:
            await inter.followup.send(embed=embed, ephemeral=False)
        except:
            self.logger.exception("ERROR no comando analisar")


    async def executar_analise(self, inter: discord.Interaction, user: discord.Member, prompt: None | str = None, mpc=100, janalisado=False):
        # verifica se a interação ainda é válida antes de deferir
        if not inter.response.is_done():
            await inter.response.defer()
        #verifica se o comando foi executado em um canal de texto
        if isinstance(inter.channel, discord.DMChannel) and not inter.guild and isinstance(inter.user, discord.Member):
            return await inter.followup.send("Esse comando só pode ser executado em um servidor.", ephemeral=True)


        try:
            guild_name = inter.guild.name if inter.guild else "{guild_name}"
            # lista que armazena as mensagens coletadas
            self.logger.info(f"/analisar - {guild_name} - getting guild messages")
            messages = await self._pegar_mensagens(inter, user, mpc)
            self.logger.info(f"/analisar - {guild_name} - sucess getting guild messages")
            # criar o prompt

            response_prompt: str = self._criar_o_prompt(user, prompt, messages)
            # download da imagem do usuario
            avatar = await self._obter_imagem_do_usuario(user)
            if avatar:
                # envia o prompt e a imagem para o modelo de IA
                self.logger.info(f"/analisar - {guild_name} - getting model response.")
                response = await self.client.aio.models.generate_content(
                    contents=[response_prompt, genai_types.Part.from_bytes(data=avatar, mime_type="image/png")],
                    config=self.generation_config,
                    model=self.model
                )
                if response.text:
                    self.logger.info(f"/analisar - {guild_name} - sucess getting model response.")
                    #contar os tokens
                    self.logger.info(f"/analisar - {guild_name} - computing tokens")
                    self._contar_os_tokens(response, inter)
                    self.logger.info(f"/analisar - {guild_name} - sucess computing tokens")


                    # divide a resposta em partes menores para respeitar o limite do Discord
                    self.logger.info(f"/analisar - {guild_name} - preparing message ")
                    print(response.text)
                    textos = textwrap.wrap(response.text, 1900, break_long_words=False)
                    print(textos)
                    textos_sanatizados: list[str] = self._organizar_mensagem(textos)
                    self.logger.info(f"/analisar - {guild_name} - sucess preparing message " + "-".join(textos_sanatizados))
                    for sanitized_text in textos_sanatizados:
                        await inter.followup.send(
                            sanitized_text,
                            view=Botoes(self.bot, user, prompt, mpc, author=inter.user.id) if sanitized_text == textos_sanatizados[-1] and not janalisado else MISSING,
                            allowed_mentions=discord.AllowedMentions.none()
                        )
                        self.logger.info(f"/analisar - {guild_name} - message sent ")
            else:
                # envia mensagem de erro se a imagem não pôde ser obtida
                await inter.followup.send("Não foi possível obter a imagem do perfil do usuário.")
        
        except discord.HTTPException as e:
            try:
                pastebin = _pastebin_send(texto="\n".join(textos_sanatizados))
            except:
                pastebin = "{pastebin_url}"
            await asyncio.sleep(10)
            await self._send_error(inter, title=f"HTTP {e.status}", description=f"A analise ficou guardada no {pastebin}")
        except genai_errors.ServerError as e:
            self.logger.exception("/analisar - ServerError")
            await self._send_error(
                inter,
                title="ERRO de comunicacao com o servidor",
                description=e.message
            )
        except genai_errors.ClientError as e:
            self.logger.exception("/analisar - ClientError")
            await self._send_error(
                inter,
                title="ERRO de Client",
                description=e.message,
                color=discord.Color.red()
            )
        except genai_errors.APIError as e:
            self.logger.exception("/analisar - APIError")
            await self._send_error(
                inter,
                title="ERRO de api",
                description=e.message,
                color=discord.Color.red()
            )   
        except Exception as e:
            # envia um embed com detalhes do erro, caso ocorra
            error_text = traceback.format_exc()
            embed = discord.Embed(
                title="Ocorreu Um Erro!",
                description=f"Erro ao analisar usuário: \n```py\n{str(error_text)}\n```py\nTipo do erro: {type(e).__name__}",
                color=discord.Color.red()
            )
            embed.set_footer(text="Suporte: https://discord.gg/H77FTb7hwH")
            await inter.followup.send(
                embed=embed,
                view=Botoes(self.bot, user, prompt, mpc, author=inter.user.id)
            )
            if inter.guild:
                self.logger.info(f"Erro ao analisar usuário em: {inter.guild.name}")


async def setup(bot):
    # adiciona o cog ao bot
    await bot.add_cog(Analisar(bot))



class PromptModal(discord.ui.Modal):
        def __init__(self, bot, user, mpc, author, original_prompt):
            super().__init__(title="Novo Prompt para Análise")
            self.bot = bot
            self.user = user
            self.mpc = mpc
            self.author = author
            self.original_prompt = original_prompt
            self.add_item(discord.ui.TextInput(
                label="Novo Prompt",
                style=discord.TextStyle.long,
                placeholder="Digite o novo prompt para análise...",
                required=False
            ))

        async def on_submit(self, interaction: discord.Interaction):
            try:
                # usa o novo prompt se tiver, se não usa o original
                new_prompt = self.children[0].value if self.children[0].value else self.original_prompt # pyright: ignore[reportAttributeAccessIssue]
                # verifica se a interação ainda é válida antes de prosseguir
                if not interaction.response.is_done():
                    await interaction.response.defer()
                await self.bot.get_cog("Analisar").executar_analise(
                    interaction, self.user, new_prompt, self.mpc, janalisado=True
                )
            except Exception as e:
                # garante que a mensagem de erro seja clara e bem formatada
                error_message = f"Erro ao processar o novo prompt: {str(e)}\nTipo do erro: {type(e).__name__}"
                embed = discord.Embed(
                    title="Ocorreu Um Erro!",
                    description=error_message,
                    color=discord.Color.red()
                )
                embed.set_footer(text="Suporte: https://discord.gg/H77FTb7hwH")
                await interaction.followup.send(embed=embed, ephemeral=False)


class Botoes(discord.ui.View):
    def __init__(self, bot, user, prompt, mpc, author=None):
        super().__init__(timeout=60)
        self.bot = bot
        self.user = user
        self.prompt = prompt
        self.mpc = mpc
        self.janalisado = False
        self.author = author

    @discord.ui.button(label="Re:Analisar", style=discord.ButtonStyle.secondary)
    async def analisar(self, interaction: discord.Interaction, button: discord.ui.Button):
        # button nao ta sendo usado ai
        # verifica se o usuário clicando é o autor do comando
        if interaction.user.id != self.author:
            return await interaction.response.send_message(
                "Apenas o usuário que executou o comando pode usar esse botão.",
                ephemeral=True
            )
        if self.janalisado:
            # informa que o usuário já foi analisado
            await interaction.response.send_message("Usuário já analisado.", ephemeral=True)
            return None
        else:
            self.janalisado = True
            # cria um menu de seleção para escolher entre novo prompt ou original
            select = discord.ui.Select(
                placeholder="Usar um novo prompt?",
                min_values=1,
                max_values=1,
                options=[
                    discord.SelectOption(label="Sim", value="sim", description="Usar um novo prompt para análise."),
                    discord.SelectOption(label="Não", value="nao", description="Usar o prompt original.")
                ]
            )

            async def select_callback(interaction: discord.Interaction):
                try:
                    if select.values[0] == "sim":
                        # exibe o modal p/ colocar um novo prompt
                        await interaction.response.send_modal(
                            PromptModal(self.bot, self.user, self.mpc, self.author, self.prompt)
                        )
                    else:
                        # faz a análise com o prompt original
                        if not interaction.response.is_done():
                            await interaction.response.defer()
                        await self.bot.get_cog("Analisar").executar_analise(
                            interaction, self.user, self.prompt, self.mpc, janalisado=True
                        )
                except discord.HTTPException as e:
                    if e.status == 429:
                        await self.bot.get_cog("Analisar")._send_error(
                            title="Erro HTTP",
                            description="Too many request, vá mais devagar."
                        )

                except Exception:
                    error = traceback.format_exc()
                    error_msg = f"```\n{error[len(error) - 1900]}\n```" if len(error) >= 2000 else f"```\n{error}\n```"
                    await self.bot.get_cog("Analisar")._send_error(
                        inter=interaction,
                        description=error_msg
                    )


            select.callback = select_callback
            view = discord.ui.View()
            view.add_item(select)

            await interaction.response.send_message(
                "Deseja usar um novo prompt para a análise?",
                view=view,
                ephemeral=True
            )
            return None