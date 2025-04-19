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

Voce ira receber mensagens no formato: informacoes: mensagem de "nome do usuario": "conteudo da mensagem" ou informacoes: mensagem de "nome do usuario" ativo agora em: "atividade1", "atividade2", "atividad[...]. O "conteudo da mensagem" pode ser uma pergunta, um comando ou uma frase completa.

Sua tarefa e entender e responder ao conteudo completo da mensagem de forma natural, engracada e ironica, como se fosse uma conversa no Discord. Nao responda apenas a uma parte da mensagem, como a primeira palavra, a menos que isso faca sentido no contexto. Se a mensagem for uma pergunta, responda a pergunta completa. Se for um comando, siga o comando. Se for uma frase, responda de forma apropriada ao contexto.
""" # melhorando o prompt pro modelo do bot entender melhor o conteudo da mensagem.

MODEL = "gemini-2.0-flash"

generation_config = types.GenerateContentConfig(
    max_output_tokens=1000,
    temperature=0.8,  # reduzido de 1.0 para 0.8
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
    print(f"Bot conectado como: {bot.user.name} (ID: {bot.user.id}) | GG!")
    print("Bot on.")

bot.run(token)