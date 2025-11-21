import asyncio
import re
from typing import Final

import httpx
from bs4 import BeautifulSoup, Tag

from barquiz.config import settings

REMOVABLE_TAGS: Final[tuple[str, ...]] = (
    "nav",
    "header",
    "footer",
    "script",
    "style",
    "form",
    "button",
    "iframe",
    "noscript",
)
CONTENT_TAGS: Final[tuple[str, ...]] = ("h1", "h2", "h3", "h4", "h5", "h6", "p", "li")
TITLE_KEYWORDS: Final[tuple[str, ...]] = (
    "бар",
    "барн",
    "коктейл",
    "напит",
    "алкогол",
    "вино",
    "пиво",
    "ресторан",
    "паб",
    "бармен",
)
MIN_PARAGRAPH_LENGTH: Final[int] = 30
MAX_CHUNK_LENGTH: Final[int] = 2000


async def fetch_urls(urls: list[str], topic: str) -> str:
    """Скачивает контент параллельно и возвращает очищенный текст.

    Args:
        urls: Список URL-адресов для загрузки.
        topic: Тема запроса для проверки релевантности.

    Returns:
        Очищенный объединённый текст из успешно загруженных страниц.
    """
    async with httpx.AsyncClient(timeout=settings.FETCH_TIMEOUT, follow_redirects=True) as client:
        tasks = [client.get(url) for url in urls]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

    full_text: list[str] = []
    for response in responses:
        if not isinstance(response, httpx.Response):
            continue

        if response.status_code != httpx.codes.OK:
            continue

        cleaned_text = _extract_readable_text(response.text, topic)
        if cleaned_text:
            full_text.append(cleaned_text[:MAX_CHUNK_LENGTH])

    return "\n\n".join(full_text)


def _extract_readable_text(html: str, topic: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    if not _title_seems_relevant(soup.title.string if soup.title else None, topic):
        return ""

    for tag in soup.find_all(REMOVABLE_TAGS):
        tag.decompose()

    container = _pick_main_container(soup)
    text_parts = []

    for element in container.find_all(CONTENT_TAGS):
        text = element.get_text(" ", strip=True)
        if not text:
            continue

        if element.name == "p" and len(text) < MIN_PARAGRAPH_LENGTH:
            continue

        text_parts.append(text)

    return "\n".join(text_parts).strip()


def _pick_main_container(soup: BeautifulSoup) -> Tag:
    for candidate in (
        soup.find("main"),
        soup.find(attrs={"role": "main"}),
        soup.find("article"),
    ):
        if isinstance(candidate, Tag):
            return candidate

    if soup.body:
        return soup.body

    return soup


def _title_seems_relevant(title: str | None, topic: str) -> bool:
    if not title:
        return False

    lowered_title = title.lower()
    topic_terms = _extract_terms(topic)
    if any(term in lowered_title for term in topic_terms):
        return True

    return any(keyword in lowered_title for keyword in TITLE_KEYWORDS)


def _extract_terms(text: str) -> set[str]:
    tokens = re.findall(r"[A-Za-zА-Яа-яёЁ]+", text.lower())
    return {token for token in tokens if len(token) > 2}
