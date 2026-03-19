from typing import List

from app.chat.config import RAGConfig
from app.chat.scoring import get_doc_score


def select_context_docs(retrieved_docs: List, max_candidates: int = None) -> tuple[List, dict]:
    """
    Select context documents with metadata about selection process.

    Returns:
    (selected_docs, metadata)
    metadata contains:
      - reason
      - max_score
      - filtered_count
    """
    if max_candidates is None:
        max_candidates = RAGConfig.MAX_CANDIDATES

    candidates = (retrieved_docs or [])[:max_candidates]
    metadata = {"reason": None, "max_score": None, "filtered_count": 0, "dedup_count": 0}

    if not candidates:
        metadata["reason"] = "no_candidates_retrieved"
        return [], metadata

    max_score = get_doc_score(candidates[0])
    metadata["max_score"] = max_score

    if max_score is None or max_score < RAGConfig.HARD_MIN:
        if max_score is None:
            metadata["reason"] = "max_score_missing"
        else:
            metadata["reason"] = f"max_score_too_low ({max_score:.4f} < {RAGConfig.HARD_MIN})"
        return [], metadata

    cutoff = max(max_score * RAGConfig.ALPHA, RAGConfig.SOFT_MIN)

    final_docs = []
    seen_pages = set()
    for i, doc in enumerate(candidates):
        score = get_doc_score(doc) or max_score
        meta = doc.metadata or {}
        source = meta.get("source", "Unknown")
        source_id = meta.get("source_id", source)
        page = meta.get("page", 0)
        brand = meta.get("brand", "")
        model_subbrand = meta.get("model_subbrand", "")
        page_key = (source_id, page, brand, model_subbrand)

        should_keep = i < RAGConfig.MIN_KEEP or score >= cutoff
        if not should_keep:
            metadata["filtered_count"] += 1
            continue

        # Prefer coverage across unique pages to avoid sending duplicates of one page.
        if page_key in seen_pages:
            metadata["dedup_count"] += 1
            continue

        final_docs.append(doc)
        seen_pages.add(page_key)
        if len(final_docs) >= RAGConfig.FINAL_K:
            break

    metadata["reason"] = "success"
    return final_docs, metadata
