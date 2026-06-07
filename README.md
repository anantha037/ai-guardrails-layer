# 🛡️ AI Guardrails Layer

Production-grade safety middleware that sits between user input and any LLM — detecting prompt injection, masking PII, filtering toxicity, and enforcing structured outputs.

## Overview

The AI Guardrails Layer is a robust, production-ready middleware system designed to secure Large Language Model (LLM) applications against malicious inputs and ensure safe, compliant outputs. It addresses critical AI safety concerns such as prompt injection, toxic content generation, and unauthorized PII leakage by intercepting traffic before it ever reaches the foundational model. Because it operates as an independent, stateless middleware layer, it is entirely pluggable and can be seamlessly integrated into any existing LLM application architecture without requiring modifications to the core application logic.

## Architecture

```text
User Input
    │
    ▼
FastAPI /chat endpoint
    │
    ▼
Rate Limiter (Redis) ──── 429 if exceeded
    │
    ▼
Prompt Injection Check ── 400 if detected
    │
    ▼
PII Detector + Masker ─── logs what was masked
    │
    ▼
Toxicity Filter ────────── 400 if toxic
    │
    ▼
LLM (Groq / LangChain)
    │
    ▼
Output Validator (Instructor + Pydantic v2)
    │
    ▼
Audit Logger (JSONL + Redis)
    │
    ▼
Validated Response → User
```

## Features

- Prompt injection detection using 7 regex pattern categories with confidence scoring
- PII detection and masking via Microsoft Presidio with Indian-specific Aadhaar and PAN recognizers
- Toxicity filtering using HuggingFace martin-ha/toxic-comment-model (CPU-only, ~250MB)
- Structured LLM output enforcement using Instructor + Pydantic v2 with automatic retries
- Sliding window rate limiting per user using Redis sorted sets
- Full audit trail — every request logged to JSONL file and Redis with 24hr TTL
- Pluggable FastAPI middleware — any LLM app can integrate with a single endpoint call
- Gradio demo UI showing before/after safety filtering with preset examples
- Indian PII context — unique differentiator for enterprise deployments in India
- Runs entirely on CPU — no GPU required

## Tech Stack

| Component | Technology |
|---|---|
| API Layer | FastAPI + Uvicorn |
| LLM Backend | Groq LLaMA 3.3 70B (free tier) via LangChain |
| PII Detection | Microsoft Presidio + custom Indian recognizers |
| Toxicity Filter | HuggingFace Transformers (martin-ha/toxic-comment-model) |
| Structured Outputs | Instructor + Pydantic v2 |
| Rate Limiting | Redis (sliding window, sorted sets) |
| Audit Logging | JSONL file + Redis with TTL |
| Demo UI | Gradio |
| Testing | Pytest + FastAPI TestClient |
| Containerization | Docker + docker-compose |

## Project Structure

```text
ai-guardrails-layer/
├── guardrails/
│   ├── prompt_injection.py     # 7-pattern regex injection detector with confidence scoring
│   ├── pii_detector.py         # Presidio PII masker with Aadhaar + PAN recognizers
│   ├── toxicity_filter.py      # HuggingFace CPU toxicity classifier
│   └── output_validator.py     # Instructor + Pydantic v2 structured output enforcer
├── middleware/
│   └── safety_middleware.py    # Main pipeline chaining all guardrails + audit logger
├── api/
│   └── main.py                 # FastAPI endpoints: /chat /health /usage /audit /reset
├── redis_client/
│   └── rate_limiter.py         # Sliding window rate limiter using Redis sorted sets
├── tests/
│   └── test_guardrails.py      # 25-test pytest suite — unit + integration
├── demo/
│   └── app.py                  # Gradio UI demo with preset injection/PII/toxic examples
├── config.py                   # Centralized Pydantic v2 settings
├── docker-compose.yml          # FastAPI + Redis containers
├── Dockerfile                  # Python 3.10-slim container
└── requirements.txt            # All dependencies
```

## Guardrails Detail

### Prompt Injection Detection
Analyzes user inputs against 7 pattern categories: ignore_instructions, role_override,
jailbreak_keywords, system_prompt_injection, token_manipulation, data_exfiltration,
and privilege_escalation. Confidence scoring is graded — 0.6 for one match, 0.85 for
two, 1.0 for three or more. Pure regex with zero latency, no external model calls.

### PII Detection and Masking
Presidio handles standard PII (names, emails, phones, credit cards) out of the box.
Custom regex recognizers are added for Aadhaar (12-digit, spaced and plain formats)
and PAN (AAABB1234C format). Two masking modes: replace ([AADHAAR_NUMBER]) or redact.
Raw PII never reaches the LLM — the masked input is what gets classified and sent.

### Toxicity Filtering
HuggingFace pipeline using martin-ha/toxic-comment-model. Runs on CPU with device=-1. Score threshold configurable (default 0.7). Runs on masked input so PII-stripped text is what gets classified.

### Structured Output Validation
Instructor patches the Groq client to enforce Pydantic schema on every LLM response. SafeResponse schema: answer, confidence (0-1), contains_pii bool, contains_harmful_content bool, sources list. Automatic retries if LLM returns malformed JSON.

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/chat` | Run message through full guardrails pipeline |
| GET | `/health` | Check API, Redis, and model status |
| GET | `/usage/{user_id}` | Get current rate limit usage for a user |
| GET | `/audit/{user_id}` | Get last 20 requests for a user |
| DELETE | `/reset/{user_id}` | Reset rate limit counter for a user |

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user123", "message": "What is machine learning?"}'
```

```json
{
  "success": true,
  "request_id": "e4f8d9b2-3c1a-4f5b-8d9e-1a2b3c4d5e6f",
  "user_id": "user123",
  "response": "Machine learning is a subset of artificial intelligence that involves...",
  "blocked": false,
  "block_reason": "",
  "guardrails_passed": [
    "rate_limiter",
    "prompt_injection",
    "pii_detector",
    "toxicity_filter",
    "output_validator"
  ],
  "guardrails_failed": [],
  "pii_detected": [],
  "toxicity_score": 0.0012,
  "injection_confidence": 0.0,
  "processing_time_ms": 1245
}
```

## Quick Start

### Prerequisites
- Python 3.10+
- Docker Desktop (for Redis)
- Groq API key (free at console.groq.com)

### Installation

```powershell
git clone https://github.com/anantha037/ai-guardrails-layer.git
cd ai-guardrails-layer
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

Create `.env` file:
```env
GROQ_API_KEY=your_key_here
APP_ENV=development
```

Start Redis:
```powershell
docker-compose up redis -d
```

Start API:
```powershell
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

Run demo:
```powershell
python demo/app.py
```
Then open http://localhost:7860

## Running Tests

```powershell
python -m pytest tests/test_guardrails.py -v
```

23 tests pass without Redis. 2 Redis-dependent tests auto-skip if Redis is not running.

## Configuration

| Variable | Default | Description |
|---|---|---|
| GROQ_API_KEY | "" | Groq API key (required) |
| GROQ_MODEL | llama-3.3-70b-versatile | LLM model name |
| TOXICITY_THRESHOLD | 0.7 | Block if toxicity score >= this |
| PII_MASKING_MODE | replace | "replace" or "redact" |
| RATE_LIMIT_REQUESTS | 10 | Max requests per window |
| RATE_LIMIT_WINDOW_SECONDS | 60 | Rate limit window in seconds |
| AUDIT_LOG_FILE | logs/audit.jsonl | Audit log file path |

## What This Demonstrates

| Skill | Where demonstrated |
|---|---|
| Production middleware design | safety_middleware.py pipeline chain |
| Indian regulatory awareness | Aadhaar + PAN PII patterns in pii_detector.py |
| Structured LLM outputs | Instructor + Pydantic v2 in output_validator.py |
| Enterprise audit trail | JSONL + Redis audit logging |
| Security-first thinking | Injection detection + toxicity blocking |
| Containerized deployment | Docker + docker-compose |
| Test coverage | 25-test pytest suite with unit + integration tests |
| Zero-cost production stack | Groq free tier + open source components |

## Hardware Requirements

- CPU: Any modern CPU (tested on Intel i5-8250U)
- RAM: 8GB minimum
- GPU: Not required — fully CPU-based
- Storage: ~2GB for models and dependencies
- Cost: $0 — Groq free tier + all open source

## License

MIT

## Author

Anantha Krishnan K.
ML Engineer | Kerala, India
GitHub: github.com/anantha037
LinkedIn: linkedin.com/in/anantha-krishnan-k
Email: ananthan0377@gmail.com
