import asyncio
import json
from time import perf_counter

import ollama
import structlog
from barquiz.config import settings

logger = structlog.get_logger(__name__)

# Схема, которую мы просим модель заполнить
JSON_SCHEMA = """
{
  "data": [
    {
      "title": "Текст вопроса",
      "value": "Ответ"
    }
  ]
}
"""

def _query_sync(prompt_text: str) -> tuple[list[dict], float]:
    """
    Синхронный вызов Ollama (блокирующий).
    Выполняется внутри отдельного потока.
    """
    started = perf_counter()
    full_prompt = f"""
    {prompt_text}
    
    IMPORTANT: Output MUST be a valid JSON strictly following this schema:
    {JSON_SCHEMA}
    Do not add any markdown formatting or explanations. Just the JSON.
    """

    try:
        response = ollama.chat(
            model=settings.OLLAMA_MODEL,
            messages=[{
                'role': 'user',
                'content': full_prompt
            }],
            format='json',  # Включаем JSON-режим
            options={
                'temperature': 0.8,
                'num_predict': 2000,
            },
            host=settings.OLLAMA_HOST,
        )
        
        content = response['message']['content']
        parsed = json.loads(content)

        elapsed_ms = (perf_counter() - started) * 1000
        
        # Проверяем, что структура правильная
        if "data" in parsed and isinstance(parsed["data"], list):
            logger.info(
                "ollama.response.completed",
                model=settings.OLLAMA_MODEL,
                inference_latency_ms=elapsed_ms,
                items=len(parsed["data"]),
            )
            return parsed["data"], elapsed_ms
        elif isinstance(parsed, list):
            # Иногда модель возвращает сразу список без ключа data
            logger.info(
                "ollama.response.completed",
                model=settings.OLLAMA_MODEL,
                inference_latency_ms=elapsed_ms,
                items=len(parsed),
            )
            return parsed, elapsed_ms

        logger.warning(
            "ollama.response.empty",
            model=settings.OLLAMA_MODEL,
            inference_latency_ms=elapsed_ms,
        )
        return [], elapsed_ms

    except Exception as e:
        elapsed_ms = (perf_counter() - started) * 1000
        logger.warning(
            "ollama.response.error",
            error=str(e),
            model=settings.OLLAMA_MODEL,
            inference_latency_ms=elapsed_ms,
        )
        return [], elapsed_ms

async def query_llm(prompt_text: str) -> tuple[list[dict], float]:
    """
    Асинхронная обертка.
    """
    # Запускаем синхронную функцию в отдельном потоке
    return await asyncio.to_thread(_query_sync, prompt_text)
