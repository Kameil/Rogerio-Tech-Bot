import httpx
from bs4 import BeautifulSoup


async def get_url_text(url: str) -> str:
    """Extrai todo o texto de uma página web.

    Args:
        url: A URL da página web.
    """
    client = httpx.AsyncClient()
    response = await client.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    return soup.text
