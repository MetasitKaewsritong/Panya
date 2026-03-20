import os
import logging

class Config:
    """Centralized configuration management"""
    
    # Database - REQUIRED
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    
    @staticmethod
    def validate():
        if not Config.DATABASE_URL:
            # We skip throwing error immediately so FastAPI can start in testing Mode
            logging.warning("DATABASE_URL environment variable is missing.")

    # Main LLM Configuration
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "ollama")
    LLM_API_KEY: str = (
        os.getenv("LLM_API_KEY", "")
        or os.getenv("OLLAMA_API_KEY", "")
        or os.getenv("DASHSCOPE_API_KEY", "")
        or os.getenv("OPENAI_API_KEY", "")
    )
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434/v1"))
    LLM_MODEL: str = os.getenv("LLM_MODEL", "hf.co/Qwen/Qwen3-VL-4B-Thinking-GGUF:Q4_K_M")
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.7"))
    LLM_TIMEOUT: int = int(os.getenv("LLM_TIMEOUT", "30"))
    LLM_NUM_PREDICT: int = int(os.getenv("LLM_NUM_PREDICT", "1024"))
    INTENT_LLM_ENABLED: bool = os.getenv("INTENT_LLM_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")
    INTENT_LLM_MODEL: str = os.getenv("INTENT_LLM_MODEL", "phi4-mini:latest")
    INTENT_LLM_TEMPERATURE: float = float(os.getenv("INTENT_LLM_TEMPERATURE", "0.0"))
    INTENT_LLM_TIMEOUT: int = int(os.getenv("INTENT_LLM_TIMEOUT", "15"))
    INTENT_LLM_NUM_PREDICT: int = int(os.getenv("INTENT_LLM_NUM_PREDICT", "160"))
    
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
