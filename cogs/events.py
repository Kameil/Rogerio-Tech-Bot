import discord 
from discord.ext import commands
from discord import app_commands
import httpx
import base64
import fitz
from PIL import Image
from io import BytesIO
import asyncio
from asyncio import Queue

from google.genai import types

class Chat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.model = bot.model
        self.generation_config = bot.generation_config
        self.chats = bot.chats
        self.httpClient = bot.httpclient
        self.processing = False
        self.message_queue = Queue()
        self.client = bot.client

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.author.bot:
            channel_id = str(message.channel.id)
            if f"<@{self.bot.user.id}>" in message.content or isinstance(message.channel, discord.DMChannel) or self.bot.user in message.mentions:
                await self.message_queue.put(message)
                await asyncio.sleep(0.2)
                await self.process_queue()

    async def process_queue(self):
        while not self.message_queue.empty():
            while self.processing:
                await asyncio.sleep(1)
            
            message = await self.message_queue.get()
            channel_id = str(message.channel.id)

            try:
                self.processing = True

                if channel_id not in self.chats:
                    self.chats[channel_id] = self.client.aio.chats.create(model=self.model, config=self.generation_config)
                chat = self.chats[channel_id]

                atividades = [atividade.name for atividade in message.author.activities] if not isinstance(message.channel, discord.DMChannel) and message.author.activities else []

                prompt = f'Informaçoes: Mensagem de "{message.author.name},"'
                if atividades:
                    prompt += f" ativo agora em: discord(aqui), {', '.join(atividades)}"
                prompt += f": {message.content.replace(f'<@{self.bot.user.id}>', 'Rogerio Tech')}"

                async with message.channel.typing():
                    images = []
                    if message.attachments:
                        for attachment in message.attachments:
                            if attachment.content_type.startswith("image/"):
                                response = await self.httpClient.get(attachment.url)
                                response.raise_for_status()
                                image = types.Part.from_bytes(data=response.content, mime_type=attachment.content_type)
                                images.append(image)
                            if attachment.content_type == "application/pdf":
                                # for attachment in message.attachments:
                                #     response = await self.httpClient.get(attachment.url)
                                #     response.raise_for_status()
                                #     pdf_document = fitz.open(stream=response.content, filetype="pdf")
                                #     for page in pdf_document:
                                #         pixmap = page.get_pixmap()
                                #         img = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
                                #         img_buffer = BytesIO()
                                #         img.save(img_buffer, format="PNG")
                                #         b64_encoded = base64.b64encode(img_buffer.getvalue()).decode('utf-8')
                                #         images.append({'mime_type': 'image/png', 'data': b64_encoded})
                                raise("Leitor de pdf desativado por enquanto.")

                    if images:
                        prompt = [prompt] + images

                    message_enviada = await message.reply("...", mention_author=False)
                    conteudo = ""  

                    async for chunk in await chat.send_message_stream(message=prompt):
                        conteudo += chunk.text  
                        if len(conteudo) >= 1900: # ajuste pq dava erro 429
                            await message_enviada.edit(content=conteudo)
                            conteudo= "" # reseta conteudo
                            await asyncio.sleep(1) 
                        else:
                            await message_enviada.edit(content=conteudo) 
                    if conteudo:  
                        await message_enviada.edit(content=conteudo)

                self.message_queue.task_done()
                self.processing = False
                return

            except Exception as e:
                if isinstance(e, discord.HTTPException) and e.status == 429: # se for 429 espera 2s pra n bugar
                    await asyncio.sleep(2)
                embed = discord.Embed(title="Ocorreu Um Erro!", description=f"\n```py\n{str(e)}\n```", color=discord.Color.red())
                await message.channel.send(embed=embed)
                self.processing = False  

            self.message_queue.task_done()

        await self.bot.process_commands(message)

async def setup(bot):
    await bot.add_cog(Chat(bot))