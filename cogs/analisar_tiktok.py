from discord.ext import commands
from discord import app_commands
import discord

from playwright.async_api import async_playwright
import asyncio
from typing import List, Dict, Optional
import httpx

from google.genai import types
from google import genai

import textwrap

class Analisar_Tiktok(commands.Cog):
    def __init__(self, bot):
        super().__init__()

        self.bot = bot 
        self.client: genai.Client = bot.client
        self.MODEL = bot.model
        self.generation_config = bot.generation_config

    async def pegarImagemENomeDosVideos(self, username: str) -> Optional[List[Dict[str,bytes]]]:
        imagens = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True,
                executable_path="chromium/chrome-linux/chrome", 
                args=[
                    "--disable-gpu",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--single-process",
                    "--no-zygote",
                    "--disable-extensions",
                    "--disable-background-networking",
                    "--disable-sync",
                    "--disable-default-apps",
                    "--disable-translate",
                    "--metrics-recording-only",
                    "--mute-audio",
                    "--no-first-run",
                    "--safebrowsing-disable-auto-update",
                    "--disable-features=site-per-process",
                    "--disable-features=IntentPickerUI",
                    "--no-default-browser-check",
                    "--disable-popup-blocking",
                    "--disable-infobars",
                ])
            context = await browser.new_context(ignore_https_errors=True)

            page = await context.new_page()

            async def block_unwanted(route, request):
                if request.resource_type in ["image", "stylesheet", "font"]:
                    await route.abort()
                else:
                    await route.continue_()

            await page.route("**/*", block_unwanted)

            await page.goto(f"https://www.tiktok.com/@{username}", timeout=60000)

            await asyncio.sleep(10)

            try:
                captcha = page.locator("#captcha_close_button")
                if await captcha.is_visible():
                    await captcha.click()
                    await asyncio.sleep(1)

            except:
                pass 
            spans = page.locator("span")
            count = await spans.count()
            for i in range(count):
                span = spans.nth(i)
                if (await span.inner_text()).strip() == "Reposts":
                    try:
                        await span.click()
                        await asyncio.sleep(1)
                        await page.evaluate("window.scrollBy(0, 2000)")
                        await asyncio.sleep(2)
                        break
                    except:
                        print("It's over")

            pictures = page.locator("picture")
            pic_count = await pictures.count()
            for i in range(pic_count):
                try:
                    img = pictures.nth(i).locator("img")
                    src = await img.get_attribute("src")
                    alt = await img.get_attribute("alt")
                    if src and alt:
                        imagens.append({"src": src, "alt": alt})
                except:
                    continue

            await browser.close()

        session = httpx.AsyncClient()

        num = 1
        print(imagens)
        valid_imagens = []
        for i, imagem in enumerate(imagens):
            src = imagem["src"]
            if "://" in src:
                response = await session.get(src)
                if response.status_code == 200:
                    num += 1
                    print("Salvo")
                    imagem["src"] = response.content
                    valid_imagens.append(imagem)
                    

                    # baixar imagem e pros beta, vamo salvar e na memoria e fodase maximo 10mega so 

                    # data = response.content
                    # mime_type = response.headers['Content-Type']
                    # file_extension = mime_type.split('/')[1]
                    # with open(f"imagens/image_{num}.{file_extension}", "wb") as file:
                    #     num += 1
                    #     file.write(data)
                    # continue

        # os baites ai taligado
        if len(valid_imagens) > 0:
            imagens = valid_imagens
            return imagens
        return None
        
        
        
    

    # pedaco de codigo roubado do /analisar q realmente esta muito baguncado
    def DividirTextoEmPartes(self, texto: str) -> List[str]:
        textos = textwrap.wrap(
            texto,
            width=1900,
            break_long_words=False,
            break_on_hyphens=False
        )
        return textos

    @app_commands.command(name="analisar_tiktok", description="Comando para analisar tiktok de uma pessoa || BETA")
    async def analisar_tiktok(self, inter: discord.Interaction, username: str):
        await inter.response.defer()
        try:
            embed = discord.Embed(title=username, description="Analisando o perfil do tiktok, isso pode demorar um pouco...", color=discord.Color.orange())
            await inter.followup.send(embed=embed)
            videos_imagens = await self.pegarImagemENomeDosVideos(username)
            videos_contents = [
                types.Content(
                    parts=[
                        types.Part.from_text(text="Video: " + video["alt"]),
                        types.Part.from_bytes(
                            data=video["src"],
                            mime_type="image/jpeg",
                        )
                        
                    ],
                    role="user"
                    
                )for video in videos_imagens
            ]
            prompt_content = [
                types.Content(
                    parts=[
                        types.Part.from_text(text=f"Analise o Perfil do tiktok de {username} e seus republicados e de seu veredito:")
                    ],
                    role="user"
                )
            ]
            print([*videos_contents, *prompt_content])
            resposta = await self.client.aio.models.generate_content(
                model=self.MODEL,
                contents=[*videos_contents, *prompt_content],
                config=self.generation_config
            )
            partesparaodiscord = self.DividirTextoEmPartes(texto=resposta.text)

            for parte in partesparaodiscord:
                await inter.followup.send(parte)
        except Exception as e:
            embed = discord.Embed(title="Ocorreu um Erro", description="```py\n" + str(e) + "\n```")
        

async def setup(bot):
    await bot.add_cog(Analisar_Tiktok(bot))
