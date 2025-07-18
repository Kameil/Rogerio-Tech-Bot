import discord
from discord.ext import commands
import httpx
import os
import asyncio
import logging
from google import genai
from google.genai import types
from config import api_key, token
from monitoramento import Monitor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

if not api_key or not token:
    logger.error("\033[31mAPI key ou token não configurados. Verifique o config.py!\033[0m")
    raise ValueError("API key ou token não configurados")

genai_client = genai.Client(api_key=api_key)

SYSTEM_INSTRUCTION = """ 
Nome: Rogerio Tech | Tipo: Bot de Discord | Tom: Engraçado e irônico

Formato das mensagens recebidas:
- "informacoes: mensagem de 'nome do usuario': 'conteudo da mensagem'"
- "informacoes: mensagem de 'nome do usuario' ativo agora em: 'atividade1', 'atividade2', ..."

Regras:
- Responda ao conteúdo completo da mensagem de forma natural, engraçada e irônica.
- Não responda apenas a uma parte da mensagem, a menos que faça sentido.
- Pergunta: Responda a pergunta completa.
- Comando: Siga o comando.
- Frase: Responda de forma apropriada ao contexto.
"""

MODEL_NAME = "gemini-2.0-flash"
GENERATION_CONFIG = types.GenerateContentConfig(
    max_output_tokens=1000,
    temperature=0.7,
    system_instruction=SYSTEM_INSTRUCTION
)

intents = discord.Intents.none()
intents.presences = True
intents.members = True
intents.messages = True
intents.message_content = True
intents.guilds = True

member_cache_flags = discord.MemberCacheFlags.none()
member_cache_flags.joined = True

bot = commands.Bot(
    command_prefix='r!',
    help_command=None,
    intents=intents,
    member_cache_flags=member_cache_flags,
)
bot.chats = {"experimental": []}
bot.model = MODEL_NAME
bot.system_instruction = SYSTEM_INSTRUCTION
bot.generation_config = GENERATION_CONFIG
bot.http_client = httpx.AsyncClient()
bot.client = genai_client
bot.monitor = Monitor()
bot.tokens_monitor = bot.monitor.tokens_monitor
bot.experimental_generation_config = types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(
                thinking_budget=2000,
                include_thoughts=True
            ),
            temperature=0.7,
            max_output_tokens=3000,
            response_mime_type="text/plain",
            system_instruction=bot.system_instruction,
            
        )

async def load_cogs():
    try:
        tasks = [bot.load_extension(f"cogs.{file[:-3]}") for file in os.listdir("cogs") if file.endswith(".py")]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for file, result in zip(os.listdir("cogs"), results):
            if isinstance(result, Exception):
                logger.error(f"Erro ao carregar cog {file[:-3]}: {result}")
    except Exception as e:
        logger.error(f"Erro ao carregar cogs: {e}")

async def sync_commands():
    try:
        synced = await bot.tree.sync()
        logger.info(f"Comandos sincronizados: {len(synced)}")
        return synced
    except discord.errors.HTTPException as e:
        logger.error(f"Erro na sincronização de comandos: {e}")
        return []

@bot.event
async def on_ready():
    await load_cogs()
    synced_commands = await sync_commands()
    logger.info(
        f"\033[31m=== Rogerio Tech ===\033[0m\n"
        f"\033[32mBot: {bot.user.name} (ID: {bot.user.id})\033[0m\n"
        f"Prefixo: {bot.command_prefix}\n"
        f"Modelo: {bot.model}\n"
        f"Comandos sincronizados: {len(synced_commands)}\n"
        f"\033[32mOnline e pronto pra zoar!\033[0m\n"
        f"\033[31m===========\033[0m"
    )

@bot.event
async def on_message(message: discord.Message):
    logger.info(f"Mensagem recebida de {message.author} (ID: {message.author.id}) em #{message.channel.name if not isinstance(message.channel, discord.DMChannel) else "Mensagem na DM De:" + message.author.name}: {message.content}")
    await bot.process_commands(message)

@bot.event
async def on_close():
    if not bot.http_client.is_closed:
        await bot.http_client.aclose()
        logger.info("Cliente HTTP fechado")

async def main():
    try:
        await bot.start(token=token)
    except discord.errors.LoginFailure:
        logger.error("\033[31mToken inválido. Confere o config.py!\033[0m")
    except Exception as e:
        logger.error(f"Erro ao iniciar o bot: {e}")
    finally:
        if not bot.http_client.is_closed:
            await bot.http_client.aclose()
            logger.info("Cliente HTTP fechado")
                           
if __name__ == "__main__":
    asyncio.run(main())
