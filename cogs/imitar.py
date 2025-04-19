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
        epoch_count=5, tuned_model_display_name=f'{user.id}'
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
            messages = await self._pegarMensagensParaTreino(inter, user, mpc)
            tuning_job = await self._TuneDataset(messages, user)
            print(tuning_job)
            tuning_job = await self._gettunningJob(tuning_job.name)
            print(tuning_job)
            
            
            response = await self.client.aio.models.generate_content(
            model=tuning_job.tuned_model.endpoint,
            contents=[
                types.Part.from_text(prompt),
                types.Part.from_text(f"Nome do usuario: {user.name}"),
            ],
                )       
            await inter.followup.send(response.text + f" \n-# mensagens usadas para treino: {len(messages)}")
        except Exception as e:
            embed = discord.Embed(title="Ocorreu Um Erro!", description=str(e), color=discord.Color.red())
            await inter.followup.send(embed=embed)



async def setup(bot):
    await bot.add_cog(Imitar(bot))