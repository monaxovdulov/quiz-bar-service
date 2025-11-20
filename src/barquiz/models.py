from pydantic import BaseModel

class QuestionItem(BaseModel):
    title: str
    value: str

class QuestionsResponse(BaseModel):
    data: list[QuestionItem]