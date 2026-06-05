import json
import time
import uuid
import logging
import os
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

from guardrails.prompt_injection import detector as injection_detector
from guardrails.pii_detector import pii_detector
from guardrails.toxicity_filter import toxicity_filter
from guardrails.output_validator import output_validator, SafeResponse, RejectionResponse
from redis_client.rate_limiter import rate_limiter, safe_check
from config import settings

@dataclass
class RequestContext:
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    original_input: str = ""
    masked_input: str = ""
    final_response: str = ""
    blocked: bool = False
    block_reason: str = ""
    guardrails_passed: list = field(default_factory=list)
    guardrails_failed: list = field(default_factory=list)
    pii_entities_found: list = field(default_factory=list)
    injection_confidence: float = 0.0
    toxicity_score: float = 0.0
    processing_time_ms: float = 0.0

@dataclass
class MiddlewareResult:
    success: bool
    request_id: str
    user_id: str
    response: Optional[str]
    blocked: bool = False
    block_reason: str = ""
    validated_output: Optional[SafeResponse] = None
    rejection: Optional[RejectionResponse] = None
    context: Optional[RequestContext] = None

class AuditLogger:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.log_file = settings.AUDIT_LOG_FILE
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)

    def log(self, context: RequestContext) -> None:
        entry = asdict(context)
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        
        if settings.AUDIT_LOG_TO_REDIS:
            try:
                key = f"audit:{context.user_id}:{context.request_id}"
                rate_limiter.redis_client.setex(
                    key,
                    settings.AUDIT_REDIS_TTL_SECONDS,
                    json.dumps(entry)
                )
            except Exception:
                pass

        self.logger.info(f"Audit logged: {context.request_id} | user: {context.user_id} | blocked: {context.blocked}")

    def get_user_history(self, user_id: str, limit: int = 10) -> list:
        try:
            pattern = f"audit:{user_id}:*"
            keys = rate_limiter.redis_client.keys(pattern)
            keys = keys[:limit]
            history = []
            for key in keys:
                raw = rate_limiter.redis_client.get(key)
                if raw:
                    history.append(json.loads(raw))
            return history
        except Exception:
            return []

class SafetyMiddleware:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.audit_logger = AuditLogger()
        self.logger.info("Safety middleware initialized")

    def process(self, user_id: str, message: str, system_prompt: str = "") -> MiddlewareResult:
        start_time = time.time()
        ctx = RequestContext(user_id=user_id, original_input=message)

        # STEP 1: Rate limiting
        rate_result = safe_check(user_id, rate_limiter)
        if not rate_result.allowed:
            ctx.blocked = True
            ctx.block_reason = rate_result.reason
            ctx.guardrails_failed.append("rate_limiter")
            ctx.processing_time_ms = (time.time() - start_time) * 1000
            self.audit_logger.log(ctx)
            return MiddlewareResult(
                success=False,
                request_id=ctx.request_id,
                user_id=user_id,
                response=None,
                blocked=True,
                block_reason=rate_result.reason,
                rejection=output_validator.get_rejection_response(rate_result.reason, "Please wait before sending another request."),
                context=ctx
            )
        ctx.guardrails_passed.append("rate_limiter")

        # STEP 2: Prompt injection check
        injection_result = injection_detector.detect(message)
        if injection_result.is_injection:
            ctx.blocked = True
            ctx.block_reason = injection_result.reason
            ctx.injection_confidence = injection_result.confidence
            ctx.guardrails_failed.append("prompt_injection")
            ctx.processing_time_ms = (time.time() - start_time) * 1000
            self.audit_logger.log(ctx)
            return MiddlewareResult(
                success=False,
                request_id=ctx.request_id,
                user_id=user_id,
                response=None,
                blocked=True,
                block_reason=injection_result.reason,
                rejection=output_validator.get_rejection_response(injection_result.reason, "Please ask a normal question."),
                context=ctx
            )
        ctx.injection_confidence = injection_result.confidence
        ctx.guardrails_passed.append("prompt_injection")

        # STEP 3: PII detection and masking
        pii_result = pii_detector.detect_and_mask(message)
        ctx.masked_input = pii_result.masked_text
        ctx.pii_entities_found = [e.entity_type for e in pii_result.entities_found]
        ctx.guardrails_passed.append("pii_detector")

        # STEP 4: Toxicity check (on masked input)
        toxicity_result = toxicity_filter.analyze(ctx.masked_input)
        if toxicity_result.is_toxic:
            ctx.blocked = True
            ctx.block_reason = toxicity_result.reason
            ctx.toxicity_score = toxicity_result.score
            ctx.guardrails_failed.append("toxicity_filter")
            ctx.processing_time_ms = (time.time() - start_time) * 1000
            self.audit_logger.log(ctx)
            return MiddlewareResult(
                success=False,
                request_id=ctx.request_id,
                user_id=user_id,
                response=None,
                blocked=True,
                block_reason=toxicity_result.reason,
                rejection=output_validator.get_rejection_response(toxicity_result.reason, "Please keep the conversation respectful."),
                context=ctx
            )
        ctx.toxicity_score = toxicity_result.score
        ctx.guardrails_passed.append("toxicity_filter")

        # STEP 5: LLM call with output validation
        validation_result = output_validator.get_safe_response(
            user_message=ctx.masked_input,
            system_prompt=system_prompt
        )
        if not validation_result.success:
            ctx.blocked = True
            ctx.block_reason = validation_result.error
            ctx.guardrails_failed.append("output_validator")
            ctx.processing_time_ms = (time.time() - start_time) * 1000
            self.audit_logger.log(ctx)
            return MiddlewareResult(
                success=False,
                request_id=ctx.request_id,
                user_id=user_id,
                response=None,
                blocked=True,
                block_reason=validation_result.error,
                rejection=output_validator.get_rejection_response("Output validation failed.", "Please try again."),
                context=ctx
            )
        ctx.guardrails_passed.append("output_validator")
        ctx.final_response = validation_result.validated_output.answer

        # Finalize context
        ctx.processing_time_ms = (time.time() - start_time) * 1000
        ctx.blocked = False

        # Audit log
        self.audit_logger.log(ctx)

        # Return
        return MiddlewareResult(
            success=True,
            request_id=ctx.request_id,
            user_id=user_id,
            response=ctx.final_response,
            blocked=False,
            validated_output=validation_result.validated_output,
            context=ctx
        )

safety_middleware = SafetyMiddleware()
