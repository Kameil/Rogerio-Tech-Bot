from discord.ext import commands
from discord import app_commands

import discord

from google import genai
from google.genai import types

from typing import List
from config import api_key


class Imitar(commands.Cog):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.client = genai.Client(api_key=api_key)
        self.chats = bot.chats

    async def _pegarMensagensParaTreino(self, inter: discord.Interaction, user: discord.User, mpc: int) -> List[List[str]]:
        messages = []

        for channel in inter.guild.text_channels:
            bot_permissions = channel.permissions_for(inter.guild.me)
            if not bot_permissions.read_message_history:
                continue

            async for message in channel.history(limit=mpc):
                if message.author == user and message.reference:
                    try:
                        reference_message = await channel.fetch_message(message.reference.message_id)
                    except (discord.NotFound, discord.HTTPException):
                        continue  # mensagem apagada ou inacessível

                    # Checar se ambas mensagens têm conteúdo visível
                    if reference_message.content.strip() and message.content.strip():
                        messages.append([reference_message.content, message.content])
        return messages
    
    # Treinar ai taligado
    async def _TuneDataset(self, messages: List[List[str]],user: discord.User, model = 'models/gemini-1.5-flash-001-tuning') :
        training_dataset = types.TuningDataset(
        # treinar com as mensagens la com m[0] sendo a referencia e m[1] sendo a resposta do user q nois quer imitar
        examples=[
            types.TuningExample(
                text_input=f'{m[0]}',
                output=f'{m[1]}',
            )
            for m in messages
        ],
        )
        tuning_job = await self.client.aio.tunings.tune(
            base_model=model,
            training_dataset=training_dataset,
            config=types.CreateTuningJobConfig(
        epoch_count=8,
        tuned_model_display_name=f'{user.id}',
        batch_size=4
    ),
        )
        return tuning_job
    async def _gettunningJob(self, tunning_job_name):
        tuning_job = await self.client.aio.tunings.get(name=tunning_job_name)
        print(tuning_job)
        import asyncio

        running_states = set(
            [
                'JOB_STATE_PENDING',
                'JOB_STATE_RUNNING',
            ]
        )

        while tuning_job.state in running_states:
            print(tuning_job.state)
            tuning_job = await self.client.aio.tunings.get(name=tuning_job.name)
            await asyncio.sleep(10)
        return tuning_job

    @app_commands.command(name="imitar", description="Imita uma pessoa perfeitamente.")
    async def imitar(self, inter: discord.Interaction, user: discord.User, prompt: str, mpc: int = 100):
        await inter.response.defer()
        """Imita uma pessoa perfeitamente."""
        # Verifica se o comando foi executado em um servidor
        if isinstance(inter.channel, discord.DMChannel):
            return await inter.response.send_message("Esse comando só pode ser executado em um servidor.")

        # Verifica se o usuário é um bot
        if user.bot:
            return await inter.response.send_message("Não posso imitar bots.")

        # Verifica se o usuário é o próprio bot
        if user == self.bot.user:
            return await inter.response.send_message("Não posso me imitar.")
        try:
            embed = discord.Embed(description="Pegando mensagens do usario...", color=discord.Color.blue())
            await inter.edit_original_response(embed=embed)
            messages = await self._pegarMensagensParaTreino(inter, user, mpc)
            embed = discord.Embed(description="Treinando Modelo...", color=discord.Color.blue())
            await inter.edit_original_response(embed=embed)
            tuning_job = await self._TuneDataset(messages, user)
            print(tuning_job)
            embed = discord.Embed(description="Renderizando modelo....", color=discord.Color.orange())
            await inter.edit_original_response(embed=embed)
            tuning_job = await self._gettunningJob(tuning_job.name)
            print(tuning_job)
        

            self.chats[str(inter.channel.id)] = self.client.aio.chats.create(
                model=tuning_job.tuned_model.endpoint,
                config=types.GenerateContentConfig(
                    max_output_tokens=1000,
                ),
            )

            embed = discord.Embed(
                title="Modelo Treinado com Sucesso!",
                description=f"Modelo treinado com sucesso! Agora posso imitar o {user.name}.\n\nPrompt: {prompt}",
                color=discord.Color.green(),
            )
            await inter.edit_original_response(embed=embed)
        except Exception as e:
            embed = discord.Embed(title="Ocorreu Um Erro!", description=str(e), color=discord.Color.red())
            await inter.followup.send(embed=embed)



async def setup(bot):
    await bot.add_cog(Imitar(bot))