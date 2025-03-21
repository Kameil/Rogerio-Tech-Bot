import discord 
from discord.ext import commands
from discord import app_commands

import httpx
import base64
import fitz
from PIL import Image
from io import BytesIO
import asyncio

class Chat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.model = bot.model
        self.generation_config = bot.generation_config
        self.chats = bot.chats
        
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.author.bot:
            channel_id = str(message.channel.id)
            if f"<@{self.bot.user.id}>" in message.content or isinstance(message.channel, discord.DMChannel) or self.bot.user in message.mentions:
                try:
                    if channel_id not in self.chats:
                        self.chats[channel_id] = self.model.start_chat()
                    chat = self.chats[channel_id]

                    atividades = [atividade.name for atividade in message.author.activities] if not isinstance(message.channel, discord.DMChannel) and message.author.activities else []

                    prompt = f'Informaçoes: Mensagem de "{message.author.name},"'
                    if atividades:
                        prompt += f" ativo agora em: discord(aqui), {', '.join(atividades)}"
                    prompt += f": {message.content.replace(f'<@{self.bot.user.id}>', 'Rogerio Tech')}"

                    async with message.channel.typing():
                        images = []
                        if message.attachments:
                            async with httpx.AsyncClient() as client:
                                for attachment in message.attachments:
                                    if attachment.content_type.startswith("image/"):
                                        response = await client.get(attachment.url)
                                        image = base64.b64encode(response.content).decode("utf-8")
                                        images.append({'mime_type': attachment.content_type, 'data': image})
                                    if attachment.content_type == "application/pdf":
                                        async with httpx.AsyncClient() as client:
                                            for attachment in message.attachments:
                                                response = await client.get(attachment.url)
                                                response.raise_for_status()

                                                pdf_document = fitz.open(stream=response.content, filetype="pdf")
                                                for page in pdf_document:
                                                    pixmap = page.get_pixmap()
                                                    # usando o PIllow para fazer essses paranaue ai
                                                    img = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)

                                                    img_buffer = BytesIO()
                                                    img.save(img_buffer, format="PNG")
                                                    b64_encoded = base64.b64encode(img_buffer.getvalue()).decode('utf-8')
                                                    images.append({'mime_type': 'image/png', 'data': b64_encoded})
                                        

                        if images:
                            prompt = images + [prompt]
                        response = chat.send_message(
                            prompt,
                            stream=True,
                            generation_config=self.generation_config
                        )

                        message_enviada = await message.reply("...", mention_author=False)
                        conteudo = ""  

                        for chunk in response:
                            await asyncio.sleep(0.2)
                            if len(conteudo) + len(chunk.text) > 2000:
                                message_enviada = await message.channel.send("z", mention_author=False)
                                conteudo = ""
                            conteudo += chunk.text  
                            await message_enviada.edit(content=conteudo)
                except Exception as e:
                    embed = discord.Embed(title="Ocorreu Um Erro!", description=f"\n```py\n{str(e)}\n```", color=discord.Color.red())
                    await message.channel.send(embed=embed)

        await self.bot.process_commands(message)

async def setup(bot):
    await bot.add_cog(Chat(bot))