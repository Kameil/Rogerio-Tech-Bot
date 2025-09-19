import asyncio
import logging
import json
from langchain_community.tools import DuckDuckGoSearchResults

logger = logging.getLogger(__name__)

async def pesquisar_na_internet(pesquisa: str) -> str:
    """Faz uma pesquisa na internet; buscar qualquer 

    Args:
        pesquisa: A string de pesquisa a ser realizada. exemplo: "Rogerio Tech Bot"
    Returns:
        Uma string com os resultados da pesquisa.
    """
    search = DuckDuckGoSearchResults(num_results=5, output_format="json")
    results = await search.ainvoke(pesquisa)
    results = json.loads(results)
    organized_string = "\n\n".join(
    f"Título: {item['title']}\nLink: {item['link']}\nResumo: {item['snippet']}" 
    for item in results 
    )
    logger.info(f"Resultados da pesquisa: {results}")
    return organized_string



if __name__ == "__main__":
    result = asyncio.run(pesquisar_na_internet("roblox"))
    print(result)
