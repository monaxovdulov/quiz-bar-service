import random

import structlog
from barquiz.config import settings
from barquiz.core.data import TOPICS, VIBES
from barquiz.models import DataGatheringResult, QuestionItem
from barquiz.utils.http_client import fetch_urls
from barquiz.utils.ollama import query_llm
from barquiz.utils.search import search_ddg

logger = structlog.get_logger(__name__)


async def gather_quiz_context(topic: str) -> tuple[DataGatheringResult | None, dict[str, float]]:
    """Ищет источники и собирает очищенный текстовый контекст.

    Args:
        topic: Тема запроса.

    Returns:
        Кортеж из результата с URL-адресами, текстом и метаданными или None, если ничего не найдено,
        а также словаря сетевых метрик.
    """
    timings: dict[str, float] = {}

    logger.info("search.start", topic=topic)
    urls, search_latency = await search_ddg(topic)
    timings["network_latency_search_ms"] = search_latency

    if not urls:
        logger.warning("search.no_urls", topic=topic)
        return None, timings

    logger.info("fetch.start", urls_count=len(urls))
    context_text, download_latency = await fetch_urls(urls, topic)
    timings["network_latency_download_ms"] = download_latency

    if not context_text:
        logger.warning("fetch.no_text", topic=topic, urls_count=len(urls))
        return None, timings

    text_preview = context_text[:500]

    logger.info(
        "gather.completed",
        topic=topic,
        text_length=len(context_text),
        network_latency_search_ms=timings["network_latency_search_ms"],
        network_latency_download_ms=timings["network_latency_download_ms"],
    )

    return DataGatheringResult(
        topic=topic,
        urls=urls,
        text=context_text,
        text_length=len(context_text),
        text_preview=text_preview,
    ), timings


def _build_fallback_context(topic: str) -> str:
    return (
        "Поиск не вернул подходящие тексты. Используй общие знания о барах, напитках и юморе "
        f"по теме \"{topic}\", чтобы придумать вопросы без привязки к конкретным фактам."
    )


def _build_prompt(selected_topic: str, selected_vibe: str, context_text: str) -> str:
    return f"""
Ты — весёлый и немного циничный бармен, ведущий игры "Барный Блеф: Что бы ты выбрал?".

Тема: {selected_topic}.
Вайб: {selected_vibe}.

Твоя задача: придумай 10 оригинальных и забавных барных вопросов в стиле "Would You Rather" для квиза. Для каждого вопроса добавь краткий ответ, факт или шутку, который подойдёт как правильный вариант.

Используй текст ниже только как источник деталей (ингредиенты, предметы интерьера, атмосферу) и превращай их в абсурдные гипотетические ситуации. Если текст выглядит общим, используй свои знания и фантазию.

Запреты:
- Не задавай экзаменационные или фактические вопросы по тексту: никаких адресов, часов работы, лет, цен, имён реальных баров или авторов.
- Не спрашивай "где находится", "когда открыли", "кто владелец". Текст — это специи для образов, а не фактологический тест.
- Не используй реальные названия заведений без преобразования; превращай их в образы или оставляй безымянными.

Правила для каждого вопроса:
1. Длина вопроса не превышает 100 символов.
2. Всегда связан с барами, вечеринками, похмельем, клиентами, напитками или неловкими ситуациями.
3. Если вопрос предлагает выбор, он обязательно содержит фразу "Что бы ты выбрал".
4. Если вопрос описывает ситуацию, обязательно содержит фразу "Что бы ты сделал".
5. Разнообразь формулировки, избегай одинаковых начал. Можно использовать персонажей (пьяный бармен, бывшая, охранник клуба, таксист, сосед, барная стойка, официант, попугай, барменша из 2007 года).
6. {selected_vibe}.

Формат ответа:
{{
  "data": [
    {{"title": "барный вопрос", "value": "краткий ответ"}}
  ]
}}
Строго следуй схеме: внутри "data" должно быть ровно 10 элементов. Верни только валидный JSON без Markdown и пояснений.

Примеры (используй как шаблон, как детали превращаются в абсурдные вопросы):
Текст: "В баре «Пестики» парты вместо столов."
Вопрос: "Что бы ты выбрал: пить текилу за школьной партой под взглядом учителя ИЛИ из лейки на перемене?"
Текст: "Автор рецепта добавил можжевельниковый дым и крыжовник."
Вопрос: "Что бы ты выбрал: вдохнуть дым можжевльника перед тостом ИЛИ бросить крыжовник в пунш как угли?"

Текст для вдохновения:
{context_text[:10000]}
    """


async def generate_round_questions(topic: str | None = None) -> list[QuestionItem]:
    """Формирует вопросы для раунда на основе контекста из поиска и Ollama.

    Args:
        topic: Тема для поиска. Если не передана или пустая, выбирается случайная тема.

    Returns:
        Сформированный список вопросов и ответов для раунда.
    """
    selected_topic: str = topic.strip() if topic and topic.strip() else random.choice(TOPICS)
    selected_vibe: str = random.choice(VIBES).capitalize()

    gather_result, network_timings = await gather_quiz_context(selected_topic)

    prompt_context = _build_fallback_context(selected_topic) if not gather_result else gather_result.text

    prompt = _build_prompt(selected_topic, selected_vibe, prompt_context)

    if not gather_result:
        logger.warning("generator.fallback", topic=selected_topic)

    logger.info("ollama.query.start", model=settings.OLLAMA_MODEL)
    llm_result, inference_latency_ms = await query_llm(prompt)

    network_latency_ms = network_timings.get("network_latency_search_ms", 0.0) + network_timings.get(
        "network_latency_download_ms", 0.0
    )

    logger.info(
        "quiz_generation.completed",
        topic=selected_topic,
        vibe=selected_vibe,
        network_latency_ms=network_latency_ms,
        network_latency_search_ms=network_timings.get("network_latency_search_ms", 0.0),
        network_latency_download_ms=network_timings.get("network_latency_download_ms", 0.0),
        inference_latency_ms=inference_latency_ms,
        urls_count=len(gather_result.urls) if gather_result else 0,
        used_fallback=not gather_result,
    )

    return [QuestionItem(**item) for item in llm_result]
