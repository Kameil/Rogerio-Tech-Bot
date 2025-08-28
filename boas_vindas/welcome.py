import json
import os
import discord
from discord.ext import commands

COUNTER_FILE = "boas_vindas/counter.json"

def load_counter():
    if os.path.exists(COUNTER_FILE):
        with open(COUNTER_FILE, "r") as f:
            return json.load(f).get("count", 0)
    return 0

def save_counter(count):
    with open(COUNTER_FILE, "w") as f:
        json.dump({"count": count}, f)

counter = load_counter()

async def handle_member_join(member: discord.Member):
    global counter
    channel = member.guild.get_channel(1410710808572198942)

    if channel:
        try:
            counter += 1
            save_counter(counter)

            embed = discord.Embed(
                title="🎉 EITA, NOVO ZOEIRO NAS ÁREAS 🎉",
                description=(
                    f"Slg, {member.mention}, encostou na moralzinha...\n"
                    f"C é o **{counter}º** ser a entrar aqui :0\n"
                    f"Agora somos **{member.guild.member_count}** loucos no servidor!"
                ),
                color=discord.Color.green()
            )
            embed.set_thumbnail(url=member.avatar.url if member.avatar else discord.Embed.Empty)
            embed.set_footer(text="Rogério Tech dá as boas-vindas!!! :D")

            await channel.send(content=f"{member.mention}", embed=embed)

        except discord.errors.Forbidden:
            print(f"Sem permissão para enviar mensagem no canal {channel.id}")
        except Exception as e:
            print(f"Erro no on_member_join: {e}")
