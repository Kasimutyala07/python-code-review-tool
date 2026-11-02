"""trace_viewer.py - Local CLI inspector for recorded observability traces."""

from datetime import datetime
import json
import os
from pathlib import Path


def load_trace_data(storage_dir: str = ".reviews") -> tuple[list[dict], list[dict]]:
    log_path = Path(storage_dir) / "traces.jsonl"
    if not log_path.exists():
        return [], []

    spans = []
    evals = []
    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if entry.get("record_type") == "eval_score":
                    evals.append(entry)
                else:
                    spans.append(entry)
            except Exception:
                continue
    return spans, evals


def display_trace_summary(limit: int = 15):
    spans, evals = load_trace_data()
    if not spans:
        print("\n[!] No traces found in .reviews/traces.jsonl. Run a review first.\n")
        return

    # Map evaluation scores by span_id
    eval_map = {}
    for ev in evals:
        eval_map[ev["span_id"]] = f"{ev['score_name']}={ev['value']:.2f}"

    print("\n" + "=" * 105)
    print(f"{'TIMESTAMP':<20} | {'NAME':<24} | {'TYPE':<12} | {'LATENCY':<10} | {'TOKENS':<8} | {'COST ($)':<10} | {'EVAL'}")
    print("=" * 105)

    recent_spans = spans[-limit:]
    for s in recent_spans:
        ts = s.get("start_time", "")[:19].replace("T", " ")
        name = s.get("name", "unknown")[:24]
        stype = s.get("span_type", "span")[:12]
        duration = f"{s.get('duration_ms', 0):.1f}ms"
        tokens = str(s.get("tokens", {}).get("total", "-")) if s.get("tokens") else "-"
        cost = f"${s.get('cost_usd', 0):.6f}" if s.get("cost_usd") else "-"
        eval_score = eval_map.get(s.get("span_id", ""), "-")

        print(f"{ts:<20} | {name:<24} | {stype:<12} | {duration:<10} | {tokens:<8} | {cost:<10} | {eval_score}")

    print("=" * 105)


def display_trace_detail(trace_id: str):
    spans, evals = load_trace_data()
    matching = [s for s in spans if s.get("trace_id") == trace_id or s.get("span_id") == trace_id]

    if not matching:
        print(f"\n[!] No trace or span matching ID: {trace_id}\n")
        return

    print(f"\nDetailed View for ID: {trace_id}")
    print("-" * 60)
    for s in matching:
        print(f"[{s.get('span_type', '').upper()}] {s.get('name')} (Status: {s.get('status')})")
        print(f"  Duration: {s.get('duration_ms')}ms")
        if s.get("tokens"):
            print(f"  Tokens: {s['tokens']}")
            print(f"  Cost: ${s.get('cost_usd', 0):.6f}")
        if s.get("error"):
            print(f"  Error: {s['error']}")
        print()

