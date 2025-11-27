from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

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
    # ✅ แก้จาก get_relevant_documents เป็น invoke
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