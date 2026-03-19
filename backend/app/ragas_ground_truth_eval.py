"""
Optional offline RAGAS evaluator for ground-truth checks.

This script is intentionally separate from runtime chat.
It evaluates context_precision/context_recall using the configured judge LLM.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from typing import Dict, Any, List

from psycopg2 import pool
from sentence_transformers import SentenceTransformer

from app.chatbot import answer_question
from app.chat.selection import select_context_docs
from app.llm_factory import create_intent_llm, create_main_llm, is_intent_llm_enabled
from app.chat.text_utils import build_retrieval_query
from app.retriever import PostgresVectorRetriever, EnhancedFlashrankRerankRetriever

logger = logging.getLogger(__name__)


def _setup_runtime():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL environment variable is required.")

    api_key = os.getenv("LLM_API_KEY") or os.getenv("DASHSCOPE_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
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
            logger.warning("Intent LLM unavailable in RAGAS ground-truth eval; falling back to original query: %s", e)

    embedder = SentenceTransformer(
        os.getenv("EMBED_MODEL", "BAAI/bge-m3"),
        cache_folder=os.getenv("MODEL_CACHE", "/app/models"),
    )
    return db_pool, llm, intent_llm, embedder


def _get_selected_contexts(question: str, db_pool, intent_llm, embedder, collection: str) -> List[str]:
    base = PostgresVectorRetriever(
        connection_pool=db_pool,
        embedder=embedder,
        collection=collection,
    )
    reranker = EnhancedFlashrankRerankRetriever(base_retriever=base)
    retrieval_query, _intent_source = build_retrieval_query(question, intent_llm=intent_llm)
    docs = reranker.invoke(retrieval_query) or []
    selected, _ = select_context_docs(docs)
    return [d.page_content for d in selected]


def evaluate_two_metrics(
    question: str,
    ground_truth: str,
    collection: str = "plcnext",
) -> Dict[str, Any]:
    try:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import context_precision, context_recall
        from langchain_huggingface import HuggingFaceEmbeddings
    except Exception as e:
        raise RuntimeError(
            "RAGAS deps are not installed. Install optional deps first: "
            "pip install -r backend/requirements-ragas.txt"
        ) from e

    db_pool, llm, intent_llm, embedder = _setup_runtime()
    try:
        chat_result = answer_question(
            question=question,
            db_pool=db_pool,
            llm=llm,
            intent_llm=intent_llm,
            embedder=embedder,
            collection=collection,
            retriever_class=PostgresVectorRetriever,
            reranker_class=EnhancedFlashrankRerankRetriever,
        )
        answer = chat_result.get("reply", "")
        contexts = _get_selected_contexts(question, db_pool, intent_llm, embedder, collection)

        ragas_embeddings = HuggingFaceEmbeddings(
            model_name=os.getenv("RAGAS_EMBED_MODEL_EVAL", "sentence-transformers/all-MiniLM-L6-v2"),
            cache_folder=os.getenv("MODEL_CACHE", "/app/models"),
        )

        data = {
            "question": [question],
            "answer": [answer],
            "contexts": [contexts],
            "ground_truth": [ground_truth],
        }
        dataset = Dataset.from_dict(data)

        result = evaluate(
            dataset=dataset,
            metrics=[context_precision, context_recall],
            llm=llm,
            embeddings=ragas_embeddings,
        )

        if hasattr(result, "to_pandas"):
            df = result.to_pandas()
            row = df.iloc[0].to_dict() if df is not None and not df.empty else {}
        else:
            row = {}

        return {
            "question": question,
            "ground_truth": ground_truth,
            "answer": answer,
            "context_count": len(contexts),
            "context_precision": float(row.get("context_precision")) if row.get("context_precision") is not None else None,
            "context_recall": float(row.get("context_recall")) if row.get("context_recall") is not None else None,
        }
    finally:
        db_pool.closeall()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate context_precision/context_recall with the configured chat LLM + ground truth.")
    parser.add_argument("--question", required=True, help="Question to evaluate")
    parser.add_argument("--ground-truth", required=True, help="Reference answer for recall/precision evaluation")
    parser.add_argument("--collection", default=os.getenv("DEFAULT_COLLECTION", "plcnext"), help="Vector collection name")
    parser.add_argument("--output", default="", help="Optional output JSON file path")
    return parser


if __name__ == "__main__":
    args = _build_parser().parse_args()
    report = evaluate_two_metrics(
        question=args.question,
        ground_truth=args.ground_truth,
        collection=args.collection,
    )
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"Saved report to {args.output}")
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))

