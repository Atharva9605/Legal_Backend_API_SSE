# schema.py
from pydantic import BaseModel, Field
from typing import List

class Reflection(BaseModel):
    missing: str = Field(description="Critique of what is missing.")
    superfluous: str = Field(description="Critique of what is superfluous.") 

class AnswerQuestion(BaseModel):
    answer: str = Field(description="~250 word detailed answer to the question.")
    search_queries: List[str] = Field(description="1-3 search queries for research.")
    reflection: Reflection = Field(description="Reflection on initial answer.")
    
class ReviseAnswer(AnswerQuestion):
    references: List[str] = Field(description="Citations motivating your updated answer.")
    references: List[str] = Field(description="Citations motivating your updated answer.")
