"""
Batch question runner for smoke-checking retrieval/generation quality.

This replaces the older RAGAS+Golden-QA evaluator with a lightweight flow:
- Read questions from a JSON file
- Ask the chatbot for each question
- Save answers + timing metadata

Input JSON can use either:
- {"question": "..."}
- {"reference_question": "..."}
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List

from psycopg2 import pool
from sentence_transformers import SentenceTransformer

from app.chatbot import answer_question
from app.llm_factory import create_intent_llm, create_main_llm, is_intent_llm_enabled
from app.retriever import PostgresVectorRetriever, EnhancedFlashrankRerankRetriever

logger = logging.getLogger(__name__)


def load_questions(filepath: str) -> List[str]:
    with open(filepath, "r", encoding="utf-8") as f:
        rows = json.load(f)

    questions: List[str] = []
    for row in rows:
        q = (row.get("question") or row.get("reference_question") or "").strip()
        if q:
            questions.append(q)
    return questions


def setup_dependencies():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL environment variable is required.")

    llm_api_key = os.getenv("LLM_API_KEY") or os.getenv("DASHSCOPE_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not llm_api_key:
        raise RuntimeError("LLM_API_KEY (or DASHSCOPE_API_KEY / OPENAI_API_KEY) environment variable is required.")

    db_pool = pool.SimpleConnectionPool(
        minconn=int(os.getenv("DB_POOL_MIN", "1")),
        maxconn=int(os.getenv("DB_POOL_MAX", "10")),
        dsn=db_url,
    )

    llm = create_main_llm(
        temperature=float(os.getenv("LLM_TEMPERATURE", "0.0")),
        timeout=int(os.getenv("LLM_TIMEOUT", "30")),
    )
    intent_llm = None
    if is_intent_llm_enabled():
        try:
            intent_llm = create_intent_llm(
                temperature=float(os.getenv("INTENT_LLM_TEMPERATURE", "0.0")),
                timeout=int(os.getenv("INTENT_LLM_TIMEOUT", "15")),
                max_tokens=int(os.getenv("INTENT_LLM_NUM_PREDICT", "160")),
            )
        except Exception as e:
            logger.warning("Intent LLM unavailable in batch mode; falling back to original query: %s", e)

    embedder = SentenceTransformer(
        os.getenv("EMBED_MODEL", "BAAI/bge-m3"),
        cache_folder=os.getenv("MODEL_CACHE", "/app/models"),
    )

    return db_pool, llm, intent_llm, embedder


def run_batch_questions(input_file: str, output_file: str, collection: str = "plcnext") -> List[Dict[str, Any]]:
    questions = load_questions(input_file)
    if not questions:
        raise RuntimeError(f"No valid questions found in {input_file}")

    db_pool, llm, intent_llm, embedder = setup_dependencies()
    results: List[Dict[str, Any]] = []

    try:
        total = len(questions)
        for i, question in enumerate(questions, start=1):
            print(f"[{i}/{total}] {question[:80]}")
            result = answer_question(
                question=question,
                db_pool=db_pool,
                llm=llm,
                intent_llm=intent_llm,
                embedder=embedder,
                collection=collection,
                retriever_class=PostgresVectorRetriever,
                reranker_class=EnhancedFlashrankRerankRetriever,
            )
            results.append(
                {
                    "question_id": i - 1,
                    "question": question,
                    "answer": result.get("reply", ""),
                    "timing": {
                        "processing_time": result.get("processing_time"),
                        "retrieval_time": result.get("retrieval_time"),
                        "rerank_time": result.get("rerank_time"),
                        "llm_time": result.get("llm_time"),
                    },
                    "sources": result.get("sources", []),
                }
            )
    finally:
        db_pool.closeall()

    out_path = Path(output_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"Saved {len(results)} responses to {output_file}")
    return results


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a batch of questions through the chatbot.")
    parser.add_argument(
        "--input",
        default="/app/data/Knowledge/golden_qa.json",
        help="Input JSON containing question rows",
    )
    parser.add_argument(
        "--output",
        default="/app/evaluation_results.json",
        help="Output JSON file path",
    )
    parser.add_argument(
        "--collection",
        default=os.getenv("DEFAULT_COLLECTION", "plcnext"),
        help="Document collection to query",
    )
    return parser


if __name__ == "__main__":
    args = _build_arg_parser().parse_args()
    run_batch_questions(args.input, args.output, args.collection)

