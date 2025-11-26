## Observability & Logging

- Logging is powered by `structlog` with contextvars. Configure format via env `LOG_FORMAT=console|json` and level via `LOG_LEVEL`.
- Middleware binds `request_id`, `path`, `method` for every request and logs `request.completed` with `duration_ms`.
- Network timings:
  - `ddg.search.completed`: `network_latency_search_ms`, `urls_found`.
  - `fetch.completed`: `network_latency_download_ms`, `pages_used`, `text_length`.
  - `quiz_generation.completed`: aggregates `network_latency_ms`, per-stage latencies, `inference_latency_ms`.
- Inference timings: `ollama.response.completed` with `inference_latency_ms`, `model`.
- Errors include `stage` in the `event` name (e.g., `request.failed`, `ollama.response.error`) and `exc_info`.
