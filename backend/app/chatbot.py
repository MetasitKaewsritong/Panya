# backend/app/chatbot.py
# ✅ VERSION 2.5 - Enhanced PLCnext Expert Prompt
# - Chain-of-Thought reasoning
# - PLCnext expertise
# - Better Thai/English support
# - More abbreviations

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from typing import Generator


def preprocess_query(query: str) -> str:
    """
    แปลงคำย่อเป็นคำเต็มเพื่อช่วยในการค้นหา
    เพิ่มคำย่อ PLCnext ที่ใช้บ่อย
    """
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
    
    # Sort by length (longest first) to avoid partial matches
    sorted_abbrs = sorted(abbreviations.items(), key=lambda x: len(x[0]), reverse=True)
    
    for abbr, full_form in sorted_abbrs:
        pattern = r'\b' + re.escape(abbr) + r'\b'
        processed_query = re.sub(pattern, full_form, processed_query, flags=re.IGNORECASE)
    
    return processed_query if processed_query != query.lower() else query


def build_enhanced_prompt() -> PromptTemplate:
    """
    ✅ VERSION 2.5: PLCnext Expert Prompt with Chain-of-Thought
    """
    template = """คุณคือผู้เชี่ยวชาญด้าน PLCnext Technology จาก Phoenix Contact 
You are an expert AI assistant specializing in Phoenix Contact's PLCnext Technology platform.

## 🧠 YOUR EXPERTISE:
- PLCnext Controllers (AXC F 1152, AXC F 2152, AXC F 3152, RFC 4072S, ELC)
- Axioline I/O Systems (AXL F, AXL SE)
- Communication Protocols (PROFINET, OPC UA, Modbus, MQTT)
- PLCnext Engineer IDE and programming (IEC 61131-3, C++, C#, Python)
- Global Data Space (GDS), ESM, Real-time Linux
- Industrial automation and control systems

## 📚 CONTEXT FROM PLCNEXT DOCUMENTATION:
{context}

## 🎯 RESPONSE RULES:

### STEP 1: UNDERSTAND THE QUESTION
- What is the user asking about?
- Is it about hardware, software, programming, or configuration?
- What specific PLCnext product or feature is involved?

### STEP 2: FIND RELEVANT INFORMATION
- Search the context for relevant information
- Identify specific model numbers, specifications, or procedures
- Note any important warnings or requirements

### STEP 3: PROVIDE STRUCTURED ANSWER
**Format your response as follows:**

📌 **สรุป/Summary:** (1-2 sentences answering the core question)

📋 **รายละเอียด/Details:**
- Provide step-by-step explanation if it's a procedure
- Include technical specifications if asking about hardware
- Mention compatibility or requirements if relevant

💡 **เคล็ดลับ/Tips:** (Optional - add practical advice if helpful)

⚠️ **ข้อควรระวัง/Warnings:** (Optional - add if there are important cautions)

### STEP 4: LANGUAGE
- ถ้าคำถามเป็นภาษาไทย → ตอบเป็นภาษาไทย
- If question is in English → Answer in English
- Use technical terms in English (e.g., "PROFINET", "GDS", "OPC UA")

### STEP 5: IF NO CONTEXT MATCHES
- Use your general knowledge about PLCnext Technology
- Clearly state: "จากความรู้ทั่วไป..." or "Based on general knowledge..."
- Still provide helpful, accurate information

## ❓ USER'S QUESTION: 
{question}

## ✅ YOUR EXPERT ANSWER:
"""
    return PromptTemplate(input_variables=["context", "question"], template=template)


def build_fast_prompt() -> PromptTemplate:
    """
    Prompt สำหรับ Fast Mode (ไม่มี context) - ตอบเร็ว กระชับ
    """
    template = """You are a helpful AI assistant with expertise in PLCnext Technology from Phoenix Contact.

Answer the following question helpfully and accurately.
If it's about PLCnext, use your knowledge about industrial automation and PLC systems.

**LANGUAGE RULE:**
- ถ้าคำถามเป็นภาษาไทย → ตอบเป็นภาษาไทย
- If question is in English → Answer in English

**Question:** {question}

**Your helpful answer:**"""
    return PromptTemplate(input_variables=["question"], template=template)


def log_query_performance(query: str, response: str, retrieval_time: float, total_time: float, context_count: int):
    import logging
    logging.info(
        f"📊 Query Performance: "
        f"Query: '{query[:50]}...' | "
        f"Response Length: {len(response)} chars | "
        f"Context Count: {context_count} | "
        f"Retrieval: {retrieval_time:.2f}s | "
        f"Total: {total_time:.2f}s"
    )


def answer_question(
    question: str,
    db_pool,
    llm,
    embedder,
    collection: str,
    retriever_class,
    reranker_class,
    top_k: int = 8,  # ✅ เพิ่มเป็น 8 เพื่อให้มี context มากขึ้น
) -> dict:
    """
    ตอบคำถามโดยใช้ RAG Pipeline
    """
    import time

    processed_msg = preprocess_query((question or "").strip())
    if not processed_msg:
        return {
            "reply": "กรุณาพิมพ์คำถาม / Please enter a question.",
            "processing_time": 0.0,
            "retrieval_time": 0.0,
            "context_count": 0,
            "contexts": []
        }

    t0 = time.perf_counter()

    # Retrieve documents
    base_retriever = retriever_class(
        connection_pool=db_pool,
        embedder=embedder,
        collection=collection,
    )
    reranker_retriever = reranker_class(base_retriever=base_retriever)

    t_retr_start = time.perf_counter()
    retrieved_docs = reranker_retriever.invoke(processed_msg) or []
    retrieval_time = time.perf_counter() - t_retr_start

    # Build context
    context_texts = [d.page_content for d in retrieved_docs][:top_k]
    context_count = len(context_texts)

    prompt = build_enhanced_prompt()
    
    if context_texts:
        context_str = "\n\n---\n\n".join(
            f"📄 [Document {i+1}]\n{c}" 
            for i, c in enumerate(context_texts)
        )
    else:
        context_str = """⚠️ ไม่พบเอกสารที่เกี่ยวข้องใน database
(No relevant documents found in the database)

กรุณาตอบจากความรู้ทั่วไปเกี่ยวกับ PLCnext Technology
Please answer based on general knowledge about PLCnext Technology."""

    # Run RAG chain
    rag_chain = (
        {"context": (lambda _: context_str), "question": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )

    response_text = rag_chain.invoke(processed_msg)
    total_time = time.perf_counter() - t0

    log_query_performance(processed_msg, response_text, retrieval_time, total_time, context_count)

    return {
        "reply": response_text,
        "processing_time": total_time,
        "retrieval_time": retrieval_time,
        "context_count": context_count,
        "contexts": context_texts
    }


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
    """
    Streaming version ของ answer_question
    ส่ง token ทีละตัวกลับไปทันทีที่ LLM generate ได้
    """
    import time
    import json

    processed_msg = preprocess_query((question or "").strip())
    if not processed_msg:
        yield f"data: {json.dumps({'token': 'กรุณาพิมพ์คำถาม', 'done': True})}\n\n"
        return

    t0 = time.perf_counter()

    # Retrieve documents
    base_retriever = retriever_class(
        connection_pool=db_pool,
        embedder=embedder,
        collection=collection,
    )
    reranker_retriever = reranker_class(base_retriever=base_retriever)

    t_retr_start = time.perf_counter()
    retrieved_docs = reranker_retriever.invoke(processed_msg) or []
    retrieval_time = time.perf_counter() - t_retr_start

    # Build context
    context_texts = [d.page_content for d in retrieved_docs][:top_k]
    context_count = len(context_texts)
    
    if context_texts:
        context_str = "\n\n---\n\n".join(
            f"📄 [Document {i+1}]\n{c}" 
            for i, c in enumerate(context_texts)
        )
    else:
        context_str = """⚠️ ไม่พบเอกสารที่เกี่ยวข้องใน database
กรุณาตอบจากความรู้ทั่วไปเกี่ยวกับ PLCnext Technology"""

    # Send metadata
    yield f"data: {json.dumps({'type': 'metadata', 'retrieval_time': round(retrieval_time, 2), 'context_count': context_count})}\n\n"

    # Generate response
    prompt = build_enhanced_prompt()
    formatted_prompt = prompt.format(context=context_str, question=processed_msg)

    full_response = ""
    try:
        for chunk in llm.stream(formatted_prompt):
            if chunk:
                full_response += chunk
                yield f"data: {json.dumps({'type': 'token', 'token': chunk})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
        return

    total_time = time.perf_counter() - t0

    # Send completion
    yield f"data: {json.dumps({'type': 'done', 'processing_time': round(total_time, 2), 'retrieval_time': round(retrieval_time, 2), 'context_count': context_count})}\n\n"

    log_query_performance(processed_msg, full_response, retrieval_time, total_time, context_count)