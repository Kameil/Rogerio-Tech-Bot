import asyncio
import logging
from langchain_community.tools import DuckDuckGoSearchResults

logger = logging.getLogger(__name__)

async def pesquisar_na_internet(pesquisa: str) -> str:
    """Faz uma pesquisa na internet; buscar qualquer 

    Args:
        pesquisa: A string de pesquisa a ser realizada. exemplo: "Rogerio Tech Bot"
    Returns:
        Uma string com os resultados da pesquisa.
    """

    search = DuckDuckGoSearchResults()
    results = await search.ainvoke(pesquisa)
    logger.info(f"Resultados da pesquisa: {results}")
    return str(results)
    



if __name__ == "__main__":
    asyncio.run(pesquisar_na_internet("bolsonaro 14 mil"))
