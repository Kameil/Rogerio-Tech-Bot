from discord.ext import commands
from discord import app_commands

import discord

from google import genai
from google.genai import types

from config import api_key
import mimetypes

import io

class Imaginar(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.client: genai.Client = bot.client
        self.MODEL = "gemini-2.0-flash-exp-image-generation"



    @app_commands.command(name="imaginar", description="use sua imaginacao.")
    async def imaginar(self, inter: discord.Interaction, prompt: str):
        await inter.response.defer()

        contents = [
            types.Content(
                parts=[
                    types.Part.from_text(text="gere uma imagem com base no prompt abaixo"),
                    types.Part.from_text(text=prompt),
                ],
            ),
        ]
        generation_config = types.GenerateContentConfig(
            response_modalities=[
                "image",
                "text"
            ],
            response_mime_type="text/plain",
        )
        try:
            response = await self.client.aio.models.generate_content(
                contents=contents,
                config=generation_config,
                model=self.MODEL
            )
            if response.candidates and response.candidates[0].content.parts[0].inline_data:
                inline_data = response.candidates[0].content.parts[0].inline_data
                file_extension = mimetypes.guess_extension(inline_data.mime_type)
                file_data = inline_data.data

                file = discord.File(
                    io.BytesIO(file_data),
                    filename=f"rogerio-image{file_extension}"
                )
                await inter.followup.send(
                    content=inter.user.mention,
                    file=file,
                )
            else:
                await inter.followup.send(
                    content=response.text,

                )
        except Exception as e:
            embed = discord.Embed(title="Erro", description="```py\n" + str(e) + "\n```", color=discord.Color.red())
            embed.set_footer(text="Suporte: https://discord.gg/XZH28BJV")
            await inter.followup.send(embed=embed)



async def setup(bot):
    await bot.add_cog(Imaginar(bot))