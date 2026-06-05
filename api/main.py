from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import logging
import time

from middleware.safety_middleware import safety_middleware
from redis_client.rate_limiter import rate_limiter
from config import settings

class ChatRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=100, description="Unique user identifier")
    message: str = Field(..., min_length=1, max_length=4000, description="User message")
    system_prompt: str = Field(default="", max_length=2000, description="Optional system prompt")

class ChatResponse(BaseModel):
    success: bool
    request_id: str
    user_id: str
    response: str | None
    blocked: bool
    block_reason: str
    guardrails_passed: list[str]
    guardrails_failed: list[str]
    pii_detected: list[str]
    toxicity_score: float
    injection_confidence: float
    processing_time_ms: float

class UsageResponse(BaseModel):
    user_id: str
    requests_made: int
    requests_limit: int
    requests_remaining: int
    window_seconds: int

class HealthResponse(BaseModel):
    status: str
    redis_connected: bool
    model_loaded: bool
    version: str = "1.0.0"


app = FastAPI(
    title="AI Guardrails Layer",
    description="Production-grade AI safety middleware — prompt injection, PII masking, toxicity filtering, structured outputs",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logger = logging.getLogger(__name__)

@app.on_event("startup")
async def startup_event():
    logger.info("AI Guardrails Layer started")
    logger.info(f"Rate limit: {settings.RATE_LIMIT_REQUESTS} req/{settings.RATE_LIMIT_WINDOW_SECONDS}s")
    logger.info(f"Toxicity threshold: {settings.TOXICITY_THRESHOLD}")
    logger.info(f"PII masking mode: {settings.PII_MASKING_MODE}")


@app.get("/health", response_model=HealthResponse)
def health():
    try:
        rate_limiter.redis_client.ping()
        redis_connected = True
    except Exception:
        redis_connected = False

    return HealthResponse(
        status="ok",
        redis_connected=redis_connected,
        model_loaded=True
    )


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    result = safety_middleware.process(
        user_id=request.user_id,
        message=request.message,
        system_prompt=request.system_prompt
    )
    ctx = result.context
    
    return ChatResponse(
        success=result.success,
        request_id=result.request_id,
        user_id=result.user_id,
        response=result.response,
        blocked=result.blocked,
        block_reason=result.block_reason or "",
        guardrails_passed=ctx.guardrails_passed if ctx else [],
        guardrails_failed=ctx.guardrails_failed if ctx else [],
        pii_detected=ctx.pii_entities_found if ctx else [],
        toxicity_score=ctx.toxicity_score if ctx else 0.0,
        injection_confidence=ctx.injection_confidence if ctx else 0.0,
        processing_time_ms=ctx.processing_time_ms if ctx else 0.0
    )


@app.get("/usage/{user_id}", response_model=UsageResponse)
def usage(user_id: str):
    usage_data = rate_limiter.get_usage(user_id)
    return UsageResponse(**usage_data)


@app.get("/audit/{user_id}")
def audit(user_id: str):
    history = safety_middleware.audit_logger.get_user_history(user_id, limit=20)
    return history


@app.delete("/reset/{user_id}")
def reset(user_id: str):
    rate_limiter.reset_user(user_id)
    return {"message": f"Rate limit reset for user {user_id}"}
