"""
RAGAS Evaluation Module
Provides optional runtime quality assessment for RAG responses.
"""

from __future__ import annotations

import logging
import os
import threading
import json
import re
import difflib
import inspect
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _env_bool(key: str, default: bool = False) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return str(val).strip().lower() in ("1", "true", "yes", "on")


def _env_int(key: str, default: int) -> int:
    val = os.getenv(key)
    if val is None:
        return default
    try:
        return int(val)
    except Exception:
        return default


# Primary toggle (keeps backward compatibility with older env flag).
ENABLE_RAGAS = _env_bool("EVAL_WITH_RAGAS", _env_bool("ENABLE_RAGAS_LLM", False))
ENABLE_BACKGROUND_RAGAS = _env_bool("ENABLE_BACKGROUND_RAGAS", True)

RAGAS_LLM_PROVIDER = os.getenv("RAGAS_LLM_PROVIDER", "gemini")
RAGAS_LLM_MODEL = os.getenv("RAGAS_LLM_MODEL", os.getenv("GEMINI_MODEL", "gemini-1.5-flash"))
RAGAS_TIMEOUT = int(os.getenv("RAGAS_TIMEOUT", "30"))
RAGAS_MAX_WORKERS = max(1, _env_int("RAGAS_MAX_WORKERS", 1))
RAGAS_METRIC_KEYS = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]

_ragas_llm = None
_ragas_embeddings = None
_ragas_lock = threading.Lock()
_ground_truth_rows: List[Tuple[str, str, str]] = []
_ground_truth_map: Dict[str, Tuple[str, str]] = {}
_ground_truth_loaded = False
_ground_truth_lock = threading.Lock()


def _normalize_question(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _ground_truth_paths() -> List[str]:
    raw = os.getenv("RAGAS_GROUND_TRUTH_FILE", "").strip()
    if raw:
        return [p.strip() for p in raw.split(",") if p.strip()]
    # Default to the file you just created for this project.
    return ["/app/data/Knowledge/golden_qa_fx485adp_ragas.json"]


def _load_ground_truth() -> None:
    global _ground_truth_loaded, _ground_truth_rows, _ground_truth_map
    if _ground_truth_loaded:
        return

    with _ground_truth_lock:
        if _ground_truth_loaded:
            return

        rows: List[Tuple[str, str, str]] = []
        mapping: Dict[str, Tuple[str, str]] = {}

        for path in _ground_truth_paths():
            try:
                if not os.path.exists(path):
                    logger.warning("[RAGAS] Ground-truth file not found: %s", path)
                    continue
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, list):
                    logger.warning("[RAGAS] Ground-truth file is not a JSON list: %s", path)
                    continue

                loaded_count = 0
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    question = (
                        item.get("question")
                        or item.get("reference_question")
                        or item.get("variation_a")
                        or item.get("variation_b")
                        or ""
                    )
                    ground_truth = (
                        item.get("ground_truth")
                        or item.get("answer")
                        or item.get("reference_answer")
                        or ""
                    )
                    qn = _normalize_question(question)
                    gt = (ground_truth or "").strip()
                    if not qn or not gt:
                        continue
                    mapping[qn] = (gt, path)
                    rows.append((qn, gt, path))
                    loaded_count += 1
                logger.info("[RAGAS] Loaded %d ground-truth rows from %s", loaded_count, path)
            except Exception as e:
                logger.error("[RAGAS] Failed to load ground-truth file %s: %s", path, e)

        _ground_truth_map = mapping
        _ground_truth_rows = rows
        _ground_truth_loaded = True


def resolve_ground_truth_with_source(question: str) -> Tuple[Optional[str], str]:
    """
    Resolve a reference answer for RAGAS precision/recall.
    Uses exact normalized match first, then optional fuzzy fallback.
    """
    if not _env_bool("RAGAS_USE_GROUND_TRUTH_LOOKUP", True):
        return None, "lookup_disabled"

    _load_ground_truth()
    if not _ground_truth_map:
        return None, "no_ground_truth_loaded"

    qn = _normalize_question(question)
    if not qn:
        return None, "empty_question"

    exact = _ground_truth_map.get(qn)
    if exact:
        gt, path = exact
        logger.info("[RAGAS] Ground-truth matched by exact question key")
        return gt, f"exact:{os.path.basename(path)}"

    if not _env_bool("RAGAS_GROUND_TRUTH_FUZZY", True):
        return None, "no_exact_match"

    threshold = float(os.getenv("RAGAS_GROUND_TRUTH_FUZZY_THRESHOLD", "0.92"))
    best_ratio = 0.0
    best_gt = None
    best_q = None
    best_path = None
    for known_q, known_gt, known_path in _ground_truth_rows:
        ratio = difflib.SequenceMatcher(None, qn, known_q).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_gt = known_gt
            best_q = known_q
            best_path = known_path

    if best_gt and best_ratio >= threshold:
        logger.info(
            "[RAGAS] Ground-truth matched by fuzzy key (ratio=%.3f, threshold=%.3f)",
            best_ratio,
            threshold,
        )
        logger.debug("[RAGAS] Fuzzy matched key: %s", best_q)
        return best_gt, f"fuzzy:{os.path.basename(best_path or 'unknown')}:{best_ratio:.3f}"

    return None, "no_match"


def resolve_ground_truth(question: str) -> Optional[str]:
    ground_truth, _source = resolve_ground_truth_with_source(question)
    return ground_truth


def _safe_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN check
        return None
    return f


def _extract_scores(result, metric_names: List[str]) -> Dict[str, float]:
    scores: Dict[str, float] = {}

    try:
        if hasattr(result, "to_pandas"):
            df = result.to_pandas()
            if df is not None and not df.empty:
                row = df.iloc[0]
                for name in metric_names:
                    val = _safe_float(row.get(name))
                    if val is not None:
                        scores[name] = val
                if scores:
                    return scores
    except Exception:
        pass

    raw_scores = getattr(result, "_scores_dict", None)
    if isinstance(raw_scores, dict):
        for name in metric_names:
            val = _safe_float(raw_scores.get(name))
            if val is not None:
                scores[name] = val
        if scores:
            return scores

    for name in metric_names:
        try:
            val = _safe_float(result[name])
            if val is not None:
                scores[name] = val
        except Exception:
            continue

    return scores


def _ordered_metric_snapshot(scores: Dict[str, float]) -> Dict[str, Optional[float]]:
    snapshot: Dict[str, Optional[float]] = {}
    for key in RAGAS_METRIC_KEYS:
        snapshot[key] = _safe_float((scores or {}).get(key))
    return snapshot


def empty_ragas_scores() -> Dict[str, Optional[float]]:
    return _ordered_metric_snapshot({})


def format_scores(scores: Dict[str, float]) -> str:
    metric_values = _ordered_metric_snapshot(scores)
    key_width = max(len(k) for k in RAGAS_METRIC_KEYS)
    lines = []
    for key in RAGAS_METRIC_KEYS:
        value = metric_values[key]
        if value is None:
            lines.append(f"  - {key:<{key_width}} : N/A")
        else:
            lines.append(f"  - {key:<{key_width}} : {value:.3f} ({value * 100:.1f}%)")
    return "\n".join(lines)


def _get_ragas_llm():
    global _ragas_llm
    if _ragas_llm is not None:
        return _ragas_llm

    if RAGAS_LLM_PROVIDER == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        _ragas_llm = ChatGoogleGenerativeAI(
            model=RAGAS_LLM_MODEL,
            google_api_key=os.getenv("GEMINI_API_KEY"),
            temperature=float(os.getenv("RAGAS_LLM_TEMPERATURE", "0.0")),
            timeout=RAGAS_TIMEOUT,
        )
        return _ragas_llm

    if RAGAS_LLM_PROVIDER == "openai":
        from langchain_openai import ChatOpenAI

        _ragas_llm = ChatOpenAI(
            model=RAGAS_LLM_MODEL,
            api_key=os.getenv("OPENAI_API_KEY"),
            temperature=float(os.getenv("RAGAS_LLM_TEMPERATURE", "0.0")),
            timeout=RAGAS_TIMEOUT,
        )
        return _ragas_llm

    raise ValueError(f"Unsupported RAGAS_LLM_PROVIDER: {RAGAS_LLM_PROVIDER}")


def _get_ragas_embeddings():
    global _ragas_embeddings
    if _ragas_embeddings is not None:
        return _ragas_embeddings

    from langchain_huggingface import HuggingFaceEmbeddings

    _ragas_embeddings = HuggingFaceEmbeddings(
        model_name=os.getenv("RAGAS_EMBED_MODEL_EVAL", "sentence-transformers/all-MiniLM-L6-v2"),
        cache_folder=os.getenv("MODEL_CACHE", "/app/models"),
    )
    return _ragas_embeddings


def evaluate_response(
    question: str,
    answer: str,
    contexts: List[str],
    ground_truth: Optional[str] = None,
) -> Dict[str, Optional[float]]:
    """
    Evaluate RAG response quality using RAGAS metrics.
    """
    if not ENABLE_RAGAS:
        logger.debug("[RAGAS] Evaluation disabled")
        return empty_ragas_scores()

    if not contexts or not answer:
        logger.warning("[RAGAS] Missing contexts or answer, skipping evaluation")
        return empty_ragas_scores()

    try:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness
    except Exception as e:
        logger.error(
            "[RAGAS] Dependencies unavailable: %s. Install optional deps: pip install -r requirements-ragas.txt",
            e,
        )
        return empty_ragas_scores()

    try:
        resolved_ground_truth = ground_truth
        ground_truth_source = "provided_argument" if ground_truth else "none"
        if not resolved_ground_truth:
            resolved_ground_truth, ground_truth_source = resolve_ground_truth_with_source(question)

        data = {
            "question": [question],
            "answer": [answer],
            "contexts": [contexts],
        }
        if resolved_ground_truth:
            data["ground_truth"] = [resolved_ground_truth]
            metrics = [faithfulness, answer_relevancy, context_precision, context_recall]
        else:
            metrics = [faithfulness, answer_relevancy]

        metric_names = [m.name for m in metrics]
        logger.info(
            "[RAGAS] Evaluating with metrics=%s (ground_truth=%s)",
            metric_names,
            "yes" if resolved_ground_truth else "no",
        )
        logger.info("[RAGAS] ground_truth_source=%s", ground_truth_source)
        if not resolved_ground_truth:
            logger.info("[RAGAS] context_precision/context_recall require ground_truth; logging as N/A")

        dataset = Dataset.from_dict(data)

        # Guard singleton init with lock; evaluate can run in background threads.
        with _ragas_lock:
            ragas_llm = _get_ragas_llm()
            ragas_embeddings = _get_ragas_embeddings()

        evaluate_kwargs = {
            "dataset": dataset,
            "metrics": metrics,
            "llm": ragas_llm,
            "embeddings": ragas_embeddings,
        }

        # Apply optional runtime controls when available (depends on ragas version).
        try:
            eval_params = inspect.signature(evaluate).parameters
            if "run_config" in eval_params:
                from ragas.run_config import RunConfig

                evaluate_kwargs["run_config"] = RunConfig(
                    timeout=RAGAS_TIMEOUT,
                    max_workers=RAGAS_MAX_WORKERS,
                )
            if "raise_exceptions" in eval_params:
                evaluate_kwargs["raise_exceptions"] = False
        except Exception as cfg_err:
            logger.debug("[RAGAS] Optional evaluate config not applied: %s", cfg_err)

        result = evaluate(**evaluate_kwargs)

        scores = _extract_scores(result, metric_names)
        metric_snapshot = _ordered_metric_snapshot(scores)
        logger.info("[RAGAS] Evaluation complete\n%s", format_scores(metric_snapshot))
        return metric_snapshot
    except Exception as e:
        logger.error("[RAGAS] Evaluation failed: %s", e, exc_info=True)
        return empty_ragas_scores()


def evaluate_response_async(
    question: str,
    answer: str,
    contexts: List[str],
    ground_truth: Optional[str] = None,
) -> Dict[str, Optional[float]]:
    """
    Async wrapper for RAGAS evaluation.
    """
    if not ENABLE_RAGAS:
        logger.debug("[RAGAS] Async evaluation skipped (disabled)")
        return empty_ragas_scores()

    if ENABLE_BACKGROUND_RAGAS:
        logger.info("[RAGAS] Starting async evaluation for question: '%s...'", (question or "")[:50])

        def run_eval():
            try:
                logger.info("[RAGAS] Background thread started")
                evaluate_response(question, answer, contexts, ground_truth)
            except Exception as e:
                logger.error("[RAGAS] Async evaluation failed: %s", e, exc_info=True)

        thread = threading.Thread(target=run_eval, daemon=True)
        thread.start()
        logger.debug("[RAGAS] Background thread spawned: %s", thread.name)
        return empty_ragas_scores()

    # Synchronous fallback if background mode is disabled.
    logger.info("[RAGAS] Running evaluation synchronously (ENABLE_BACKGROUND_RAGAS=false)")
    return evaluate_response(question, answer, contexts, ground_truth)
