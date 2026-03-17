import os


class RAGConfig:
    """Centralized RAG configuration - tune via environment variables."""

    FINAL_K = int(os.getenv("RAG_FINAL_K", "3"))
    MIN_KEEP = int(os.getenv("RAG_MIN_KEEP", "2"))
    ALPHA = float(os.getenv("RAG_ALPHA", "0.6"))
    HARD_MIN = float(os.getenv("RAG_HARD_MIN", "0.10"))
    SOFT_MIN = float(os.getenv("RAG_SOFT_MIN", "0.15"))
    MAX_CANDIDATES = int(os.getenv("RAG_MAX_CANDIDATES", "5"))


USE_PAGE_IMAGES = os.getenv("USE_PAGE_IMAGES", "false").lower() in ("true", "1", "yes")

