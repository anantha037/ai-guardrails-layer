from transformers import pipeline, Pipeline
from dataclasses import dataclass
import logging

from config import settings

@dataclass
class ToxicityResult:
    is_toxic: bool
    score: float
    label: str
    reason: str

class ToxicityFilter:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.classifier = pipeline(
            "text-classification",
            model=settings.TOXICITY_MODEL,
            device=-1,
            truncation=True,
            max_length=512
        )
        self.threshold = settings.TOXICITY_THRESHOLD
        self.logger.info(f"Toxicity filter loaded: {settings.TOXICITY_MODEL}")

    def analyze(self, text: str) -> ToxicityResult:
        if not text:
            return ToxicityResult(
                is_toxic=False, 
                score=0.0, 
                label="NON_TOXIC", 
                reason="Empty input"
            )

        result = self.classifier(text[:512])
        raw_label = result[0]["label"]
        raw_score = result[0]["score"]

        if raw_label.lower() == "toxic":
            label = "TOXIC"
            score = raw_score
        else:
            label = "NON_TOXIC"
            score = 1.0 - raw_score

        is_toxic = (label == "TOXIC") and (score >= self.threshold)

        if is_toxic:
            reason = f"Toxic content detected (score: {score:.3f}, threshold: {self.threshold})"
            self.logger.warning(f"{reason} | Input preview: {text[:100]}")
        else:
            reason = f"Content is safe (score: {score:.3f})"

        return ToxicityResult(
            is_toxic=is_toxic,
            score=score,
            label=label,
            reason=reason
        )

    def is_safe(self, text: str) -> bool:
        return not self.analyze(text).is_toxic

toxicity_filter = ToxicityFilter()
