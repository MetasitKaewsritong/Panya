import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.db import init_db_pool
from app.embed_logic import get_embedder
from app.llm_factory import (
    create_intent_llm,
    create_main_llm,
    is_intent_llm_enabled,
    resolve_intent_llm_settings,
    resolve_main_llm_settings,
)
from app.utils import set_intent_llm, set_llm
from app.config import config

logger = logging.getLogger("PLCAssistant")

def _provider_allows_blank_api_key(provider: str) -> bool:
    return (provider or "").strip().lower() == "ollama"

def _has_usable_api_key(provider: str, api_key: str) -> bool:
    return _provider_allows_blank_api_key(provider) or bool(api_key and len(api_key) >= 10)

def test_database_connection() -> bool:
    """Test database connection and verify pgvector extension"""
    conn = None
    cur = None
    try:
        import psycopg2
        conn = psycopg2.connect(config.DATABASE_URL)
        cur = conn.cursor()
        
        cur.execute("SELECT extname FROM pg_extension WHERE extname = 'vector';")
        if not cur.fetchone():
            logger.error("pgvector extension not found")
            return False
        
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

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager - handles startup and shutdown"""
    logger.info("Starting application...")
    
    # Initialize database pool
    try:
        if test_database_connection():
            db_pool = init_db_pool()
            app.state.db_pool = db_pool
            logger.info("Database connection pool initialized")
        else:
            app.state.db_pool = None
            logger.error("test_database_connection() failed; DB pool not created")
    except Exception as e:
        logger.error("Failed to initialize DB pool via init_db_pool(): %s", e, exc_info=True)
        app.state.db_pool = None
    
    # Initialize main LLM
    app.state.llm = None
    llm_settings = resolve_main_llm_settings()
    try:
        logger.info("Initializing main LLM: %s", config.LLM_MODEL)
        if not _has_usable_api_key(llm_settings["provider"], llm_settings["api_key"]):
            logger.error("Invalid LLM API key format. Server will start without LLM.")
        else:
            app.state.llm = create_main_llm(
                temperature=config.LLM_TEMPERATURE,
                timeout=config.LLM_TIMEOUT,
                max_tokens=config.LLM_NUM_PREDICT,
            )
            set_llm(app.state.llm)
            logger.info("Main LLM loaded: %s", config.LLM_MODEL)
    except Exception as e:
        logger.error("Failed to load main LLM: %s", e)

    intent_llm_settings = resolve_intent_llm_settings()
    app.state.intent_llm = None
    set_intent_llm(None)
    try:
        if not is_intent_llm_enabled():
            logger.info("Intent extraction LLM disabled")
        elif not _has_usable_api_key(intent_llm_settings["provider"], intent_llm_settings["api_key"]):
            logger.warning("Intent extraction LLM skipped because no valid API key is configured")
        else:
            logger.info("Initializing intent LLM: %s", config.INTENT_LLM_MODEL)
            app.state.intent_llm = create_intent_llm(
                temperature=config.INTENT_LLM_TEMPERATURE,
                timeout=config.INTENT_LLM_TIMEOUT,
                max_tokens=config.INTENT_LLM_NUM_PREDICT,
            )
            set_intent_llm(app.state.intent_llm)
    except Exception as e:
        logger.error("Failed to load intent LLM: %s", e)
    
    app.state.embedder = None
    try:
        app.state.embedder = get_embedder()
        logger.info("Embedder loaded: %s", config.EMBED_MODEL_NAME)
    except Exception as e:
        logger.error("Failed to load embedder: %s", e)
    
    app.state.whisper_model = None
    logger.info("Whisper model will load lazily on first transcription request")
    
    logger.info("Application startup complete")
    yield  
    
    logger.info("Shutting down...")
    if hasattr(app.state, 'db_pool') and app.state.db_pool:
        app.state.db_pool.closeall()
        logger.info("Database pool closed")
