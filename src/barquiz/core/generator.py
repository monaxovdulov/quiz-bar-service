import logging
import random

from barquiz.core.data import TOPICS, VIBES
from barquiz.models import DataGatheringResult, QuestionItem
from barquiz.utils.http_client import fetch_urls
from barquiz.utils.ollama import query_llm
from barquiz.utils.search import search_ddg

logger = logging.getLogger(__name__)


async def gather_quiz_context(topic: str) -> DataGatheringResult | None:
    """Ищет источники и собирает очищенный текстовый контекст.

    Args:
        topic: Тема запроса.

    Returns:
        Результат с URL-адресами, текстом и метаданными или None, если ничего не найдено.
    """
    logger.info("Searching for topic: %s", topic)
    urls = await search_ddg(topic)

    if not urls:
        logger.warning("No URLs found")
        return None

    logger.info("Fetching %s URLs...", len(urls))
    context_text = await fetch_urls(urls, topic)

    if not context_text:
        logger.warning("No text fetched for topic: %s", topic)
        return None

    text_preview = context_text[:500]

    return DataGatheringResult(
        topic=topic,
        urls=urls,
        text=context_text,
        text_length=len(context_text),
        text_preview=text_preview,
    )


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

    gather_result = await gather_quiz_context(selected_topic)

    prompt_context = _build_fallback_context(selected_topic) if not gather_result else gather_result.text

    prompt = _build_prompt(selected_topic, selected_vibe, prompt_context)

    if not gather_result:
        logger.warning("Falling back to topic-only generation for: %s", selected_topic)

    logger.info("Querying Ollama...")
    result = await query_llm(prompt)

    return [QuestionItem(**item) for item in result]
