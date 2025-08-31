import httpx
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)

async def get_url_text(url: str) -> str:
    """Extrai todo o texto de uma página web.

    Args:
        url: A URL da página web.
    """
    client = httpx.AsyncClient()
    response = await client.get(url)
    logger.info(f"Fetching URL: {url} - Status Code: {response.status_code}")
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    return soup.text


if __name__ == "__main__":
    import asyncio
    url = "https://example.com"
    text = asyncio.run(get_url_text(url))
    print(text)