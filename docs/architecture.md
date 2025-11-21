## Архитектура сервиса

- API: `src/barquiz/api.py`. `/questions` уходит в `generate_round_questions`, `/debug/search` возвращает только поиск+сбор текста через `gather_quiz_context`.
- Генератор: `src/barquiz/core/generator.py` выбирает тему/вайб, ищет DuckDuckGo (`utils/search.py`), грузит контент (`utils/http_client.py`), собирает промпт и зовёт Ollama (`utils/ollama.py`).
- Data gathering: `gather_quiz_context` собирает URL, очищенный текст, длину и превью; переиспользуется генератором и debug-эндпоинтом.
- Модели ответа: `QuestionItem`, `QuestionsResponse`, `DataGatheringResult` описаны в `src/barquiz/models.py`.
- Данные для промпта (темы/вайбы) лежат в `src/barquiz/core/data.py`, чтобы не хардкодить тексты.
