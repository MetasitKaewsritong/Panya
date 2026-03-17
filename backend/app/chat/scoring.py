import math
from typing import Optional


def normalize_score(raw_score: float) -> float:
    if raw_score is None:
        return 0.0
    if 0 <= raw_score <= 1:
        return raw_score
    return 1 / (1 + math.exp(-raw_score))


def get_doc_score(doc) -> Optional[float]:
    score = getattr(doc, "score", None)
    if score is not None:
        return normalize_score(score)
    metadata = getattr(doc, "metadata", {})
    if isinstance(metadata, dict):
        score = metadata.get("score") or metadata.get("relevance_score")
        if score is not None:
            return normalize_score(score)
    return None

