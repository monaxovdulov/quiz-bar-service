import logging
import logging.config
import os
import sys
from typing import Any

import structlog

from barquiz.config import settings


def _round_floats(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 2)
    if isinstance(value, dict):
        return {key: _round_floats(sub_value) for key, sub_value in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(_round_floats(item) for item in value)
    if isinstance(value, set):
        return {_round_floats(item) for item in value}
    return value


def float_rounder(_: Any, __: str, event_dict: dict) -> dict:
    """Recursively round all float values in the log payload."""
    return {key: _round_floats(value) for key, value in event_dict.items()}


def _drop_request_id(_: Any, __: str, event_dict: dict) -> dict:
    event_dict.pop("request_id", None)
    return event_dict


def _guess_stage(event: str | None, logger_name: str | None) -> str:
    value = (event or "").lower()
    logger_value = (logger_name or "").lower()
    if value.startswith(("search.", "fetch.", "http.", "ddg.", "network.")) or logger_value.startswith(
        ("httpx", "httpcore", "urllib3")
    ):
        return "web"
    if value.startswith(("ollama.", "quiz_generation.", "ai.")):
        return "ai"
    return "app"


COLOR_RESET = "\x1b[0m"
COLOR_GREEN = "\x1b[32m"
COLOR_YELLOW = "\x1b[33m"
COLOR_RED = "\x1b[31m"
STAGE_COLORS: dict[str, str] = {
    "web": "\x1b[36m",  # cyan
    "ai": "\x1b[35m",  # magenta
    "app": "\x1b[32m",  # green
}
STAGE_TAGS: dict[str, str] = {"web": "[WEB]", "ai": "[AI]", "app": "[APP]"}
KEY_ALIASES: dict[str, str] = {
    "network_latency_download_ms": "dl_ms",
    "network_latency_search_ms": "search_ms",
    "latency_ms": "t_ms",
    "duration_ms": "t_ms",
    "inference_latency_ms": "llm_ms",
    "text_length": "len",
    "urls_count": "urls",
    "pages_used": "pages",
    "status_code": "status",
}


def _colorize(text: str, stage: str, enabled: bool) -> str:
    if not enabled:
        return text
    color = STAGE_COLORS.get(stage)
    if not color:
        return text
    return f"{color}{text}{COLOR_RESET}"


def _colorize_status(status: int, enabled: bool) -> str:
    if not enabled:
        return str(status)

    if status >= 500:
        color = COLOR_RED
    elif status >= 300:
        color = COLOR_YELLOW
    else:
        color = COLOR_GREEN
    return f"{color}{status}{COLOR_RESET}"


def _format_status_value(value: Any, colorize: bool) -> str:
    try:
        status_int = int(value)
    except Exception:
        return _format_value(value)
    return _colorize_status(status_int, colorize)


def _format_value(value: Any) -> str:
    if isinstance(value, str):
        return f"'{value}'"
    if isinstance(value, (int, float, bool)):
        return str(value)
    return repr(value)


def _shorten_keys(event_dict: dict) -> dict:
    return {KEY_ALIASES.get(key, key): value for key, value in event_dict.items()}


def _build_console_renderer(show_request_id: bool, colorize: bool):
    def renderer(_: Any, __: str, event_dict: dict) -> str:
        timestamp = event_dict.pop("timestamp", "")
        level = event_dict.pop("level", "").upper()
        event = event_dict.pop("event", "") or __
        logger_name = event_dict.pop("logger", None)
        exc_info = event_dict.pop("exception", None) or event_dict.pop("exc_info", None)
        stack_info = event_dict.pop("stack", None) or event_dict.pop("stack_info", None)

        if show_request_id and "request_id" in event_dict:
            request_id = event_dict.pop("request_id")
            if request_id:
                event_dict = {"request_id": request_id, **event_dict}

        stage = _guess_stage(event, logger_name)
        event_display = _colorize(event, stage, colorize)
        stage_tag = STAGE_TAGS.get(stage, "[APP]")
        stage_tag_display = _colorize(stage_tag, stage, colorize)

        event_dict = _shorten_keys(event_dict)

        kv_items: list[str] = []
        for key, value in event_dict.items():
            if key in ("status",):
                kv_items.append(f"{key}={_format_status_value(value, colorize)}")
            else:
                kv_items.append(f"{key}={_format_value(value)}")

        suffix = f" | {' '.join(kv_items)}" if kv_items else ""
        line = f"{timestamp} {stage_tag_display} [{level}] {event_display}{suffix}"

        if stack_info:
            line = f"{line}\n{stack_info}"
        if exc_info:
            line = f"{line}\n{exc_info}"
        return line

    return renderer


def _mute_loggers(*logger_names: str, level: int = logging.WARNING) -> None:
    """Tame noisy third-party loggers without touching handlers."""
    for name in logger_names:
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.propagate = False


def configure_logging() -> None:
    """Configure structlog with dual INFO/DEBUG presentation modes."""
    log_level_name = os.getenv("LOG_LEVEL", settings.LOG_LEVEL).upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
    is_debug_mode = log_level == logging.DEBUG
    timestamp_format = "%H:%M:%S.%f" if is_debug_mode else "%H:%M:%S"
    colorize = sys.stdout.isatty()
    render_json = settings.LOG_FORMAT.lower() == "json"

    renderer = (
        structlog.processors.JSONRenderer()
        if render_json
        else _build_console_renderer(show_request_id=is_debug_mode, colorize=colorize)
    )

    formatter_processors = [
        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
        structlog.processors.TimeStamper(fmt=timestamp_format, utc=False),
    ]

    if not is_debug_mode:
        formatter_processors.append(float_rounder)
        if not render_json:
            formatter_processors.append(_drop_request_id)

    formatter_processors.extend(
        [
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ]
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        cache_logger_on_first_use=True,
    )

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "structlog": {
                    "()": structlog.stdlib.ProcessorFormatter,
                    "processors": formatter_processors,
                    "foreign_pre_chain": [
                        structlog.contextvars.merge_contextvars,
                        structlog.stdlib.add_logger_name,
                        structlog.stdlib.add_log_level,
                    ],
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stdout",
                    "formatter": "structlog",
                }
            },
            "loggers": {
                "uvicorn": {"handlers": ["console"], "level": logging.INFO, "propagate": False},
                "uvicorn.error": {"handlers": ["console"], "level": logging.INFO, "propagate": False},
                "uvicorn.access": {
                    "handlers": ["console"],
                    "level": logging.INFO,
                    "propagate": False,
                },
                "duckduckgo_search": {"handlers": ["console"], "level": logging.WARNING, "propagate": False},
                "duckduckgo_search.DDGS": {"handlers": ["console"], "level": logging.WARNING, "propagate": False},
                "ddgs": {"handlers": ["console"], "level": logging.WARNING, "propagate": False},
                "barquiz": {"handlers": ["console"], "level": logging.INFO, "propagate": False},
            },
            "root": {"handlers": ["console"], "level": log_level},
        }
    )

    _mute_loggers(
        "duckduckgo_search",
        "duckduckgo_search.DDGS",
        "duckduckgo_search.utils",
        "ddgs",
        "ddgs.http_client",
        "ddgs.http_client2",
        "ddgs.base",
        "ddgs.ddgs",
    )

    if is_debug_mode:
        logging.getLogger("httpx").setLevel(logging.DEBUG)
        logging.getLogger("httpcore").setLevel(logging.DEBUG)
        logging.getLogger("asyncio").setLevel(logging.DEBUG)
    else:
        for noisy_logger in (
            "httpx",
            "httpcore",
            "urllib3",
            "asyncio",
            "duckduckgo_search",
            "ddgs",
        ):
            logging.getLogger(noisy_logger).setLevel(logging.WARNING)
