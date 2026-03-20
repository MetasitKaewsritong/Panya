import os
import time
import logging
from uuid import uuid4

from fastapi import FastAPI, Request, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.lifespan import lifespan
from app.config import config
from app.routes_auth import router as auth_router
from app.routes_chat import router as chat_router
from app.routes_documents import router as documents_router
from app.errors import ErrorCode, AppException, create_error_response

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("PLCAssistant")

# Database requires URL early validation
config.validate()

app = FastAPI(
    lifespan=lifespan,
    title="PLC Assistant API",
    description="Universal PLC & Industrial Automation Assistant with RAG capabilities.",
    version="3.0.0"
)

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(documents_router)

# Serve PDF Manuals directly
app.mount("/api/documents", StaticFiles(directory="data/Knowledge"), name="documents")

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = str(uuid4())
    request.state.request_id = request_id
    start = time.perf_counter()
    logger.info("[%s] %s %s", request_id[:8], request.method, request.url.path)
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000.0
    logger.info("[%s] %s %s -> %s (%.1fms)", request_id[:8], request.method, request.url.path, response.status_code, duration_ms)
    response.headers["X-Request-ID"] = request_id
    return response

@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    request_id = getattr(request.state, 'request_id', None)
    return create_error_response(code=exc.code, message=exc.message, status_code=exc.status_code, request_id=request_id, details=exc.details)

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    request_id = getattr(request.state, 'request_id', None)
    return create_error_response(code=f"HTTP_{exc.status_code}", message=str(exc.detail), status_code=exc.status_code, request_id=request_id)

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, 'request_id', None)
    logger.error(f"[{request_id}] Unhandled exception: {exc}", exc_info=True)
    return create_error_response(code=ErrorCode.INTERNAL_ERROR, message="An unexpected error occurred. Please try again.", status_code=500, request_id=request_id)

class HealthResponse(BaseModel):
    status: str
    services: dict
    timestamp: str
    version: str = "3.0.0"

@app.get("/", tags=["Info"])
def root():
    return {"name": "PLC Assistant API", "version": "3.0.0"}

@app.get("/health", response_model=HealthResponse, tags=["Health"])
def health_check(request: Request):
    services = {
        "database": False, "llm": False, "intent_llm": False, "embedder": False, "whisper": False
    }
    try:
        if request.app.state.db_pool:
            conn = request.app.state.db_pool.getconn()
            request.app.state.db_pool.putconn(conn)
            services["database"] = True
    except Exception: pass
    services["llm"] = request.app.state.llm is not None
    services["intent_llm"] = getattr(request.app.state, "intent_llm", None) is not None
    services["embedder"] = request.app.state.embedder is not None
    services["whisper"] = request.app.state.whisper_model is not None
    status = "healthy" if services["database"] and services["llm"] and services["embedder"] else "degraded"
    return HealthResponse(status=status, services=services, timestamp=time.strftime("%Y-%m-%d %H:%M:%S"))

@app.post("/api/transcribe", tags=["Audio"])
def transcribe(file: UploadFile = File(...)):
    import tempfile
    
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise HTTPException(status_code=503, detail="Whisper not available.")
    
    if not hasattr(app.state, 'whisper_model') or app.state.whisper_model is None:
        model_cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models", "whisper")
        os.makedirs(model_cache_dir, exist_ok=True)
        try:
            # Upgraded from small.en to medium.en for smarter accent handling
            app.state.whisper_model = WhisperModel("medium.en", device="auto", compute_type="int8", cpu_threads=8, download_root=model_cache_dir)
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Failed to load Whisper: {e}")
    
    suffix = "." + file.filename.split('.')[-1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(file.file.read())
        tmp_path = tmp.name
    try:
        # VAD Filter removes absolute silence before processing, massive speedup
        # Beam Size 2 provides near-identical accuracy to 5 for English but runs 2.5x faster
        segments, _ = app.state.whisper_model.transcribe(
            tmp_path, 
            language="en", 
            beam_size=2, 
            condition_on_previous_text=False, 
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500, speech_pad_ms=400)
        )
        return {"text": " ".join(s.text for s in segments).strip()}
    finally:
        os.unlink(tmp_path)

@app.get("/api/collections", tags=["Data"])
def get_collections(request: Request):
    db_pool = request.app.state.db_pool
    if not db_pool: raise HTTPException(status_code=503, detail="DB unavailable")
    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT collection FROM documents ORDER BY collection;")
            return {"collections": [row[0] for row in cur.fetchall()]}
    finally:
        db_pool.putconn(conn)

@app.get("/api/stats", tags=["Data"])
def get_stats(request: Request):
    db_pool = request.app.state.db_pool
    if not db_pool: raise HTTPException(status_code=503, detail="DB unavailable")
    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT collection, COUNT(*) as c, ROUND(AVG(LENGTH(content))::numeric, 2) as a, MIN(LENGTH(content)) as min, MAX(LENGTH(content)) as max FROM documents GROUP BY collection ORDER BY collection;")
            stats = [
                {
                    "collection": row[0],
                    "document_count": row[1],
                    "avg_content_length": float(row[2]) if row[2] else 0,
                    "min_content_length": int(row[3]) if row[3] is not None else 0,
                    "max_content_length": int(row[4]) if row[4] is not None else 0,
                }
                for row in cur.fetchall()
            ]
        return {"statistics": stats}
    finally:
        db_pool.putconn(conn)
