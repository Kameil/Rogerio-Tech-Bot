import json
import os
import discord

COUNTER_FILE = "boas_vindas/counter.json"
CHANNEL_ID = 1410710808572198942

os.makedirs(os.path.dirname(COUNTER_FILE), exist_ok=True)

def load_counter():
    if os.path.exists(COUNTER_FILE):
        try:
            with open(COUNTER_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("count", 0)
        except (json.JSONDecodeError, IOError):
            return 0
    return 0

def save_counter(count):
    with open(COUNTER_FILE, "w", encoding="utf-8") as f:
        json.dump({"count": count}, f, indent=4)

counter = load_counter()

async def handle_member_join(member: discord.Member):
    global counter
    
    channel = member.guild.get_channel(CHANNEL_ID)
    if not channel:
        print(f" Canal {CHANNEL_ID} não encontrado no servidor {member.guild.name}")
        return

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
        
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text="Rogério Tech dá as boas-vindas!!! :D")

        await channel.send(content=f"{member.mention}", embed=embed)

    except discord.Forbidden:
        print(f" Erro: O bot não tem permissão de 'Enviar Mensagens' ou 'Links' no canal {CHANNEL_ID}")
    except Exception as e:
        print(f" Erro inesperado ao processar entrada de membro: {e}")
