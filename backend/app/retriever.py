import os
import json
import logging
import re
from typing import List, Any, Tuple

from pydantic import Field
from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document

from pgvector.psycopg2 import register_vector
import psycopg2  # noqa: F401 (used with connection_pool)

# flashrank is optional - falls back to base score if not available
try:
    from flashrank import Ranker, RerankRequest  # type: ignore
    _FLASHRANK_AVAILABLE = True
except Exception:
    _FLASHRANK_AVAILABLE = False

# Singleton ranker instance for performance
_ranker_instance = None
logger = logging.getLogger(__name__)

def _get_ranker():
    """Get or create singleton Ranker instance."""
    global _ranker_instance
    if _ranker_instance is None and _FLASHRANK_AVAILABLE:
        model = os.getenv("RERANK_MODEL", "ms-marco-MiniLM-L-12-v2")
        cache_dir = os.getenv("MODEL_CACHE", "/app/models")
        _ranker_instance = Ranker(model_name=model, cache_dir=cache_dir)
        logger.info("[Ranker] Initialized: %s", model)
    return _ranker_instance


def _safe_load_json(val):
    """Always returns a dict, even if metadata is a string or None."""
    if not val:
        return {}
    if isinstance(val, dict):
        return val
    try:
        return json.loads(val)
    except Exception:
        return {"_raw_meta": str(val)}


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except Exception:
        return default


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except Exception:
        return default


def _env_bool(key: str, default: bool = False) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return str(val).strip().lower() in ("1", "true", "yes", "on")


def _distance_to_similarity(distance: float) -> float:
    """
    Convert pgvector L2 distance to bounded similarity in [0, 1].
    This is safer than `1 - distance`, which can become negative.
    """
    try:
        d = max(0.0, float(distance))
    except Exception:
        d = 1.0
    return 1.0 / (1.0 + d)


# ===============================
# Reranking Boost Configuration
# ===============================
class RerankBoostConfig:
    """Centralized configuration for reranking boost values."""
    
    # Domain-specific boosts
    PLC_TERM_BOOST = _env_float("RERANK_BOOST_PLC_TERM", 0.10)
    QUERY_TOKEN_BOOST = _env_float("RERANK_BOOST_QUERY_TOKEN", 0.20)
    PROTOCOL_TERM_BOOST_PER_HIT = _env_float("RERANK_BOOST_PROTOCOL_PER_HIT", 0.08)
    PROTOCOL_TERM_BOOST_MAX = _env_float("RERANK_BOOST_PROTOCOL_MAX", 0.30)
    
    # Chunk type boosts
    # Keep this modest so Golden QA helps, but does not dominate all retrieval.
    GOLDEN_QA_BOOST = _env_float("RERANK_BOOST_GOLDEN_QA", 0.35)
    SPEC_PAIR_BOOST = _env_float("RERANK_BOOST_SPEC_PAIR", 0.15)
    COMMAND_TABLE_BOOST = _env_float("RERANK_BOOST_COMMAND_TABLE", 0.45)
    COMMAND_TOKEN_BOOST = _env_float("RERANK_BOOST_COMMAND_TOKEN", 0.60)
    COMMAND_HINT_BOOST = _env_float("RERANK_BOOST_COMMAND_HINT", 0.25)

    # Error/event code boost
    ERROR_CODE_BOOST = _env_float("RERANK_BOOST_ERROR_CODE", 2.0)
    MAX_TOTAL_BOOST = _env_float("RERANK_BOOST_MAX_TOTAL", 1.5)


# ===============================
# Base Vector Retriever (pgvector)
# ===============================
class PostgresVectorRetriever(BaseRetriever):
    """
    Retrieve documents from the 'documents' table (pgvector).
    - Uses connection_pool (psycopg2.pool) prepared by main.py
    - Calls register_vector(conn) before each query
    - Returns list[Document] with metadata['distance']
    """
    connection_pool: Any = Field(...)
    embedder: Any = Field(...)
    collection: str = Field(default="plcnext")
    limit: int = Field(default_factory=lambda: _env_int("RETRIEVE_LIMIT", 50))
    include_golden_qa: bool = Field(default_factory=lambda: _env_bool("RETRIEVE_INCLUDE_GOLDEN_QA", False))
    brand_filters: List[str] = Field(default_factory=list)
    model_subbrand_filters: List[str] = Field(default_factory=list)

    def _get_relevant_documents(self, query: str) -> List[Document]:
        # SentenceTransformer embedder returns numpy.ndarray
        query_vector = self.embedder.encode(query)

        conn = self.connection_pool.getconn()
        try:
            register_vector(conn)
            with conn.cursor() as cur:
                where_clauses = [
                    "collection = %s",
                    "COALESCE(metadata->>'readable', 'true') <> 'false'",
                ]
                params: list[Any] = [self.collection]

                if not self.include_golden_qa:
                    where_clauses.append("COALESCE(metadata->>'chunk_type', '') <> 'golden_qa'")

                if self.brand_filters:
                    where_clauses.append("brand = ANY(%s)")
                    params.append(self.brand_filters)

                if self.model_subbrand_filters:
                    where_clauses.append("model_subbrand = ANY(%s)")
                    params.append(self.model_subbrand_filters)

                sql = f"""
                    SELECT content, metadata, embedding <-> %s AS distance
                    FROM documents
                    WHERE {' AND '.join(where_clauses)}
                    ORDER BY embedding <-> %s
                    LIMIT %s
                """
                cur.execute(sql, [query_vector, *params, query_vector, self.limit])
                rows = cur.fetchall()

            docs: List[Document] = []
            for content, metadata, distance in rows:
                meta = _safe_load_json(metadata)
                meta["distance"] = float(distance)
                docs.append(Document(page_content=content, metadata=meta))
            return docs

        except Exception as e:
            logger.error("Error in PostgresVectorRetriever: %s", e, exc_info=True)
            return []
        finally:
            self.connection_pool.putconn(conn)


# ===============================
# Flashrank-based Reranker
# ===============================
class EnhancedFlashrankRerankRetriever(BaseRetriever):
    """
    Rerank stage (lexical+semantic) using Flashrank with domain-boost.
    - base_retriever: first retrieves candidates
    - top_n: number of final results (env: RERANK_TOPN)
    - Limits candidates sent to Flashrank via env: RERANK_CANDIDATES_MAX (for speed/stability)
    """
    base_retriever: BaseRetriever = Field(...)
    top_n: int = Field(default_factory=lambda: _env_int("RERANK_TOPN", 8))

    # Domain-specific keywords for boosting
    _PLC_TERMS = [
        # Phoenix Contact
        "plcnext", "phoenix contact", "gds", "esm", "profinet", "axc f",
        "axc f 2152", "axc f 3152", "axc f 1152", "plcnext engineer",
        # Mitsubishi
        "melsec", "melsecnet", "melsecnet/h", "fx3", "fx3u", "fx3g", "iq-r", "rcpu", "qcpu", "lcpu",
        "cc-link", "cc link", "edgecross", "data collector", "gx works",
        "iq edgecross", "mitsubishi", "qj71", "qj72", "qj71lp21", "qj71br11", "network module"
    ]
    _PROTO_TERMS = [
        "protocol", "mode", "rs-485", "rs485", "profinet", "ethernet",
        "serial", "communication", "modbus", "tcp", "udp", "interface",
        "opcua", "opc ua"
    ]

    def _rank(self, query: str, docs: List[Document]) -> List[Tuple[float, Document]]:
        # 1) Get scores from Flashrank (if available), otherwise use 1 - distance as similarity
        ranker = _get_ranker()
        if ranker is not None:
            try:
                passages = [{"id": i, "text": d.page_content} for i, d in enumerate(docs)]
                req = RerankRequest(query=query, passages=passages)
                result = ranker.rerank(req)
                # Field names may be "id/score" or "index/relevance_score" depending on flashrank version
                pairs: List[Tuple[float, Document]] = []
                for it in result:
                    idx = int(it.get("id", it.get("index")))
                    sc = float(it.get("score", it.get("relevance_score")))
                    pairs.append((sc, docs[idx]))
            except Exception as e:
                logger.warning("Flashrank failed, using distance-based fallback scores: %s", e)
                pairs = [(_distance_to_similarity(d.metadata.get("distance", 1.0)), d) for d in docs]
        else:
            pairs = [(_distance_to_similarity(d.metadata.get("distance", 1.0)), d) for d in docs]

        # 2) Apply domain-specific boosts (soft + capped)
        boosted: List[Tuple[float, Document]] = []
        # Keep two-letter command tokens (e.g., BR/BW) while filtering noisy stopwords.
        raw_tokens = re.findall(r"[a-z0-9]+", (query or "").lower())
        two_char_allowlist = {"br", "bw", "wr", "ww", "rr", "rq", "st", "fx"}
        two_char_stopwords = {"an", "as", "at", "by", "do", "if", "in", "is", "it", "of", "on", "or", "to"}
        q_tokens = [
            tok
            for tok in raw_tokens
            if len(tok) > 2 or (len(tok) == 2 and tok in two_char_allowlist and tok not in two_char_stopwords)
        ]
        q_token_set = set(q_tokens)
        query_upper = (query or "").upper()
        query_low = (query or "").lower()
        command_tokens = {tok for tok in q_token_set if tok in {"br", "bw", "wr", "ww", "rr", "rq"}}
        command_query = bool(command_tokens) or any(
            phrase in query_low
            for phrase in ("computer command", "ascii code", "bit read", "bit write", "objective device")
        )
        
        # Extract error/event codes from query (pattern: letter + numbers + H, e.g., F800H, 9801H)
        code_pattern = re.compile(r'\b[A-F0-9]{4,5}H\b', re.IGNORECASE)
        query_codes = set(code_pattern.findall(query_upper))
        
        for s, d in pairs:
            text_low = (d.page_content or "").lower()
            text_upper = (d.page_content or "").upper()
            bonus = 0.0
            
            # HIGH PRIORITY: Exact error/event code match (e.g., F800H, F389H)
            if query_codes:
                chunk_codes = set(code_pattern.findall(text_upper))
                matching_codes = query_codes & chunk_codes
                if matching_codes:
                    bonus += RerankBoostConfig.ERROR_CODE_BOOST
            
            if any(w in text_low for w in self._PLC_TERMS):
                bonus += RerankBoostConfig.PLC_TERM_BOOST
            if q_token_set:
                matched = sum(1 for tok in q_token_set if tok in text_low)
                if matched > 0:
                    # Partial match scoring: scales bonus by token coverage ratio.
                    coverage = matched / len(q_token_set)
                    bonus += RerankBoostConfig.QUERY_TOKEN_BOOST * coverage
            proto_hits = sum(1 for t in self._PROTO_TERMS if t in text_low)
            if proto_hits > 0:
                bonus += min(
                    RerankBoostConfig.PROTOCOL_TERM_BOOST_MAX,
                    proto_hits * RerankBoostConfig.PROTOCOL_TERM_BOOST_PER_HIT
                )
            ctype = (d.metadata or {}).get("chunk_type")
            if ctype == "golden_qa":
                bonus += RerankBoostConfig.GOLDEN_QA_BOOST
            elif ctype == "spec_pair":
                bonus += RerankBoostConfig.SPEC_PAIR_BOOST

            if command_query:
                if ctype == "table":
                    bonus += RerankBoostConfig.COMMAND_TABLE_BOOST
                if command_tokens and any(re.search(rf"\b{re.escape(tok)}\b", text_low) for tok in command_tokens):
                    bonus += RerankBoostConfig.COMMAND_TOKEN_BOOST
                if "objective device symbol" in text_low or "command" in text_low:
                    bonus += RerankBoostConfig.COMMAND_HINT_BOOST

            bounded_bonus = min(RerankBoostConfig.MAX_TOTAL_BOOST, bonus)
            boosted.append((s + bounded_bonus, d))

        boosted.sort(key=lambda x: x[0], reverse=True)
        return boosted

    def _get_relevant_documents(self, query: str) -> List[Document]:
        # Use invoke() instead of deprecated get_relevant_documents()
        cand = self.base_retriever.invoke(query) or []
        if not cand:
            return []
        # Limit candidates sent to Flashrank for speed/stability
        cap = _env_int("RERANK_CANDIDATES_MAX", 32)
        ranked = self._rank(query, cand[:cap])
        
        # Store score in metadata
        results = []
        for score, doc in ranked[:self.top_n]:
            doc.metadata["score"] = score
            results.append(doc)
        return results
