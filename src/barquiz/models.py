from pydantic import BaseModel


class QuestionItem(BaseModel):
    title: str
    value: str


class QuestionsResponse(BaseModel):
    data: list[QuestionItem]


class DataGatheringResult(BaseModel):
    """Результат этапа поиска и сбора текста."""

    topic: str
    urls: list[str]
    text: str
    text_length: int
    text_preview: str
