## Отладка поиска и сбора текста

- Функция: `barquiz.core.generator.gather_quiz_context(topic)` возвращает URLs, очищенный текст, длину и превью; не вызывает LLM.
- Эндпоинт: `GET /debug/search?topic=...` проксирует результат `gather_quiz_context` (возвращает 404, если ничего не найдено).
- Формат ответа: `DataGatheringResult` с полями `topic`, `urls`, `text`, `text_length`, `text_preview`.
- Использование: проверяйте качество поиска/парсинга быстро, не дожидаясь генерации вопросов.
