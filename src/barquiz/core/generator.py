import logging
from barquiz.utils.search import search_ddg
from barquiz.utils.http_client import fetch_urls
from barquiz.utils.ollama import query_llm
from barquiz.models import QuestionItem

logger = logging.getLogger(__name__)

async def generate_round_questions(topic: str = "интересные факты о барах") -> list[QuestionItem]:
    # 1. Поиск
    logger.info(f"Searching for: {topic}")
    urls = await search_ddg(topic) # Обертка над ddgs (можно синхронно, ddgs быстрый)
    
    if not urls:
        logger.warning("No URLs found")
        return []

    # 2. Параллельная загрузка (Главное ускорение)
    logger.info(f"Fetching {len(urls)} URLs...")
    context_text = await fetch_urls(urls)
    
    if not context_text:
        return []

    # 3. Промптинг
    # Промпт вынесен сюда, так как это часть бизнес-логики
    prompt = f"""
    Ты ведущий барного квиза. Используй этот текст:
    {context_text[:10000]} 
    
    Создай 10 интересных вопросов с ответами на основе текста.
    Верни ТОЛЬКО валидный JSON в формате: 
    [{{"title": "вопрос", "value": "ответ"}}]
    """

    # 4. LLM
    logger.info("Querying Ollama...")
    # query_llm должна возвращать распаршенный список словарей или Pydantic объектов
    # Внутри она обрабатывает json.loads и ошибки парсинга
    result = await query_llm(prompt) 
    
    return [QuestionItem(**item) for item in result]