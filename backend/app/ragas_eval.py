"""
RAGAS Evaluation Module
Provides optional runtime quality assessment for RAG responses.
"""

from __future__ import annotations

from collections import Counter
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


def _first_non_empty(*values: Optional[str]) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


# Primary toggle (keeps backward compatibility with older env flag).
ENABLE_RAGAS = _env_bool("EVAL_WITH_RAGAS", _env_bool("ENABLE_RAGAS_LLM", False))
ENABLE_BACKGROUND_RAGAS = _env_bool("ENABLE_BACKGROUND_RAGAS", True)

RAGAS_LLM_PROVIDER = os.getenv("RAGAS_LLM_PROVIDER", "openai")
RAGAS_LLM_MODEL = os.getenv(
    "RAGAS_LLM_MODEL",
    os.getenv("LLM_MODEL", "hf.co/Qwen/Qwen3-VL-4B-Thinking-GGUF:Q4_K_M"),
)
RAGAS_TIMEOUT = int(os.getenv("RAGAS_TIMEOUT", "30"))
RAGAS_MAX_WORKERS = max(1, _env_int("RAGAS_MAX_WORKERS", 1))
# Reusing a single chat client across async evaluation loops can trigger
# "attached to a different loop" runtime errors in some provider stacks.
RAGAS_REUSE_LLM = _env_bool("RAGAS_REUSE_LLM", False)
RAGAS_METRIC_KEYS = [
    "faithfulness",
    "answer_relevancy",
    "answer_match",
    "context_precision",
    "context_recall",
]

_ragas_llm = None
_ragas_embeddings = None
_ragas_lock = threading.Lock()
_ground_truth_rows: List[Tuple[str, str, str]] = []
_ground_truth_map: Dict[str, Tuple[str, str]] = {}
_ground_truth_loaded = False
_ground_truth_lock = threading.Lock()

_MANUAL_SCOPE_PREFIX_RE = re.compile(
    r"^\s*(?:for|in|from)\s+[^:]{0,180}\bmanual\b\s*:\s*",
    re.IGNORECASE,
)
_MATCH_TOKEN_RE = re.compile(r"[a-z0-9]+")
_MATCH_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
_ANSWER_MATCH_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "was",
    "were",
    "with",
}


def _strip_manual_scope_prefix(text: str) -> str:
    """Remove leading 'For <manual> manual:' scoping so lookup keys still match."""
    raw = (text or "").strip()
    if not raw:
        return raw
    stripped = _MANUAL_SCOPE_PREFIX_RE.sub("", raw, count=1).strip()
    return stripped or raw


def _normalize_question(text: str) -> str:
    text = _strip_manual_scope_prefix(text).lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _normalize_match_text(text: str) -> str:
    value = (text or "").strip().lower()
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _match_tokens(text: str) -> List[str]:
    normalized = _normalize_match_text(text)
    return [
        token
        for token in _MATCH_TOKEN_RE.findall(normalized)
        if token and token not in _ANSWER_MATCH_STOPWORDS
    ]


def _token_f1(answer_tokens: List[str], ground_truth_tokens: List[str]) -> tuple[float, float]:
    if not answer_tokens or not ground_truth_tokens:
        return 0.0, 0.0

    common = sum((Counter(answer_tokens) & Counter(ground_truth_tokens)).values())
    if common <= 0:
        return 0.0, 0.0

    precision = common / len(answer_tokens)
    recall = common / len(ground_truth_tokens)
    if precision + recall == 0:
        return 0.0, recall
    return (2 * precision * recall) / (precision + recall), recall


def _ground_truth_number_coverage(answer_text: str, ground_truth_text: str) -> Optional[float]:
    answer_numbers = set(_MATCH_NUMBER_RE.findall(_normalize_match_text(answer_text)))
    ground_truth_numbers = set(_MATCH_NUMBER_RE.findall(_normalize_match_text(ground_truth_text)))
    if not ground_truth_numbers:
        return None
    return len(answer_numbers.intersection(ground_truth_numbers)) / len(ground_truth_numbers)


def calculate_answer_match(answer: str, ground_truth: Optional[str]) -> Optional[float]:
    if not ground_truth:
        return None

    answer_norm = _normalize_match_text(answer)
    ground_truth_norm = _normalize_match_text(ground_truth)
    if not answer_norm or not ground_truth_norm:
        return None
    if answer_norm == ground_truth_norm:
        return 1.0

    answer_tokens = _match_tokens(answer)
    ground_truth_tokens = _match_tokens(ground_truth)
    token_f1, token_recall = _token_f1(answer_tokens, ground_truth_tokens)
    sequence_ratio = difflib.SequenceMatcher(None, answer_norm, ground_truth_norm).ratio()

    lexical_score = max((0.55 * token_f1) + (0.45 * token_recall), sequence_ratio * 0.9)
    if ground_truth_norm in answer_norm:
        lexical_score = max(lexical_score, 0.97)
    elif answer_norm in ground_truth_norm:
        lexical_score = max(lexical_score, 0.92)

    numeric_coverage = _ground_truth_number_coverage(answer, ground_truth)
    if numeric_coverage is not None:
        lexical_score = (0.75 * lexical_score) + (0.25 * numeric_coverage)

    return round(min(max(lexical_score, 0.0), 1.0), 4)


def _ground_truth_paths() -> List[str]:
    raw = os.getenv("RAGAS_GROUND_TRUTH_FILE", "").strip()
    if raw:
        return [p.strip() for p in raw.split(",") if p.strip()]
    return []


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
    if RAGAS_REUSE_LLM and _ragas_llm is not None:
        return _ragas_llm

    if RAGAS_LLM_PROVIDER == "openai":
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model=RAGAS_LLM_MODEL,
            api_key=_first_non_empty(
                os.getenv("RAGAS_OPENAI_API_KEY"),
                os.getenv("LLM_API_KEY"),
                os.getenv("OLLAMA_API_KEY"),
                os.getenv("DASHSCOPE_API_KEY"),
                os.getenv("OPENAI_API_KEY"),
                "ollama",
            ),
            base_url=_first_non_empty(
                os.getenv("RAGAS_OPENAI_BASE_URL"),
                os.getenv("LLM_BASE_URL"),
                os.getenv("OLLAMA_BASE_URL"),
                os.getenv("OPENAI_BASE_URL"),
                "http://host.docker.internal:11434/v1",
            ),
            temperature=float(os.getenv("RAGAS_LLM_TEMPERATURE", "0.0")),
            timeout=RAGAS_TIMEOUT,
        )
        if RAGAS_REUSE_LLM:
            _ragas_llm = llm
        return llm

    if RAGAS_LLM_PROVIDER == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        llm = ChatGoogleGenerativeAI(
            model=RAGAS_LLM_MODEL,
            google_api_key=os.getenv("GEMINI_API_KEY"),
            temperature=float(os.getenv("RAGAS_LLM_TEMPERATURE", "0.0")),
            timeout=RAGAS_TIMEOUT,
        )
        if RAGAS_REUSE_LLM:
            _ragas_llm = llm
        return llm

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
    resolved_ground_truth = ground_truth
    ground_truth_source = "provided_argument" if ground_truth else "none"
    if not resolved_ground_truth:
        resolved_ground_truth, ground_truth_source = resolve_ground_truth_with_source(question)
    answer_match = calculate_answer_match(answer, resolved_ground_truth)

    if not ENABLE_RAGAS:
        logger.debug("[RAGAS] Evaluation disabled")
        return _ordered_metric_snapshot({"answer_match": answer_match})

    if not contexts or not answer:
        logger.warning("[RAGAS] Missing contexts or answer, skipping evaluation")
        return _ordered_metric_snapshot({"answer_match": answer_match})

    try:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness
    except Exception as e:
        logger.error(
            "[RAGAS] Dependencies unavailable: %s. Install optional deps: pip install -r requirements-ragas.txt",
            e,
        )
        return _ordered_metric_snapshot({"answer_match": answer_match})

    try:
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
        scores["answer_match"] = answer_match
        metric_snapshot = _ordered_metric_snapshot(scores)
        logger.info("[RAGAS] Evaluation complete\n%s", format_scores(metric_snapshot))
        return metric_snapshot
    except Exception as e:
        logger.error("[RAGAS] Evaluation failed: %s", e, exc_info=True)
        return _ordered_metric_snapshot({"answer_match": answer_match})


def evaluate_response_async(
    question: str,
    answer: str,
    contexts: List[str],
    ground_truth: Optional[str] = None,
    on_complete=None,
    on_error=None,
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
                scores = evaluate_response(question, answer, contexts, ground_truth)
                if on_complete:
                    try:
                        on_complete(scores)
                    except Exception as callback_err:
                        logger.error("[RAGAS] Completion callback failed: %s", callback_err, exc_info=True)
            except Exception as e:
                logger.error("[RAGAS] Async evaluation failed: %s", e, exc_info=True)
                if on_error:
                    try:
                        on_error(e)
                    except Exception as callback_err:
                        logger.error("[RAGAS] Error callback failed: %s", callback_err, exc_info=True)

        thread = threading.Thread(target=run_eval, daemon=True)
        thread.start()
        logger.debug("[RAGAS] Background thread spawned: %s", thread.name)
        return empty_ragas_scores()

    # Synchronous fallback if background mode is disabled.
    logger.info("[RAGAS] Running evaluation synchronously (ENABLE_BACKGROUND_RAGAS=false)")
    return evaluate_response(question, answer, contexts, ground_truth)
