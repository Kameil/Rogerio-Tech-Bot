from httpx import AsyncClient
from config import pastebin_api_key

async def pastebin_send_text(texto: str, client=AsyncClient) -> str:
    "Vamos Economizar Tokens, Enviar os Erros para o Pastebin"
    data = {
        "api_dev_key": pastebin_api_key,
        "api_option": "paste",
        "api_paste_code": texto,
        "api_paste_name": "Rogério Tech", # titulo
        "api_paste_format": "text",
        "api_paste_private": 0, # 0 publico 1 privado
        "api_paste_expire_date": "1H" # some depois de 10minutos

    }

    response = await client.post(url="https://pastebin.com/api/api_post.php", data=data, timeout=10)
    if response.status_code == 200:
        return response.text
    raise(response.text, "Ocorreu um ERROR ao enviar a mensagem para o pastebin")



if __name__ == "__main__":
    import asyncio
    pastebin = asyncio.run(pastebin_send_text(texto="teste", client=AsyncClient()))
    print(pastebin)
    