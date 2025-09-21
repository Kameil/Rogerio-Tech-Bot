import httpx
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
}
client = httpx.AsyncClient(timeout=10, verify=False, headers=headers)

async def get_url_text(url: str) -> str:
    """Extrai todo o texto de uma página web.

    Args:
        url: A URL da página web.
    """
    
    response = await client.get(url)
    logger.info(f"Fetching URL: {url} - Status Code: {response.status_code}")
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    return soup.text.strip()


if __name__ == "__main__":
    import asyncio
    url = "https://portal.stf.jus.br/"
    text = asyncio.run(get_url_text(url))
    print(text)