import os
import json
import logging
from typing import List, Any, Tuple

from pydantic import Field
from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document

from pgvector.psycopg2 import register_vector
import psycopg2  # noqa: F401 (ไว้ให้ชัดว่าใช้กับ connection_pool)
import numpy as np  # noqa: F401 (บางกรณีใช้ตรวจชนิด)

# flashrank เป็น optional — ถ้าไม่มีจะ fallback ไปใช้ base score
try:
    from flashrank import Ranker, RerankRequest  # type: ignore
    _FLASHRANK_AVAILABLE = True
except Exception:
    _FLASHRANK_AVAILABLE = False


def _safe_load_json(val):
    """คืน dict เสมอ แม้ metadata จะเป็นสตริงหรือ None"""
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


# ===============================
# Base Vector Retriever (pgvector)
# ===============================
class PostgresVectorRetriever(BaseRetriever):
    """
    ดึงเอกสารจากตาราง documents (pgvector)
    - ใช้ connection_pool (psycopg2.pool) ที่ main.py เตรียมไว้
    - register_vector(conn) ทุกครั้งก่อน query
    - คืน list[Document] พร้อม metadata['distance']
    """
    connection_pool: Any = Field(...)
    embedder: Any = Field(...)
    collection: str = Field(default="plcnext")
    limit: int = Field(default_factory=lambda: _env_int("RETRIEVE_LIMIT", 50))

    def _get_relevant_documents(self, query: str) -> List[Document]:
        # embedder ของคุณ (SentenceTransformer) คืน numpy.ndarray
        query_vector = self.embedder.encode(query)

        conn = self.connection_pool.getconn()
        try:
            register_vector(conn)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT content, metadata, embedding <-> %s AS distance
                    FROM documents
                    WHERE collection = %s
                    ORDER BY embedding <-> %s
                    LIMIT %s
                    """,
                    (query_vector, self.collection, query_vector, self.limit),
                )
                rows = cur.fetchall()

            docs: List[Document] = []
            for content, metadata, distance in rows:
                meta = _safe_load_json(metadata)
                meta["distance"] = float(distance)
                docs.append(Document(page_content=content, metadata=meta))
            return docs

        except Exception as e:
            logging.error("🔥 Error in PostgresVectorRetriever: %s", e, exc_info=True)
            return []
        finally:
            self.connection_pool.putconn(conn)


# ===============================
# Flashrank-based Reranker
# ===============================
class EnhancedFlashrankRerankRetriever(BaseRetriever):
    """
    ขั้น rerank (lexical+semantic) ด้วย Flashrank แล้วบวก domain-boost
    - base_retriever: เรียกหา candidates ก่อน
    - top_n: จำนวนผลลัพธ์สุดท้าย (env: RERANK_TOPN)
    - จำกัดจำนวนแคนดิเดตที่ส่งไป Flashrank ด้วย env: RERANK_CANDIDATES_MAX (ดีต่อความไว)
    """
    base_retriever: BaseRetriever = Field(...)
    top_n: int = Field(default_factory=lambda: _env_int("RERANK_TOPN", 8))

    # คำสำคัญเฉพาะโดเมน (boost)
    _PLC_TERMS = [
        "plcnext", "phoenix contact", "gds", "esm", "profinet", "axc f",
        "axc f 2152", "axc f 3152", "axc f 1152", "plcnext engineer"
    ]
    _PROTO_TERMS = [
        "protocol", "mode", "rs-485", "rs485", "profinet", "ethernet",
        "serial", "communication", "modbus", "tcp", "udp", "interface",
        "opcua", "opc ua"
    ]

    def _rank(self, query: str, docs: List[Document]) -> List[Tuple[float, Document]]:
        # 1) คะแนนจาก Flashrank (ถ้าใช้ได้) ไม่งั้นใช้ 1 - distance เป็น similarity
        if _FLASHRANK_AVAILABLE:
            try:
                ranker = Ranker(model_name="ms-marco-MiniLM-L-12-v2", cache_dir="/app/models")
                passages = [{"id": i, "text": d.page_content} for i, d in enumerate(docs)]
                req = RerankRequest(query=query, passages=passages)
                result = ranker.rerank(req)
                # ชื่อฟิลด์ของ flashrank บางเวอร์ชันอาจเป็น "id/score" หรือ "index/relevance_score"
                pairs: List[Tuple[float, Document]] = []
                for it in result:
                    idx = int(it.get("id", it.get("index")))
                    sc = float(it.get("score", it.get("relevance_score")))
                    pairs.append((sc, docs[idx]))
            except Exception as e:
                logging.warning("⚠️ Flashrank failed, fallback to base scores: %s", e)
                pairs = [(1.0 - float(d.metadata.get("distance", 1.0)), d) for d in docs]
        else:
            pairs = [(1.0 - float(d.metadata.get("distance", 1.0)), d) for d in docs]

        # 2) domain-boost (นุ่มลง + capped)
        boosted: List[Tuple[float, Document]] = []
        q_tokens = (query or "").lower().split()
        for s, d in pairs:
            text_low = (d.page_content or "").lower()
            bonus = 0.0
            if any(w in text_low for w in self._PLC_TERMS):
                bonus += 0.10
            if any(tok in text_low for tok in q_tokens if tok and len(tok) > 2):
                bonus += 0.20
            proto_hits = sum(1 for t in self._PROTO_TERMS if t in text_low)
            if proto_hits > 0:
                bonus += min(0.30, proto_hits * 0.08)  # cap 0.30
            ctype = (d.metadata or {}).get("chunk_type")
            if ctype == "golden_qa":
                bonus += 10.0
            elif ctype == "spec_pair":
                bonus += 0.15
            boosted.append((s + bonus, d))

        boosted.sort(key=lambda x: x[0], reverse=True)
        return boosted

    def _get_relevant_documents(self, query: str) -> List[Document]:
        # ✅ แก้จาก get_relevant_documents เป็น invoke
        cand = self.base_retriever.invoke(query) or []
        if not cand:
            return []
        # ✅ จำกัดจำนวนที่ส่งเข้า Flashrank เพื่อความไว/เสถียร
        cap = _env_int("RERANK_CANDIDATES_MAX", 32)
        ranked = self._rank(query, cand[:cap])
        
        # Store score in metadata
        results = []
        for score, doc in ranked[:self.top_n]:
            doc.metadata["score"] = score
            results.append(doc)
        return results


# ===============================
# No-op Reranker (สำหรับ A/B test)
# ===============================
class NoRerankRetriever(BaseRetriever):
    """
    ไม่ทำ rerank ใด ๆ — ส่งต่อผลจาก base_retriever แล้วตัด Top-N
    """
    base_retriever: BaseRetriever = Field(...)
    top_n: int = Field(default=8)

    def _get_relevant_documents(self, query: str) -> List[Document]:
        # ✅ แก้จาก get_relevant_documents เป็น invoke
        docs = self.base_retriever.invoke(query) or []
        return docs[: self.top_n]