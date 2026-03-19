import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


def log_chat_request(
    question: str,
    retrieval_time: float,
    rerank_time: float,
    llm_time: float,
    total_time: float,
    retrieved_docs: List,
    selected_docs: List,
    max_score: Optional[float],
):
    """
    Log concise, production-friendly request telemetry.
    Detailed chunk logs stay at DEBUG level to reduce noise.
    """
    selected_refs = []
    for doc in selected_docs or []:
        metadata = getattr(doc, "metadata", {}) or {}
        source = metadata.get("source", "unknown")
        page = metadata.get("page", "N/A")
        chunk_id = metadata.get("chunk_id", "N/A")
        selected_refs.append(f"{source}:page={page}:chunk={chunk_id}")

    logger.info(
        "[RAG] q='%s' retrieved=%d selected=%d max_score=%s timings(retrieval=%.3fs rerank=%.3fs llm=%.3fs total=%.3fs) selected_refs=%s",
        (question or "")[:100],
        len(retrieved_docs or []),
        len(selected_docs or []),
        f"{max_score:.4f}" if isinstance(max_score, (int, float)) else "N/A",
        retrieval_time,
        rerank_time,
        llm_time,
        total_time,
        selected_refs if selected_refs else ["none"],
    )
    for i, doc in enumerate((selected_docs or [])[:3], start=1):
        logger.debug(
            "[RAG] selected[%d] source=%s page=%s type=%s score=%s preview=%s",
            i,
            doc.metadata.get("source", "unknown"),
            doc.metadata.get("page", "N/A"),
            doc.metadata.get("chunk_type", "unknown"),
            doc.metadata.get("score", "N/A"),
            doc.page_content[:120].replace("\n", " "),
        )

