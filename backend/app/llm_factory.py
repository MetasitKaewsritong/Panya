import os
from typing import Any, Dict, Optional

from langchain_openai import ChatOpenAI

DEFAULT_LLM_PROVIDER = "ollama"
DEFAULT_LLM_MODEL = "hf.co/Qwen/Qwen3-VL-4B-Thinking-GGUF:Q4_K_M"
DEFAULT_LLM_BASE_URL = "http://host.docker.internal:11434/v1"
DEFAULT_INTENT_LLM_MODEL = "phi4-mini:latest"


def _first_non_empty(*values: Optional[str]) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def resolve_main_llm_settings() -> Dict[str, str]:
    provider = _first_non_empty(os.getenv("LLM_PROVIDER"), DEFAULT_LLM_PROVIDER).lower()
    model = _first_non_empty(os.getenv("LLM_MODEL"), DEFAULT_LLM_MODEL)
    api_key = _first_non_empty(
        os.getenv("LLM_API_KEY"),
        os.getenv("OLLAMA_API_KEY"),
        os.getenv("DASHSCOPE_API_KEY"),
        os.getenv("OPENAI_API_KEY"),
    )
    base_url = _first_non_empty(
        os.getenv("LLM_BASE_URL"),
        os.getenv("OLLAMA_BASE_URL"),
        os.getenv("OPENAI_BASE_URL"),
        DEFAULT_LLM_BASE_URL,
    )
    return {
        "provider": provider,
        "model": model,
        "api_key": api_key,
        "base_url": base_url,
    }


def resolve_intent_llm_settings() -> Dict[str, str]:
    provider = _first_non_empty(os.getenv("INTENT_LLM_PROVIDER"), os.getenv("LLM_PROVIDER"), DEFAULT_LLM_PROVIDER).lower()
    model = _first_non_empty(os.getenv("INTENT_LLM_MODEL"), DEFAULT_INTENT_LLM_MODEL)
    api_key = _first_non_empty(
        os.getenv("INTENT_LLM_API_KEY"),
        os.getenv("LLM_API_KEY"),
        os.getenv("OLLAMA_API_KEY"),
        os.getenv("DASHSCOPE_API_KEY"),
        os.getenv("OPENAI_API_KEY"),
    )
    base_url = _first_non_empty(
        os.getenv("INTENT_LLM_BASE_URL"),
        os.getenv("LLM_BASE_URL"),
        os.getenv("OLLAMA_BASE_URL"),
        os.getenv("OPENAI_BASE_URL"),
        DEFAULT_LLM_BASE_URL,
    )
    return {
        "provider": provider,
        "model": model,
        "api_key": api_key,
        "base_url": base_url,
    }


def is_intent_llm_enabled() -> bool:
    value = os.getenv("INTENT_LLM_ENABLED", "true").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _create_llm_from_settings(
    settings: Dict[str, str],
    *,
    temperature: float,
    timeout: int,
    max_tokens: Optional[int] = None,
) -> ChatOpenAI:
    provider = settings["provider"]

    if provider not in {"openai", "openai_compatible", "dashscope", "qwen", "ollama"}:
        raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")

    kwargs: Dict[str, Any] = {
        "model": settings["model"],
        "api_key": settings["api_key"] or ("ollama" if provider == "ollama" else ""),
        "base_url": settings["base_url"],
        "temperature": temperature,
        "timeout": timeout,
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens

    return ChatOpenAI(**kwargs)


def create_main_llm(
    *,
    temperature: float,
    timeout: int,
    max_tokens: Optional[int] = None,
) -> ChatOpenAI:
    settings = resolve_main_llm_settings()
    return _create_llm_from_settings(
        settings,
        temperature=temperature,
        timeout=timeout,
        max_tokens=max_tokens,
    )


def create_intent_llm(
    *,
    temperature: float,
    timeout: int,
    max_tokens: Optional[int] = None,
) -> ChatOpenAI:
    settings = resolve_intent_llm_settings()
    return _create_llm_from_settings(
        settings,
        temperature=temperature,
        timeout=timeout,
        max_tokens=max_tokens,
    )
