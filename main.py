import discord
from discord.ext import commands
import httpx
import os
from google import genai
from google.genai import types
from config import api_key, token
from monitoramento import Tokens

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

chats = {}

bot = commands.Bot(
    command_prefix='r!',
    help_command=None,
    intents=discord.Intents.all()
)

bot.chats = chats
bot.model = MODEL_NAME
bot.generation_config = GENERATION_CONFIG
bot.httpclient = httpx.AsyncClient()
bot.client = genai_client
bot.tokens_monitor = Tokens()

@bot.event
async def on_ready():
    from time import sleep
    for file in os.listdir("cogs"):
        if file.endswith(".py"):
            await bot.load_extension(f"cogs.{file[:-3]}")
    
    synced_commands = await bot.tree.sync()
    sleep(0.3)
    print("=== Inicialização do Rogerio Tech ===")
    sleep(0.5)
    print(f"Comandos sincronizados: {len(synced_commands)}")
    sleep(0.5)
    print(f"Nome do bot: {bot.user.name}")
    sleep(0.5)
    print(f"ID do bot: {bot.user.id}")
    sleep(0.5)
    print(f"Prefixo configurado: {bot.command_prefix}")
    sleep(0.5)
    print(f"Modelo de IA: {bot.model}")
    sleep(0.5)
    print("\033[32mBot está online e pronto para uso!\033[0m")
    print("===================================")

bot.run(token=token)