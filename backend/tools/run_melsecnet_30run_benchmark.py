"""
Run 30-run MELSECNET benchmark (15 sets, 2 modes each). 
Requires running backend via Docker and LLM connectivity.

Results output to /app/eval_reports/.
"""
import os
import sys
import json
import logging
import asyncio
from datetime import datetime, timezone
import httpx
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout
)
logger = logging.getLogger("melsecnet_30run_benchmark")

# Override to localhost for running from host if needed, or http://backend:8000 internally
BASE_URL = os.getenv("API_BASE_URL", "http://localhost:5000")

QUESTIONS = [
    # Q1
    {"qid": "Q1A", "mode": "text", "q": "For Mitsubishi Q-series MELSECNET/H system, which model do I use for an optical loop network module?", "ans": "Mitsubishi QJ71LP21-25", "group": "Optical Network Module"},
    {"qid": "Q1B", "mode": "vision", "q": "In a MELSECNET/H setup (Q-series), what model should I install for optical fiber communication?", "ans": "Mitsubishi QJ71LP21-25", "group": "Optical Network Module"},
    # Q2
    {"qid": "Q2A", "mode": "text", "q": "For Mitsubishi MELSECNET/H, which model is used for coaxial bus communication?", "ans": "Mitsubishi QJ71BR11", "group": "Coaxial Network Module"},
    {"qid": "Q2B", "mode": "vision", "q": "In a Q-series PLC network using coaxial cable, what module model do I need?", "ans": "Mitsubishi QJ71BR11", "group": "Coaxial Network Module"},
    # Q3
    {"qid": "Q3A", "mode": "text", "q": "For Mitsubishi MELSECNET/H remote I/O, what model is used for optical loop stations?", "ans": "Mitsubishi QJ72LP25-25", "group": "Remote I/O Optical Module"},
    {"qid": "Q3B", "mode": "vision", "q": "In a remote I/O optical network, which Q-series module should I install at each station?", "ans": "Mitsubishi QJ72LP25-25", "group": "Remote I/O Optical Module"},
    # Q4
    {"qid": "Q4A", "mode": "text", "q": "For Mitsubishi remote I/O over coaxial cable, which module model should I use?", "ans": "Mitsubishi QJ72BR15", "group": "Remote I/O Coaxial Module"},
    {"qid": "Q4B", "mode": "vision", "q": "In a coaxial remote I/O network (MELSECNET/H), what is the correct module?", "ans": "Mitsubishi QJ72BR15", "group": "Remote I/O Coaxial Module"},
    # Q5
    {"qid": "Q5A", "mode": "text", "q": "For Mitsubishi MELSECNET/H master station, which models can act as master modules?", "ans": "Mitsubishi QJ71LP21 / QJ71BR11", "group": "Master Module Selection"},
    {"qid": "Q5B", "mode": "vision", "q": "If I'm configuring a control/master station, which Mitsubishi modules are valid?", "ans": "Mitsubishi QJ71LP21 / QJ71BR11", "group": "Master Module Selection"},
    # Q6
    {"qid": "Q6A", "mode": "text", "q": "For Mitsubishi Q-series MELSECNET/H, what software do I use to set network parameters?", "ans": "Mitsubishi GX Developer", "group": "Software Tool"},
    {"qid": "Q6B", "mode": "vision", "q": "When configuring a network module, which Mitsubishi software is required?", "ans": "Mitsubishi GX Developer", "group": "Software Tool"},
    # Q7
    {"qid": "Q7A", "mode": "text", "q": "For Mitsubishi MELSECNET/H PLC-to-PLC network, what CPU series should I use?", "ans": "Mitsubishi QCPU", "group": "CPU Compatibility"},
    {"qid": "Q7B", "mode": "vision", "q": "Which Mitsubishi CPU family is required for Q-series network systems?", "ans": "Mitsubishi QCPU", "group": "CPU Compatibility"},
    # Q8
    {"qid": "Q8A", "mode": "text", "q": "On a Mitsubishi MELSECNET/H system, which instruction do I use to send data to another station?", "ans": "SEND", "group": "Transmission Instruction (Send)"},
    {"qid": "Q8B", "mode": "vision", "q": "For Q-series PLC communication, what instruction handles data transmission?", "ans": "SEND", "group": "Transmission Instruction (Send)"},
    # Q9
    {"qid": "Q9A", "mode": "text", "q": "For Mitsubishi MELSECNET/H, what instruction is used to receive data from another station?", "ans": "RECV", "group": "Transmission Instruction (Receive)"},
    {"qid": "Q9B", "mode": "vision", "q": "In a Q-series PLC network, which instruction handles incoming data?", "ans": "RECV", "group": "Transmission Instruction (Receive)"},
    # Q10
    {"qid": "Q10A", "mode": "text", "q": "On a Mitsubishi MELSECNET/H routing system, which instruction reads data from another station?", "ans": "ZNRD", "group": "Routing Access Instruction"},
    {"qid": "Q10B", "mode": "vision", "q": "For multi-network communication, what instruction is used to access remote word devices?", "ans": "ZNRD", "group": "Routing Access Instruction"},
    # Q11
    {"qid": "Q11A", "mode": "text", "q": "In a Mitsubishi MELSECNET/H routing setup, which instruction writes to another station?", "ans": "ZNWR", "group": "Routing Write Instruction"},
    {"qid": "Q11B", "mode": "vision", "q": "What instruction should I use to send data to another PLC over routing?", "ans": "ZNWR", "group": "Routing Write Instruction"},
    # Q12
    {"qid": "Q12A", "mode": "text", "q": "For Mitsubishi QJ71LP21 module, which test checks both cables and internal circuits?", "ans": "Self-loopback test", "group": "Standalone Test (Cable + Circuit)"},
    {"qid": "Q12B", "mode": "vision", "q": "When troubleshooting network wiring, which test mode should I run first?", "ans": "Self-loopback test", "group": "Standalone Test (Cable + Circuit)"},
    # Q13
    {"qid": "Q13A", "mode": "text", "q": "On a Mitsubishi network module, which test checks only internal circuitry?", "ans": "Internal self-loopback test", "group": "Internal Circuit Test"},
    {"qid": "Q13B", "mode": "vision", "q": "If I want to test hardware without cables, which test should I run?", "ans": "Internal self-loopback test", "group": "Internal Circuit Test"},
    # Q14
    {"qid": "Q14A", "mode": "text", "q": "For a Mitsubishi MELSECNET/H module, which test is used for hardware diagnostics?", "ans": "Hardware test", "group": "Hardware Diagnostic Test"},
    {"qid": "Q14B", "mode": "vision", "q": "If I suspect a hardware fault, which test should I select?", "ans": "Hardware test", "group": "Hardware Diagnostic Test"},
    # Q15
    {"qid": "Q15A", "mode": "text", "q": "On a Mitsubishi QJ71LP21 module, which LED indicates communication errors (CRC, TIME, etc.)?", "ans": "L ERR. LED", "group": "Communication Error Indicator"},
    {"qid": "Q15B", "mode": "vision", "q": "When diagnosing network issues, which LED should I check for link errors?", "ans": "L ERR. LED", "group": "Communication Error Indicator"}
]

async def run_single_query(client: httpx.AsyncClient, item: Dict[str, Any], idx: int) -> Dict[str, Any]:
    question = item["q"]
    mode = item["mode"]
    qid = item["qid"]
    ans = item["ans"]
    user = f"melsecnet_30run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}@example.com"
    req = {
        "message": question,
        "chat_history": [],
        "user_email": user,
        "is_vision_enabled": mode == "vision",
        "llm_model": None,  # System default
        "ragas_ground_truth": ans
    }
    
    logger.info(f"[{idx}/30] {qid} mode={mode}")
    url = f"{BASE_URL}/api/chat/stream"
    result = {
        "run_idx": idx,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "qid": qid,
        "group": item["group"],
        "question": question,
        "expected_answer": ans,
        "mode_requested": mode,
        "requested_mode_echo": None,
        "response_mode": None,
        "mode_fallback_reason": None,
        "answer_support_status": None,
        "answer": "",
        "session_id": None,
        "error": None,
        "sources": [],
        "source_details": [],
        "faithfulness": None,
        "answer_relevancy": None,
        "answer_match": None,
        "context_precision": None,
        "context_recall": None,
        "ragas_status": "pending",
        "exact_model_hit": False
    }

    metrics_captured = False
    full_answer = ""
    try:
        async with client.stream("POST", url, json=req, timeout=300.0) as response:
            if response.status_code != 200:
                body = await response.aread()
                result["error"] = f"HTTP {response.status_code}: {body.decode(errors='ignore')}"
                logger.error(f"  -> Error: {result['error']}")
                return result

            async for line in response.aiter_lines():
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                    typ = payload.get("type")
                    if typ == "token":
                        full_answer += payload.get("text", "")
                    elif typ == "stats":
                        metrics_captured = True
                        result["answer"] = full_answer.strip()
                        stats = payload.get("stats", {})
                        
                        # Populate
                        result["session_id"] = stats.get("session_id")
                        result["answer_support_status"] = stats.get("answer_support_status")
                        result["requested_mode_echo"] = stats.get("mode_requested")
                        result["response_mode"] = stats.get("mode_response")
                        result["mode_fallback_reason"] = stats.get("mode_fallback_reason")
                        
                        scores = stats.get("scores") or {}
                        result["faithfulness"] = scores.get("faithfulness")
                        result["answer_relevancy"] = scores.get("answer_relevancy")
                        result["answer_match"] = scores.get("answer_match")
                        result["context_precision"] = scores.get("context_precision")
                        result["context_recall"] = scores.get("context_recall")
                        
                        result["ragas_status"] = "computed" if result["answer_match"] is not None else "pending"
                        
                        sel = payload.get("selections", [])
                        result["source_details"] = [
                            {
                                "source": s.get("source"),
                                "source_id": s.get("source_id"),
                                "page": s.get("page"),
                                "brand": s.get("brand"),
                                "model_subbrand": s.get("model_subbrand"),
                                "chunk_id": s.get("chunk_id"),
                                "score": s.get("score")
                            } for s in sel
                        ]
                        result["sources"] = list(dict.fromkeys(s.get("source") for s in sel if s.get("source")))
                        
                        ans_lower = result["answer"].lower()
                        exp_lower = ans.lower().replace("mitsubishi", "").strip()
                        hit = False
                        if " / " in exp_lower:
                            parts = exp_lower.split(" / ")
                            hit = all(p.strip() in ans_lower for p in parts)
                        else:
                            hit = exp_lower in ans_lower
                            
                        result["exact_model_hit"] = hit
                        
                except Exception as e:
                    pass
    except Exception as e:
        result["error"] = str(e)
        logger.error(f"  -> Exception: {e}")

    if not metrics_captured:
        result["answer"] = full_answer.strip()
    
    logger.info(f"  -> resp={result['response_mode']} hit={result['exact_model_hit']} "
                f"fallback={result['mode_fallback_reason'] or '-'} "
                f"faith={result['faithfulness'] or 'N/A'} rel={result['answer_relevancy'] or 'N/A'} "
                f"match={result['answer_match'] or 'N/A'}")
    logger.info(f"  -> Answer: {result['answer']}")
    return result

import time

async def main():
    logger.info(f"Starting benchmark with {len(QUESTIONS)} runs. ENABLE_BACKGROUND_RAGAS MUST BE FALSE for synchronous scores.")
    
    results = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_count": len(QUESTIONS),
        "runs": []
    }
    
    async with httpx.AsyncClient() as client:
        try:
            auth_email = f"benchmark_{int(time.time())}@example.com"
            auth_pass = "benchmark_pass"
            await client.post(f"{BASE_URL}/api/auth/register", json={"email": auth_email, "full_name": "Benchmark User", "password": auth_pass}, timeout=10.0)
            r_log = await client.post(f"{BASE_URL}/api/auth/login", json={"email": auth_email, "password": auth_pass}, timeout=10.0)
            r_log.raise_for_status()
            token = r_log.json().get("access_token")
            client.headers.update({"Authorization": f"Bearer {token}"})
            logger.info("Successfully authenticated with backend.")
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            return

        # Check health
        try:
            r = await client.get(f"{BASE_URL}/health", timeout=5.0)
            r.raise_for_status()
        except Exception as e:
            logger.error(f"Backend not reachable at {BASE_URL}/health: {e}")
            return
            
        for i, item in enumerate(QUESTIONS):
            run_res = await run_single_query(client, item, i + 1)
            results["runs"].append(run_res)
    
    # Save results
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    os.makedirs("/app/eval_reports", exist_ok=True)
    out_json = f"/app/eval_reports/melsecnet_30run_benchmark_{ts}.json"
    
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
        
    logger.info(f"Done. JSON: {out_json}")

if __name__ == "__main__":
    asyncio.run(main())
