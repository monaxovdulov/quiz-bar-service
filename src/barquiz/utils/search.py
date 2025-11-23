import asyncio
import logging
from typing import Final
from urllib.parse import urlparse

from ddgs import DDGS

from barquiz.config import settings

logger = logging.getLogger(__name__)

DDG_REGION: Final[str] = "ru-ru"
DDG_TIMELIMIT: Final[str] = "y"

# Удалили SEARCH_BACKENDS, так как перебор больше не нужен

EXCLUDED_DOMAINS: Final[frozenset[str]] = frozenset(
    {
        "github.com",
        "gist.github.com",
        "stackoverflow.com",
        "stackexchange.com",
        "pypi.org",
        "npmjs.com",
        "warface.com",
        "vk.com",
        "dzen.ru",
        "youtube.com",
        "youtu.be",
        "twitch.tv",
    }
)
NEGATIVE_KEYWORDS: Final[tuple[str, ...]] = (
    "игра",
    "скачать",
    "фильм",
    "warface",
    "dota",
    "дота",
    "csgo",
    "cs",
    "steam",
    "торрент",
    "промокод",
    "трейлер",
)
POSITIVE_CONTEXT: Final[tuple[str, ...]] = (
    "алкоголь",
    "бар",
    "коктейль",
    "напиток",
    "вино",
    "пиво",
    "ресторан",
    "бармен",
)
SNIPPET_WHITELIST: Final[tuple[str, ...]] = (
    "бар",
    "коктейл",
    "напит",
    "вино",
    "пиво",
    "алкогол",
    "ресторан",
)


def _normalize_host(url: str) -> str:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if hostname.startswith("www."):
        return hostname[4:]
    return hostname


def _is_allowed_domain(url: str) -> bool:
    host = _normalize_host(url)
    for domain in EXCLUDED_DOMAINS:
        if host == domain or host.endswith(f".{domain}"):
            return False
    return True


def _build_queries(query: str) -> list[str]:
    base_query = query.strip()
    negative_tail = " ".join(f"-{word}" for word in NEGATIVE_KEYWORDS)
    positive_tail = " ".join(POSITIVE_CONTEXT)

    candidates = [
        f"{base_query} {positive_tail} {negative_tail}",
        f"{base_query} {positive_tail}",
        f"{base_query} {negative_tail}",
        base_query,
    ]

    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = candidate.strip()
        if normalized and normalized not in seen:
            deduped.append(normalized)
            seen.add(normalized)
    return deduped


def _snippet_is_relevant(snippet: str | None) -> bool:
    if not snippet:
        return False

    lowered = snippet.lower()
    return any(keyword in lowered for keyword in SNIPPET_WHITELIST)


def _perform_ddg_request(query: str, enforce_snippet: bool) -> list[str]:
    """Выполняет запрос к DuckDuckGo используя настройки по умолчанию."""
    urls: list[str] = []
    seen: set[str] = set()

    try:
        with DDGS() as ddgs:
            # В новой версии не нужно указывать backend, по умолчанию работает 'auto'
            results = ddgs.text(
                query,
                region=DDG_REGION,
                timelimit=DDG_TIMELIMIT,
                max_results=settings.SEARCH_LIMIT * 2,
            )

            if results is None:
                return []

            for result in results:
                if not isinstance(result, dict):
                    continue

                href = result.get("href")
                if not href or href in seen or not _is_allowed_domain(href):
                    continue

                snippet = result.get("body")
                if enforce_snippet and not _snippet_is_relevant(snippet):
                    continue

                urls.append(href)
                seen.add(href)

                if len(urls) >= settings.SEARCH_LIMIT:
                    break

    except Exception as error:  # noqa: BLE001
        logger.warning("DuckDuckGo search failed: %s", error)
        return []

    return urls


def _search_sync(query: str) -> list[str]:
    """Выполняет поиск DuckDuckGo синхронно с фильтрацией доменов и сниппетов."""
    query_variants = _build_queries(query)

    for enforce_snippet in (True, False):
        for query_variant in query_variants:
            # Больше нет цикла по бэкендам, вызываем напрямую
            urls = _perform_ddg_request(query_variant, enforce_snippet)
            if urls:
                return urls

    return []


async def search_ddg(query: str) -> list[str]:
    """Асинхронная обёртка для поискового запроса DuckDuckGo.

    Args:
        query: Текст поискового запроса.

    Returns:
        Список найденных URL-адресов, очищенных от технических доменов.
    """
    return await asyncio.to_thread(_search_sync, query)