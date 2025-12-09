# backend/app/chatbot.py
# VERSION 3.4 - Simple English Output (no translation, no rejection)

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from typing import Generator, List, Optional
import math
import logging
import re


# ============================================================
# CONFIGURATION
# ============================================================

FINAL_K = 3
MIN_KEEP = 2
ALPHA = 0.6
HARD_MIN = 0.10
SOFT_MIN = 0.15
MAX_CANDIDATES = 5


# ============================================================
# SCORE UTILITIES
# ============================================================

def normalize_score(raw_score: float) -> float:
    if raw_score is None:
        return 0.0
    if 0 <= raw_score <= 1:
        return raw_score
    return 1 / (1 + math.exp(-raw_score))


def get_doc_score(doc) -> Optional[float]:
    score = getattr(doc, "score", None)
    if score is not None:
        return normalize_score(score)
    metadata = getattr(doc, "metadata", {})
    if isinstance(metadata, dict):
        score = metadata.get("score") or metadata.get("relevance_score")
        if score is not None:
            return normalize_score(score)
    return None


# ============================================================
# CONTEXT SELECTION (Dynamic Cutoff)
# ============================================================

def select_context_docs(retrieved_docs: List, max_candidates: int = MAX_CANDIDATES) -> List:
    candidates = (retrieved_docs or [])[:max_candidates]
    
    if not candidates:
        logging.info("No candidates from retriever")
        return []
    
    max_score = get_doc_score(candidates[0])
    
    if max_score is None:
        logging.warning("Reranker has no score - using top_k directly")
        return candidates[:FINAL_K]
    
    logging.info(f"Max score: {max_score:.3f}")
    
    if max_score < HARD_MIN:
        logging.info(f"Max score {max_score:.3f} < HARD_MIN {HARD_MIN} - no docs selected")
        return []
    
    base_cutoff = max_score * ALPHA
    cutoff = max(base_cutoff, SOFT_MIN)
    logging.info(f"Cutoff: {cutoff:.3f}")
    
    final_docs = []
    for i, doc in enumerate(candidates):
        score = get_doc_score(doc) or max_score
        if i < MIN_KEEP or score >= cutoff:
            final_docs.append(doc)
        if len(final_docs) >= FINAL_K:
            break
    
    logging.info(f"Selected {len(final_docs)} docs from {len(candidates)} candidates")
    return final_docs


# ============================================================
# QUERY PREPROCESSING (abbreviations only)
# ============================================================

def preprocess_query(query: str) -> str:
    if not query:
        return query
    
    # MODIFIED: Changed "PLCnext" to "Programmable Logic Controller"
    # to allow for generic PLC context.
    abbreviations = {
        "plc": "Programmable Logic Controller", 
        "hmi": "Human Machine Interface",
        "profinet": "PROFINET",
        "i/o": "input output",
        "gds": "Global Data Space",
        "esm": "Execution and Synchronization Manager"
    }
    
    processed_query = query.lower()
    for abbr, full_form in abbreviations.items():
        pattern = r'\b' + re.escape(abbr) + r'\b'
        processed_query = re.sub(pattern, full_form, processed_query)
    
    return processed_query if processed_query != query.lower() else query


# ============================================================
# PROMPTS - ENGLISH OUTPUT ENFORCED
# ============================================================

def build_enhanced_prompt() -> PromptTemplate:
    # MODIFIED: Updated persona to "Industrial Automation expert" 
    # and removed the strict "Phoenix Contact only" rule.
    template = """You are Panya, an Industrial Automation and PLC expert assistant.

LANGUAGE RULE: You must ALWAYS answer in English only. Even if the user asks in Thai, Chinese, Japanese, German, or any other language, you must respond in English. Never respond in any language other than English.

REFERENCE DOCUMENTS:
{context}

GUIDELINES:
1. Answer based ONLY on the documents above
2. Be specific with technical standards (e.g., IEC 61131-3), protocols, and hardware specifications
3. If the documents do not contain the answer, state that you don't have that specific information in your database
4. You can discuss general PLC concepts (Ladder Logic, Structured Text, etc.)

USER QUESTION: {question}

ANSWER IN ENGLISH ONLY:"""
    return PromptTemplate(input_variables=["context", "question"], template=template)


def build_no_context_prompt() -> PromptTemplate:
    # MODIFIED: broadened the list of topics the bot offers to discuss.
    template = """You are Panya, an Industrial Automation assistant.

LANGUAGE RULE: You must ALWAYS answer in English only. Even if the user asks in Thai, Chinese, Japanese, German, or any other language, you must respond in English. Never respond in any language other than English.

I could not find specific documents in my database for your question.

However, I can help with general automation topics such as:
- IEC 61131-3 Programming (Ladder, ST, FBD)
- Industrial Protocols (PROFINET, Modbus, OPC UA)
- General I/O and Control Logic principles
- HMI design and best practices

USER QUESTION: {question}

ANSWER IN ENGLISH ONLY:"""
    return PromptTemplate(input_variables=["question"], template=template)


def build_fast_prompt() -> PromptTemplate:
    template = """You are Panya, a helpful assistant.

LANGUAGE RULE: You must ALWAYS answer in English only. Even if the user asks in Thai, Chinese, Japanese, German, or any other language, you must respond in English. Never respond in any language other than English.

# MODIFIED: Trigger phrase is now generic for any technical automation question
If the question is about PLCs, automation, industrial controllers, wiring, or programming:
Reply: "For technical automation questions, please use Deep mode. Click the Deep button and ask again."

Otherwise answer the general question helpfully.

USER QUESTION: {question}

ANSWER IN ENGLISH ONLY:"""
    return PromptTemplate(input_variables=["question"], template=template)


# ============================================================
# LOGGING
# ============================================================

def log_query_performance(query: str, response: str, retrieval_time: float,
                          total_time: float, context_count: int, max_score: float = None):
    score_str = f"{max_score:.3f}" if max_score is not None else "N/A"
    logging.info(
        f"Query: '{query[:50]}...' | "
        f"Contexts: {context_count} | "
        f"MaxScore: {score_str} | "
        f"Retrieval: {retrieval_time:.2f}s | "
        f"Total: {total_time:.2f}s"
    )


# ============================================================
# MAIN RAG FUNCTION
# ============================================================

def answer_question(
    question: str,
    db_pool,
    llm,
    embedder,
    collection: str,
    retriever_class,
    reranker_class,
    top_k: int = 4,
) -> dict:
    import time

    processed_msg = preprocess_query((question or "").strip())

    if not processed_msg:
        return {
            "reply": "Please enter a question.",
            "processing_time": 0.0,
            "retrieval_time": 0.0,
            "context_count": 0,
            "contexts": [],
            "max_score": None
        }

    t0 = time.perf_counter()

    base_retriever = retriever_class(
        connection_pool=db_pool,
        embedder=embedder,
        collection=collection,
    )
    reranker_retriever = reranker_class(base_retriever=base_retriever)

    t_retr_start = time.perf_counter()
    retrieved_docs = reranker_retriever.invoke(processed_msg) or []
    retrieval_time = time.perf_counter() - t_retr_start

    selected_docs = select_context_docs(retrieved_docs)
    context_texts = [d.page_content for d in selected_docs]
    context_count = len(context_texts)
    max_score = get_doc_score(retrieved_docs[0]) if retrieved_docs else None

    if context_texts:
        prompt = build_enhanced_prompt()
        context_str = "\n\n---\n\n".join(
            f"[Document {i+1}]\n{c}"
            for i, c in enumerate(context_texts)
        )
        rag_chain = (
            {"context": (lambda _: context_str), "question": RunnablePassthrough()}
            | prompt
            | llm
            | StrOutputParser()
        )
    else:
        prompt = build_no_context_prompt()
        rag_chain = (
            {"question": RunnablePassthrough()}
            | prompt
            | llm
            | StrOutputParser()
        )

    response_text = rag_chain.invoke(processed_msg)
    total_time = time.perf_counter() - t0

    log_query_performance(processed_msg, response_text, retrieval_time,
                          total_time, context_count, max_score)

    return {
        "reply": response_text,
        "processing_time": total_time,
        "retrieval_time": retrieval_time,
        "context_count": context_count,
        "contexts": context_texts,
        "max_score": max_score
    }


# ============================================================
# STREAMING VERSION
# ============================================================

def answer_question_stream(
    question: str,
    db_pool,
    llm,
    embedder,
    collection: str,
    retriever_class,
    reranker_class,
    top_k: int = 8,
) -> Generator[str, None, None]:
    import time
    import json

    processed_msg = preprocess_query((question or "").strip())

    if not processed_msg:
        yield f"data: {json.dumps({'type': 'error', 'error': 'Please enter a question.'})}\n\n"
        return

    t0 = time.perf_counter()

    base_retriever = retriever_class(
        connection_pool=db_pool,
        embedder=embedder,
        collection=collection,
    )
    reranker_retriever = reranker_class(base_retriever=base_retriever)

    t_retr_start = time.perf_counter()
    retrieved_docs = reranker_retriever.invoke(processed_msg) or []
    retrieval_time = time.perf_counter() - t_retr_start

    selected_docs = select_context_docs(retrieved_docs)
    context_texts = [d.page_content for d in selected_docs]
    context_count = len(context_texts)
    max_score = get_doc_score(retrieved_docs[0]) if retrieved_docs else None

    yield f"data: {json.dumps({'type': 'metadata', 'retrieval_time': round(retrieval_time, 2), 'context_count': context_count, 'max_score': round(max_score, 3) if max_score else None})}\n\n"

    if context_texts:
        prompt = build_enhanced_prompt()
        context_str = "\n\n---\n\n".join(
            f"[Document {i+1}]\n{c}"
            for i, c in enumerate(context_texts)
        )
        formatted_prompt = prompt.format(context=context_str, question=processed_msg)
    else:
        prompt = build_no_context_prompt()
        formatted_prompt = prompt.format(question=processed_msg)

    full_response = ""
    try:
        for chunk in llm.stream(formatted_prompt):
            if chunk:
                full_response += chunk
                yield f"data: {json.dumps({'type': 'token', 'token': chunk})}\n\n"
    except Exception as e:
        logging.error(f"Streaming error: {e}")
        yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
        return

    total_time = time.perf_counter() - t0
    yield f"data: {json.dumps({'type': 'done', 'processing_time': round(total_time, 2)})}\n\n"

    log_query_performance(processed_msg, full_response, retrieval_time,
                          total_time, context_count, max_score)