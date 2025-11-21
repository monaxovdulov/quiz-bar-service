import logging

import uvicorn
from fastapi import FastAPI, HTTPException
from barquiz.config import settings
from barquiz.core.generator import gather_quiz_context, generate_round_questions
from barquiz.models import DataGatheringResult, QuestionsResponse

logger = logging.getLogger(__name__)

app = FastAPI(title="BarQuiz AI Service")


@app.get("/questions", response_model=QuestionsResponse)
async def get_questions(topic: str = "барные факты"):
    try:
        questions = await generate_round_questions(topic)
        if not questions:
            raise HTTPException(status_code=500, detail="Could not generate questions")
        return {"data": questions}
    except Exception as e:
        logger.error(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/debug/search", response_model=DataGatheringResult)
async def debug_search(topic: str = "барные факты"):
    try:
        result = await gather_quiz_context(topic)
        if not result:
            raise HTTPException(status_code=404, detail="No search results")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Debug search error: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


def start():
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)

if __name__ == "__main__":
    start()
