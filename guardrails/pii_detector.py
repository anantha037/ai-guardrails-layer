from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig
from dataclasses import dataclass, field
from typing import List, Dict
import logging
from config import settings

@dataclass
class PIIEntity:
    entity_type: str
    original_value: str
    start: int
    end: int
    score: float

@dataclass
class PIIResult:
    has_pii: bool
    masked_text: str
    entities_found: List[PIIEntity] = field(default_factory=list)
    entity_summary: Dict[str, int] = field(default_factory=dict)
    reason: str = ""

def create_aadhaar_recognizer() -> PatternRecognizer:
    patterns = [
        Pattern(name="aadhaar_spaced", regex=r"\b[2-9]{1}[0-9]{3}\s[0-9]{4}\s[0-9]{4}\b", score=0.9),
        Pattern(name="aadhaar_plain", regex=r"\b[2-9]{1}[0-9]{11}\b", score=0.75)
    ]
    return PatternRecognizer(
        supported_entity="AADHAAR_NUMBER",
        supported_language="en",
        patterns=patterns,
        context=["aadhaar", "aadhar", "uid", "uidai"]
    )

def create_pan_recognizer() -> PatternRecognizer:
    patterns = [
        Pattern(name="pan_standard", regex=r"\b[A-Z]{5}[0-9]{4}[A-Z]{1}\b", score=0.85)
    ]
    return PatternRecognizer(
        supported_entity="PAN_NUMBER",
        supported_language="en",
        patterns=patterns,
        context=["pan", "permanent account", "income tax", "tax"]
    )

class PIIDetector:
    def __init__(self):
        self.analyzer = AnalyzerEngine()
        self.anonymizer = AnonymizerEngine()
        
        self.analyzer.registry.add_recognizer(create_aadhaar_recognizer())
        self.analyzer.registry.add_recognizer(create_pan_recognizer())
        
        self.entities = [
            "PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER",
            "CREDIT_CARD", "LOCATION", "URL",
            "AADHAAR_NUMBER", "PAN_NUMBER"
        ]
        self.logger = logging.getLogger(__name__)

    def detect_and_mask(self, text: str) -> PIIResult:
        if not text:
            return PIIResult(has_pii=False, masked_text=text or "", reason="Empty input")

        results = self.analyzer.analyze(text=text, entities=self.entities, language="en")
        
        if not results:
            return PIIResult(has_pii=False, masked_text=text, reason="No PII detected")

        entities_found = []
        entity_summary = {}

        for result in results:
            original_value = text[result.start:result.end]
            entities_found.append(
                PIIEntity(
                    entity_type=result.entity_type,
                    original_value=original_value,
                    start=result.start,
                    end=result.end,
                    score=result.score
                )
            )
            entity_summary[result.entity_type] = entity_summary.get(result.entity_type, 0) + 1

        operators = {}
        if settings.PII_MASKING_MODE == "replace":
            for entity_type in entity_summary.keys():
                operators[entity_type] = OperatorConfig("replace", {"new_value": f"[{entity_type}]"})
        elif settings.PII_MASKING_MODE == "redact":
            for entity_type in entity_summary.keys():
                operators[entity_type] = OperatorConfig("redact", {})

        anonymized = self.anonymizer.anonymize(
            text=text, 
            analyzer_results=results, 
            operators=operators
        )
        masked_text = anonymized.text

        reason = f"Masked {len(entities_found)} PII entity/entities: {', '.join(entity_summary.keys())}"
        self.logger.info(reason)

        return PIIResult(
            has_pii=True,
            masked_text=masked_text,
            entities_found=entities_found,
            entity_summary=entity_summary,
            reason=reason
        )

    def has_pii(self, text: str) -> bool:
        return self.detect_and_mask(text).has_pii

pii_detector = PIIDetector()
