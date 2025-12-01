# backend/app/chatbot.py
# ✅ VERSION 2.7 - Dynamic Cutoff + Anti-Hallucination
# 
# Changes from v2.6:
# - Dynamic Score Cutoff (ไม่ใช่ fixed threshold)
# - Normalize score เป็น 0-1
# - MIN_KEEP logic (เก็บ top-2 เสมอ)
# - HARD_MIN / SOFT_MIN safety
# - Anti-hallucination prompt ที่เข้มงวด
# - ลบ DuckDuckGo fallback
# - Optimized สำหรับ Llama 3.2

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from typing import Generator, List, Optional
import math
import logging

# ============================================================
# CONFIGURATION - ปรับค่าได้ตามต้องการ
# ============================================================

FINAL_K = 3        # จำนวน doc สุดท้ายที่ส่งเข้า LLM
MIN_KEEP = 2       # เก็บ top-N เสมอ (ไม่สน cutoff)
ALPHA = 0.6        # สัดส่วนของ max_score สำหรับ cutoff
HARD_MIN = 0.10    # max_score ต่ำกว่านี้ = no-doc
SOFT_MIN = 0.15    # cutoff ขั้นต่ำทั่วไป
MAX_CANDIDATES = 5 # พิจารณาแค่ N ตัวแรกจาก reranker


# ============================================================
# SCORE UTILITIES
# ============================================================

def normalize_score(raw_score: float) -> float:
    """
    Normalize score ให้อยู่ในช่วง 0-1
    ใช้ sigmoid สำหรับ score ที่อาจเป็นค่าลบหรือ > 1
    """
    if raw_score is None:
        return 0.0
    
    # ถ้า score อยู่ในช่วง 0-1 อยู่แล้ว ไม่ต้อง normalize
    if 0 <= raw_score <= 1:
        return raw_score
    
    # ใช้ sigmoid สำหรับ score นอกช่วง (เช่น CrossEncoder -10 to +10)
    return 1 / (1 + math.exp(-raw_score))


def get_doc_score(doc) -> Optional[float]:
    """
    ดึง score จาก document object
    รองรับหลาย format: .score, .metadata["score"], etc.
    """
    # Try direct attribute
    score = getattr(doc, "score", None)
    if score is not None:
        return normalize_score(score)
    
    # Try metadata dict
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
    """
    เลือกเอกสารที่ดีที่สุดแบบ Dynamic Cutoff + Safety
    
    Logic:
    1. ถ้าไม่มี doc → return []
    2. ถ้า max_score < HARD_MIN → return [] (ไม่มี doc ที่ดีเลย)
    3. คำนวณ cutoff = max(max_score * ALPHA, SOFT_MIN)
    4. เก็บ doc ตามเงื่อนไข:
       - index < MIN_KEEP → เก็บเสมอ
       - index >= MIN_KEEP → เก็บถ้า score >= cutoff
    5. หยุดเมื่อครบ FINAL_K
    
    Returns:
        List of selected documents (อาจว่างได้)
    """
    candidates = (retrieved_docs or [])[:max_candidates]
    
    if not candidates:
        logging.info("📭 No candidates from retriever")
        return []
    
    # Get max score
    max_score = get_doc_score(candidates[0])
    
    if max_score is None:
        # Reranker ไม่มี score → ใช้ top_k ตรงๆ
        logging.warning("⚠️ Reranker has no score - using top_k directly")
        return candidates[:FINAL_K]
    
    logging.info(f"📊 Max score: {max_score:.3f}")
    
    # Hard no-doc: score ต่ำมากทั้งก้อน
    if max_score < HARD_MIN:
        logging.info(f"❌ Max score {max_score:.3f} < HARD_MIN {HARD_MIN} → no-doc")
        return []
    
    # Calculate dynamic cutoff
    base_cutoff = max_score * ALPHA
    cutoff = max(base_cutoff, SOFT_MIN)
    logging.info(f"📐 Cutoff: {cutoff:.3f} (base={base_cutoff:.3f}, soft_min={SOFT_MIN})")
    
    # Select docs
    final_docs = []
    for i, doc in enumerate(candidates):
        score = get_doc_score(doc) or max_score  # fallback
        
        # เก็บ top-N เสมอ หรือ score >= cutoff
        if i < MIN_KEEP or score >= cutoff:
            final_docs.append(doc)
            logging.debug(f"  ✓ Doc[{i}] score={score:.3f} - KEPT")
        else:
            logging.debug(f"  ✗ Doc[{i}] score={score:.3f} - REJECTED")
        
        if len(final_docs) >= FINAL_K:
            break
    
    logging.info(f"📚 Selected {len(final_docs)} docs from {len(candidates)} candidates")
    return final_docs


# ============================================================
# QUERY PREPROCESSING
# ============================================================

def preprocess_query(query: str) -> str:
    """แปลงคำย่อเป็นคำเต็มเพื่อช่วยในการค้นหา"""
    abbreviations = {
        # PLCnext Controllers
        "axc": "AXC PLCnext Controller",
        "axc f 1152": "AXC F 1152 PLCnext Controller",
        "axc f 2152": "AXC F 2152 PLCnext Controller",
        "axc f 3152": "AXC F 3152 PLCnext Controller",
        "rfc": "RFC 4072S PLCnext Controller",
        "elc": "ELC PLCnext Controller",
        
        # Axioline I/O
        "axl": "Axioline",
        "axl f": "Axioline F",
        "axl se": "Axioline Smart Elements",
        
        # Communication
        "profinet": "PROFINET",
        "opc ua": "OPC UA",
        "opcua": "OPC UA",
        "modbus": "Modbus TCP/RTU",
        
        # PLCnext Concepts
        "plc": "PLCnext",
        "plcnext": "PLCnext Technology",
        "gds": "Global Data Space",
        "esm": "Execution and Synchronization Manager",
        "wbm": "Web Based Management",
        "hmi": "Human Machine Interface",
        "i/o": "Input/Output",
        "io": "Input/Output",
        
        # Programming
        "iec": "IEC 61131-3",
        "st": "Structured Text",
        "fbd": "Function Block Diagram",
        "ld": "Ladder Diagram",
        "sfc": "Sequential Function Chart",
        
        # Software
        "plcnext engineer": "PLCnext Engineer IDE",
        "plcne": "PLCnext Engineer",
    }
    
    import re
    processed_query = query.lower()
    sorted_abbrs = sorted(abbreviations.items(), key=lambda x: len(x[0]), reverse=True)
    
    for abbr, full_form in sorted_abbrs:
        pattern = r'\b' + re.escape(abbr) + r'\b'
        processed_query = re.sub(pattern, full_form, processed_query, flags=re.IGNORECASE)
    
    return processed_query if processed_query != query.lower() else query


# ============================================================
# PROMPTS
# ============================================================

def build_enhanced_prompt() -> PromptTemplate:
    """
    ✅ VERSION 2.7: Anti-Hallucination Prompt for Llama 3.2
    - สั้นกว่าเดิม (Llama ทำงานดีกับ prompt สั้น)
    - เข้มงวดเรื่อง "ตอบจาก context เท่านั้น"
    - บังคับปฏิเสธถ้าไม่มีข้อมูล
    """
    template = """You are Panya, a PLCnext expert. Answer ONLY from the documents below.

## DOCUMENTS:
{context}

## RULES:
1. ONLY use information from documents above
2. If documents don't contain the answer → say "ไม่พบข้อมูล"
3. NEVER invent product names or specifications
4. If asked for specific info not in documents → admit you don't know
5. Answer in same language as question (Thai→Thai, English→English)

## QUESTION: {question}

## ANSWER:"""
    return PromptTemplate(input_variables=["context", "question"], template=template)


def build_no_context_prompt() -> PromptTemplate:
    """
    Prompt สำหรับกรณีไม่มี context ที่เกี่ยวข้อง
    บังคับให้ LLM ปฏิเสธตอบ
    """
    template = """You are Panya, a PLCnext assistant.

The knowledge base was searched but NO relevant documents were found for this question.

You MUST respond with this exact format:

❌ **ขออภัย:** ไม่พบข้อมูลที่ตรงกับคำถามนี้ในฐานความรู้

💡 **สิ่งที่ค้นหาได้ในระบบ:**
- PLCnext Controllers (AXC F 1152, AXC F 2152, AXC F 3152)
- Axioline I/O modules
- PLCnext Engineer programming
- Communication protocols (PROFINET, OPC UA, Modbus)

DO NOT make up any information. DO NOT guess.

## QUESTION: {question}

## YOUR RESPONSE:"""
    return PromptTemplate(input_variables=["question"], template=template)


def build_fast_prompt() -> PromptTemplate:
    """
    Fast Mode - ตอบคำถามทั่วไป ห้ามระบุ PLCnext spec เฉพาะ
    """
    template = """You are Panya, a helpful AI assistant.

## RULES:
✅ CAN answer: greetings, general questions, basic concepts
❌ CANNOT answer (say "กรุณาใช้โหมด Deep"): 
   - Specific PLCnext product specs
   - Model comparisons
   - Installation procedures
   - Error troubleshooting

## LANGUAGE: Answer in same language as question

## QUESTION: {question}

## ANSWER:"""
    return PromptTemplate(input_variables=["question"], template=template)


# ============================================================
# LOGGING
# ============================================================

def log_query_performance(query: str, response: str, retrieval_time: float, 
                          total_time: float, context_count: int, max_score: float = None):
    # Format max_score safely
    score_str = f"{max_score:.3f}" if max_score is not None else "N/A"
    
    logging.info(
        f"📊 Query: '{query[:50]}...' | "
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
    top_k: int = 8,  # initial retrieval (จะถูก filter โดย select_context_docs)
) -> dict:
    """
    ✅ VERSION 2.7: RAG Pipeline with Dynamic Cutoff
    
    Flow:
    1. Preprocess query (expand abbreviations)
    2. Retrieve documents (top_k)
    3. Rerank documents
    4. Select best docs with Dynamic Cutoff
    5. If no good docs → use no_context_prompt (force rejection)
    6. If has good docs → use enhanced_prompt
    7. Return response
    """
    import time

    processed_msg = preprocess_query((question or "").strip())
    if not processed_msg:
        return {
            "reply": "กรุณาพิมพ์คำถาม / Please enter a question.",
            "processing_time": 0.0,
            "retrieval_time": 0.0,
            "context_count": 0,
            "contexts": [],
            "max_score": None
        }

    t0 = time.perf_counter()

    # Retrieve & Rerank
    base_retriever = retriever_class(
        connection_pool=db_pool,
        embedder=embedder,
        collection=collection,
    )
    reranker_retriever = reranker_class(base_retriever=base_retriever)

    t_retr_start = time.perf_counter()
    retrieved_docs = reranker_retriever.invoke(processed_msg) or []
    retrieval_time = time.perf_counter() - t_retr_start

    # ✅ Dynamic Cutoff Selection
    selected_docs = select_context_docs(retrieved_docs)
    context_texts = [d.page_content for d in selected_docs]
    context_count = len(context_texts)
    
    # Get max score for logging
    max_score = get_doc_score(retrieved_docs[0]) if retrieved_docs else None

    # Build prompt based on context availability
    if context_texts:
        # มี context ที่ดี → ใช้ enhanced prompt
        prompt = build_enhanced_prompt()
        context_str = "\n\n---\n\n".join(
            f"[Doc {i+1}]\n{c}" 
            for i, c in enumerate(context_texts)
        )
        rag_chain = (
            {"context": (lambda _: context_str), "question": RunnablePassthrough()}
            | prompt
            | llm
            | StrOutputParser()
        )
    else:
        # ไม่มี context ที่ดี → บังคับ rejection
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
    """✅ VERSION 2.7: Streaming with Dynamic Cutoff"""
    import time
    import json

    processed_msg = preprocess_query((question or "").strip())
    if not processed_msg:
        yield f"data: {json.dumps({'type': 'error', 'error': 'กรุณาพิมพ์คำถาม'})}\n\n"
        return

    t0 = time.perf_counter()

    # Retrieve & Rerank
    base_retriever = retriever_class(
        connection_pool=db_pool,
        embedder=embedder,
        collection=collection,
    )
    reranker_retriever = reranker_class(base_retriever=base_retriever)

    t_retr_start = time.perf_counter()
    retrieved_docs = reranker_retriever.invoke(processed_msg) or []
    retrieval_time = time.perf_counter() - t_retr_start

    # ✅ Dynamic Cutoff Selection
    selected_docs = select_context_docs(retrieved_docs)
    context_texts = [d.page_content for d in selected_docs]
    context_count = len(context_texts)
    max_score = get_doc_score(retrieved_docs[0]) if retrieved_docs else None

    # Send metadata
    yield f"data: {json.dumps({'type': 'metadata', 'retrieval_time': round(retrieval_time, 2), 'context_count': context_count, 'max_score': round(max_score, 3) if max_score else None})}\n\n"

    # Build prompt
    if context_texts:
        prompt = build_enhanced_prompt()
        context_str = "\n\n---\n\n".join(
            f"[Doc {i+1}]\n{c}" 
            for i, c in enumerate(context_texts)
        )
        formatted_prompt = prompt.format(context=context_str, question=processed_msg)
    else:
        prompt = build_no_context_prompt()
        formatted_prompt = prompt.format(question=processed_msg)

    # Stream response
    full_response = ""
    try:
        for chunk in llm.stream(formatted_prompt):
            if chunk:
                full_response += chunk
                yield f"data: {json.dumps({'type': 'token', 'token': chunk})}\n\n"
    except Exception as e:
        logging.error(f"❌ Streaming error: {e}")
        yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
        return

    total_time = time.perf_counter() - t0
    yield f"data: {json.dumps({'type': 'done', 'processing_time': round(total_time, 2)})}\n\n"

    log_query_performance(processed_msg, full_response, retrieval_time, 
                          total_time, context_count, max_score)