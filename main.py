import google.generativeai as genai

from config import api_key, token
import discord

import discord
from discord.ext import commands
import os


genai.configure(api_key=api_key)

SYSTEM_INSTRUCTION = """
- Seu nome e Rogerio Tech.
- Voce e um bot de discord.
- Voce e engracado e ironico.

voce ira receber mensagens assim: informacoes: mensagem de "nome do usuario": "conteudo da mensagem" ou informacoes: mensagem de "nome do usuario" ativo agora em: "atividade1", "atividade2", "atividad[...]
Voce deve responder o conteudo da mensagem.
"""

model = genai.GenerativeModel("gemini-2.0-flash", system_instruction=SYSTEM_INSTRUCTION)

generation_config = genai.GenerationConfig(
    max_output_tokens=1000,
    temperature=1.0
)

chats = {}

bot = commands.Bot('!!!!!!!!', help_command=None, intents=discord.Intents.all())

bot.chats = chats
bot.model = model
bot.generation_config = generation_config   



@bot.event
async def on_ready():
    for file in os.listdir("cogs"):
        if file.endswith(".py"):
            await bot.load_extension(f"cogs.{file[:-3]}")
    print("Bot on.")

bot.run(token)
