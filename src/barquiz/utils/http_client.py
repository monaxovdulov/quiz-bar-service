import httpx
import asyncio
from bs4 import BeautifulSoup
from barquiz.config import settings

async def fetch_urls(urls: list[str]) -> str:
    """Скачивает контент параллельно и чистит HTML."""
    async with httpx.AsyncClient(timeout=settings.FETCH_TIMEOUT, follow_redirects=True) as client:
        tasks = [client.get(url) for url in urls]
        # return_exceptions=True чтобы один упавший сайт не ломал всё
        responses = await asyncio.gather(*tasks, return_exceptions=True)

    full_text = []
    for response in responses:
        if isinstance(response, httpx.Response) and response.status_code == 200:
            # Простая чистка (можно вынести в отдельную ф-цию если станет сложнее)
            soup = BeautifulSoup(response.text, "html.parser")
            for script in soup(["script", "style", "nav", "footer"]):
                script.extract()
            text = " ".join(soup.get_text().split())
            if text:
                full_text.append(text[:2000]) # Ограничиваем длину одного куска

    return "\n\n".join(full_text)