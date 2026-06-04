import instructor
from groq import Groq
from pydantic import BaseModel, Field, field_validator
from dataclasses import dataclass
from typing import Optional, Type, TypeVar
import logging

from config import settings

T = TypeVar("T", bound=BaseModel)

class SafeResponse(BaseModel):
    answer: str = Field(..., description="The main response to the user query")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score between 0 and 1")
    contains_pii: bool = Field(default=False, description="Whether the response contains PII")
    contains_harmful_content: bool = Field(default=False, description="Whether response has harmful content")
    sources: list[str] = Field(default_factory=list, description="Sources referenced if any")

    @field_validator("answer")
    @classmethod
    def validate_answer(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Answer cannot be empty")
        return v

class RejectionResponse(BaseModel):
    rejected: bool = Field(default=True)
    reason: str = Field(..., description="Why the request was rejected")
    suggestion: str = Field(default="", description="What the user could ask instead")


@dataclass
class ValidationResult:
    success: bool
    validated_output: Optional[BaseModel]
    raw_output: str
    error: str = ""
    schema_used: str = ""


class OutputValidator:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.groq_client = Groq(api_key=settings.GROQ_API_KEY)
        self.client = instructor.from_groq(self.groq_client, mode=instructor.Mode.JSON)
        self.model = settings.GROQ_MODEL
        self.logger.info(f"Output validator initialized with model: {self.model}")

    def validate_response(self, user_message: str, system_prompt: str = "", response_schema: Type[T] = SafeResponse) -> ValidationResult:
        if system_prompt:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ]
        else:
            messages = [
                {"role": "user", "content": user_message}
            ]

        validated = self.client.chat.completions.create(
            model=self.model,
            response_model=response_schema,
            messages=messages,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS,
        )

        return ValidationResult(
            success=True,
            validated_output=validated,
            raw_output=str(validated),
            schema_used=response_schema.__name__
        )

    def get_safe_response(self, user_message: str, system_prompt: str = "") -> ValidationResult:
        return self.validate_response(
            user_message=user_message, 
            system_prompt=system_prompt, 
            response_schema=SafeResponse
        )

    def get_rejection_response(self, reason: str, suggestion: str = "") -> RejectionResponse:
        return RejectionResponse(
            rejected=True, 
            reason=reason, 
            suggestion=suggestion
        )


output_validator = OutputValidator()
