import json
import logging
import re
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from typing import Any, List

from langchain_core.output_parsers import StrOutputParser

from app.chat.prompts import build_intent_extraction_prompt
from app.chat.text_utils import call_llm_with_retry, preprocess_query

logger = logging.getLogger(__name__)

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)
_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_ID_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[-_/][a-z0-9]+)*", re.IGNORECASE)

_HIGH_MATCH_THRESHOLD = 0.93
_MEDIUM_MATCH_THRESHOLD = 0.74
_SECONDARY_MATCH_DELTA = 0.03

_INTENT_ALIASES = {
    "troubleshooting": "troubleshooting",
    "troubleshoot": "troubleshooting",
    "fix": "troubleshooting",
    "error": "troubleshooting",
    "fault": "troubleshooting",
    "repair": "troubleshooting",
    "how_to": "procedure",
    "how-to": "procedure",
    "procedure": "procedure",
    "method": "procedure",
    "setup": "procedure",
    "configure": "procedure",
    "configuration": "procedure",
    "general": "general_info",
    "general_info": "general_info",
    "overview": "general_info",
    "explanation": "general_info",
    "specification": "specification",
    "specifications": "specification",
    "spec": "specification",
    "installation": "installation_wiring",
    "wiring": "installation_wiring",
    "installation_wiring": "installation_wiring",
    "compatibility": "compatibility",
    "compatible": "compatibility",
    "reference": "reference_lookup",
    "reference_lookup": "reference_lookup",
    "lookup": "reference_lookup",
    "manual": "reference_lookup",
    "unknown": "unknown",
}

_INTENT_QUERY_TERMS = {
    "troubleshooting": "troubleshooting fix",
    "procedure": "procedure how to",
    "general_info": "general information overview",
    "specification": "specification parameter rating",
    "installation_wiring": "installation wiring connection",
    "compatibility": "compatibility supported models",
    "reference_lookup": "reference lookup manual section",
}

_GENERIC_TOPIC_STOPWORDS = {
    "a",
    "an",
    "and",
    "automation",
    "controller",
    "device",
    "for",
    "how",
    "i",
    "industrial",
    "issue",
    "my",
    "not",
    "of",
    "on",
    "problem",
    "system",
    "the",
    "to",
    "turning",
    "with",
}

_QUESTION_INTENT_KEYWORDS = {
    "troubleshooting": ("fix", "troubleshoot", "error", "fault", "alarm", "warning", "fail", "failure", "not turn", "cannot", "can't"),
    "procedure": ("how to", "steps", "procedure", "install", "installation", "mount", "setup", "configure", "reset", "replace", "check"),
    "specification": ("spec", "specification", "rating", "range", "maximum", "minimum", "limit", "capacity", "how many"),
    "installation_wiring": ("wiring", "wire", "connect", "connection", "terminal", "power supply", "ground", "din rail"),
    "compatibility": ("compatible", "compatibility", "supported", "support", "compare", "difference", "versus", "vs"),
    "reference_lookup": ("manual", "page", "where", "which section", "reference", "buffer memory", "address"),
}


@dataclass
class IntentResolution:
    status: str
    source: str
    raw_question: str
    extraction_confidence: float = 0.0
    brand: str = ""
    model_input: str = ""
    intent: str = ""
    topic: str = ""
    normalized_query: str = ""
    matched_brand: str = ""
    matched_model_subbrand: str = ""
    brand_score: float = 0.0
    model_score: float = 0.0
    brand_filters: List[str] = field(default_factory=list)
    model_subbrand_filters: List[str] = field(default_factory=list)
    reply: str = ""
    clarification: str = ""
    suggestions: List[str] = field(default_factory=list)
    raw_extractor_output: str = ""

    def to_metadata(self) -> dict[str, Any]:
        return asdict(self)


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _normalize_ws(value: str) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize_compact(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _tokenize_text(value: str) -> list[str]:
    return [tok.lower() for tok in _TOKEN_RE.findall(str(value or "").lower()) if tok]


def _tokenize_identifier(value: str) -> list[str]:
    tokens: list[str] = []
    for raw_token in _ID_TOKEN_RE.findall(str(value or "").lower()):
        token = raw_token.strip().lower()
        if not token:
            continue
        tokens.append(token)

        compact = re.sub(r"[-_/]+", "", token)
        if compact and compact != token:
            tokens.append(compact)

        for part in re.split(r"[/_]+", token):
            part = part.strip()
            if not part:
                continue
            tokens.append(part)
            compact_part = re.sub(r"[-_/]+", "", part)
            if compact_part and compact_part != part:
                tokens.append(compact_part)

    return list(dict.fromkeys(tokens))


def _normalize_intent_label(value: str) -> str:
    cleaned = _normalize_ws(str(value or "")).lower().replace(" ", "_")
    return _INTENT_ALIASES.get(cleaned, cleaned or "unknown")


def _extract_identifier_hints(value: str) -> list[str]:
    hints = []
    for token in _tokenize_identifier(value):
        has_letter = any(ch.isalpha() for ch in token)
        has_digit = any(ch.isdigit() for ch in token)
        if has_letter and has_digit and len(token) >= 3:
            hints.append(token.upper())
    return list(dict.fromkeys(hints))


def _sanitize_topic_text(candidate: str, raw_question: str, allowed_terms: list[str]) -> str:
    if not candidate:
        return ""

    raw_tokens = set(_tokenize_identifier(raw_question))
    allowed_tokens = raw_tokens | {tok.lower() for term in allowed_terms for tok in _tokenize_identifier(term)}

    kept: list[str] = []
    for token in _tokenize_identifier(candidate):
        if token in allowed_tokens:
            kept.append(token)
            continue
        if len(token) <= 2 or token in _GENERIC_TOPIC_STOPWORDS:
            kept.append(token)
            continue
        if any(SequenceMatcher(None, token, raw_tok).ratio() >= 0.90 for raw_tok in raw_tokens):
            kept.append(token)

    return " ".join(dict.fromkeys(kept))


def _parse_structured_intent_output(raw_output: str) -> dict[str, Any]:
    text = str(raw_output or "").strip()
    if not text:
        return {}

    candidates = [text]
    match = _JSON_BLOCK_RE.search(text)
    if match:
        candidates.insert(0, match.group(0))

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _score_candidate(query: str, candidate: str) -> float:
    q_text = _normalize_ws(query)
    c_text = _normalize_ws(candidate)
    if not q_text or not c_text:
        return 0.0

    q_compact = _normalize_compact(q_text)
    c_compact = _normalize_compact(c_text)
    if q_compact and q_compact == c_compact:
        return 1.0

    q_tokens = _tokenize_identifier(q_text)
    c_tokens = _tokenize_identifier(c_text)

    exact_token_hits = sum(1 for token in q_tokens if token in c_tokens)
    token_coverage = (exact_token_hits / len(q_tokens)) if q_tokens else 0.0

    fuzzy_hits = []
    for q_token in q_tokens:
        best = 0.0
        for c_token in c_tokens:
            best = max(best, SequenceMatcher(None, q_token, c_token).ratio())
        fuzzy_hits.append(best)
    fuzzy_avg = (sum(fuzzy_hits) / len(fuzzy_hits)) if fuzzy_hits else 0.0

    substring_score = 0.0
    if q_compact and q_compact in c_compact:
        substring_score = 0.97 if len(q_compact) >= 4 else 0.92

    full_ratio = SequenceMatcher(None, q_text.lower(), c_text.lower()).ratio()
    score = max(
        substring_score,
        token_coverage,
        (0.75 * token_coverage) + (0.25 * fuzzy_avg),
        (0.60 * fuzzy_avg) + (0.40 * full_ratio),
        0.85 * full_ratio,
    )
    if len(q_tokens) == 1:
        score = max(score, fuzzy_avg)
    return max(0.0, min(1.0, score))


def _choose_candidates(query: str, candidates: list[str]) -> tuple[str, float, list[str]]:
    if not query or not candidates:
        return "", 0.0, []

    scored = [
        (candidate, _score_candidate(query, candidate))
        for candidate in candidates
        if candidate
    ]
    scored.sort(key=lambda item: item[1], reverse=True)
    if not scored:
        return "", 0.0, []

    best_candidate, best_score = scored[0]
    strong_matches = [
        candidate
        for candidate, score in scored
        if score >= _HIGH_MATCH_THRESHOLD and (best_score - score) <= _SECONDARY_MATCH_DELTA
    ]
    return best_candidate, best_score, strong_matches


def _infer_brand_from_question(raw_question: str, brands: list[str]) -> tuple[str, float]:
    question_compact = _normalize_compact(raw_question)
    if "melsec" in question_compact and "Mitsubishi" in brands:
        return "Mitsubishi", 1.0
        
    for brand in brands:
        brand_compact = _normalize_compact(brand)
        if brand_compact and brand_compact in question_compact:
            return brand, 1.0
    return "", 0.0


def _infer_intent_from_question(raw_question: str) -> str:
    lowered = _normalize_ws(raw_question).lower()
    if not lowered:
        return "unknown"

    for intent, keywords in _QUESTION_INTENT_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return intent
    return "general_info"


def _candidate_contains_query(candidate: str, query: str) -> bool:
    candidate_compact = _normalize_compact(candidate)
    query_compact = _normalize_compact(query)
    if not candidate_compact or not query_compact:
        return False
    return query_compact in candidate_compact


def _should_auto_accept_candidate(
    query: str,
    best_candidate: str,
    score: float,
    candidates: list[str],
) -> bool:
    if not best_candidate or score < _MEDIUM_MATCH_THRESHOLD:
        return False
    if len(candidates) == 1:
        return True

    containing_candidates = [
        candidate
        for candidate in candidates
        if _candidate_contains_query(candidate, query)
    ]
    if len(containing_candidates) == 1 and containing_candidates[0] == best_candidate:
        return True

    return False


def _find_single_family_candidate(query: str, candidates: list[str]) -> str:
    if not query or not candidates:
        return ""

    family_hints = _merge_unique(
        _extract_identifier_hints(query)
        + [
            token.upper()
            for token in _tokenize_identifier(query)
            if len(token) >= 3
            and any(ch.isalpha() for ch in token)
            and token not in _GENERIC_TOPIC_STOPWORDS
        ]
    )
    for hint in family_hints:
        compact_hint = _normalize_compact(hint)
        if not compact_hint:
            continue
        containing = [
            candidate
            for candidate in candidates
            if compact_hint in _normalize_compact(candidate)
        ]
        if len(containing) == 1:
            return containing[0]
    return ""


def _merge_unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _prefer_non_empty(*values: str) -> str:
    for value in values:
        normalized = _normalize_ws(value)
        if normalized:
            return normalized
    return ""


def _question_has_specific_model_hint(raw_question: str) -> bool:
    return bool(_extract_identifier_hints(raw_question))


def _build_heuristic_intent_resolution(
    raw_question: str,
    *,
    catalog: list[dict[str, str]],
    source: str,
) -> IntentResolution:
    brands = sorted({row["brand"] for row in catalog if row["brand"]})
    unique_models = list(dict.fromkeys(row["model_subbrand"] for row in catalog if row["model_subbrand"]))
    inferred_intent = _infer_intent_from_question(raw_question)

    resolution = IntentResolution(
        status="ok",
        source=source,
        raw_question=raw_question,
        extraction_confidence=0.0,
        intent=inferred_intent,
    )

    question_brand, question_brand_score = _infer_brand_from_question(raw_question, brands)
    if question_brand:
        resolution.brand = question_brand
        resolution.matched_brand = question_brand
        resolution.brand_score = question_brand_score
        resolution.brand_filters = [question_brand]
    elif len(brands) == 1:
        resolution.brand = brands[0]
        resolution.matched_brand = brands[0]
        resolution.brand_score = 0.74
        resolution.brand_filters = [brands[0]]

    model_candidates = catalog
    if resolution.brand_filters:
        brand_scope = set(resolution.brand_filters)
        model_candidates = [row for row in catalog if row["brand"] in brand_scope]
    scoped_models = list(dict.fromkeys(row["model_subbrand"] for row in model_candidates if row["model_subbrand"]))
    if not scoped_models:
        scoped_models = unique_models

    matched_models: list[str] = []
    best_model_from_question, full_question_score, _ = _choose_candidates(raw_question, scoped_models)
    if _should_auto_accept_candidate(raw_question, best_model_from_question, full_question_score, scoped_models):
        matched_models.append(best_model_from_question)
        resolution.model_input = best_model_from_question
        resolution.matched_model_subbrand = best_model_from_question
        resolution.model_score = full_question_score
    else:
        family_match = _find_single_family_candidate(raw_question, scoped_models)
        if family_match:
            matched_models.append(family_match)
            resolution.model_input = resolution.model_input or family_match
            resolution.matched_model_subbrand = family_match
            resolution.model_score = max(resolution.model_score, _score_candidate(raw_question, family_match))

    for hint in _extract_identifier_hints(raw_question):
        best_model, model_score, strong_matches = _choose_candidates(hint, scoped_models)
        if model_score >= _HIGH_MATCH_THRESHOLD:
            matched_models.extend(strong_matches or ([best_model] if best_model else []))
            resolution.model_input = resolution.model_input or hint
            resolution.matched_model_subbrand = resolution.matched_model_subbrand or best_model
            resolution.model_score = max(resolution.model_score, model_score)
        elif _should_auto_accept_candidate(hint, best_model, model_score, scoped_models):
            matched_models.append(best_model)
            resolution.model_input = resolution.model_input or hint
            resolution.matched_model_subbrand = resolution.matched_model_subbrand or best_model
            resolution.model_score = max(resolution.model_score, model_score)

    matched_models = _merge_unique(matched_models)
    if matched_models:
        resolution.model_subbrand_filters = matched_models
    elif len(scoped_models) == 1 and not _question_has_specific_model_hint(raw_question):
        only_model = scoped_models[0]
        resolution.model_input = resolution.model_input or only_model
        resolution.matched_model_subbrand = only_model
        resolution.model_score = max(resolution.model_score, 0.60)
        resolution.model_subbrand_filters = [only_model]

    if not resolution.brand_filters and resolution.model_subbrand_filters:
        inferred_brands = _merge_unique(
            [
                row["brand"]
                for row in catalog
                if row["model_subbrand"] in set(resolution.model_subbrand_filters)
            ]
        )
        if inferred_brands:
            resolution.brand_filters = inferred_brands
            resolution.matched_brand = inferred_brands[0]
            resolution.brand = inferred_brands[0]
            resolution.brand_score = max(resolution.brand_score, 0.74)

    if not resolution.brand_filters and not resolution.model_subbrand_filters:
        # Fallback: allow unfiltered retrieval instead of hard-failing.
        # The vector search may still find relevant content even when
        # brand/model cannot be resolved from the question text.
        logger.info(
            "[INTENT] No brand/model filters matched (heuristic); "
            "falling back to unfiltered retrieval for query='%s'",
            raw_question[:120],
        )
        resolution.normalized_query = preprocess_query(raw_question)
        resolution.extraction_confidence = 0.30

    effective_brand = resolution.matched_brand or resolution.brand
    effective_model = resolution.model_input or resolution.matched_model_subbrand
    sanitized_topic = _sanitize_topic_text(
        raw_question,
        raw_question,
        [effective_brand, effective_model, *resolution.model_subbrand_filters],
    )
    resolution.topic = sanitized_topic
    resolution.normalized_query = _build_normalized_query(
        raw_question=raw_question,
        brand=effective_brand,
        model_input=effective_model,
        intent=resolution.intent,
        topic=sanitized_topic or raw_question,
    )
    resolution.extraction_confidence = max(resolution.brand_score, resolution.model_score, 0.55)
    return resolution


def _build_normalized_query(
    *,
    raw_question: str,
    brand: str,
    model_input: str,
    intent: str,
    topic: str,
) -> str:
    parts: list[str] = []
    if brand:
        parts.append(brand)
    if model_input:
        parts.append(model_input)

    intent_term = _INTENT_QUERY_TERMS.get(intent or "", "")
    if intent_term:
        parts.append(intent_term)
    elif intent and intent != "unknown":
        parts.append(intent.replace("_", " "))

    if topic:
        parts.append(topic)
    elif raw_question:
        parts.append(raw_question)

    return preprocess_query(" ".join(part for part in parts if part).strip())


def _load_scope_catalog(db_pool, collection: str) -> list[dict[str, str]]:
    if db_pool is None:
        return []

    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT brand, model_subbrand
                FROM documents
                WHERE collection = %s
                  AND COALESCE(metadata->>'chunk_type', '') <> 'golden_qa'
                  AND COALESCE(metadata->>'readable', 'true') <> 'false'
                  AND COALESCE(brand, '') <> ''
                  AND COALESCE(model_subbrand, '') <> ''
                ORDER BY brand, model_subbrand
                """,
                (collection,),
            )
            return [
                {
                    "brand": _normalize_ws(brand),
                    "model_subbrand": _normalize_ws(model_subbrand),
                }
                for brand, model_subbrand in cur.fetchall()
                if _normalize_ws(brand) and _normalize_ws(model_subbrand)
            ]
    finally:
        db_pool.putconn(conn)


def _extract_intent_payload(question: str, *, intent_llm, history_section: str = "") -> tuple[dict[str, Any], str, str]:
    if intent_llm is None:
        return {}, "", "intent_llm_unavailable"

    chain = build_intent_extraction_prompt() | intent_llm | StrOutputParser()
    raw_output = call_llm_with_retry(
        lambda: chain.invoke(
            {
                "history_section": history_section,
                "question": question,
            }
        ),
        max_retries=2,
        base_wait=0.5,
    )
    parsed = _parse_structured_intent_output(raw_output)
    return parsed, str(raw_output or ""), "intent_llm_structured"


def resolve_question_intent(
    question: str,
    *,
    db_pool,
    collection: str,
    intent_llm=None,
    history_section: str = "",
) -> IntentResolution:
    raw_question = _normalize_ws(question)
    if not raw_question:
        return IntentResolution(
            status="empty_question",
            source="empty_question",
            raw_question="",
            reply="Please enter a question.",
        )

    catalog = _load_scope_catalog(db_pool, collection)

    try:
        payload, raw_output, source = _extract_intent_payload(
            raw_question,
            intent_llm=intent_llm,
            history_section=history_section,
        )
    except Exception as exc:
        logger.warning("[INTENT] Extraction failed: %s", exc)
        return _build_heuristic_intent_resolution(
            raw_question,
            catalog=catalog,
            source="intent_llm_error",
        )

    brand_input = _normalize_ws(payload.get("brand", ""))
    model_input = _normalize_ws(payload.get("model_subbrand") or payload.get("model") or "")
    intent = _normalize_intent_label(payload.get("intent", ""))
    topic = _normalize_ws(payload.get("topic", ""))
    structured_normalized_query = preprocess_query(_normalize_ws(payload.get("normalized_query", "")))
    confidence = _safe_float(payload.get("confidence"))

    resolution = IntentResolution(
        status="ok",
        source=source,
        raw_question=raw_question,
        extraction_confidence=confidence,
        brand=brand_input,
        model_input=model_input,
        intent=intent,
        topic=topic,
        raw_extractor_output=raw_output,
    )

    if not any([brand_input, model_input, topic, structured_normalized_query]):
        return _build_heuristic_intent_resolution(
            raw_question,
            catalog=catalog,
            source="intent_llm_empty",
        )

    brands = sorted({row["brand"] for row in catalog if row["brand"]})
    question_brand, question_brand_score = _infer_brand_from_question(raw_question, brands)

    if not brand_input and question_brand_score >= _HIGH_MATCH_THRESHOLD:
        brand_input = question_brand
        resolution.brand = brand_input

    if brand_input:
        best_brand, brand_score, strong_brand_matches = _choose_candidates(brand_input, brands)
        resolution.matched_brand = best_brand
        resolution.brand_score = brand_score
        if brand_score >= _HIGH_MATCH_THRESHOLD:
            resolution.brand_filters = strong_brand_matches or ([best_brand] if best_brand else [])
        elif _should_auto_accept_candidate(brand_input, best_brand, brand_score, brands):
            resolution.brand_filters = [best_brand]
        elif brand_score >= _MEDIUM_MATCH_THRESHOLD and best_brand:
            resolution.status = "clarify_brand"
            resolution.clarification = f"Did you mean the brand {best_brand}?"
            resolution.reply = resolution.clarification
            resolution.suggestions = [best_brand]
            return resolution
        else:
            # Fallback: proceed with brand only (no model filter).
            logger.info(
                "[INTENT] Brand match too low (score=%.3f); "
                "falling back to unfiltered retrieval",
                brand_score,
            )
            resolution.brand = ""
            resolution.matched_brand = ""
            resolution.brand_score = 0.0
            resolution.brand_filters = []
    elif len(brands) == 1:
        resolution.brand = brands[0]
        resolution.matched_brand = brands[0]
        resolution.brand_score = max(resolution.brand_score, 0.60)
        resolution.brand_filters = [brands[0]]

    model_candidates = catalog
    if resolution.brand_filters:
        brand_scope = set(resolution.brand_filters)
        model_candidates = [row for row in catalog if row["brand"] in brand_scope]

    unique_models = list(dict.fromkeys(row["model_subbrand"] for row in model_candidates if row["model_subbrand"]))
    if not model_input:
        for hint in _extract_identifier_hints(raw_question):
            best_model_hint, model_hint_score, strong_hint_matches = _choose_candidates(hint, unique_models)
            if model_hint_score >= _MEDIUM_MATCH_THRESHOLD and best_model_hint:
                model_input = hint
                resolution.model_input = hint
                resolution.matched_model_subbrand = best_model_hint
                resolution.model_score = model_hint_score
                if model_hint_score >= _HIGH_MATCH_THRESHOLD:
                    resolution.model_subbrand_filters = strong_hint_matches or [best_model_hint]
                break
        if (
            not model_input
            and not resolution.model_subbrand_filters
            and len(unique_models) == 1
            and not _question_has_specific_model_hint(raw_question)
        ):
            only_model = unique_models[0]
            resolution.model_input = only_model
            resolution.matched_model_subbrand = only_model
            resolution.model_score = max(resolution.model_score, 0.60)
            resolution.model_subbrand_filters = [only_model]

    if model_input and not resolution.model_subbrand_filters:
        best_model, model_score, strong_model_matches = _choose_candidates(model_input, unique_models)
        resolution.matched_model_subbrand = best_model
        resolution.model_score = model_score
        family_match = _find_single_family_candidate(model_input or raw_question, unique_models)
        family_match_score = _score_candidate(model_input or raw_question, family_match) if family_match else 0.0

        if model_score >= _HIGH_MATCH_THRESHOLD:
            resolution.model_subbrand_filters = strong_model_matches or ([best_model] if best_model else [])
        elif _should_auto_accept_candidate(model_input, best_model, model_score, unique_models):
            resolution.model_subbrand_filters = [best_model]
        elif family_match and family_match_score >= 0.60:
            resolution.matched_model_subbrand = family_match
            resolution.model_score = max(model_score, family_match_score)
            resolution.model_subbrand_filters = [family_match]
        elif model_score >= _MEDIUM_MATCH_THRESHOLD and best_model:
            resolution.status = "clarify_model"
            resolution.clarification = f"Did you mean this version: {best_model}?"
            resolution.reply = resolution.clarification
            resolution.suggestions = [best_model]
            return resolution
        else:
            # Fallback: proceed without model filter.
            logger.info(
                "[INTENT] Model match too low (score=%.3f, input='%s'); "
                "proceeding without model filter",
                model_score,
                model_input[:60],
            )

    if not resolution.brand_filters and resolution.model_subbrand_filters:
        inferred_brands = sorted(
            {
                row["brand"]
                for row in catalog
                if row["model_subbrand"] in set(resolution.model_subbrand_filters)
            }
        )
        if len(inferred_brands) == 1:
            resolution.matched_brand = inferred_brands[0]
            resolution.brand_filters = inferred_brands

    effective_brand = resolution.matched_brand or resolution.brand
    effective_model = resolution.model_input or resolution.matched_model_subbrand
    sanitized_topic = _sanitize_topic_text(
        topic,
        raw_question,
        [
            effective_brand,
            effective_model,
            resolution.matched_model_subbrand,
        ],
    )
    fallback_query = _build_normalized_query(
        raw_question=raw_question,
        brand=effective_brand,
        model_input=effective_model,
        intent=resolution.intent,
        topic=sanitized_topic,
    )
    resolution.normalized_query = _prefer_non_empty(structured_normalized_query, fallback_query)
    resolution.topic = sanitized_topic or topic

    if not resolution.normalized_query:
        resolution.status = "unresolved"
        resolution.reply = "I don't understand the question, could you be more specific?"
        return resolution

    return resolution
