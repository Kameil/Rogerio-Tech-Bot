import asyncio
import logging
import os

import discord
import httpx
from config import api_key, token
from discord.ext import commands
from google import genai
from google.genai import types
from boas_vindas import welcome

from monitoramento import Monitor

# logging
# gambiara fudida pra tirar o logging de afc pq eu nao tava sabendo como, isso silencia TODAS as lib
logging.basicConfig(
    level=logging.WARNING,  # INFO para WARNING
    format="%(asctime)s [%(levelname)s] [%(filename)s:%(lineno)d] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    filename="rogerio.log",
    filemode="a",
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# validação de chaves de api
if not api_key or not token:
    logger.error("\033[31mAPI key ou token não configurados. Verifique o config.py!\033[0m")
    raise ValueError("API key ou token não configurados")

# inicializa o cliente da api generativa do google.
genai_client = genai.Client(api_key=api_key)

# instrucao do sistema (personalidade)
with open("prompt", "r", encoding="utf-8") as file:
    SYSTEM_INSTRUCTION = file.read()

# importando ferramentass (tools)
from tools.extract_url_text import get_url_text
from tools.internet_search import pesquisar_na_internet

# modelo padrao
MODEL_NAME = "gemini-2.5-flash-lite"
GENERATION_CONFIG = types.GenerateContentConfig(
    max_output_tokens=2000,
    temperature=0.7,
    system_instruction=SYSTEM_INSTRUCTION,
    tools=[get_url_text, pesquisar_na_internet],
)

# # modelo experimental
# EXPERIMENTAL_GENERATION_CONFIG = types.GenerateContentConfig(
#     thinking_config=types.ThinkingConfig(thinking_budget=2000, include_thoughts=True),
#     temperature=0.7,
#     max_output_tokens=2000,
#     response_mime_type="text/plain",
#     system_instruction=SYSTEM_INSTRUCTION,
#     tools=[get_url_text, pesquisar_na_internet],
# )

# intents do discord
intents = discord.Intents.none()
intents.presences = True
intents.members = True
intents.messages = True
intents.message_content = True
intents.guilds = True

# config de cache dos membros
member_cache_flags = discord.MemberCacheFlags.none()
member_cache_flags.joined = True

# inicialização do bot
bot = commands.Bot(
    command_prefix="r!",
    help_command=None,
    intents=intents,
    member_cache_flags=member_cache_flags,
)

# armazena os objetos e configurações no bot para acesso global pelos cogs
# bot.chats = {"experimental": []}
bot.chats = {}
bot.model = MODEL_NAME
bot.system_instruction = SYSTEM_INSTRUCTION
bot.generation_config = GENERATION_CONFIG
#bot.experimental_generation_config = EXPERIMENTAL_GENERATION_CONFIG
bot.http_client = httpx.AsyncClient()
bot.client = genai_client
bot.monitor = Monitor()
bot.tokens_monitor = bot.monitor.tokens_monitor


async def load_cogs():
    try:
        cogs_dir = "cogs"
        for file in os.listdir(cogs_dir):
            if file.endswith(".py") and file not in ["experimental.py", "imaginar.py"]:
                await bot.load_extension(f"{cogs_dir}.{file[:-3]}")
                logger.info(f"Cog '{file[:-3]}' carregado com sucesso.")
    except Exception as e:
        logger.error(f"Erro ao carregar cogs: {e}", exc_info=True)


async def sync_commands():
    try:
        synced = await bot.tree.sync()
        logger.info(f"Comandos de barra sincronizados: {len(synced)}")
        return synced
    except discord.errors.HTTPException as e:
        logger.error(f"Erro na sincronização de comandos: {e}")
        return []


@bot.event
async def on_ready():
    await load_cogs()
    synced_commands = await sync_commands()
    logger.info(
        f"Rogerio Tech\n"
        f"Bot: {bot.user.name} (ID: {bot.user.id})\n"
        f"Prefixo: {bot.command_prefix}\n"
        f"Modelo: {bot.model}\n"
        f"Comandos sincronizados: {len(synced_commands)}\n"
        f"Online e zueiro!\n"
    )


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if (
        f"<@{bot.user.id}>" in message.content
        or bot.user in message.mentions
        or isinstance(message.channel, discord.DMChannel)
    ):
        logger.info(f"Mensagem de {message.author} em #{message.channel}: {message.content}")

    await bot.process_commands(message)

@bot.event
async def on_member_join(member):
    await welcome.handle_member_join(member)

async def main():
    try:
        await bot.start(token=token)
    except discord.errors.LoginFailure:
        logger.error("\033[31mToken inválido. Confere o config.py!\033[0m")
    except Exception as e:
        logger.error(f"Erro ao iniciar o bot: {e}", exc_info=True)
    finally:
        if not bot.is_closed():
            await bot.close()

        if not bot.http_client.is_closed:
            await bot.http_client.aclose()
            logger.info("Cliente HTTP fechado.")


if __name__ == "__main__":
    asyncio.run(main())
