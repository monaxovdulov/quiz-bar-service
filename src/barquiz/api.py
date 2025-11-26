import asyncio
from time import perf_counter
from uuid import uuid4

import uvicorn
import structlog
from fastapi import FastAPI, HTTPException, Request
from barquiz.config import settings
from barquiz.core.generator import gather_quiz_context, generate_round_questions
from barquiz.models import DataGatheringResult, QuestionsResponse
from barquiz.logging_config import configure_logging

from structlog.contextvars import bind_contextvars, unbind_contextvars

configure_logging()
logger = structlog.get_logger("barquiz.api")

app = FastAPI(title="BarQuiz AI Service")


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id", str(uuid4()))
    bind_contextvars(request_id=request_id, path=request.url.path, method=request.method)
    started = perf_counter()

    try:
        response = await call_next(request)
        duration_ms = (perf_counter() - started) * 1000
        logger.info(
            "request.completed",
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        return response
    except HTTPException as http_exc:
        duration_ms = (perf_counter() - started) * 1000
        logger.warning(
            "request.http_error",
            status_code=http_exc.status_code,
            duration_ms=duration_ms,
        )
        raise
    except Exception:
        duration_ms = (perf_counter() - started) * 1000
        logger.exception("request.failed", status_code=500, duration_ms=duration_ms)
        raise
    finally:
        unbind_contextvars("request_id", "path", "method")


@app.get("/questions", response_model=QuestionsResponse)
async def get_questions(topic: str = "барные факты"):
    try:
        questions = await generate_round_questions(topic)
        if not questions:
            raise HTTPException(status_code=503, detail="Could not generate questions for the topic")
        return {"data": questions}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error generating questions")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/debug/search", response_model=DataGatheringResult)
async def debug_search(topic: str = "барные факты"):
    logger.info("request.received", path="/debug/search", topic=topic)
    try:
        result, _ = await gather_quiz_context(topic)
        if not result:
            raise HTTPException(status_code=404, detail="No search results")
        return result
    except asyncio.TimeoutError:
        logger.warning("debug.search_timeout", topic=topic, timeout_s=5)
        raise HTTPException(status_code=504, detail="Search timed out")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("debug.search_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


def start():
    # Keep our structlog setup; prevent uvicorn from overriding logging configuration.
    uvicorn.run(app, host="127.0.0.1", port=settings.PORT, log_config=None)

if __name__ == "__main__":
    start()
