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

METRIC_KEYS = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]
PREFIX_DEFAULT = "For FX/FX0N-485ADP manual: "

QUESTION_BANK = [
    {
        "qid": "Q1A",
        "group": "Weight",
        "question": "According to the external dimensions diagram for the FX-485ADP, what is the weight listed for the unit?",
        "expected_answer": "Approximately 0.3 kg (0.66 lbs)",
    },
    {
        "qid": "Q1B",
        "group": "Weight",
        "question": "Based on the technical drawing for the FX0N-485ADP, what is the approximate mass of the device?",
        "expected_answer": "Approximately 0.3 kg (0.66 lbs)",
    },
    {
        "qid": "Q2A",
        "group": "Resistance",
        "question": 'According to the "Two-pair wiring" notes, what is the specific resistance value (R) that must be connected between terminals SDA and SDB?',
        "expected_answer": "330 Ω",
    },
    {
        "qid": "Q2B",
        "group": "Resistance",
        "question": 'Based on the "Terminating resistances" classification table, what ohm value is required for a 1/4W resistor when using an RS-422 circuit?',
        "expected_answer": "330 Ω",
    },
    {
        "qid": "Q3A",
        "group": "Device Symbols",
        "question": 'According to the Computer Commands table, which objective device symbols are listed for the "BR" (Bit Read) function?',
        "expected_answer": "X, Y, M, S, T, and C",
    },
    {
        "qid": "Q3B",
        "group": "Device Symbols",
        "question": 'Looking at the "BW" command entry in the ASCII code table, what specific devices can be written in batch as one-point units?',
        "expected_answer": "X, Y, M, S, T, and C",
    },
]


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _avg(values: list[float | None]) -> float | None:
    nums = [v for v in values if v is not None]
    if not nums:
        return None
    return sum(nums) / len(nums)


def _fmt_metric(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.3f}"


def _manual_match_score(group: str, answer: str) -> float:
    text = (answer or "").lower()
    if group == "Weight":
        has_03 = bool(re.search(r"\b0\.?3\b", text))
        has_066_or_lbs = bool(re.search(r"\b0\.?66\b", text)) or ("lbs" in text)
        return 1.0 if has_03 and has_066_or_lbs else 0.0
    if group == "Resistance":
        return 1.0 if bool(re.search(r"\b330\b", text)) else 0.0
    if group == "Device Symbols":
        symbols = ["x", "y", "m", "s", "t", "c"]
        hits = 0
        for symbol in symbols:
            if re.search(rf"\b{symbol}\b", text):
                hits += 1
        return hits / len(symbols)
    return 0.0


def _make_questions(prefix: str) -> list[dict[str, str]]:
    questions: list[dict[str, str]] = []
    for item in QUESTION_BANK:
        q = dict(item)
        q["question"] = f"{prefix}{item['question']}"
        questions.append(q)
    return questions


def _auth(session: requests.Session, base_url: str, email: str, password: str) -> str:
    register_payload = {
        "email": email,
        "password": password,
        "full_name": "Benchmark Runner",
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
    session: requests.Session,
    base_url: str,
    token: str,
    question: str,
    ragas_ground_truth: str,
    mode_requested: str,
    timeout_s: int,
) -> dict[str, Any]:
    payload = {
        "message": question,
        "session_id": None,
        "use_page_images": mode_requested == "vision",
        "ragas_ground_truth": ragas_ground_truth,
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
        ) as resp:
            resp.raise_for_status()
            chunks: list[str] = []
            stats: dict[str, Any] = {}
            for raw in resp.iter_lines(decode_unicode=True):
                if not raw:
                    continue
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                ev_type = event.get("type")
                if ev_type == "session":
                    result["session_id"] = event.get("id")
                elif ev_type == "token":
                    chunks.append(str(event.get("text") or ""))
                elif ev_type == "stats":
                    stats = event.get("data") or {}

            result["answer"] = "".join(chunks).strip()
            result["stats"] = stats
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)

    return result


def _build_run_record(
    *,
    run_idx: int,
    q: dict[str, str],
    mode: str,
    rep: int,
    out: dict[str, Any],
    attempt: int,
    max_attempts: int,
) -> dict[str, Any]:
    stats = out.get("stats") or {}
    ragas = stats.get("ragas") or {}
    ragas_status = stats.get("ragas_status")
    if not ragas_status:
        ragas_status = "error" if out.get("error") else "unknown"

    answer = (out.get("answer") or "").strip()
    if not answer and out.get("error"):
        answer = f"[ERROR] {out['error']}"

    run = {
        "run_idx": run_idx,
        "session_id": out.get("session_id"),
        "created_at": _now_utc_iso(),
        "qid": q["qid"],
        "group": q["group"],
        "mode_requested": mode,
        "repeat": rep,
        "question": q["question"],
        "expected_answer": q["expected_answer"],
        "ragas_ground_truth": q["expected_answer"],
        "answer": answer,
        "requested_mode_echo": stats.get("requested_mode", mode),
        "response_mode": stats.get("response_mode", mode),
        "mode_fallback_reason": stats.get("mode_fallback_reason"),
        "ragas_status": ragas_status,
        "faithfulness": _safe_float(ragas.get("faithfulness")),
        "answer_relevancy": _safe_float(ragas.get("answer_relevancy")),
        "context_precision": _safe_float(ragas.get("context_precision")),
        "context_recall": _safe_float(ragas.get("context_recall")),
        "manual_match_score": _manual_match_score(q["group"], answer),
        "error": out.get("error"),
        "attempt": attempt,
        "max_attempts": max_attempts,
    }
    missing_metrics = [k for k in METRIC_KEYS if run[k] is None]
    run["missing_metrics"] = missing_metrics
    run["metrics_complete"] = len(missing_metrics) == 0
    return run


def _mode_summary(runs: list[dict[str, Any]], mode: str) -> dict[str, Any]:
    subset = [r for r in runs if r["mode_requested"] == mode]
    return {
        "mode": mode,
        "runs": len(subset),
        "faithfulness_avg": _avg([r["faithfulness"] for r in subset]),
        "answer_relevancy_avg": _avg([r["answer_relevancy"] for r in subset]),
        "context_precision_avg": _avg([r["context_precision"] for r in subset]),
        "context_recall_avg": _avg([r["context_recall"] for r in subset]),
        "manual_match_avg": _avg([r["manual_match_score"] for r in subset]),
        "fallback_count": sum(1 for r in subset if r.get("mode_fallback_reason")),
        "faith_na": sum(1 for r in subset if r["faithfulness"] is None),
        "rel_na": sum(1 for r in subset if r["answer_relevancy"] is None),
        "cp_na": sum(1 for r in subset if r["context_precision"] is None),
        "cr_na": sum(1 for r in subset if r["context_recall"] is None),
    }


def _per_question_summary(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in QUESTION_BANK:
        qid = item["qid"]
        for mode in ("text", "vision"):
            subset = [r for r in runs if r["qid"] == qid and r["mode_requested"] == mode]
            rows.append(
                {
                    "qid": qid,
                    "mode": mode,
                    "runs": len(subset),
                    "faithfulness_avg": _avg([r["faithfulness"] for r in subset]),
                    "answer_relevancy_avg": _avg([r["answer_relevancy"] for r in subset]),
                    "context_precision_avg": _avg([r["context_precision"] for r in subset]),
                    "context_recall_avg": _avg([r["context_recall"] for r in subset]),
                    "manual_match_avg": _avg([r["manual_match_score"] for r in subset]),
                    "cp_na": sum(1 for r in subset if r["context_precision"] is None),
                    "cr_na": sum(1 for r in subset if r["context_recall"] is None),
                }
            )
    return rows


def _markdown_report(
    generated_at: str,
    benchmark_user: str,
    prefix: str,
    runs: list[dict[str, Any]],
    mode_summary: list[dict[str, Any]],
    q_summary: list[dict[str, Any]],
) -> str:
    lines: list[str] = []
    lines.append("# Text vs Vision Benchmark (FX/FX0N-485ADP)")
    lines.append("")
    lines.append(f"- Generated: {generated_at}")
    lines.append(f"- Benchmark user: `{benchmark_user}`")
    lines.append(f"- Total completed runs: {len(runs)}")
    lines.append(f"- Prefix used: `{prefix}`")
    lines.append("- RAGAS ground-truth mode: `injected_expected_answer`")
    lines.append("")
    lines.append("## Ground Truth Used")
    lines.append("")
    lines.append("- Weight (`Q1A`, `Q1B`): `Approximately 0.3 kg (0.66 lbs)`")
    lines.append("- Resistance (`Q2A`, `Q2B`): `330 Ω`")
    lines.append("- Device Symbols (`Q3A`, `Q3B`): `X, Y, M, S, T, and C`")
    lines.append("")
    lines.append("## Overall Mode Comparison")
    lines.append("")
    lines.append("| Mode | Runs | Faithfulness Avg | Answer Relevancy Avg | Context Precision Avg | Context Recall Avg | Manual Match Avg | Fallback Count | Faith N/A | Rel N/A | CP N/A | CR N/A |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in mode_summary:
        lines.append(
            f"| {row['mode']} | {row['runs']} | {_fmt_metric(row['faithfulness_avg'])} | {_fmt_metric(row['answer_relevancy_avg'])} | {_fmt_metric(row['context_precision_avg'])} | {_fmt_metric(row['context_recall_avg'])} | {_fmt_metric(row['manual_match_avg'])} | {row['fallback_count']} | {row['faith_na']} | {row['rel_na']} | {row['cp_na']} | {row['cr_na']} |"
        )

    lines.append("")
    lines.append("## Per-Question Averages (Text vs Vision)")
    lines.append("")
    lines.append("| QID | Mode | Runs | Faithfulness Avg | Answer Relevancy Avg | Context Precision Avg | Context Recall Avg | Manual Match Avg | CP N/A | CR N/A |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in q_summary:
        lines.append(
            f"| {row['qid']} | {row['mode']} | {row['runs']} | {_fmt_metric(row['faithfulness_avg'])} | {_fmt_metric(row['answer_relevancy_avg'])} | {_fmt_metric(row['context_precision_avg'])} | {_fmt_metric(row['context_recall_avg'])} | {_fmt_metric(row['manual_match_avg'])} | {row['cp_na']} | {row['cr_na']} |"
        )

    lines.append("")
    lines.append("## Detailed Runs")
    lines.append("")
    lines.append("| # | QID | Mode Req | Mode Resp | Repeat | Faith | Rel | Ctx Prec | Ctx Rec | RAGAS Status | Fallback | Manual Match |")
    lines.append("|---:|---|---|---|---:|---:|---:|---:|---:|---|---|---:|")
    for row in runs:
        lines.append(
            f"| {row['run_idx']} | {row['qid']} | {row['mode_requested']} | {row.get('response_mode') or '-'} | {row['repeat']} | {_fmt_metric(row['faithfulness'])} | {_fmt_metric(row['answer_relevancy'])} | {_fmt_metric(row['context_precision'])} | {_fmt_metric(row['context_recall'])} | {row.get('ragas_status') or '-'} | {row.get('mode_fallback_reason') or '-'} | {_fmt_metric(row['manual_match_score'])} |"
        )

    lines.append("")
    lines.append("## Answer Snapshots")
    lines.append("")
    for row in runs:
        answer = (row.get("answer") or "").replace("\n", " ").strip()
        if len(answer) > 220:
            answer = answer[:220].rstrip() + "..."
        lines.append(f"- `#{row['run_idx']} {row['qid']} {row['mode_requested']} rep{row['repeat']}`: {answer}")

    error_count = sum(1 for r in runs if r.get("ragas_status") == "error")
    pending_count = sum(1 for r in runs if r.get("ragas_status") == "pending")
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append(f"- `ragas_status=error` count: {error_count}")
    lines.append(f"- `ragas_status=pending` count: {pending_count}")
    lines.append(f"- runs with all 4 metrics present: {sum(1 for r in runs if r.get('metrics_complete'))}/{len(runs)}")
    lines.append("- Manual-match score is a simple heuristic against expected answers.")
    lines.append("- For fairness, benchmark injects exact `expected_answer` as `ragas_ground_truth` on each request.")
    lines.append("")

    return "\n".join(lines)


def _write_reports(
    *,
    generated_str: str,
    benchmark_user: str,
    prefix: str,
    stamp: str,
    output_dir: str,
    runs: list[dict[str, Any]],
    metric_retries: int,
    retry_sleep: float,
    interrupted: bool,
    interruption_reason: str | None,
) -> tuple[Path, Path]:
    mode_summary = [_mode_summary(runs, "text"), _mode_summary(runs, "vision")]
    q_summary = _per_question_summary(runs)

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base_name = f"benchmark_text_vs_vision_fx_fx0n_consolidated_{stamp}"
    json_path = out_dir / f"{base_name}.json"
    md_path = out_dir / f"{base_name}.md"

    payload = {
        "generated_at": _now_utc_iso(),
        "benchmark_user": benchmark_user,
        "total_runs": len(runs),
        "prefix_used": prefix,
        "ragas_ground_truth_mode": "injected_expected_answer",
        "metric_retries": metric_retries,
        "retry_sleep": retry_sleep,
        "interrupted": interrupted,
        "interruption_reason": interruption_reason,
        "runs": runs,
        "overall_mode_comparison": mode_summary,
        "per_question_mode_summary": q_summary,
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    md = _markdown_report(
        generated_at=generated_str,
        benchmark_user=benchmark_user,
        prefix=prefix,
        runs=runs,
        mode_summary=mode_summary,
        q_summary=q_summary,
    )
    if interrupted:
        md += "\n\n## Run Status\n\n- This run ended early.\n"
        if interruption_reason:
            md += f"- Reason: `{interruption_reason}`\n"
    md_path.write_text(md, encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run text-vs-vision benchmark and export JSON/MD reports.")
    parser.add_argument("--base-url", default="http://localhost:5000")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--prefix", default=PREFIX_DEFAULT)
    parser.add_argument("--timeout", type=int, default=420, help="Per-request timeout in seconds")
    parser.add_argument("--output-dir", default="reports")
    parser.add_argument("--email", default="")
    parser.add_argument("--password", default="Benchmark!123")
    parser.add_argument("--sleep", type=float, default=1.0, help="Sleep seconds between runs")
    parser.add_argument(
        "--metric-retries",
        type=int,
        default=2,
        help="Retries when any RAGAS metric is missing (total attempts = 1 + metric-retries)",
    )
    parser.add_argument("--retry-sleep", type=float, default=5.0, help="Sleep seconds between retry attempts")
    parser.add_argument(
        "--checkpoint-interval",
        type=int,
        default=1,
        help="Write JSON/MD checkpoints every N completed runs (0 to disable checkpoints)",
    )
    parser.add_argument(
        "--max-runs",
        type=int,
        default=0,
        help="Stop after N runs (0 = no limit) and still write partial JSON/MD outputs",
    )
    args = parser.parse_args()

    generated_dt = datetime.now()
    stamp = generated_dt.strftime("%Y%m%d_%H%M%S")
    generated_str = generated_dt.strftime("%Y-%m-%d %H:%M:%S")
    email = args.email.strip() or f"benchmark_{stamp}@example.com"

    questions = _make_questions(args.prefix)
    total_runs = len(questions) * 2 * args.repeats
    print(f"Starting benchmark: {total_runs} runs")
    print(f"Base URL: {args.base_url}")
    print(f"Benchmark user: {email}")

    session = requests.Session()
    runs: list[dict[str, Any]] = []
    run_idx = 0
    interrupted = False
    interruption_reason: str | None = None

    try:
        token = _auth(session, args.base_url.rstrip("/"), email, args.password)
        for q in questions:
            for mode in ("text", "vision"):
                for rep in range(1, args.repeats + 1):
                    if args.max_runs > 0 and run_idx >= args.max_runs:
                        print(f"Reached --max-runs={args.max_runs}; finalizing partial report.")
                        break
                    run_idx += 1
                    print(f"[{run_idx}/{total_runs}] {q['qid']} mode={mode} rep={rep}")
                    max_attempts = max(1, args.metric_retries + 1)
                    run: dict[str, Any] | None = None

                    for attempt in range(1, max_attempts + 1):
                        out = _run_stream(
                            session=session,
                            base_url=args.base_url.rstrip("/"),
                            token=token,
                            question=q["question"],
                            ragas_ground_truth=q["expected_answer"],
                            mode_requested=mode,
                            timeout_s=args.timeout,
                        )
                        run_candidate = _build_run_record(
                            run_idx=run_idx,
                            q=q,
                            mode=mode,
                            rep=rep,
                            out=out,
                            attempt=attempt,
                            max_attempts=max_attempts,
                        )
                        run = run_candidate
                        if run_candidate["metrics_complete"] or attempt == max_attempts:
                            break
                        missing = ",".join(run_candidate["missing_metrics"])
                        print(
                            "  -> "
                            f"missing_metrics={missing} "
                            f"(attempt {attempt}/{max_attempts}); retrying..."
                        )
                        time.sleep(max(0.0, args.retry_sleep))

                    if run is None:
                        raise RuntimeError("internal error: run record was not captured")

                    runs.append(run)
                    print(
                        "  -> "
                        f"resp={run['response_mode']} "
                        f"fallback={run['mode_fallback_reason'] or '-'} "
                        f"ragas={run['ragas_status']} "
                        f"attempt={run['attempt']}/{run['max_attempts']} "
                        f"faith={_fmt_metric(run['faithfulness'])} "
                        f"rel={_fmt_metric(run['answer_relevancy'])}"
                    )

                    if args.checkpoint_interval > 0 and len(runs) % args.checkpoint_interval == 0:
                        _write_reports(
                            generated_str=generated_str,
                            benchmark_user=email,
                            prefix=args.prefix,
                            stamp=stamp,
                            output_dir=args.output_dir,
                            runs=runs,
                            metric_retries=args.metric_retries,
                            retry_sleep=args.retry_sleep,
                            interrupted=False,
                            interruption_reason=None,
                        )
                    time.sleep(max(0.0, args.sleep))
                if args.max_runs > 0 and run_idx >= args.max_runs:
                    break
            if args.max_runs > 0 and run_idx >= args.max_runs:
                break
    except KeyboardInterrupt:
        interrupted = True
        interruption_reason = "KeyboardInterrupt"
        print("\nInterrupted by user. Writing partial report...")
    except Exception as exc:  # noqa: BLE001
        interrupted = True
        interruption_reason = f"{type(exc).__name__}: {exc}"
        print(f"\nRun interrupted by error: {interruption_reason}")

    json_path, md_path = _write_reports(
        generated_str=generated_str,
        benchmark_user=email,
        prefix=args.prefix,
        stamp=stamp,
        output_dir=args.output_dir,
        runs=runs,
        metric_retries=args.metric_retries,
        retry_sleep=args.retry_sleep,
        interrupted=interrupted,
        interruption_reason=interruption_reason,
    )
    print(f"Done. JSON: {json_path}")
    print(f"Done. MD:   {md_path}")
    return 130 if interrupted else 0


if __name__ == "__main__":
    raise SystemExit(main())
