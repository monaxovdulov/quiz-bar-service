import asyncio
from duckduckgo_search import DDGS
from barquiz.config import settings

def _search_sync(query: str) -> list[str]:
    """
    Внутренняя синхронная функция поиска.
    Работает блокирующе, поэтому вызывать её напрямую в async коде нельзя.
    """
    urls = []
    try:
        # Используем обычный синхронный DDGS
        with DDGS() as ddgs:
            results = ddgs.text(
                keywords=query, 
                max_results=settings.SEARCH_LIMIT
            )
            
            # results - это генератор, нужно пройтись по нему
            if results:
                for r in results:
                    if "href" in r:
                        urls.append(r["href"])
                        
    except Exception as e:
        print(f"⚠️ Ошибка поиска DuckDuckGo: {e}")
        return []

    return urls

async def search_ddg(query: str) -> list[str]:
    """
    Асинхронная обертка.
    Запускает поиск в отдельном потоке, чтобы не блокировать сервер.
    """
    return await asyncio.to_thread(_search_sync, query)