# Electron ↔ BarQuiz Integration Guide

This note explains how the Electron main process should boot the Python backend, detect the dynamic port, and talk to the HTTP API. Keep it simple: spawn the service, wait for the handshake, then hit `/questions`.

## 1. Process Lifecycle & Handshake

- **Spawn command**: use `child_process.spawn('uv', ['run', 'python', '-m', 'barquiz.api'], …)` so the same env that the backend expects (managed by `uv`) is used inside the packaged app. You can swap `uv` for a bundled Python executable as long as it activates the same environment and entry point.
- **Dynamic port**: set `PORT=0` (or leave empty) in the child’s environment to ask Uvicorn to bind to a random free port. If you need a fixed port, set `PORT=8000` (default in `settings.PORT`).
- **Handshake**: once Uvicorn is ready it prints a single line to STDOUT in plain text: `SERVER_STARTED_ON_PORT={port}`. Stroke the STDOUT stream, capture chunks as strings, and use `/SERVER_STARTED_ON_PORT=(\d+)/` to detect readiness. Only show the UI once the regex matches.
- **Other STDOUT/STDERR**: forward everything else to the Electron log for debugging (Ollama errors, FastAPI logs, etc.). The handshake line is the only structured message.
- **Graceful shutdown**: when the Electron app quits (`app.on('before-quit')` or `app.on('window-all-closed')`), call `child.kill('SIGTERM')`. Also listen for `exit`/`error` to restart or report fatal issues.

## 2. API Reference (`barquiz.api`)

- **Endpoint**: `GET /questions`
- **Query params**:
  - `topic` (optional, string). Defaults to `"барные факты"` if omitted.
- **Success response** (`200 OK`): JSON shaped exactly like `QuestionsResponse` (`src/barquiz/models.py`):

  ```json
  {
    "data": [
      { "title": "Что бы ты выбрал...", "value": "короткий ответ" }
    ]
  }
  ```

  `data` always contains 10 `QuestionItem` objects (FastAPI enforces schema).

- **Failures**:
  - `500 Internal Server Error` — main failure mode when DuckDuckGo search fails, Ollama refuses to answer, or the generator raises.
  - `422 Unprocessable Entity` — FastAPI validation error (e.g., non-string `topic`).
  - Use `response.status` to branch in the renderer; `500` means you should show a retry button.

## 3. Environment Setup for JS Devs

- **Python runtime**: install [uv](https://astral.sh/uv) locally or ship a Python 3.12 runtime plus this project installed via `uv pip install -e .`. The spawn example assumes `uv` is on the PATH; change the command if you embed Python differently.
- **Dependencies**: run `uv sync` once before packaging so `.venv` (or uv’s cache) contains FastAPI, Uvicorn, etc.
- **Ollama**: the backend talks to `http://localhost:11434` (see `settings.OLLAMA_HOST`). Make sure Nikita has Ollama installed, the `qwen2.5:7b` model pulled, and the daemon running before he launches the Electron shell.

## 4. Main-Process Example (`main.js`)

```js
const { app } = require('electron');
const { spawn } = require('child_process');

let quizProcess;
let quizPort;

function startQuizService() {
  return new Promise((resolve, reject) => {
    const env = {
      ...process.env,
      PORT: process.env.PORT || '0', // ask for a random port
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
  return payload.data; // array of { title, value }
}

app.whenReady().then(async () => {
  await startQuizService();
  const round = await fetchQuestions('истории про виски');
  console.log('Received quiz round', round);
  // Continue booting BrowserWindow here.
});

app.on('before-quit', () => {
  if (quizProcess && !quizProcess.killed) {
    quizProcess.kill('SIGTERM');
  }
});
```

Swap out `fetchQuestions` with your IPC call chain to Renderer. The key bits are: spawn via `uv`, wait for `SERVER_STARTED_ON_PORT=…`, and always kill the child on exit.
