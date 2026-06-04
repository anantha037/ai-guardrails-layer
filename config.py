from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Literal

class Settings(BaseSettings):

    # Groq LLM
    GROQ_API_KEY: str = Field(default="", env="GROQ_API_KEY")
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_TOKENS: int = 1024

    # Redis
    REDIS_URL: str = "redis://localhost:6379"
    REDIS_DB: int = 0

    # Rate limiting
    RATE_LIMIT_REQUESTS: int = 10       # max requests
    RATE_LIMIT_WINDOW_SECONDS: int = 60 # per this many seconds

    # PII
    PII_MASKING_MODE: Literal["replace", "redact"] = "replace"
    # "replace" → [AADHAAR_NUMBER], "redact" → ████████████

    # Toxicity
    TOXICITY_MODEL: str = "martin-ha/toxic-comment-model"
    TOXICITY_THRESHOLD: float = 0.7     # block if score >= this

    # Prompt injection
    INJECTION_BLOCK_ON_PATTERN: bool = True   # block on regex match
    INJECTION_BLOCK_ON_MODEL: bool = False    # no model check for now (CPU constraint)

    # Audit
    AUDIT_LOG_FILE: str = "logs/audit.jsonl"
    AUDIT_LOG_TO_REDIS: bool = True
    AUDIT_REDIS_TTL_SECONDS: int = 86400  # 24 hours

    # App
    APP_ENV: Literal["development", "production"] = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
