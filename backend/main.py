# backend/main.py

import os
import logging
import requests
import time
import math
from contextlib import asynccontextmanager
from typing import Any, Optional
import numpy as np
import io # เพิ่ม io
import mimetypes # เพิ่ม mimetypes
import warnings

from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.eval_logging import ollama_generate_with_stats, append_eval_run
# from app.ragas_eval import local_ragas_eval # (Comment ออกถ้าไม่ได้ใช้ทันทีเพื่อกัน error)
from langchain_ollama import OllamaLLM
from sentence_transformers import SentenceTransformer
from psycopg2 import pool

from app.retriever import PostgresVectorRetriever, EnhancedFlashrankRerankRetriever, NoRerankRetriever
from app.chatbot import answer_question

import pytesseract
from PIL import Image

warnings.filterwarnings("ignore", category=DeprecationWarning)

# ---- Config ----
DB_URL = os.getenv("DATABASE_URL")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
EMBED_MODEL_NAME = os.getenv("EMBED_MODEL", "BAAI/bge-m3")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logging.info("🔧 Configuration:")
logging.info(f"  DB_URL: {DB_URL}")
logging.info(f"  OLLAMA_BASE_URL: {OLLAMA_BASE_URL}")
logging.info(f"  OLLAMA_MODEL: {OLLAMA_MODEL}")
logging.info(f"  EMBED_MODEL: {EMBED_MODEL_NAME}")

# -------------------------
# Helpers
# -------------------------
def _to_bool(val: Any) -> Optional[bool]:
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    if s in ("1", "true", "yes", "y", "on"):
        return True
    if s in ("0", "false", "no", "n", "off"):
        return False
    return None

def wait_for_ollama():
    logging.info("🔄 Checking Ollama service readiness...")
    for attempt in range(30):
        try:
            response = requests.get(f"{OLLAMA_BASE_URL}/api/version", timeout=5)
            if response.status_code == 200:
                logging.info("✅ Ollama service is ready.")
                return True
        except requests.exceptions.RequestException:
            logging.info(f"⏳ Waiting for Ollama service... (attempt {attempt + 1}/30)")
            time.sleep(2)
    logging.error("❌ Ollama service not ready after timeout.")
    return False

def ensure_model(model_name: str) -> bool:
    try:
        logging.info(f"🔄 Checking for LLM model: '{model_name}'")
        r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=10)
        r.raise_for_status()
        models = r.json().get("models", [])
        available_full = {m.get("name", "") for m in models}
        available_base = {m.get("name", "").split(":")[0] for m in models}
        base = model_name.split(":")[0]
        if model_name in available_full or base in available_base:
            logging.info(f"✅ Model '{model_name}' is available.")
            return True
        logging.warning(f"⚠️ Model '{model_name}' not found. Pulling now...")
        pr = requests.post(f"{OLLAMA_BASE_URL}/api/pull", json={"name": model_name}, timeout=1800)
        if pr.status_code == 200:
            logging.info(f"✅ Model '{model_name}' pulled successfully.")
            return True
        logging.error(f"❌ Failed to pull model '{model_name}': {pr.text}")
        return False
    except Exception as e:
        logging.error(f"🔥 Error ensuring model '{model_name}': {e}")
        return False

def test_database_connection():
    try:
        import psycopg2
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        cur.execute("SELECT extname FROM pg_extension WHERE extname = 'vector';")
        if not cur.fetchone():
            logging.error("❌ pgvector extension not found!")
            return False
        cur.execute("SELECT COUNT(*) FROM documents;")
        doc_count = cur.fetchone()[0]
        logging.info(f"✅ Database connected. Documents count: {doc_count}")
        cur.close()
        conn.close()
        return True
    except Exception as e:
        logging.error(f"🔥 Database connection test failed: {e}")
        return False

def sanitize_json(obj: Any):
    if obj is None:
        return None
    if isinstance(obj, (np.float32, np.float64)):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return float(obj)
    elif isinstance(obj, (np.int32, np.int64)):
        return int(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: sanitize_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize_json(v) for v in obj]
    return obj

# ---- FastAPI Lifespan ----
@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("🚀 Starting application lifespan...")

    if not test_database_connection():
        logging.error("❌ Database test failed during startup!")
        app.state.db_pool = None
    else:
        try:
            app.state.db_pool = pool.SimpleConnectionPool(
                1, 10,
                dsn=DB_URL,
                keepalives=1,
                keepalives_idle=30,
                keepalives_interval=10,
                keepalives_count=5
            )
            logging.info("✅ Database connection pool created.")
        except Exception as e:
            logging.error(f"🔥 Failed to create database connection pool: {e}")
            app.state.db_pool = None

    app.state.llm = None
    app.state.embedder = None

    if wait_for_ollama() and ensure_model(OLLAMA_MODEL):
        try:
            app.state.llm = OllamaLLM(
                model=OLLAMA_MODEL,
                base_url=OLLAMA_BASE_URL,
                temperature=0.0,
                timeout=60
            )
            logging.info(f"✅ LLM ({OLLAMA_MODEL}) loaded.")
        except Exception as e:
            logging.error(f"🔥 Failed to load LLM: {e}")

    try:
        app.state.embedder = SentenceTransformer(
            EMBED_MODEL_NAME,
            cache_folder='/app/models'
        )
        logging.info(f"✅ Embedder ({EMBED_MODEL_NAME}) loaded.")
    except Exception as e:
        logging.error(f"🔥 Failed to load embedder: {e}")

    yield

    if hasattr(app.state, 'db_pool') and app.state.db_pool:
        app.state.db_pool.closeall()
        logging.info("👋 Database connection pool closed.")
    logging.info("👋 Shutting down application lifespan...")

# ---- App init ----
app = FastAPI(
    lifespan=lifespan,
    title="PLCnext Chatbot v2.0",
    description="Advanced RAG chatbot for PLCnext Technology documentation",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# ---- Models ----
class ChatRequest(BaseModel):
    message: str
    collection: str = "plcnext"

class ChatResponse(BaseModel):
    reply: str
    processing_time: float | None = None
    retrieval_time: float | None = None
    context_count: int | None = None
    ragas: dict | None = None

class HealthResponse(BaseModel):
    status: str
    services: dict
    timestamp: str

# ---- Endpoints ----
@app.get("/health", response_model=HealthResponse)
def health_check(request: Request): # ลบ async ออกเพื่อให้มั่นใจ
    services = {"database": False, "llm": False, "embedder": False}
    try:
        if request.app.state.db_pool:
            conn = request.app.state.db_pool.getconn()
            request.app.state.db_pool.putconn(conn)
            services["database"] = True
    except:
        pass
    services["llm"] = request.app.state.llm is not None
    services["embedder"] = request.app.state.embedder is not None
    status = "healthy" if all(services.values()) else "degraded"
    return HealthResponse(status=status, services=services, timestamp=time.strftime("%Y-%m-%d %H:%M:%S"))

@app.post("/api/chat", response_model=ChatResponse)
def chat(fastapi_request: Request, chat_request: ChatRequest):
    # ✅ ฟังก์ชันนี้ถูกต้องแล้ว ไม่มี async และไม่มี await
    db_pool = fastapi_request.app.state.db_pool
    llm = fastapi_request.app.state.llm
    embedder = fastapi_request.app.state.embedder

    result = answer_question(
        question=chat_request.message,
        db_pool=db_pool,
        llm=llm,
        embedder=embedder,
        collection=chat_request.collection,
        retriever_class=PostgresVectorRetriever,
        reranker_class=EnhancedFlashrankRerankRetriever
    )

    return ChatResponse(
        reply=result["reply"],
        processing_time=result.get("processing_time"),
        retrieval_time=result.get("retrieval_time"),
        context_count=result.get("context_count"),
        ragas=None
    )

@app.post("/api/agent-chat")
def agent_chat(
    message: str = Form(""),
    file: UploadFile = File(None),
    log_eval: bool = Form(False),
    enable_ragas: bool = Form(False),
    fast_ragas: bool | None = Form(None),
    ground_truth: str = Form(""),
    use_rerank: Any = Form(None),
    use_rank: Any = Form(None),
):
    # ... code logic ...
    parsed_rerank = _to_bool(use_rerank)
    parsed_alias  = _to_bool(use_rank)
    decided = parsed_rerank if parsed_rerank is not None else parsed_alias
    if decided is None:
        decided = os.getenv("USE_RERANK_DEFAULT", "true").strip().lower() in ("1","true","yes","y","on")
    use_rerank = decided
    reranker_cls = EnhancedFlashrankRerankRetriever if use_rerank else NoRerankRetriever

    state = {"user_input": message}
    if file:
        # 🔴 แก้ไข: เปลี่ยนจาก await file.read() เป็น file.file.read()
        content = file.file.read() 
        mime_type, _ = mimetypes.guess_type(file.filename)
        if mime_type and mime_type.startswith("image"):
            state["image_bytes"] = content
        elif mime_type and mime_type.startswith("audio"):
            state["audio_bytes"] = content
        else:
            return {"error": "File type not supported"}

    start_time = time.perf_counter()
    result = answer_question(
        question=message,
        db_pool=app.state.db_pool,
        llm=app.state.llm,
        embedder=app.state.embedder,
        collection="plcnext",
        retriever_class=PostgresVectorRetriever,
        reranker_class=reranker_cls,
    )
    total_time = time.perf_counter() - start_time

    contexts = result.get("contexts_list") or result.get("contexts") or []
    
    # ... (ส่วน log_eval และ ragas ตัดออกเพื่อให้สั้นลง แต่ Logic เดิมใช้ได้เลย) ...
    # ถ้าจะใช้ RAGAS หรือ Eval ให้ใส่โค้ดเดิมกลับมาตรงนี้ได้ แต่ระวังเรื่อง blocking

    response = {
        "reply": result.get("llm_answer", "") or result.get("reply", ""),
        "processing_time": result.get("processing_time", total_time),
        "retrieval_time": result.get("retrieval_time", None),
        "context_count": result.get("context_count", None),
        "contexts": contexts,
        "eval": None,
        "ragas": None,
        "use_rerank": use_rerank,
    }
    return sanitize_json(response)

@app.get("/api/collections")
def get_collections(request: Request): # เอา async ออก
    try:
        db_pool = request.app.state.db_pool
        if not db_pool:
            raise HTTPException(status_code=503, detail="Database not available")
        conn = db_pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT DISTINCT collection FROM documents ORDER BY collection;")
                collections = [row[0] for row in cur.fetchall()]
            return {"collections": collections}
        finally:
            db_pool.putconn(conn)
    except Exception as e:
        logging.error(f"🔥 Error fetching collections: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/stats")
def get_stats(request: Request): # เอา async ออก
    try:
        db_pool = request.app.state.db_pool
        if not db_pool:
            raise HTTPException(status_code=503, detail="Database not available")
        conn = db_pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        collection,
                        COUNT(*) as doc_count,
                        AVG(LENGTH(content)) as avg_content_length
                    FROM documents 
                    GROUP BY collection
                    ORDER BY collection;
                """)
                stats = []
                for row in cur.fetchall():
                    stats.append({
                        "collection": row[0],
                        "document_count": row[1],
                        "avg_content_length": round(row[2], 2) if row[2] else 0
                    })
            return {"statistics": stats}
        finally:
            db_pool.putconn(conn)
    except Exception as e:
        logging.error(f"🔥 Error fetching stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def root(): # เอา async ออก
    return {
        "message": "PLCnext Chatbot API v2.0",
        "endpoints": {
            "health": "/health",
            "chat": "/api/chat",
            "agent_chat": "/api/agent-chat",
            "collections": "/api/collections",
            "stats": "/api/stats"
        }
    }

@app.post("/api/transcribe")
def transcribe(file: UploadFile = File(...)): # เอา async ออก
    import tempfile
    from faster_whisper import WhisperModel

    suffix = "." + file.filename.split('.')[-1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        # 🔴 แก้ไข: เปลี่ยนจาก await file.read() เป็น file.file.read()
        tmp.write(file.file.read()) 
        tmp_path = tmp.name

    model = WhisperModel("small.en", device="cpu", compute_type="float32")
    segments, _ = model.transcribe(tmp_path, language="en", beam_size=1)
    transcript = "".join([s.text for s in segments])
    return {"text": transcript}

@app.post("/api/chat-image", response_model=ChatResponse)
def chat_image(
    request: Request,
    file: UploadFile = File(...),
    message: str = Form("")
):
    import io
    import pytesseract
    from PIL import Image

    # 🔴 แก้ไข: เปลี่ยนจาก await file.read() เป็น file.file.read()
    image_bytes = file.file.read()
    image = Image.open(io.BytesIO(image_bytes))
    ocr_text = pytesseract.image_to_string(image)

    final_question = ((message or "") + "\n" + ocr_text).strip()
    db_pool = request.app.state.db_pool
    llm = request.app.state.llm
    embedder = request.app.state.embedder
    result = answer_question(
        question=final_question,
        db_pool=db_pool,
        llm=llm,
        embedder=embedder,
        collection="plcnext",
        retriever_class=PostgresVectorRetriever,
        reranker_class=EnhancedFlashrankRerankRetriever,
    )
    return ChatResponse(**result)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)