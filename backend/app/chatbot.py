from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from typing import Generator

def preprocess_query(query: str) -> str:
    abbreviations = {
        "plc": "PLCnext", 
        "hmi": "Human Machine Interface", 
        "profinet": "PROFINET",
        "i/o": "input output", 
        "gds": "Global Data Space", 
        "esm": "Execution and Synchronization Manager"
    }
    import re
    processed_query = query.lower()
    for abbr, full_form in abbreviations.items():
        pattern = r'\b' + re.escape(abbr) + r'\b'
        processed_query = re.sub(pattern, full_form, processed_query)
    return processed_query if processed_query != query.lower() else query


def build_enhanced_prompt() -> PromptTemplate:
    template = """You are a specialized AI assistant for Phoenix Contact's PLCnext Technology platform.
**CONTEXT:**
{context}
**RESPONSE RULES:**
1. **GOLDEN ANSWERS PRIORITY:** If context contains "Question:...Answer:" pairs, you MUST use them verbatim.
2. **TECHNICAL PRECISION:** Include specific technical details, model numbers, and specifications.
3. **STRUCTURED ANSWERS:** For technical questions, provide a direct answer first, followed by specifications if relevant.
4. **PROTOCOL/MODE PRIORITY:** If the user question asks about 'protocol', 'communication mode', 'interface', or related topics, you must extract and clearly display protocol/mode information from the context. If not found, say: "I could not find protocol/mode information in the PLCnext documentation."
5. **CONTEXT ONLY:** Base answers exclusively on the provided context.
6. **NO INFO RESPONSE:** If no relevant info is found, respond with ONLY: "I could not find relevant information in the PLCnext documentation."
7. **LANGUAGE:** Answer in English language.

**QUESTION:** {question}
**TECHNICAL ANSWER:**"""
    return PromptTemplate(input_variables=["context", "question"], template=template)

def log_query_performance(query: str, response: str, retrieval_time: float, total_time: float, context_count: int):
    import logging
    logging.info(
        f"📊 Query Performance: "
        f"Query: '{query[:50]}...' | "
        f"Response Length: {len(response)} | "
        f"Context Count: {context_count} | "
        f"Retrieval Time: {retrieval_time:.2f}s | "
        f"Total Time: {total_time:.2f}s"
    )

# ============================================================
# ฟังก์ชันเดิม (ไม่มี streaming) - ใช้สำหรับ /api/chat
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
            "reply": "Message cannot be empty.",
            "processing_time": 0.0,
            "retrieval_time": 0.0,
            "context_count": 0,
            "contexts": []
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

    context_texts = [d.page_content for d in retrieved_docs][:top_k]
    context_count = len(context_texts)

    prompt = build_enhanced_prompt()
    context_str = "\n".join(f"- {c}" for c in context_texts)

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


# ============================================================
# ⚡ ฟังก์ชันใหม่ (Streaming) - ใช้สำหรับ /api/chat/stream
# ============================================================
def answer_question_stream(
    question: str,
    db_pool,
    llm,
    embedder,
    collection: str,
    retriever_class,
    reranker_class,
    top_k: int = 4,
) -> Generator[str, None, None]:
    """
    Streaming version ของ answer_question
    ส่ง token ทีละตัวกลับไปทันทีที่ LLM generate ได้
    """
    import time
    import json

    processed_msg = preprocess_query((question or "").strip())
    if not processed_msg:
        yield f"data: {json.dumps({'token': 'Message cannot be empty.', 'done': True})}\n\n"
        return

    t0 = time.perf_counter()

    # Step 1: Retrieval (ส่วนนี้ยังต้องรอ แต่ใช้เวลาแค่ 1-2 วินาที)
    base_retriever = retriever_class(
        connection_pool=db_pool,
        embedder=embedder,
        collection=collection,
    )
    reranker_retriever = reranker_class(base_retriever=base_retriever)

    t_retr_start = time.perf_counter()
    retrieved_docs = reranker_retriever.invoke(processed_msg) or []
    retrieval_time = time.perf_counter() - t_retr_start

    context_texts = [d.page_content for d in retrieved_docs][:top_k]
    context_count = len(context_texts)
    context_str = "\n".join(f"- {c}" for c in context_texts)

    # ส่ง metadata ก่อน (retrieval เสร็จแล้ว)
    yield f"data: {json.dumps({'type': 'metadata', 'retrieval_time': round(retrieval_time, 2), 'context_count': context_count})}\n\n"

    # Step 2: Build prompt
    prompt = build_enhanced_prompt()
    formatted_prompt = prompt.format(context=context_str, question=processed_msg)

    # Step 3: Stream from LLM
    full_response = ""
    try:
        # ใช้ .stream() method ของ LangChain LLM
        for chunk in llm.stream(formatted_prompt):
            if chunk:
                full_response += chunk
                yield f"data: {json.dumps({'type': 'token', 'token': chunk})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
        return

    total_time = time.perf_counter() - t0

    # ส่ง final message
    yield f"data: {json.dumps({'type': 'done', 'processing_time': round(total_time, 2), 'retrieval_time': round(retrieval_time, 2), 'context_count': context_count})}\n\n"

    log_query_performance(processed_msg, full_response, retrieval_time, total_time, context_count)