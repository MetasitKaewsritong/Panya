# backend/main.py
# ✅ VERSION 2.4 - แก้ไข:
# 1. ตอบได้ทุกเรื่อง ไม่ใช่แค่ PLCnext
# 2. Web search ที่ใช้งานได้จริง (ใช้ DuckDuckGo HTML search)
# 3. Auto mode แสดงเป็น "auto"
# 4. Deep mode ตอบละเอียด
# 5. Chat history support

import os
import logging
import requests
import time
import math
from contextlib import asynccontextmanager
from typing import Any, Optional, List
import numpy as np
import io
import mimetypes
import warnings
import json
import re

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
FAST_MODE_CHARS = 8000
DEEP_MODE_CHARS = 60000
AUTO_THRESHOLD = 10000

# Keywords สำหรับ PLCnext (ใช้ RAG)
PLCNEXT_KEYWORDS = [
    "plcnext", "plc next", "phoenix contact", "axc", "axl", "axioline",
    "profinet", "modbus", "opcua", "opc ua", "gds", "global data space",
    "esm", "execution", "synchronization", "firmware", "wbm",
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


def is_plcnext_specific_question(question: str) -> bool:
    """ตรวจสอบว่าคำถามเกี่ยวกับ PLCnext หรือไม่"""
    question_lower = question.lower()
    for keyword in PLCNEXT_KEYWORDS:
        if keyword in question_lower:
            return True
    return False


# ✅ NEW: Web Search ที่ใช้งานได้จริง
def web_search(query: str, max_results: int = 5) -> str:
    """
    ค้นหาข้อมูลจากอินเทอร์เน็ตโดยใช้ DuckDuckGo HTML
    """
    try:
        # ใช้ DuckDuckGo HTML search
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # URL encode query
        from urllib.parse import quote_plus
        search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        
        response = requests.get(search_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            # Parse HTML ง่ายๆ ด้วย regex
            html = response.text
            
            # หา snippets จาก result
            results = []
            
            # Pattern สำหรับหา result snippets
            snippet_pattern = r'<a class="result__snippet"[^>]*>(.*?)</a>'
            snippets = re.findall(snippet_pattern, html, re.DOTALL)
            
            for i, snippet in enumerate(snippets[:max_results]):
                # ลบ HTML tags
                clean_snippet = re.sub(r'<[^>]+>', '', snippet)
                clean_snippet = clean_snippet.strip()
                if clean_snippet:
                    results.append(f"- {clean_snippet}")
            
            # หา titles ด้วย
            title_pattern = r'<a class="result__a"[^>]*>(.*?)</a>'
            titles = re.findall(title_pattern, html, re.DOTALL)
            
            if results:
                logging.info(f"🌐 Web search found {len(results)} results for: {query[:50]}")
                return "\n".join(results)
            elif titles:
                # ถ้าไม่มี snippets ให้ใช้ titles
                clean_titles = []
                for title in titles[:max_results]:
                    clean_title = re.sub(r'<[^>]+>', '', title).strip()
                    if clean_title:
                        clean_titles.append(f"- {clean_title}")
                return "\n".join(clean_titles)
        
        logging.warning(f"⚠️ Web search returned status {response.status_code}")
        return ""
        
    except Exception as e:
        logging.error(f"🔥 Web search error: {e}")
        return ""


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


def extract_text_from_file(file_content: bytes, filename: str, mime_type: str) -> str:
    """อ่านเนื้อหาจากไฟล์หลายประเภท"""
    try:
        if mime_type == "text/plain" or filename.endswith(".txt"):
            return file_content.decode("utf-8", errors="ignore")
        
        if mime_type == "text/csv" or filename.endswith(".csv"):
            return file_content.decode("utf-8", errors="ignore")
        
        if mime_type == "application/json" or filename.endswith(".json"):
            try:
                data = json.loads(file_content.decode("utf-8"))
                return json.dumps(data, indent=2, ensure_ascii=False)
            except:
                return file_content.decode("utf-8", errors="ignore")
        
        if mime_type == "application/pdf" or filename.endswith(".pdf"):
            try:
                import fitz
                pdf_document = fitz.open(stream=file_content, filetype="pdf")
                text = ""
                for page in pdf_document:
                    text += page.get_text()
                pdf_document.close()
                return text.strip()
            except ImportError:
                try:
                    import pdfplumber
                    with pdfplumber.open(io.BytesIO(file_content)) as pdf:
                        text = ""
                        for page in pdf.pages:
                            text += (page.extract_text() or "") + "\n"
                    return text.strip()
                except ImportError:
                    return "[Error: PDF reader not installed]"
        
        if filename.endswith(".docx"):
            try:
                from docx import Document
                doc = Document(io.BytesIO(file_content))
                text = "\n".join([para.text for para in doc.paragraphs])
                return text.strip()
            except ImportError:
                return "[Error: python-docx not installed]"
        
        if mime_type and mime_type.startswith("image"):
            try:
                image = Image.open(io.BytesIO(file_content))
                text = pytesseract.image_to_string(image)
                return text.strip()
            except Exception as e:
                return f"[Error reading image: {str(e)}]"
        
        return f"[Unsupported file type: {mime_type or filename}]"
        
    except Exception as e:
        logging.error(f"🔥 Error extracting text from file: {e}")
        return f"[Error reading file: {str(e)}]"


# ✅ UPDATED: ถาม LLM โดยตรง - ตอบได้ทุกเรื่อง
def ask_llm_directly(llm, question: str, file_content: str = "", filename: str = "", 
                     mode: str = "auto", chat_history: List[dict] = None,
                     web_context: str = "") -> dict:
    """
    ส่งคำถามไป LLM โดยตรง - ตอบได้ทุกเรื่อง ไม่จำกัดแค่ PLCnext
    """
    start_time = time.perf_counter()
    
    # Build chat history string
    history_str = ""
    if chat_history:
        for msg in chat_history[-10:]:
            role = "User" if msg.get("sender") == "user" else "Assistant"
            text = msg.get("text", "")[:500]  # จำกัดความยาว
            history_str += f"{role}: {text}\n"
    
    # Handle file content
    file_section = ""
    if file_content:
        original_length = len(file_content)
        max_chars = DEEP_MODE_CHARS if mode == "deep" else FAST_MODE_CHARS
        truncated = len(file_content) > max_chars
        if truncated:
            file_content = file_content[:max_chars]
        
        file_section = f"""
=== UPLOADED FILE: {filename} ===
{file_content}
{"[... content truncated ...]" if truncated else ""}
===
"""
    
    # Web search section
    web_section = ""
    if web_context:
        web_section = f"""
=== WEB SEARCH RESULTS ===
{web_context}
===
"""
    
    # ✅ UPDATED: Prompt ที่ตอบได้ทุกเรื่อง
    prompt = f"""You are a helpful AI assistant that can answer questions on ANY topic.
You are knowledgeable, friendly, and provide comprehensive answers.

{"=== CONVERSATION HISTORY ===" + chr(10) + history_str + "===" if history_str else ""}

{file_section}

{web_section}

**User's Question:** {question}

**Instructions:**
1. Answer the question thoroughly and helpfully
2. If there is conversation history, use it to maintain context
3. If there is file content, analyze and reference it
4. If there are web search results, use them to provide accurate information
5. Answer in the SAME LANGUAGE as the user's question (Thai/English)
6. Be detailed and informative - don't give short, unhelpful answers
7. You can discuss ANY topic - technology, science, entertainment, business, etc.

**Your comprehensive answer:**"""

    try:
        response = llm.invoke(prompt)
        total_time = time.perf_counter() - start_time
        
        return {
            "reply": response,
            "processing_time": total_time,
            "mode": mode
        }
    except Exception as e:
        logging.error(f"🔥 Error asking LLM: {e}")
        return {
            "reply": f"Error: {str(e)}",
            "processing_time": time.perf_counter() - start_time,
            "mode": mode
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
                temperature=0.7,  # เพิ่มความคิดสร้างสรรค์
                timeout=180
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
    title="PLCnext Chatbot v2.4",
    description="General AI Assistant with RAG for PLCnext + Web Search",
    version="2.4.0"
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


# ✅ UPDATED: agent-chat v2.4 - ตอบได้ทุกเรื่อง + web search
@app.post("/api/agent-chat")
def agent_chat(
    message: str = Form(""),
    file: UploadFile = File(None),
    mode: str = Form("auto"),
    chat_history: str = Form("[]"),
    log_eval: bool = Form(False),
    enable_ragas: bool = Form(False),
    fast_ragas: bool | None = Form(None),
    ground_truth: str = Form(""),
    use_rerank: Any = Form(None),
    use_rank: Any = Form(None),
):
    start_time = time.perf_counter()
    
    # Parse chat history
    try:
        history = json.loads(chat_history) if chat_history else []
    except:
        history = []
    
    # Validate mode
    if mode not in ["auto", "fast", "deep"]:
        mode = "auto"
    
    # เก็บ original mode ไว้แสดงผล
    display_mode = mode
    
    # ตัดสินใจ internal mode
    internal_mode = mode
    file_text = ""
    file_content_bytes = None
    mime_type = None
    
    if file:
        file_content_bytes = file.file.read()
        mime_type, _ = mimetypes.guess_type(file.filename)
        
        if mime_type and mime_type.startswith("audio"):
            return {"error": "Please use /api/transcribe for audio files"}
        
        file_text = extract_text_from_file(file_content_bytes, file.filename, mime_type)
        logging.info(f"📄 Extracted {len(file_text)} characters from {file.filename}")
        
        if mode == "auto":
            if len(file_text) > AUTO_THRESHOLD:
                internal_mode = "fast"
            else:
                internal_mode = "deep"
    else:
        if mode == "auto":
            # ถ้าเกี่ยวกับ PLCnext → Deep (RAG)
            # ถ้าไม่ → Fast (LLM + web search ถ้าจำเป็น)
            if is_plcnext_specific_question(message):
                internal_mode = "deep"
            else:
                internal_mode = "fast"
    
    logging.info(f"🎯 Mode: {display_mode} (internal: {internal_mode})")
    
    # ====================================
    # 🚀 FAST MODE - ตอบได้ทุกเรื่อง
    # ====================================
    if internal_mode == "fast":
        # ลอง search เว็บก่อนถ้าไม่ใช่คำถามทั่วไป
        web_context = ""
        
        # ตรวจสอบว่าควร search หรือไม่
        should_search = any([
            "netflix" in message.lower(),
            "google" in message.lower(),
            "facebook" in message.lower(),
            "amazon" in message.lower(),
            "microsoft" in message.lower(),
            "apple" in message.lower(),
            "ข้อมูล" in message.lower(),
            "บริษัท" in message.lower(),
            "โครงสร้าง" in message.lower(),
            "ราคา" in message.lower(),
            "ข่าว" in message.lower(),
            "ล่าสุด" in message.lower(),
            "2024" in message.lower(),
            "2025" in message.lower(),
        ])
        
        if should_search:
            logging.info(f"🌐 Searching web for: {message[:50]}...")
            web_context = web_search(message)
        
        result = ask_llm_directly(
            llm=app.state.llm,
            question=message,
            file_content=file_text,
            filename=file.filename if file else "",
            mode=display_mode,
            chat_history=history,
            web_context=web_context
        )
        
        total_time = time.perf_counter() - start_time
        
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
            "mode": display_mode,
            "web_searched": bool(web_context)
        }
        return sanitize_json(response)
    
    # ====================================
    # 🔍 DEEP MODE - RAG สำหรับ PLCnext
    # ====================================
    parsed_rerank = _to_bool(use_rerank)
    parsed_alias = _to_bool(use_rank)
    decided = parsed_rerank if parsed_rerank is not None else parsed_alias
    if decided is None:
        decided = os.getenv("USE_RERANK_DEFAULT", "true").strip().lower() in ("1","true","yes","y","on")
    use_rerank_flag = decided
    reranker_cls = EnhancedFlashrankRerankRetriever if use_rerank_flag else NoRerankRetriever
    
    # รวม chat history
    history_context = ""
    if history:
        recent_history = history[-6:]
        for msg in recent_history:
            role = "User" if msg.get("sender") == "user" else "Assistant"
            history_context += f"{role}: {msg.get('text', '')[:200]}\n"
    
    combined_message = message
    if history_context:
        combined_message = f"[Previous conversation]\n{history_context}\n[Current question]\n{message}"
    
    if file_text:
        truncated_file_text = file_text[:DEEP_MODE_CHARS] if len(file_text) > DEEP_MODE_CHARS else file_text
        combined_message = f"{combined_message}\n\n--- File Content ({file.filename}) ---\n{truncated_file_text}"

    result = answer_question(
        question=combined_message,
        db_pool=app.state.db_pool,
        llm=app.state.llm,
        embedder=app.state.embedder,
        collection="plcnext",
        retriever_class=PostgresVectorRetriever,
        reranker_class=reranker_cls,
    )
    
    contexts = result.get("contexts_list") or result.get("contexts") or []
    reply_text = result.get("llm_answer", "") or result.get("reply", "")
    
    # Fallback ถ้าไม่เจอข้อมูล
    if "I could not find relevant information" in reply_text or not reply_text.strip():
        logging.info(f"⚠️ Deep Mode: No context found, using general LLM...")
        
        # ใช้ LLM โดยตรง
        result = ask_llm_directly(
            llm=app.state.llm,
            question=message,
            file_content=file_text,
            filename=file.filename if file else "",
            mode=display_mode,
            chat_history=history,
            web_context=""
        )
        reply_text = result.get("reply", "")
    
    total_time = time.perf_counter() - start_time
    logging.info(f"📊 Deep Mode: Time: {total_time:.2f}s")

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
        "mode": display_mode
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
        "message": "PLCnext Chatbot API v2.4 - General AI Assistant",
        "features": [
            "Answer ANY topic (not just PLCnext)",
            "Chat History Support",
            "Web Search for current information", 
            "RAG for PLCnext documentation",
            "Multi-language support (Thai/English)"
        ],
        "endpoints": {
            "health": "/health",
            "chat": "/api/chat",
            "agent_chat": "/api/agent-chat",
            "collections": "/api/collections",
            "stats": "/api/stats"
        },
        "modes": {
            "auto": "Smart: PLCnext → RAG, Others → LLM + Web Search",
            "fast": "Direct LLM with web search (~5-15s)",
            "deep": "RAG for PLCnext docs (~30-60s)"
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