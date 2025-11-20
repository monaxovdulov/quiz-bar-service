import json
import asyncio
import ollama
from barquiz.config import settings

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

def _query_sync(prompt_text: str) -> list[dict]:
    """
    Синхронный вызов Ollama (блокирующий).
    Выполняется внутри отдельного потока.
    """
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
            }
        )
        
        content = response['message']['content']
        parsed = json.loads(content)
        
        # Проверяем, что структура правильная
        if "data" in parsed and isinstance(parsed["data"], list):
            return parsed["data"]
        elif isinstance(parsed, list):
            # Иногда модель возвращает сразу список без ключа data
            return parsed
            
        return []

    except Exception as e:
        print(f"⚠️ Ошибка Ollama: {e}")
        return []

async def query_llm(prompt_text: str) -> list[dict]:
    """
    Асинхронная обертка.
    """
    # Запускаем синхронную функцию в отдельном потоке
    return await asyncio.to_thread(_query_sync, prompt_text)