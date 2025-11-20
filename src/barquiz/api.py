import uvicorn
import logging
from barquiz.config import settings
from fastapi import FastAPI, HTTPException
from barquiz.core.generator import generate_round_questions
from barquiz.models import QuestionsResponse

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

def start():
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)

if __name__ == "__main__":
    start()