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
    # ✅ VERSION 2.3: Prompt ที่ตอบละเอียดและครอบคลุมมากขึ้น
    template = """You are a specialized AI assistant for Phoenix Contact's PLCnext Technology platform.

**CONTEXT FROM DOCUMENTATION:**
{context}

**RESPONSE GUIDELINES:**

1. **COMPREHENSIVE ANSWERS:** Provide **detailed, thorough responses**. Do not give brief or superficial answers.

2. **STRUCTURE YOUR RESPONSE:** 
   - Start with a clear summary/overview
   - Break down into key points with explanations
   - Include technical details, specifications, model numbers when available
   - End with practical implications or next steps if relevant

3. **GOLDEN ANSWERS:** If context contains "Question:...Answer:" pairs, prioritize that information.

4. **USE ALL RELEVANT CONTEXT:** Extract and synthesize information from multiple parts of the context to provide complete answers.

5. **LANGUAGE:** Answer in the **same language** as the user's question:
   - If question is in Thai → Answer in Thai
   - If question is in English → Answer in English

6. **WHEN NO CONTEXT MATCHES:** If the context doesn't contain relevant information, provide a helpful answer based on your general knowledge about PLCnext, Phoenix Contact, or industrial automation. Clearly indicate when using general knowledge.

7. **FOR DOCUMENT SUMMARIES:** When asked about uploaded files, provide:
   - Main topic/purpose of the document
   - Key findings or main points (at least 5-7 points)
   - Technical details or specifications mentioned
   - Conclusions or recommendations

**USER'S QUESTION:** {question}

**DETAILED TECHNICAL ANSWER:**"""
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


def answer_question(
    question: str,
    db_pool,
    llm,
    embedder,
    collection: str,
    retriever_class,
    reranker_class,
    top_k: int = 6,  # ✅ เพิ่มจาก 4 เป็น 6 เพื่อให้มี context มากขึ้น
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
    
    if context_texts:
        context_str = "\n\n".join(f"[Source {i+1}]\n{c}" for i, c in enumerate(context_texts))
    else:
        context_str = "(No specific documentation found. Please provide a helpful answer based on general knowledge about PLCnext Technology and industrial automation.)"

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
    top_k: int = 6,
) -> Generator[str, None, None]:
    """Streaming version ของ answer_question"""
    import time
    import json

    processed_msg = preprocess_query((question or "").strip())
    if not processed_msg:
        yield f"data: {json.dumps({'token': 'Message cannot be empty.', 'done': True})}\n\n"
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

    context_texts = [d.page_content for d in retrieved_docs][:top_k]
    context_count = len(context_texts)
    
    if context_texts:
        context_str = "\n\n".join(f"[Source {i+1}]\n{c}" for i, c in enumerate(context_texts))
    else:
        context_str = "(No specific documentation found. Please provide a helpful answer based on general knowledge about PLCnext Technology.)"

    yield f"data: {json.dumps({'type': 'metadata', 'retrieval_time': round(retrieval_time, 2), 'context_count': context_count})}\n\n"

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

    yield f"data: {json.dumps({'type': 'done', 'processing_time': round(total_time, 2), 'retrieval_time': round(retrieval_time, 2), 'context_count': context_count})}\n\n"

    log_query_performance(processed_msg, full_response, retrieval_time, total_time, context_count)