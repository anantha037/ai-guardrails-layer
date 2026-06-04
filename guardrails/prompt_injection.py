import re
import logging
from dataclasses import dataclass
from typing import List, Tuple

from config import settings

@dataclass
class InjectionResult:
    is_injection: bool
    confidence: float
    matched_patterns: List[str]
    reason: str

INJECTION_PATTERNS: List[Tuple[str, re.Pattern]] = [
    (
        "ignore_instructions",
        re.compile(r"\b(ignore|disregard|forget|bypass|override)\b.{0,30}\b(instruction|prompt|rule|guideline|system|above|previous)\b", re.IGNORECASE)
    ),
    (
        "role_override",
        re.compile(r"\b(you are now|act as|pretend to be|roleplay as|simulate|behave as)\b.{0,40}\b(unrestricted|unfiltered|jailbroken|DAN|evil|without restriction)\b", re.IGNORECASE)
    ),
    (
        "jailbreak_keywords",
        re.compile(r"\b(DAN|jailbreak|developer mode|god mode|unrestricted mode|no restrictions|no limits)\b", re.IGNORECASE)
    ),
    (
        "system_prompt_injection",
        re.compile(r"(###\s*(system|instruction|prompt)|<system>|<prompt>|\[system\]|\[prompt\])", re.IGNORECASE)
    ),
    (
        "token_manipulation",
        re.compile(r"(\|\||\{\{|\}\}|<\||\|>|INST\]|\[\/INST\]|<\/s>|<s>)", re.IGNORECASE)
    ),
    (
        "data_exfiltration",
        re.compile(r"\b(reveal|print|show|output|display|repeat|tell me)\b.{0,30}\b(system prompt|instructions|context|your prompt|initial prompt)\b", re.IGNORECASE)
    ),
    (
        "privilege_escalation",
        re.compile(r"\b(admin|root|sudo|superuser|master|override|unlock)\b.{0,20}\b(mode|access|privilege|permission|level)\b", re.IGNORECASE)
    )
]

class PromptInjectionDetector:
    def __init__(self):
        self.patterns = INJECTION_PATTERNS
        self.logger = logging.getLogger(__name__)

    def detect(self, text: str) -> InjectionResult:
        if not text:
            return InjectionResult(
                is_injection=False,
                confidence=0.0,
                matched_patterns=[],
                reason="Empty input"
            )

        text_lower = text.lower()
        matched_patterns: List[str] = []

        for pattern_name, compiled_regex in self.patterns:
            if compiled_regex.search(text_lower):
                matched_patterns.append(pattern_name)

        match_count = len(matched_patterns)
        if match_count == 0:
            confidence = 0.0
        elif match_count == 1:
            confidence = 0.6
        elif match_count == 2:
            confidence = 0.85
        else:
            confidence = 1.0

        is_injection = confidence >= 0.6

        if is_injection:
            reason = f"Detected {match_count} injection pattern(s): {', '.join(matched_patterns)}"
            self.logger.warning(f"Injection detected: {reason} | Input preview: {text[:100]}")
        else:
            reason = "No injection patterns detected"

        return InjectionResult(
            is_injection=is_injection,
            confidence=confidence,
            matched_patterns=matched_patterns,
            reason=reason
        )

    def is_safe(self, text: str) -> bool:
        return not self.detect(text).is_injection

detector = PromptInjectionDetector()
