# ============================================================================
# backend/main.py v3.1 - Universal PLC Assistant
# ============================================================================
# API provides a RAG-powered chat interface for PLC/Industrial Automation.
# 
# Key endpoints:
#   - POST /api/chat - Main chat endpoint (handled by routes_chat.py)
#   - POST /api/transcribe - Audio transcription using Whisper
#   - GET /health - Service health check
#   - GET /api/collections - List document collections
#   - GET /api/stats - Document statistics
# ============================================================================

import os
import logging
import time
from uuid import uuid4
import warnings

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


from app.db import init_db_pool
from app.routes_auth import router as auth_router
from app.routes_chat import router as chat_router

from app.embed_logic import get_embedder
from app.utils import set_llm
from app.errors import (
    ErrorCode, AppException,
    create_error_response
)

# Suppress warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

# ============================================================================
# CONFIGURATION
# ============================================================================

class Config:
    """Centralized configuration management"""
    
    # Database - REQUIRED, no fallback to avoid hardcoded credentials
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    
    @staticmethod
    def validate():
        """Validate required configuration"""
        if not Config.DATABASE_URL:
            raise RuntimeError("DATABASE_URL environment variable is required.")
        # Don't fail on missing GEMINI_API_KEY - allow server to start
        if not Config.GEMINI_API_KEY:
            logging.warning("GEMINI_API_KEY not set - LLM features will be unavailable")
    
    # Gemini Configuration
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.7"))
    LLM_TIMEOUT: int = int(os.getenv("LLM_TIMEOUT", "30"))
    LLM_NUM_PREDICT: int = int(os.getenv("LLM_NUM_PREDICT", "1024"))  # Max output tokens
    
    # Embeddings
    EMBED_MODEL_NAME: str = os.getenv("EMBED_MODEL", "BAAI/bge-m3")
    
    # File processing limits
    FAST_MODE_CHARS: int = int(os.getenv("FAST_MODE_CHARS", "8000"))
    DEEP_MODE_CHARS: int = int(os.getenv("DEEP_MODE_CHARS", "60000"))
    
    # Web search
    WEB_SEARCH_TIMEOUT: int = int(os.getenv("WEB_SEARCH_TIMEOUT", "10"))
    WEB_SEARCH_MAX_RESULTS: int = int(os.getenv("WEB_SEARCH_MAX_RESULTS", "5"))
    
    # Database pool
    DB_POOL_MIN: int = int(os.getenv("DB_POOL_MIN", "1"))
    DB_POOL_MAX: int = int(os.getenv("DB_POOL_MAX", "10"))
    
    # Default collection name for vector store
    DEFAULT_COLLECTION: str = os.getenv("DEFAULT_COLLECTION", "plcnext")


config = Config()

# ============================================================================
# LOGGING SETUP
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("PLCAssistant")

logger.info("=" * 60)
logger.info("PLC Assistant v3.0 - Starting up")
logger.info("=" * 60)

# Validate required configuration
Config.validate()

logger.info("  Database URL: configured")
logger.info(f"  Gemini Model: {config.GEMINI_MODEL}")
logger.info(f"  Embed Model: {config.EMBED_MODEL_NAME}")
logger.info("=" * 60)

# ============================================================================
# SERVICE INITIALIZATION HELPERS
# ============================================================================

def test_database_connection() -> bool:
    """Test database connection and verify pgvector extension"""
    conn = None
    cur = None
    try:
        import psycopg2
        conn = psycopg2.connect(config.DATABASE_URL)
        cur = conn.cursor()
        
        # Check pgvector extension
        cur.execute("SELECT extname FROM pg_extension WHERE extname = 'vector';")
        if not cur.fetchone():
            logger.error("pgvector extension not found")
            return False
        
        # Get document count
        cur.execute("SELECT COUNT(*) FROM documents;")
        doc_count = cur.fetchone()[0]
        
        logger.info("Database connected. Documents: %d", doc_count)
        return True
        
    except Exception as e:
        logger.error("Database connection failed: %s", e)
        return False
    finally:
        if cur is not None:
            cur.close()
        if conn is not None:
            conn.close()


# ============================================================================
# FASTAPI APPLICATION
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager - handles startup and shutdown"""
    logger.info("Starting application...")
    
    # Initialize database pool
    try:
        if test_database_connection():
            # init_db_pool() creates and returns SimpleConnectionPool as defined in backend/app/db.py
            db_pool = init_db_pool()
            app.state.db_pool = db_pool
            logger.info("Database connection pool initialized")
        else:
            app.state.db_pool = None
            logger.error("test_database_connection() failed; DB pool not created")
    except Exception as e:
        logger.error("Failed to initialize DB pool via init_db_pool(): %s", e, exc_info=True)
        app.state.db_pool = None
    
    # Initialize LLM (Gemini)
    app.state.llm = None
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        
        logger.info("Initializing Gemini model: %s", config.GEMINI_MODEL)
        
        # Validate API key format before attempting to initialize
        if not config.GEMINI_API_KEY or len(config.GEMINI_API_KEY) < 20:
            logger.error("Invalid GEMINI_API_KEY format. Check your .env file.")
            logger.warning("Server will start without LLM; chat functionality will be limited")
        else:
            app.state.llm = ChatGoogleGenerativeAI(
                model=config.GEMINI_MODEL,
                google_api_key=config.GEMINI_API_KEY,
                temperature=config.LLM_TEMPERATURE,
                timeout=config.LLM_TIMEOUT,
                max_tokens=config.LLM_NUM_PREDICT,
            )
            set_llm(app.state.llm)  # Share LLM with utils module
            logger.info("Gemini loaded: %s (max %d tokens)", config.GEMINI_MODEL, config.LLM_NUM_PREDICT)
    except ImportError:
        logger.error("langchain-google-genai not installed. Run: pip install langchain-google-genai")
    except Exception as e:
        logger.error("Failed to load Gemini: %s", e)
        logger.warning("Server will start without LLM; chat functionality will be limited")
    
    # Initialize embedder (use singleton from embed_logic)
    app.state.embedder = None
    try:
        app.state.embedder = get_embedder()
        logger.info("Embedder loaded: %s", config.EMBED_MODEL_NAME)
    except Exception as e:
        logger.error("Failed to load embedder: %s", e)
    
    # Log PDF Page Image Context mode
    use_page_images = os.getenv("USE_PAGE_IMAGES", "false").lower() in ("true", "1", "yes")
    if use_page_images:
        logger.info("PDF Page Image Context: ENABLED (vision LLM mode)")
    else:
        logger.info("PDF Page Image Context: DISABLED (text-only mode)")
    
    # Initialize Whisper model for transcription (non-blocking)
    app.state.whisper_model = None
    logger.info("Whisper model will load lazily on first transcription request")
    
    logger.info("Application startup complete")

    logger.debug("Registered routes:")
    for route in app.routes:
        if hasattr(route, "path"):
            logger.debug("  - %s [%s]", route.path, ",".join(route.methods))
    
    yield  # Application runs here
    
    # Shutdown
    logger.info("Shutting down...")
    if hasattr(app.state, 'db_pool') and app.state.db_pool:
        app.state.db_pool.closeall()
        logger.info("Database pool closed")


# Create FastAPI app
app = FastAPI(
    lifespan=lifespan,
    title="PLC Assistant API",
    description="""
    Universal PLC & Industrial Automation Assistant with RAG capabilities.
    
    ## Modes
    - **Fast**: Direct LLM response for general questions (~5-15s)
    - **Deep**: RAG-powered response using documentation (~30-60s)
    
    ## Features
    - Multi-file support (PDF, DOCX, images, etc.)
    - Web search integration
    - Chat history context
    - Voice transcription
    """,
    version="3.0.0"
)

app.include_router(auth_router)
app.include_router(chat_router)

# CORS middleware - tightened for security
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"]
)


# ============================================================================
# REQUEST TRACING MIDDLEWARE
# ============================================================================

@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Add request ID to all requests for tracing/debugging"""
    request_id = str(uuid4())
    request.state.request_id = request_id
    
    start = time.perf_counter()
    logger.info("[%s] %s %s", request_id[:8], request.method, request.url.path)
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000.0
    logger.info(
        "[%s] %s %s -> %s (%.1fms)",
        request_id[:8],
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    response.headers["X-Request-ID"] = request_id
    return response


# ============================================================================
# EXCEPTION HANDLERS
# ============================================================================

@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    """Handle custom application exceptions"""
    request_id = getattr(request.state, 'request_id', None)
    logger.warning(f"[{request_id}] AppException: {exc.code} - {exc.message}")
    return create_error_response(
        code=exc.code,
        message=exc.message,
        status_code=exc.status_code,
        request_id=request_id,
        details=exc.details
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Convert HTTPException to unified error format"""
    request_id = getattr(request.state, 'request_id', None)
    return create_error_response(
        code=f"HTTP_{exc.status_code}",
        message=str(exc.detail),
        status_code=exc.status_code,
        request_id=request_id
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Catch-all for unhandled exceptions"""
    request_id = getattr(request.state, 'request_id', None)
    logger.error(f"[{request_id}] Unhandled exception: {exc}", exc_info=True)
    return create_error_response(
        code=ErrorCode.INTERNAL_ERROR,
        message="An unexpected error occurred. Please try again.",
        status_code=500,
        request_id=request_id
    )


class HealthResponse(BaseModel):
    status: str
    services: dict
    timestamp: str
    version: str = "3.0.0"


# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.get("/", tags=["Info"])
def root():
    """API information and documentation"""
    return {
        "name": "PLC Assistant API",
        "version": "3.0.0",
        "description": "Universal PLC & Industrial Automation Assistant",
        "modes": {
            "fast": {
                "description": "Direct LLM response for general questions",
                "response_time": "~5-15 seconds",
                "use_for": ["General PLC concepts", "Quick troubleshooting", "Syntax help"]
            },
            "deep": {
                "description": "RAG-powered response using embedded documentation",
                "response_time": "~30-60 seconds",
                "use_for": ["Specific documentation lookups", "Detailed specifications", "Accuracy-critical queries"]
            }
        },
        "endpoints": {
            "health": "GET /health",
            "chat": "POST /api/chat",
            "stream": "POST /api/chat/stream",
            "transcribe": "POST /api/transcribe",
            "collections": "GET /api/collections",
            "stats": "GET /api/stats"
        }
    }


@app.get("/health", response_model=HealthResponse, tags=["Health"])
def health_check(request: Request):
    """Check service health status"""
    services = {
        "database": False,
        "llm": False,
        "embedder": False,
        "whisper": False
    }
    
    # Check database
    try:
        if request.app.state.db_pool:
            conn = request.app.state.db_pool.getconn()
            request.app.state.db_pool.putconn(conn)
            services["database"] = True
    except Exception:
        pass
    
    # Check LLM, embedder, and whisper
    services["llm"] = request.app.state.llm is not None
    services["embedder"] = request.app.state.embedder is not None
    services["whisper"] = request.app.state.whisper_model is not None
    
    # Whisper loads lazily and should not mark overall service as degraded.
    core_services_ok = services["database"] and services["llm"] and services["embedder"]
    status = "healthy" if core_services_ok else "degraded"
    
    return HealthResponse(
        status=status,
        services=services,
        timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
    )

# NOTE: /api/chat endpoint is defined in routes_chat.py (via chat_router)
# It handles session-based chat with history. The router is included via:
#     app.include_router(chat_router)
# Do NOT add a duplicate /api/chat here as it would be overridden.


@app.post("/api/transcribe", tags=["Audio"])
def transcribe(file: UploadFile = File(...)):
    """Transcribe audio file to text using Whisper"""
    import tempfile
    
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Whisper not available. Install faster-whisper."
        )
    
    # Lazy load model on first request (with persistent cache)
    if not hasattr(app.state, 'whisper_model') or app.state.whisper_model is None:
        # Define persistent model cache directory
        model_cache_dir = os.path.join(os.path.dirname(__file__), "models", "whisper")
        os.makedirs(model_cache_dir, exist_ok=True)
        
        logger.info("🎤 Loading Whisper model (base with int8 quantization)...")
        logger.info(f"   Model cache: {model_cache_dir}")
        
        try:
            app.state.whisper_model = WhisperModel(
                "base",  # Good balance of speed and accuracy
                device="cpu",
                compute_type="int8",
                download_root=model_cache_dir
            )
            logger.info("✅ Whisper model loaded and ready")
        except Exception as e:
            logger.error(f"🔥 Failed to load Whisper model: {e}")
            raise HTTPException(
                status_code=503,
                detail=f"Failed to load Whisper model: {str(e)}"
            )
    
    # Save to temp file
    suffix = "." + file.filename.split('.')[-1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(file.file.read())
        tmp_path = tmp.name
    
    try:
        segments, _ = app.state.whisper_model.transcribe(
            tmp_path,
            language="en",
            beam_size=1,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500)
        )
        transcript = " ".join(s.text for s in segments)
        return {"text": transcript.strip()}
    finally:
        # Cleanup temp file
        os.unlink(tmp_path)

@app.get("/api/collections", tags=["Data"])
def get_collections(request: Request):
    """List available document collections"""
    db_pool = request.app.state.db_pool
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")
    
    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT collection 
                FROM documents 
                ORDER BY collection;
            """)
            collections = [row[0] for row in cur.fetchall()]
        return {"collections": collections}
    finally:
        db_pool.putconn(conn)


@app.get("/api/stats", tags=["Data"])
def get_stats(request: Request):
    """Get document statistics"""
    db_pool = request.app.state.db_pool
    if not db_pool:
        raise HTTPException(status_code=503, detail="Database not available")
    
    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    collection,
                    COUNT(*) as document_count,
                    ROUND(AVG(LENGTH(content))::numeric, 2) as avg_content_length,
                    MIN(LENGTH(content)) as min_content_length,
                    MAX(LENGTH(content)) as max_content_length
                FROM documents 
                GROUP BY collection
                ORDER BY collection;
            """)
            stats = []
            for row in cur.fetchall():
                stats.append({
                    "collection": row[0],
                    "document_count": row[1],
                    "avg_content_length": float(row[2]) if row[2] else 0,
                    "min_content_length": row[3],
                    "max_content_length": row[4]
                })
        return {"statistics": stats}
    finally:
        db_pool.putconn(conn)


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=5000,
        reload=False,
        workers=1
    )
