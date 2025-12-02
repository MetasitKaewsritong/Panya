# backend/app/chatbot.py
# ✅ VERSION 2.9 - Fix language matching + Fast mode strict redirect
# 
# Changes from v2.8:
# - Deep Mode: ตอบภาษาเดียวกับคำถาม แม้ docs เป็นภาษาอื่น
# - Fast Mode: ห้ามตอบ PLCnext เด็ดขาด → redirect ไป Deep
# - Better language detection

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
# LANGUAGE DETECTION
# ============================================================

def detect_language(text: str) -> str:
    """ตรวจจับภาษาของข้อความ"""
    thai_pattern = re.compile(r'[\u0E00-\u0E7F]')
    thai_chars = len(thai_pattern.findall(text))
    total_chars = len(text.replace(" ", ""))
    
    if total_chars == 0:
        return "en"
    
    thai_ratio = thai_chars / total_chars
    return "th" if thai_ratio > 0.3 else "en"


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
        logging.info("📭 No candidates from retriever")
        return []
    
    max_score = get_doc_score(candidates[0])
    
    if max_score is None:
        logging.warning("⚠️ Reranker has no score - using top_k directly")
        return candidates[:FINAL_K]
    
    logging.info(f"📊 Max score: {max_score:.3f}")
    
    if max_score < HARD_MIN:
        logging.info(f"❌ Max score {max_score:.3f} < HARD_MIN {HARD_MIN} → no-doc")
        return []
    
    base_cutoff = max_score * ALPHA
    cutoff = max(base_cutoff, SOFT_MIN)
    logging.info(f"📐 Cutoff: {cutoff:.3f}")
    
    final_docs = []
    for i, doc in enumerate(candidates):
        score = get_doc_score(doc) or max_score
        if i < MIN_KEEP or score >= cutoff:
            final_docs.append(doc)
        if len(final_docs) >= FINAL_K:
            break
    
    logging.info(f"📚 Selected {len(final_docs)} docs from {len(candidates)} candidates")
    return final_docs


# ============================================================
# QUERY PREPROCESSING
# ============================================================

def preprocess_query(query: str) -> str:
    abbreviations = {
        "axc": "AXC PLCnext Controller",
        "axc f 1152": "AXC F 1152 PLCnext Controller",
        "axc f 2152": "AXC F 2152 PLCnext Controller",
        "axc f 3152": "AXC F 3152 PLCnext Controller",
        "rfc": "RFC 4072S PLCnext Controller",
        "elc": "ELC PLCnext Controller",
        "axl": "Axioline",
        "axl f": "Axioline F",
        "axl se": "Axioline Smart Elements",
        "profinet": "PROFINET",
        "opc ua": "OPC UA",
        "opcua": "OPC UA",
        "modbus": "Modbus TCP/RTU",
        "plc": "PLCnext",
        "plcnext": "PLCnext Technology",
        "gds": "Global Data Space",
        "esm": "Execution and Synchronization Manager",
        "wbm": "Web Based Management",
        "hmi": "Human Machine Interface",
        "i/o": "Input/Output",
        "io": "Input/Output",
        "iec": "IEC 61131-3",
        "st": "Structured Text",
        "fbd": "Function Block Diagram",
        "ld": "Ladder Diagram",
        "sfc": "Sequential Function Chart",
        "plcnext engineer": "PLCnext Engineer IDE",
        "plcne": "PLCnext Engineer",
    }
    
    processed_query = query.lower()
    sorted_abbrs = sorted(abbreviations.items(), key=lambda x: len(x[0]), reverse=True)
    
    for abbr, full_form in sorted_abbrs:
        pattern = r'\b' + re.escape(abbr) + r'\b'
        processed_query = re.sub(pattern, full_form, processed_query, flags=re.IGNORECASE)
    
    return processed_query if processed_query != query.lower() else query


# ============================================================
# PROMPTS
# ============================================================

def build_enhanced_prompt(question_language: str = "en") -> PromptTemplate:
    """
    ✅ VERSION 2.9: Deep Mode with language matching
    """
    if question_language == "th":
        lang_instruction = """## LANGUAGE INSTRUCTION:
คำถามเป็นภาษาไทย → ตอบเป็นภาษาไทย
แม้ว่าเอกสารจะเป็นภาษาอังกฤษ ให้แปลและตอบเป็นภาษาไทย"""
    else:
        lang_instruction = """## LANGUAGE INSTRUCTION:
The question is in English → Answer in English
Even if the documents are in Thai, translate and answer in English"""

    template = f"""You are Panya, a PLCnext Technology expert from Phoenix Contact.

## DOCUMENTS FROM KNOWLEDGE BASE:
{{context}}

{lang_instruction}

## IMPORTANT RULES:

1. **USE ONLY information from the documents above**
2. **DO NOT repeat the same point multiple times** - each sentence must add NEW information
3. **Be comprehensive** - cover different aspects (features, benefits, use cases, technical details)
4. **Be specific** - mention actual product names, specifications, protocols when available
5. **STRICTLY follow the language instruction above**

## HOW TO STRUCTURE YOUR ANSWER:

For "What is X?" questions:
- Start with a clear definition (1-2 sentences)
- Explain key features and capabilities (3-4 unique points)
- Mention specific products or components if relevant
- Explain benefits or use cases (2-3 points)
- Each point should be UNIQUE - no repetition!

## CRITICAL:
- PLCnext is made by **Phoenix Contact** (NOT Siemens, NOT Schneider Electric!)
- If documents don't contain enough info, say so honestly
- NEVER make up specifications or features not in the documents

## QUESTION: {{question}}

## YOUR COMPREHENSIVE ANSWER:"""
    return PromptTemplate(input_variables=["context", "question"], template=template)


def build_no_context_prompt(question_language: str = "en") -> PromptTemplate:
    """Prompt เมื่อไม่มี context"""
    if question_language == "th":
        template = """คุณคือ Panya ผู้ช่วย AI สำหรับ PLCnext

ไม่พบเอกสารที่เกี่ยวข้องในฐานความรู้

ตอบว่า:
❌ **ขออภัย:** ไม่พบข้อมูลที่ตรงกับคำถามนี้ในฐานความรู้

💡 **หัวข้อที่ค้นหาได้:**
- PLCnext Controllers (AXC F 1152, AXC F 2152, AXC F 3152)
- Axioline I/O modules
- PLCnext Engineer programming
- Communication protocols (PROFINET, OPC UA, Modbus)

ห้ามแต่งข้อมูลขึ้นมา

## คำถาม: {question}

## คำตอบ:"""
    else:
        template = """You are Panya, a PLCnext assistant.

NO relevant documents were found in the knowledge base for this question.

Respond with:
❌ **Sorry:** No information matching this question was found in the knowledge base.

💡 **Topics available:**
- PLCnext Controllers (AXC F 1152, AXC F 2152, AXC F 3152)
- Axioline I/O modules
- PLCnext Engineer programming
- Communication protocols (PROFINET, OPC UA, Modbus)

DO NOT make up information.

## QUESTION: {question}

## YOUR RESPONSE:"""
    return PromptTemplate(input_variables=["question"], template=template)


def build_fast_prompt() -> PromptTemplate:
    """
    ✅ VERSION 2.9: Fast Mode - ห้ามตอบ PLCnext เด็ดขาด
    """
    template = """You are Panya, a helpful AI assistant.

## 🚫 ABSOLUTE RULE - READ CAREFULLY:

If the question contains ANY of these words: PLCnext, PLC, Phoenix Contact, AXC, Axioline, PROFINET, OPC UA, industrial automation, controller

You MUST respond with ONLY this message (in the same language as the question):

**English question:**
"For PLCnext-related questions, please use Deep mode to search our knowledge base for accurate information. Click the 🔍 Deep button and ask again."

**Thai question (คำถามภาษาไทย):**
"สำหรับคำถามเกี่ยวกับ PLCnext กรุณาใช้โหมด Deep เพื่อค้นหาข้อมูลจากฐานความรู้ คลิกปุ่ม 🔍 Deep แล้วถามใหม่อีกครั้ง"

DO NOT provide any information about PLCnext, PLC, or industrial automation.
DO NOT mention Siemens, Schneider Electric, or any other company.
DO NOT explain what PLCnext is.

## ✅ CAN ANSWER (only if NOT about PLCnext/PLC):
- Greetings (สวัสดี, hello, hi)
- Weather, general knowledge
- Math, coding help (not PLC-related)
- Other topics completely unrelated to industrial automation

## QUESTION: {question}

## YOUR RESPONSE:"""
    return PromptTemplate(input_variables=["question"], template=template)


# ============================================================
# LOGGING
# ============================================================

def log_query_performance(query: str, response: str, retrieval_time: float, 
                          total_time: float, context_count: int, max_score: float = None):
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
    top_k: int = 8,
) -> dict:
    """
    ✅ VERSION 2.9: RAG Pipeline with language detection
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

    # Detect question language
    question_lang = detect_language(question)
    logging.info(f"🌐 Detected language: {question_lang}")

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

    # Dynamic Cutoff Selection
    selected_docs = select_context_docs(retrieved_docs)
    context_texts = [d.page_content for d in selected_docs]
    context_count = len(context_texts)
    
    max_score = get_doc_score(retrieved_docs[0]) if retrieved_docs else None

    # Build prompt with language awareness
    if context_texts:
        prompt = build_enhanced_prompt(question_lang)
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
        prompt = build_no_context_prompt(question_lang)
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
    """✅ VERSION 2.9: Streaming with language detection"""
    import time
    import json

    processed_msg = preprocess_query((question or "").strip())
    if not processed_msg:
        yield f"data: {json.dumps({'type': 'error', 'error': 'กรุณาพิมพ์คำถาม'})}\n\n"
        return

    # Detect question language
    question_lang = detect_language(question)
    logging.info(f"🌐 Detected language: {question_lang}")

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

    yield f"data: {json.dumps({'type': 'metadata', 'retrieval_time': round(retrieval_time, 2), 'context_count': context_count, 'max_score': round(max_score, 3) if max_score else None, 'language': question_lang})}\n\n"

    if context_texts:
        prompt = build_enhanced_prompt(question_lang)
        context_str = "\n\n---\n\n".join(
            f"[Document {i+1}]\n{c}" 
            for i, c in enumerate(context_texts)
        )
        formatted_prompt = prompt.format(context=context_str, question=processed_msg)
    else:
        prompt = build_no_context_prompt(question_lang)
        formatted_prompt = prompt.format(question=processed_msg)

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