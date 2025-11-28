# backend/main.py

import os
import logging
import requests
import time
import math
from contextlib import asynccontextmanager
from typing import Any, Optional
import numpy as np
import io
import mimetypes
import warnings

from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.eval_logging import ollama_generate_with_stats, append_eval_run
from langchain_ollama import OllamaLLM
from sentence_transformers import SentenceTransformer
from psycopg2 import pool

from app.retriever import PostgresVectorRetriever, EnhancedFlashrankRerankRetriever, NoRerankRetriever
from app.chatbot import answer_question, answer_question_stream

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


# ⚡ ฟังก์ชันใหม่: อ่านเนื้อหาจากไฟล์ต่างๆ
def extract_text_from_file(file_content: bytes, filename: str, mime_type: str) -> str:
    """
    อ่านเนื้อหาจากไฟล์หลายประเภท
    รองรับ: PDF, TXT, CSV, JSON, DOCX, Image (OCR)
    """
    import json
    
    try:
        # 1. Text files (.txt)
        if mime_type == "text/plain" or filename.endswith(".txt"):
            return file_content.decode("utf-8", errors="ignore")
        
        # 2. CSV files
        if mime_type == "text/csv" or filename.endswith(".csv"):
            return file_content.decode("utf-8", errors="ignore")
        
        # 3. JSON files
        if mime_type == "application/json" or filename.endswith(".json"):
            try:
                data = json.loads(file_content.decode("utf-8"))
                return json.dumps(data, indent=2, ensure_ascii=False)
            except:
                return file_content.decode("utf-8", errors="ignore")
        
        # 4. PDF files
        if mime_type == "application/pdf" or filename.endswith(".pdf"):
            try:
                import fitz  # PyMuPDF
                pdf_document = fitz.open(stream=file_content, filetype="pdf")
                text = ""
                for page in pdf_document:
                    text += page.get_text()
                pdf_document.close()
                return text.strip()
            except ImportError:
                logging.warning("PyMuPDF not installed. Trying pdfplumber...")
                try:
                    import pdfplumber
                    with pdfplumber.open(io.BytesIO(file_content)) as pdf:
                        text = ""
                        for page in pdf.pages:
                            text += (page.extract_text() or "") + "\n"
                    return text.strip()
                except ImportError:
                    return "[Error: PDF reader not installed. Please install PyMuPDF or pdfplumber]"
        
        # 5. Word documents (.docx)
        if filename.endswith(".docx"):
            try:
                from docx import Document
                doc = Document(io.BytesIO(file_content))
                text = "\n".join([para.text for para in doc.paragraphs])
                return text.strip()
            except ImportError:
                return "[Error: python-docx not installed]"
        
        # 6. Image files (OCR)
        if mime_type and mime_type.startswith("image"):
            try:
                image = Image.open(io.BytesIO(file_content))
                text = pytesseract.image_to_string(image)
                return text.strip()
            except Exception as e:
                return f"[Error reading image: {str(e)}]"
        
        # 7. Unknown file type
        return f"[Unsupported file type: {mime_type or filename}]"
        
    except Exception as e:
        logging.error(f"🔥 Error extracting text from file: {e}")
        return f"[Error reading file: {str(e)}]"


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
                timeout=120
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
def health_check(request: Request):
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

# ⚡ Streaming endpoint
@app.post("/api/chat/stream")
def chat_stream(fastapi_request: Request, chat_request: ChatRequest):
    db_pool = fastapi_request.app.state.db_pool
    llm = fastapi_request.app.state.llm
    embedder = fastapi_request.app.state.embedder

    if not all([db_pool, llm, embedder]):
        return {"error": "Services not ready"}

    def generate():
        yield from answer_question_stream(
            question=chat_request.message,
            db_pool=db_pool,
            llm=llm,
            embedder=embedder,
            collection=chat_request.collection,
            retriever_class=PostgresVectorRetriever,
            reranker_class=EnhancedFlashrankRerankRetriever
        )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@app.get("/api/chat/stream")
def chat_stream_get(message: str, collection: str = "plcnext", request: Request = None):
    db_pool = request.app.state.db_pool
    llm = request.app.state.llm
    embedder = request.app.state.embedder

    if not all([db_pool, llm, embedder]):
        return {"error": "Services not ready"}

    def generate():
        yield from answer_question_stream(
            question=message,
            db_pool=db_pool,
            llm=llm,
            embedder=embedder,
            collection=collection,
            retriever_class=PostgresVectorRetriever,
            reranker_class=EnhancedFlashrankRerankRetriever
        )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


# ⚡ แก้ไข agent-chat ให้รองรับไฟล์หลายประเภท
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
    parsed_rerank = _to_bool(use_rerank)
    parsed_alias  = _to_bool(use_rank)
    decided = parsed_rerank if parsed_rerank is not None else parsed_alias
    if decided is None:
        decided = os.getenv("USE_RERANK_DEFAULT", "true").strip().lower() in ("1","true","yes","y","on")
    use_rerank = decided
    reranker_cls = EnhancedFlashrankRerankRetriever if use_rerank else NoRerankRetriever

    # ⚡ ปรับปรุงการจัดการไฟล์
    file_text = ""
    if file:
        content = file.file.read()
        mime_type, _ = mimetypes.guess_type(file.filename)
        
        # ⚡ รองรับไฟล์หลายประเภท
        if mime_type and mime_type.startswith("audio"):
            # Audio files - ใช้ transcribe endpoint แทน
            return {"error": "Please use /api/transcribe for audio files"}
        else:
            # ทุกประเภทอื่นๆ - extract text
            file_text = extract_text_from_file(content, file.filename, mime_type)
            logging.info(f"📄 Extracted {len(file_text)} characters from {file.filename}")
    
    # รวม message กับ file content
    combined_message = message
    if file_text:
        combined_message = f"{message}\n\n--- File Content ({file.filename if file else 'unknown'}) ---\n{file_text}"

    start_time = time.perf_counter()
    result = answer_question(
        question=combined_message,
        db_pool=app.state.db_pool,
        llm=app.state.llm,
        embedder=app.state.embedder,
        collection="plcnext",
        retriever_class=PostgresVectorRetriever,
        reranker_class=reranker_cls,
    )
    total_time = time.perf_counter() - start_time

    contexts = result.get("contexts_list") or result.get("contexts") or []

    response = {
        "reply": result.get("llm_answer", "") or result.get("reply", ""),
        "processing_time": result.get("processing_time", total_time),
        "retrieval_time": result.get("retrieval_time", None),
        "context_count": result.get("context_count", None),
        "contexts": contexts,
        "eval": None,
        "ragas": None,
        "use_rerank": use_rerank,
        "file_processed": file.filename if file else None,
    }
    return sanitize_json(response)

@app.get("/api/collections")
def get_collections(request: Request):
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
def get_stats(request: Request):
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
def root():
    return {
        "message": "PLCnext Chatbot API v2.0",
        "endpoints": {
            "health": "/health",
            "chat": "/api/chat",
            "chat_stream": "/api/chat/stream",
            "agent_chat": "/api/agent-chat",
            "collections": "/api/collections",
            "stats": "/api/stats"
        },
        "supported_files": ["image/*", "audio/*", "pdf", "txt", "csv", "json", "docx"]
    }

@app.post("/api/transcribe")
def transcribe(file: UploadFile = File(...)):
    import tempfile
    from faster_whisper import WhisperModel

    suffix = "." + file.filename.split('.')[-1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
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