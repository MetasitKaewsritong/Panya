# backend/app/utils.py
"""
Shared resource getters for FastAPI app.
These resources are initialized in main.py lifespan and stored in app.state.
"""

# Module-level singleton (set by main.py during startup)
_llm_instance = None
_intent_llm_instance = None


def set_llm(llm):
    """Called by main.py lifespan to share the LLM instance"""
    global _llm_instance
    _llm_instance = llm


def get_llm():
    """Get the shared LLM instance"""
    return _llm_instance


def set_intent_llm(llm):
    """Called by main.py lifespan to share the intent extraction LLM instance"""
    global _intent_llm_instance
    _intent_llm_instance = llm


def get_intent_llm():
    """Get the shared intent extraction LLM instance"""
    return _intent_llm_instance
