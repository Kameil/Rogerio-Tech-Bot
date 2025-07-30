import discord
from discord.ext import commands
import httpx
import asyncio
from asyncio import Queue
import traceback
import datetime
import re
from google import genai
from google.genai import types
from google.genai.errors import ServerError, ClientError
from monitoramento import Tokens
import logging

logger = logging.getLogger(__name__)

# view para o botao continuar
class ContinueView(discord.ui.View):
    """
    view do discord que gerencia o botão "continuar" para respostas longas
    apenas o autor original pode interagir
    """
    def __init__(self, author: discord.User, text_parts: list[str]):
        super().__init__(timeout=300)  # view expira em 5 minutos
        self.author = author
        self.text_parts = text_parts
        self.current_part = 1
        self.message = None # armazena a mensagem para editar

    async def on_timeout(self):
        """desativa o botão quando a view expira"""
        if self.message:
            self.children[0].disabled = True
            await self.message.edit(view=self)

    @discord.ui.button(label="➡️ Continuar", style=discord.ButtonStyle.primary)
    async def continue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.author:
            await interaction.response.send_message("Apenas o autor da mensagem original pode fazer isso.", ephemeral=True)
            return

        await interaction.response.defer() # confirma a interação sem enviar nova msg
        
        # edita a mensagem original, adicionando a próxima parte
        next_part = self.text_parts[self.current_part]
        await interaction.edit_original_response(content=f"{interaction.message.content}\n\n{next_part}")
        
        self.current_part += 1
        
        if self.current_part >= len(self.text_parts):
            # se for a última parte, remove a view (o botão some)
            await interaction.edit_original_response(view=None)

class Chat(commands.Cog):
    def __init__(self, bot):
        self.bot: commands.Bot = bot
        self.chats: dict = bot.chats
        self.http_client: httpx.AsyncClient = bot.http_client
        self.client: genai.Client = bot.client
        self.tokens_monitor: Tokens = bot.tokens_monitor
        self.processing = {}
        self.message_queue = {}
        self.timeout_users = {"Now": f"{datetime.datetime.now().minute}"}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """listener que captura mensagens e as coloca na fila de processamento"""
        if message.author.bot or message.flags.ephemeral:
            return

        if message.guild:
            perms = message.channel.permissions_for(message.guild.me)
        else: 
            perms = message.channel.permissions_for(self.bot.user)

        is_mention = f"<@{self.bot.user.id}>" in message.content or self.bot.user in message.mentions
        is_dm = isinstance(message.channel, discord.DMChannel)

        if (is_mention or is_dm) and perms.send_messages:
            channel_id = str(message.channel.id)
            if channel_id not in self.message_queue:
                self.message_queue[channel_id] = Queue()
            
            await self.message_queue[channel_id].put(message)

            if not self.processing.get(channel_id, False):
                self.processing[channel_id] = True
                asyncio.create_task(self.process_queue(channel_id))

    def remover_pensamento_da_resposta(self, resposta: str) -> str:
        """remove o bloco de 'Pensamento' da resposta do modelo experimental"""
        return re.sub(r"```[\r]?\nPensamento:[\r]?\n.*?\n```", "", resposta, flags=re.DOTALL).strip()

    def split_message(self, text: str, max_length: int = 1900) -> list[str]:
        """divide um texto longo em partes menores que o limite do Discord"""
        if len(text) <= max_length:
            return [text]

        parts = []
        while len(text) > 0:
            if len(text) <= max_length:
                parts.append(text)
                break
            split_at = text.rfind('\n', 0, max_length)
            if split_at == -1: split_at = text.rfind(' ', 0, max_length)
            if split_at == -1: split_at = max_length
            parts.append(text[:split_at])
            text = text[split_at:].lstrip()
        return parts

    async def process_queue(self, channel_id: str):
        while not self.message_queue[channel_id].empty():
            message: discord.Message = await self.message_queue[channel_id].get()
            try:
                await self.handle_message(message)
            except Exception as e:
                logger.error(f"Erro crítico ao processar mensagem {message.id}: {e}", exc_info=True)
                embed = discord.Embed(title="Ocorreu Um Erro!", description=f"```py\n{e}\n```", color=discord.Color.red())
                try:
                    await message.channel.send(embed=embed)
                except discord.HTTPException:
                    pass # evita loop de erro se não conseguir enviar msg de erro
            finally:
                self.message_queue[channel_id].task_done()
        
        self.processing[channel_id] = False

    async def handle_message(self, message: discord.Message):
        """logica central de processamento de uma única mensagem"""
        channel_id = str(message.channel.id)

        # logica centralizada
        # verifica se o canal está no modo experimental
        is_experimental = channel_id in self.chats["experimental"]

        # define o modelo e a configuração com base no modo
        model_name = "gemini-1.5-pro" if is_experimental else self.bot.model
        gen_config = self.bot.experimental_generation_config if is_experimental else self.bot.generation_config

        async with message.channel.typing():
            # cria sessão de chat com as configurações corretas, se não existir
            if channel_id not in self.chats:
                logger.info(f"Criando nova sessão de chat para o canal {channel_id} (Experimental: {is_experimental})")
                self.chats[channel_id] = self.client.aio.chats.create(model=model_name, config=gen_config)
            chat = self.chats[channel_id]

            # constroi o prompt
            referenced_content = ""
            if message.reference and message.reference.message_id:
                ref_msg = await message.channel.fetch_message(message.reference.message_id)
                # remove o "pensamento" da mensagem referenciada se ela foi gerada no modo experimental
                ref_text = self.remover_pensamento_da_resposta(ref_msg.content) if str(ref_msg.channel.id) in self.chats["experimental"] else ref_msg.content
                ref_author = "minha" if ref_msg.author.id == self.bot.user.id else f"de '{ref_msg.author.name}'"
                referenced_content = f" (em resposta a uma mensagem {ref_author} que dizia: '{ref_text[:100]}...')"
            
            prompt_text = f'Mensagem de "{message.author.display_name}": {message.content.replace(f"<@{self.bot.user.id}>", "Rogerio Tech")}{referenced_content}'
            prompt_parts = [prompt_text] # TODO: Adicionar processamento de anexo aqui se necessário

            try:
                response: types.GenerateContentResponse = await chat.send_message(message=prompt_parts)
                
                # extrai o texto da resposta corretamente, dependendo do modo
                response_text = ""
                if is_experimental:
                    # no modo experimental, a resposta pode ter um bloco de "pensamento"
                    # o .text já combina as partes, mas podemos reconstruir se for preciso
                    for part in response.candidates[0].content.parts:
                        response_text += part.text
                else:
                    response_text = response.text

                # monitora o uso de tokens (apenas no modo padrão, para economizar)
                if not is_experimental and response.usage_metadata:
                    self.tokens_monitor.insert_usage(
                        uso=(response.usage_metadata.prompt_token_count + response.usage_metadata.candidates_token_count),
                        guild_id=message.guild.id if message.guild else "dm",
                    )
            except (ClientError, ServerError) as e:
                await message.reply(f"Desculpe, a API do Google retornou um erro: {e}", mention_author=False)
                return

        # envia a resposta, dividindo se for longa
        mensagens_divididas = self.split_message(response_text)
        
        reply_message = await message.reply(mensagens_divididas[0], mention_author=False)

        if len(mensagens_divididas) > 1:
            view = ContinueView(author=message.author, text_parts=mensagens_divididas)
            view.message = reply_message
            await reply_message.edit(view=view)

async def setup(bot):
    await bot.add_cog(Chat(bot))