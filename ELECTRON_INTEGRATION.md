# Руководство по интеграции Electron ↔ BarQuiz

В этой заметке описано, как основной процесс Electron должен запускать Python-бэкенд, узнавать динамический порт и обращаться к HTTP-API. Держим всё простым: запускаем сервис, ждём handshake, потом стучимся в `/questions`.

## 1. Жизненный цикл процесса и handshake

* **Команда запуска**: используйте
  `child_process.spawn('uv', ['run', 'python', '-m', 'barquiz.api'], …)`,
  чтобы внутри упакованного приложения использовалась та же среда, которой ожидает бэкенд (управляемая `uv`). Можно заменить `uv` на встроенный исполняемый файл Python, если он активирует ту же среду и тот же entry point.

* **Динамический порт**: установите `PORT=0` (или оставьте пустым) в окружении дочернего процесса, чтобы Uvicorn забиндился на случайный свободный порт. Если нужен фиксированный порт, задайте `PORT=8000` (значение по умолчанию в `settings.PORT`).

* **Handshake**: когда Uvicorn будет готов, он выведет одну строку в STDOUT обычным текстом:
  `SERVER_STARTED_ON_PORT={port}`.
  Читайте поток STDOUT, собирайте чанки как строки и используйте регулярку `/SERVER_STARTED_ON_PORT=(\d+)/`, чтобы обнаружить готовность. Показывайте UI только после того, как регэксп сработал.

* **Остальной STDOUT/STDERR**: всё остальное перенаправляйте в лог Electron для отладки (ошибки Ollama, логи FastAPI и т.п.). Строка handshake — единственное структурированное сообщение.

* **Корректное завершение**: когда приложение Electron закрывается (`app.on('before-quit')` или `app.on('window-all-closed')`), вызовите `child.kill('SIGTERM')`. Также слушайте события `exit`/`error`, чтобы при необходимости перезапустить сервис или сообщить о фатальной ошибке.

## 2. API-справка (`barquiz.api`)

* **Endpoint**: `GET /questions`

* **Query-параметры**:

  * `topic` (опционально, строка). По умолчанию `"барные факты"`, если параметр не передан.

* **Успешный ответ** (`200 OK`): JSON строго соответствующий `QuestionsResponse` (`src/barquiz/models.py`):

  ```json
  {
    "data": [
      { "title": "Что бы ты выбрал...", "value": "короткий ответ" }
    ]
  }
  ```

  `data` всегда содержит 10 объектов `QuestionItem` (FastAPI проверяет схему).

* **Ошибки**:

  * `500 Internal Server Error` — основной режим отказа, если не сработал поиск DuckDuckGo, Ollama отказалась отвечать или генератор бросил исключение.
  * `422 Unprocessable Entity` — ошибка валидации FastAPI (например, `topic` не строка).
  * В рендерере используйте `response.status` для ветвления логики; `500` означает, что стоит показать кнопку «Повторить».

## 3. Настройка окружения для JS-разработчиков

* **Python-рантайм**: установите локально [uv](https://astral.sh/uv) или поставьте Python 3.13 вместе с этим проектом через `uv pip install -e .`. Пример со `spawn` предполагает, что `uv` есть в `PATH`; измените команду, если вы встраиваете Python другим способом.

* **Зависимости**: один раз выполните `uv sync` перед сборкой, чтобы в `.venv` (или кэше uv) оказались FastAPI, Uvicorn и прочие зависимости.

* **Ollama**: бэкенд ходит в `http://localhost:11434` (см. `settings.OLLAMA_HOST`). Убедитесь, что у Никиты установлена Ollama, модель `qwen2.5:7b` скачана и демон запущен до старта оболочки Electron.

## 4. Пример кода в основном процессе (`main.js`)

```js
const { app } = require('electron');
const { spawn } = require('child_process');

let quizProcess;
let quizPort;

function startQuizService() {
  return new Promise((resolve, reject) => {
    const env = {
      ...process.env,
      PORT: process.env.PORT || '0', // запросить случайный порт
    };

    quizProcess = spawn(
      'uv',
      ['run', 'python', '-m', 'barquiz.api'],
      {
        cwd: app.getAppPath(),
        env,
        stdio: ['ignore', 'pipe', 'pipe'],
      },
    );

    const handshakeRegex = /SERVER_STARTED_ON_PORT=(\d+)/;

    quizProcess.stdout.on('data', (buf) => {
      const text = buf.toString();
      console.log('[quiz stdout]', text.trim());
      const match = text.match(handshakeRegex);
      if (match && !quizPort) {
        quizPort = Number(match[1]);
        resolve(quizPort);
      }
    });

    quizProcess.stderr.on('data', (buf) => {
      console.error('[quiz stderr]', buf.toString());
    });

    quizProcess.on('exit', (code) => {
      console.warn('Quiz service exited', code);
      if (!quizPort) {
        reject(new Error(`Quiz service failed before handshake (code ${code})`));
      }
    });

    quizProcess.on('error', reject);
  });
}

async function fetchQuestions(topic = 'барные факты') {
  const response = await fetch(`http://127.0.0.1:${quizPort}/questions?topic=${encodeURIComponent(topic)}`);
  if (!response.ok) {
    throw new Error(`Quiz HTTP ${response.status}`);
  }
  const payload = await response.json();
  return payload.data; // массив объектов { title, value }
}

app.whenReady().then(async () => {
  await startQuizService();
  const round = await fetchQuestions('истории про виски');
  console.log('Received quiz round', round);
  // Здесь продолжаем создание BrowserWindow.
});

app.on('before-quit', () => {
  if (quizProcess && !quizProcess.killed) {
    quizProcess.kill('SIGTERM');
  }
});
```

Замените `fetchQuestions` на свою цепочку IPC-вызовов к Renderer. Ключевые моменты: запуск через `uv`, ожидание строки `SERVER_STARTED_ON_PORT=…` и обязательное завершение дочернего процесса при выходе приложения.
