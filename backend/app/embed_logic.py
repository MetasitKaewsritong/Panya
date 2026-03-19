import json
import logging
import os
import threading
from typing import List

from langchain_core.documents import Document
from sentence_transformers import SentenceTransformer

# Singleton embedder instance with thread-safe initialization
_embedder = None
_embedder_lock = threading.Lock()


def get_embedder():
    """
    Returns a thread-safe singleton SentenceTransformer embedder.
    Uses BAAI/bge-m3 model (matching embed.py and .env configuration).
    """
    global _embedder
    if _embedder is None:
        with _embedder_lock:
            if _embedder is None:
                model_name = os.getenv("EMBED_MODEL", "BAAI/bge-m3")
                cache_folder = os.getenv("MODEL_CACHE", "/app/models")
                logging.info("[get_embedder] Loading embedder: %s", model_name)
                _embedder = SentenceTransformer(model_name, cache_folder=cache_folder)
                logging.info("[get_embedder] Embedder loaded successfully")
    return _embedder


def enhance_metadata(metadata: dict, chunk_content: str) -> dict:
    """Add lightweight metadata to a chunk."""
    enhanced_meta = metadata.copy()
    enhanced_meta.update(
        {
            "char_count": len(chunk_content),
            "word_count": len(chunk_content.split()),
        }
    )
    return enhanced_meta


def create_json_qa_chunks(file_path: str) -> List[Document]:
    """
    Create chunks from JSON QA file.

    Supports both schemas:
    - {"question": "...", "answer": "..."}
    - {"reference_question": "...", "reference_answer": "..."}
    """
    chunks = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            qa_pairs = json.load(f)

        skipped = 0
        for pair in qa_pairs:
            question = (pair.get("question") or pair.get("reference_question") or "").strip()
            answer = (pair.get("answer") or pair.get("reference_answer") or "").strip()

            if not question or not answer:
                skipped += 1
                continue

            content = f"Question: {question}\nAnswer: {answer}"
            metadata = enhance_metadata(
                {"source": os.path.basename(file_path), "chunk_type": "golden_qa"},
                content,
            )
            chunks.append(Document(page_content=content, metadata=metadata))
        logging.info("Created %d chunks from Golden QA Set (skipped %d invalid rows).", len(chunks), skipped)
    except Exception as e:
        logging.error("Failed to process JSON file %s: %s", file_path, e)
    return chunks


def get_embedding_instruction(chunk_type: str) -> str:
    """Customize instruction based on chunk type for better embedding quality."""
    instructions = {
        "page_summary": "Represent this technical manual page retrieval note for search: ",
        "golden_qa": "Represent this authoritative question-answer pair for search: ",
        "page_unreadable": "Represent this unreadable or blank page marker for filtering only: ",
    }
    return instructions.get(chunk_type, "Represent this sentence for searching relevant passages: ")
