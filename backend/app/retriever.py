
import os
import json
import logging
from typing import List, Any

from pydantic import Field
from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document

from pgvector.psycopg2 import register_vector
from flashrank import Ranker, RerankRequest


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


class PostgresVectorRetriever(BaseRetriever):
    """
    ดึงเอกสารจากตาราง documents (pgvector)
    - ใช้ connection_pool (psycopg2.pool)
    - ลงทะเบียน register_vector(conn) ทุกครั้งก่อน query
    - คืน list[Document] พร้อม metadata['distance']
    """
    connection_pool: Any = Field(...)
    embedder: Any = Field(...)
    collection: str = Field(default="plcnext")
    limit: int = Field(default_factory=lambda: _env_int("RETRIEVE_LIMIT", 50))

    def _get_relevant_documents(self, query: str) -> List[Document]:
        # ฝั่ง embedder (SentenceTransformer) คืน numpy.ndarray / list ได้ → ใช้ได้ตรง ๆ
        query_vector = self.embedder.encode(query)

        conn = self.connection_pool.getconn()
        try:
            # สำคัญ: ลงทะเบียน vector type กับ connection นี้
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


class EnhancedFlashrankRerankRetriever(BaseRetriever):
    """
    ขั้น rerank (lexical+semantic) ด้วย Flashrank แล้วบวก domain-boost
    - base_retriever: เรียกหา candidates ก่อน
    - ranker: ms-marco-MiniLM-L-12-v2 (โหลด/แคชใน /app/models)
    - top_n: จำนวนผลลัพธ์สุดท้าย (env: RERANK_TOPN)
    """
    base_retriever: BaseRetriever = Field(...)
    ranker: Ranker = Field(
        default_factory=lambda: Ranker(
            model_name="ms-marco-MiniLM-L-12-v2", cache_dir="/app/models"
        )
    )
    top_n: int = Field(default_factory=lambda: _env_int("RERANK_TOPN", 8))

    # ---- ด้านล่างคือ heuristic ที่อ่านง่ายและปรับง่าย ----
    _PLC_TERMS = [
        "plcnext", "phoenix contact", "gds", "esm", "profinet", "axc f",
        "axc f 2152", "axc f 3152", "axc f 1152", "plcnext engineer"
    ]
    _PROTO_TERMS = [
        "protocol", "mode", "rs-485", "rs485", "profinet", "ethernet",
        "serial", "communication", "modbus", "tcp", "udp", "interface",
        "opcuA", "opc ua"
    ]

    def _calculate_domain_boost(self, doc: Document, query: str) -> float:
        txt = (doc.page_content or "").lower()
        q_tokens = (query or "").lower().split()

        boost = 0.0

        # 1) keyword จาก PLCnext domain
        plc_hits = sum(1 for t in self._PLC_TERMS if t in txt)
        boost += plc_hits * 0.10  # 0.1 ต่อคำ

        # 2) มี token จากคำถามโผล่ในเนื้อหาหรือไม่
        if any(tok in txt for tok in q_tokens if tok and len(tok) > 2):
            boost += 0.30

        # 3) protocol/mode สำคัญกับสายอุตสาหกรรม
        proto_hits = sum(1 for t in self._PROTO_TERMS if t in txt)
        if proto_hits > 0:
            boost += proto_hits * 0.50  # ให้หนักหน่อย

        # 4) ให้ golden/spec พิเศษ
        ctype = (doc.metadata or {}).get("chunk_type")
        if ctype == "golden_qa":
            boost += 10.0
        elif ctype == "spec_pair":
            boost += 0.20

        return boost

    def _get_relevant_documents(self, query: str) -> List[Document]:
        try:
            candidates = self.base_retriever.get_relevant_documents(query)
            if not candidates:
                return []

            passages = [
                {"id": i, "text": d.page_content, "meta": d.metadata}
                for i, d in enumerate(candidates)
            ]
            rr = RerankRequest(query=query, passages=passages)
            reranked = self.ranker.rerank(rr)

            scored = []
            for r in reranked:
                d = candidates[r["id"]]
                final_score = float(r["score"]) + self._calculate_domain_boost(d, query)
                scored.append({"doc": d, "score": final_score})

            scored.sort(key=lambda x: x["score"], reverse=True)
            return [x["doc"] for x in scored[: self.top_n]]

        except Exception as e:
            logging.error("🔥 Error in EnhancedFlashrankRerankRetriever: %s", e, exc_info=True)
            return []
