#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

QUESTION_BANK = [
    {
        "qid": "Q1A",
        "group": "Network Module Model",
        "question": "What is the model number of the MELSECNET/H network module used in the exercise?",
        "expected_answer": "QJ71LP21-25",
    },
    {
        "qid": "Q1B",
        "group": "Network Module Model",
        "question": "Identify the network module model shown in Chapter 3 component setup.",
        "expected_answer": "QJ71LP21-25",
    },
    {
        "qid": "Q2A",
        "group": "Remote I/O Module Model",
        "question": "What is the model number of the remote I/O module in MELSECNET/H?",
        "expected_answer": "QJ72LP25-25",
    },
    {
        "qid": "Q2B",
        "group": "Remote I/O Module Model",
        "question": "Identify the module used as a remote I/O station.",
        "expected_answer": "QJ72LP25-25",
    },
    {
        "qid": "Q3A",
        "group": "Coaxial Network Module",
        "question": "What model is used for the coaxial bus type network module?",
        "expected_answer": "QJ71BR11",
    },
    {
        "qid": "Q3B",
        "group": "Coaxial Network Module",
        "question": "Identify the MELSECNET/H module for coaxial communication.",
        "expected_answer": "QJ71BR11",
    },
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _avg(values: list[float | None]) -> float | None:
    items = [v for v in values if v is not None]
    if not items:
        return None
    return sum(items) / len(items)


def _fmt(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.3f}"


def _normalize_model(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _exact_model_hit(expected: str, answer: str) -> bool:
    normalized_expected = _normalize_model(expected)
    normalized_answer = _normalize_model(answer)
    return bool(normalized_expected) and normalized_expected in normalized_answer


def _auth(session: requests.Session, base_url: str, email: str, password: str) -> str:
    register_payload = {
        "email": email,
        "password": password,
        "full_name": "MELSECNET Benchmark",
    }
    session.post(f"{base_url}/api/auth/register", json=register_payload, timeout=30)
    login = session.post(
        f"{base_url}/api/auth/login",
        json={"email": email, "password": password},
        timeout=30,
    )
    login.raise_for_status()
    return login.json()["access_token"]


def _run_stream(
    *,
    session: requests.Session,
    base_url: str,
    token: str,
    question: str,
    expected_answer: str,
    mode_requested: str,
    timeout_s: int,
) -> dict[str, Any]:
    payload = {
        "message": question,
        "session_id": None,
        "use_page_images": mode_requested == "vision",
        "ragas_ground_truth": expected_answer,
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    result: dict[str, Any] = {
        "session_id": None,
        "answer": "",
        "stats": {},
        "error": None,
    }

    try:
        with session.post(
            f"{base_url}/api/chat/stream",
            headers=headers,
            json=payload,
            stream=True,
            timeout=timeout_s,
        ) as response:
            response.raise_for_status()
            chunks: list[str] = []
            stats: dict[str, Any] = {}
            for raw in response.iter_lines(decode_unicode=True):
                if not raw:
                    continue
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                event_type = event.get("type")
                if event_type == "session":
                    result["session_id"] = event.get("id")
                elif event_type == "token":
                    chunks.append(str(event.get("text") or ""))
                elif event_type == "stats":
                    stats = event.get("data") or {}

            result["answer"] = "".join(chunks).strip()
            result["stats"] = stats
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)

    return result


def _build_run_record(
    *,
    run_idx: int,
    item: dict[str, str],
    mode: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    stats = result.get("stats") or {}
    ragas = stats.get("ragas") or {}
    answer = (result.get("answer") or "").strip()
    if not answer and result.get("error"):
        answer = f"[ERROR] {result['error']}"

    record = {
        "run_idx": run_idx,
        "created_at": _now_iso(),
        "qid": item["qid"],
        "group": item["group"],
        "question": item["question"],
        "expected_answer": item["expected_answer"],
        "mode_requested": mode,
        "requested_mode_echo": stats.get("requested_mode", mode),
        "response_mode": stats.get("response_mode"),
        "mode_fallback_reason": stats.get("mode_fallback_reason"),
        "answer_support_status": stats.get("answer_support_status"),
        "answer": answer,
        "session_id": result.get("session_id"),
        "error": result.get("error"),
        "sources": stats.get("sources") or [],
        "source_details": stats.get("source_details") or [],
        "faithfulness": _safe_float(ragas.get("faithfulness")),
        "answer_relevancy": _safe_float(ragas.get("answer_relevancy")),
        "answer_match": _safe_float(ragas.get("answer_match")),
        "context_precision": _safe_float(ragas.get("context_precision")),
        "context_recall": _safe_float(ragas.get("context_recall")),
        "ragas_status": stats.get("ragas_status") or ("error" if result.get("error") else "unknown"),
    }
    record["exact_model_hit"] = _exact_model_hit(item["expected_answer"], answer)
    return record


def _mode_summary(runs: list[dict[str, Any]], mode: str) -> dict[str, Any]:
    subset = [run for run in runs if run["mode_requested"] == mode]
    return {
        "mode": mode,
        "runs": len(subset),
        "exact_hits": sum(1 for run in subset if run["exact_model_hit"]),
        "hit_rate": (sum(1 for run in subset if run["exact_model_hit"]) / len(subset)) if subset else None,
        "faithfulness_avg": _avg([run["faithfulness"] for run in subset]),
        "answer_relevancy_avg": _avg([run["answer_relevancy"] for run in subset]),
        "answer_match_avg": _avg([run["answer_match"] for run in subset]),
        "fallback_count": sum(1 for run in subset if run.get("mode_fallback_reason")),
        "response_modes": sorted({run.get("response_mode") or "unknown" for run in subset}),
    }


def _question_summary(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in QUESTION_BANK:
        for mode in ("text", "vision"):
            subset = [
                run for run in runs
                if run["qid"] == item["qid"] and run["mode_requested"] == mode
            ]
            rows.append(
                {
                    "qid": item["qid"],
                    "mode": mode,
                    "expected_answer": item["expected_answer"],
                    "exact_hits": sum(1 for run in subset if run["exact_model_hit"]),
                    "runs": len(subset),
                    "faithfulness_avg": _avg([run["faithfulness"] for run in subset]),
                    "answer_relevancy_avg": _avg([run["answer_relevancy"] for run in subset]),
                    "answer_match_avg": _avg([run["answer_match"] for run in subset]),
                    "response_modes": sorted({run.get("response_mode") or "unknown" for run in subset}),
                }
            )
    return rows


def _render_markdown(
    *,
    generated_at: str,
    benchmark_user: str,
    runs: list[dict[str, Any]],
    mode_rows: list[dict[str, Any]],
    question_rows: list[dict[str, Any]],
) -> str:
    lines: list[str] = []
    lines.append("# MELSECNET/H Benchmark (Q1A-Q3B, Text vs Vision)")
    lines.append("")
    lines.append(f"- Generated: {generated_at}")
    lines.append(f"- Benchmark user: `{benchmark_user}`")
    lines.append(f"- Total runs: {len(runs)}")
    lines.append("- Coverage: `Q1A`, `Q1B`, `Q2A`, `Q2B`, `Q3A`, `Q3B` in both `text` and `vision` modes")
    lines.append("")
    lines.append("## Overall Results")
    lines.append("")
    lines.append("| Mode | Runs | Exact Hits | Hit Rate | Faithfulness Avg | Answer Relevancy Avg | Answer Match Avg | Fallback Count | Response Modes |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---|")
    for row in mode_rows:
        hit_rate = "N/A" if row["hit_rate"] is None else f"{row['hit_rate']:.1%}"
        response_modes = ", ".join(row["response_modes"]) or "-"
        lines.append(
            f"| {row['mode']} | {row['runs']} | {row['exact_hits']} | {hit_rate} | {_fmt(row['faithfulness_avg'])} | {_fmt(row['answer_relevancy_avg'])} | {_fmt(row['answer_match_avg'])} | {row['fallback_count']} | {response_modes} |"
        )

    lines.append("")
    lines.append("## Per-Question Results")
    lines.append("")
    lines.append("| QID | Mode | Expected | Exact Hits | Runs | Faithfulness Avg | Answer Relevancy Avg | Answer Match Avg | Response Modes |")
    lines.append("|---|---|---|---:|---:|---:|---:|---:|---|")
    for row in question_rows:
        response_modes = ", ".join(row["response_modes"]) or "-"
        lines.append(
            f"| {row['qid']} | {row['mode']} | `{row['expected_answer']}` | {row['exact_hits']} | {row['runs']} | {_fmt(row['faithfulness_avg'])} | {_fmt(row['answer_relevancy_avg'])} | {_fmt(row['answer_match_avg'])} | {response_modes} |"
        )

    lines.append("")
    lines.append("## Detailed Runs")
    lines.append("")
    lines.append("| # | QID | Mode Req | Mode Resp | Exact Hit | Faith | Rel | Match | Fallback |")
    lines.append("|---:|---|---|---|---|---:|---:|---:|---|")
    for run in runs:
        lines.append(
            f"| {run['run_idx']} | {run['qid']} | {run['mode_requested']} | {run.get('response_mode') or '-'} | {'yes' if run['exact_model_hit'] else 'no'} | {_fmt(run['faithfulness'])} | {_fmt(run['answer_relevancy'])} | {_fmt(run['answer_match'])} | {run.get('mode_fallback_reason') or '-'} |"
        )

    lines.append("")
    lines.append("## Answers")
    lines.append("")
    for run in runs:
        answer = (run.get("answer") or "").replace("\n", " ").strip()
        if len(answer) > 260:
            answer = answer[:260].rstrip() + "..."
        lines.append(f"- `#{run['run_idx']} {run['qid']} {run['mode_requested']}` expected `{run['expected_answer']}` -> {answer}")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run MELSECNET/H Q1A-Q3B benchmark in text and vision modes.")
    parser.add_argument("--base-url", default="http://localhost:5000")
    parser.add_argument("--output-dir", default="/app/eval_reports")
    parser.add_argument("--email", default="")
    parser.add_argument("--password", default="Benchmark!123")
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--sleep", type=float, default=1.0)
    args = parser.parse_args()

    generated_dt = datetime.now()
    stamp = generated_dt.strftime("%Y%m%d_%H%M%S")
    generated_str = generated_dt.strftime("%Y-%m-%d %H:%M:%S")
    email = args.email.strip() or f"melsecnet_benchmark_{stamp}@example.com"

    base_url = args.base_url.rstrip("/")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    token = _auth(session, base_url, email, args.password)

    runs: list[dict[str, Any]] = []
    run_idx = 0
    total_runs = len(QUESTION_BANK) * 2
    print(f"Starting benchmark with {total_runs} runs")

    for item in QUESTION_BANK:
        for mode in ("text", "vision"):
            run_idx += 1
            print(f"[{run_idx}/{total_runs}] {item['qid']} mode={mode}")
            result = _run_stream(
                session=session,
                base_url=base_url,
                token=token,
                question=item["question"],
                expected_answer=item["expected_answer"],
                mode_requested=mode,
                timeout_s=args.timeout,
            )
            record = _build_run_record(
                run_idx=run_idx,
                item=item,
                mode=mode,
                result=result,
            )
            runs.append(record)
            print(
                "  -> "
                f"resp={record.get('response_mode') or '-'} "
                f"hit={'yes' if record['exact_model_hit'] else 'no'} "
                f"fallback={record.get('mode_fallback_reason') or '-'} "
                f"faith={_fmt(record['faithfulness'])} "
                f"rel={_fmt(record['answer_relevancy'])}"
            )
            time.sleep(max(0.0, args.sleep))

    mode_rows = [_mode_summary(runs, "text"), _mode_summary(runs, "vision")]
    question_rows = _question_summary(runs)

    payload = {
        "generated_at": _now_iso(),
        "benchmark_user": email,
        "question_scope": [item["qid"] for item in QUESTION_BANK],
        "run_count": len(runs),
        "runs": runs,
        "mode_summary": mode_rows,
        "question_summary": question_rows,
    }

    json_path = output_dir / f"melsecnet_q1_q3_benchmark_{stamp}.json"
    md_path = output_dir / f"melsecnet_q1_q3_benchmark_{stamp}.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(
        _render_markdown(
            generated_at=generated_str,
            benchmark_user=email,
            runs=runs,
            mode_rows=mode_rows,
            question_rows=question_rows,
        ),
        encoding="utf-8",
    )

    print(f"Done. JSON: {json_path}")
    print(f"Done. MD:   {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
