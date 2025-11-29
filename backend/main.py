# backend/main.py
# ✅ FIXED VERSION - แก้ปัญหา Auto Mode เลือก Deep ตลอด และ Deep ไม่ตอบ

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

# ⚡ โหมดการอ่านไฟล์
FAST_MODE_CHARS = 8000      # ~4 หน้า
DEEP_MODE_CHARS = 60000     # ~30 หน้า
AUTO_THRESHOLD = 10000      # ถ้าไฟล์ < 10,000 ใช้ Fast, ถ้า >= 10,000 ใช้ Deep

# ✅ NEW: Keywords ที่บ่งบอกว่าต้องใช้ Deep Mode (RAG)
PLCNEXT_KEYWORDS = [
    "plcnext", "plc next", "phoenix contact", "axc", "axl", "axioline",
    "profinet", "modbus", "opcua", "opc ua", "gds", "global data space",
    "esm", "execution", "synchronization", "firmware", "wbm", "web based management",
    "iec 61131", "structured text", "function block", "ladder", "fbd",
    "proficloud", "plcnext store", "plcnext engineer"
]

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


# ✅ NEW: ฟังก์ชันตรวจสอบว่าคำถามเกี่ยวกับ PLCnext หรือไม่
def is_plcnext_specific_question(question: str) -> bool:
    """
    ตรวจสอบว่าคำถามเกี่ยวกับ PLCnext โดยเฉพาะหรือไม่
    ถ้าใช่ → ควรใช้ Deep Mode (RAG)
    ถ้าไม่ → ใช้ Fast Mode (LLM โดยตรง)
    """
    question_lower = question.lower()
    for keyword in PLCNEXT_KEYWORDS:
        if keyword in question_lower:
            return True
    return False


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


# ⚡ ฟังก์ชันใหม่: ถาม LLM โดยตรง (ไม่ต้อง RAG) พร้อมรองรับ 3 โหมด
def ask_llm_directly(llm, question: str, file_content: str, filename: str, mode: str = "auto") -> dict:
    """
    ส่งคำถามและเนื้อหาไฟล์ไป LLM โดยตรง (ไม่ต้องทำ RAG)
    
    Modes:
    - auto: เลือกอัตโนมัติตามขนาดไฟล์
    - fast: อ่านแค่ 8,000 ตัวอักษรแรก (~4 หน้า)
    - deep: อ่านทั้งไฟล์ สูงสุด 60,000 ตัวอักษร (~30 หน้า)
    """
    start_time = time.perf_counter()
    
    original_length = len(file_content)
    
    # ⚡ เลือก max_chars ตามโหมด
    if mode == "fast":
        max_chars = FAST_MODE_CHARS
        actual_mode = "fast"
    elif mode == "deep":
        max_chars = DEEP_MODE_CHARS
        actual_mode = "deep"
    else:  # auto
        if original_length < AUTO_THRESHOLD:
            max_chars = FAST_MODE_CHARS
            actual_mode = "auto→fast"
        else:
            max_chars = DEEP_MODE_CHARS
            actual_mode = "auto→deep"
    
    # ตัดเนื้อหาถ้ายาวเกินไป
    truncated = False
    if len(file_content) > max_chars:
        file_content = file_content[:max_chars]
        truncated = True
    
    logging.info(f"📖 Mode: {actual_mode} | Original: {original_length} chars | Using: {len(file_content)} chars | Truncated: {truncated}")
    
    # สร้าง prompt
    prompt = f"""You are a helpful assistant. The user has uploaded a file named "{filename}".

Here is the content of the file:
---
{file_content}
{"... [content truncated due to length - showing first " + str(len(file_content)) + " characters]" if truncated else ""}
---

User's question: {question if question else "Please summarize this file."}

Please answer based on the file content above. Answer in the same language as the user's question."""

    try:
        response = llm.invoke(prompt)
        total_time = time.perf_counter() - start_time
        
        return {
            "reply": response,
            "processing_time": total_time,
            "retrieval_time": 0,
            "context_count": 0,
            "contexts": [],
            "mode": actual_mode,
            "file_chars_used": len(file_content),
            "file_chars_total": original_length,
            "truncated": truncated
        }
    except Exception as e:
        logging.error(f"🔥 Error asking LLM directly: {e}")
        return {
            "reply": f"Error processing file: {str(e)}",
            "processing_time": time.perf_counter() - start_time,
            "retrieval_time": 0,
            "context_count": 0,
            "contexts": [],
            "mode": actual_mode,
            "file_chars_used": len(file_content),
            "file_chars_total": original_length,
            "truncated": truncated
        }


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
                timeout=180  # เพิ่ม timeout สำหรับ deep mode
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
    title="PLCnext Chatbot v2.2",
    description="Advanced RAG chatbot with Smart Auto/Fast/Deep modes",
    version="2.2.0"
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

    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")
    if not llm:
        raise HTTPException(status_code=503, detail="LLM not available")
    if not embedder:
        raise HTTPException(status_code=503, detail="Embedder not available")

    result = answer_question(
        question=chat_request.message,
        db_pool=db_pool,
        llm=llm,
        embedder=embedder,
        collection=chat_request.collection,
        retriever_class=PostgresVectorRetriever,
        reranker_class=EnhancedFlashrankRerankRetriever,
    )
    return ChatResponse(**result)


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


# ⚡ agent-chat พร้อม 3 โหมด: auto, fast, deep
# Fast = Direct to LLM (เร็ว)
# Deep = RAG (ช้า แต่ละเอียด ใช้ข้อมูลจาก database)
# Auto = เลือกอัตโนมัติ (✅ FIXED: ฉลาดขึ้น!)
@app.post("/api/agent-chat")
def agent_chat(
    message: str = Form(""),
    file: UploadFile = File(None),
    mode: str = Form("auto"),  # ⚡ auto, fast, deep
    log_eval: bool = Form(False),
    enable_ragas: bool = Form(False),
    fast_ragas: bool | None = Form(None),
    ground_truth: str = Form(""),
    use_rerank: Any = Form(None),
    use_rank: Any = Form(None),
):
    start_time = time.perf_counter()
    
    # ⚡ Validate mode
    if mode not in ["auto", "fast", "deep"]:
        mode = "auto"
    
    # ✅ FIXED: ตัดสินใจโหมดจริงที่จะใช้ (ฉลาดขึ้น!)
    actual_mode = mode
    file_text = ""
    file_content_bytes = None
    mime_type = None
    
    if file:
        file_content_bytes = file.file.read()
        mime_type, _ = mimetypes.guess_type(file.filename)
        
        # Audio files - ใช้ transcribe endpoint แทน
        if mime_type and mime_type.startswith("audio"):
            return {"error": "Please use /api/transcribe for audio files"}
        
        # Extract text จากไฟล์
        file_text = extract_text_from_file(file_content_bytes, file.filename, mime_type)
        logging.info(f"📄 Extracted {len(file_text)} characters from {file.filename}")
        
        # Auto mode logic สำหรับไฟล์
        if mode == "auto":
            if len(file_text) > AUTO_THRESHOLD:
                actual_mode = "fast"  # ไฟล์ใหญ่ → Fast
            else:
                actual_mode = "deep"  # ไฟล์เล็ก → Deep (ละเอียดกว่า)
    else:
        # ✅ FIXED: ไม่มีไฟล์ - Auto จะเลือกตามประเภทคำถาม
        if mode == "auto":
            # ตรวจสอบว่าคำถามเกี่ยวกับ PLCnext หรือไม่
            if is_plcnext_specific_question(message):
                actual_mode = "deep"  # คำถามเกี่ยวกับ PLCnext → Deep (RAG)
                logging.info(f"🎯 Auto Mode: Detected PLCnext-specific question → Deep")
            else:
                actual_mode = "fast"  # คำถามทั่วไป → Fast (เร็วกว่า)
                logging.info(f"⚡ Auto Mode: General question → Fast")
    
    # ====================================
    # 🚀 FAST MODE: Direct to LLM (เร็ว)
    # ====================================
    if actual_mode == "fast":
        if file_text:
            # มีไฟล์ → ส่งไฟล์ไป LLM โดยตรง
            result = ask_llm_directly(
                llm=app.state.llm,
                question=message,
                file_content=file_text,
                filename=file.filename if file else "unknown"
            )
            
            total_time = time.perf_counter() - start_time
            logging.info(f"📊 Fast Mode (File): {file.filename} | Time: {total_time:.2f}s")
            
            response = {
                "reply": result.get("reply", ""),
                "processing_time": total_time,
                "retrieval_time": 0,
                "context_count": 0,
                "contexts": [],
                "eval": None,
                "ragas": None,
                "use_rerank": False,
                "file_processed": file.filename if file else None,
                "mode": "fast",
                "file_info": {
                    "chars_used": result.get("file_chars_used"),
                    "chars_total": result.get("file_chars_total"),
                    "truncated": result.get("truncated")
                }
            }
            return sanitize_json(response)
        else:
            # ไม่มีไฟล์ → ถาม LLM โดยตรง (ไม่ใช้ RAG)
            try:
                llm_response = app.state.llm.invoke(message)
                total_time = time.perf_counter() - start_time
                logging.info(f"📊 Fast Mode (No File): Time: {total_time:.2f}s")
                
                response = {
                    "reply": llm_response,
                    "processing_time": total_time,
                    "retrieval_time": 0,
                    "context_count": 0,
                    "contexts": [],
                    "eval": None,
                    "ragas": None,
                    "use_rerank": False,
                    "file_processed": None,
                    "mode": "fast"
                }
                return sanitize_json(response)
            except Exception as e:
                logging.error(f"🔥 Fast mode error: {e}")
                return {"error": str(e), "mode": "fast"}
    
    # ====================================
    # 🔍 DEEP MODE: RAG (ช้า แต่ละเอียด)
    # ====================================
    # ใช้ RAG - embed + search database + LLM
    
    parsed_rerank = _to_bool(use_rerank)
    parsed_alias = _to_bool(use_rank)
    decided = parsed_rerank if parsed_rerank is not None else parsed_alias
    if decided is None:
        decided = os.getenv("USE_RERANK_DEFAULT", "true").strip().lower() in ("1","true","yes","y","on")
    use_rerank_flag = decided
    reranker_cls = EnhancedFlashrankRerankRetriever if use_rerank_flag else NoRerankRetriever
    
    # รวม message กับ file content (ถ้ามี)
    combined_message = message
    if file_text:
        # ตัดให้สั้นลงถ้ายาวเกินไป เพื่อไม่ให้ embed ช้าเกินไป
        truncated_file_text = file_text[:DEEP_MODE_CHARS] if len(file_text) > DEEP_MODE_CHARS else file_text
        combined_message = f"{message}\n\n--- File Content ({file.filename}) ---\n{truncated_file_text}"
        if len(file_text) > DEEP_MODE_CHARS:
            combined_message += f"\n[... truncated, showing first {DEEP_MODE_CHARS} of {len(file_text)} characters]"

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
    reply_text = result.get("llm_answer", "") or result.get("reply", "")
    
    # ✅ FIXED: ถ้า RAG หาไม่เจอ ให้ fallback ไปใช้ LLM โดยตรง
    if "I could not find relevant information" in reply_text or not reply_text.strip():
        logging.info(f"⚠️ Deep Mode: No relevant context found, falling back to LLM...")
        try:
            # Fallback: ถาม LLM โดยตรงโดยไม่มี context
            fallback_prompt = f"""You are an expert on Phoenix Contact's PLCnext Technology platform.

Please answer this question about PLCnext based on your knowledge:

Question: {message}

Provide a helpful and accurate answer. If you're not sure about specific details, say so."""

            fallback_response = app.state.llm.invoke(fallback_prompt)
            reply_text = fallback_response
            logging.info(f"✅ Deep Mode: Fallback to LLM successful")
        except Exception as e:
            logging.error(f"🔥 Fallback error: {e}")
            # Keep original response if fallback fails
    
    logging.info(f"📊 Deep Mode (RAG): Query length: {len(combined_message)} | Time: {total_time:.2f}s")

    response = {
        "reply": reply_text,
        "processing_time": result.get("processing_time", total_time),
        "retrieval_time": result.get("retrieval_time", None),
        "context_count": result.get("context_count", None),
        "contexts": contexts,
        "eval": None,
        "ragas": None,
        "use_rerank": use_rerank_flag,
        "file_processed": file.filename if file else None,
        "mode": "deep"
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
        "message": "PLCnext Chatbot API v2.2 (Fixed Auto Mode)",
        "endpoints": {
            "health": "/health",
            "chat": "/api/chat",
            "chat_stream": "/api/chat/stream",
            "agent_chat": "/api/agent-chat",
            "collections": "/api/collections",
            "stats": "/api/stats"
        },
        "supported_files": ["image/*", "audio/*", "pdf", "txt", "csv", "json", "docx"],
        "modes": {
            "auto": "Smart selection: PLCnext questions → Deep, General questions → Fast, Large files → Fast",
            "fast": "Direct to LLM - Fast response (~5-10s), no database search",
            "deep": "RAG mode - Slower (~30-60s) but uses database knowledge (with fallback if no results)"
        }
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