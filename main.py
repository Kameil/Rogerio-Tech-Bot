
from google import genai as geneai
from google.genai import types

from config import api_key, token
import discord

import discord
from discord.ext import commands
import os

import httpx

client = geneai.Client(api_key=api_key)

SYSTEM_INSTRUCTION = """
- Seu nome e Rogerio Tech.
- Voce e um bot de discord.
- Voce e engracado e ironico.

voce ira receber mensagens assim: informacoes: mensagem de "nome do usuario": "conteudo da mensagem" ou informacoes: mensagem de "nome do usuario" ativo agora em: "atividade1", "atividade2", "atividad[...]
Voce deve responder o conteudo da mensagem.
"""


MODEL = "gemini-2.0-flash"

generation_config = types.GenerateContentConfig(
    max_output_tokens=1000,
    temperature=1.0,
    system_instruction=SYSTEM_INSTRUCTION

)

chats = {}

bot = commands.Bot('r!', help_command=None, intents=discord.Intents.all())

bot.chats = chats
bot.model = MODEL
bot.generation_config = generation_config 
bot.httpclient = httpx.AsyncClient()
bot.client = client



@bot.event
async def on_ready():
    for file in os.listdir("cogs"):
        if file.endswith(".py"):
            await bot.load_extension(f"cogs.{file[:-3]}")
    sync = await bot.tree.sync()
    print(f"{len(sync)} comandos foram sincronizados.")
    print("Bot on.")

bot.run(token)

