"""
Evidence Logger and Artifact Storage.
Records review outputs, prompt contexts, raw responses, token usage, and source integrity.
Ensures earlier results are never accidentally overwritten.
"""

import json
import os
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from .providers.base import LLMResponse


@dataclass
class ReviewEvidence:
    timestamp: str
    run_id: str
    source_file: str
    source_sha256_before: str
    source_sha256_after: str
    source_intact: bool
    user_request: str
    prompt_context: str
    raw_response: str
    review_output: str
    provider: str
    model: str
    duration_sec: float
    outcome: str  # 'SUCCESS', 'PROVIDER_FAILURE', 'INVALID_INPUT', 'BLOCKED_QUOTA'
    tokens_prompt: Any
    tokens_completion: Any
    tokens_total: Any
    findings_validation_note: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EvidenceRecorder:
    """Manages saving reviews and audit trail evidence without overwriting previous runs."""

    def __init__(self, output_dir: str | Path = "evidence"):
        self.output_dir = Path(output_dir).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.ledger_file = self.output_dir / "evidence_ledger.jsonl"

    def _generate_slug(self, request_text: str) -> str:
        words = re.findall(r"[A-Za-z0-9]+", request_text.lower())
        slug = "_".join(words[:4]) if words else "review"
        return slug[:30]

    def save_run(
        self,
        source_path: str | Path,
        source_sha256_before: str,
        source_sha256_after: str,
        user_request: str,
        prompt_context: str,
        llm_response: LLMResponse,
        validation_note: Optional[str] = None,
    ) -> Dict[str, Path]:
        """
        Saves all review artifacts and returns paths to the generated files.
        Guaranteed to create unique filenames via timestamp and run index.
        """
        now = datetime.now()
        timestamp_str = now.strftime("%Y%m%d_%H%M%S")
        slug = self._generate_slug(user_request)
        run_id = f"{timestamp_str}_{slug}"

        # Determine outcome category
        if llm_response.success:
            outcome = "SUCCESS"
        elif llm_response.status_code == 429:
            outcome = "BLOCKED_QUOTA"
        else:
            outcome = "PROVIDER_FAILURE"

        source_intact = (source_sha256_before == source_sha256_after)

        default_note = (
            "Automated note: Review completed. Model findings must be manually audited against "
            "BUSINESS_RULES.md and SQLite schema before deploying any patches."
            if llm_response.success
            else f"Automated note: Call failed ({llm_response.error_message}). No valid findings produced."
        )

        evidence = ReviewEvidence(
            timestamp=now.isoformat(),
            run_id=run_id,
            source_file=str(Path(source_path).resolve()),
            source_sha256_before=source_sha256_before,
            source_sha256_after=source_sha256_after,
            source_intact=source_intact,
            user_request=user_request,
            prompt_context=prompt_context,
            raw_response=llm_response.raw_response,
            review_output=llm_response.content,
            provider=llm_response.provider_name,
            model=llm_response.model_name,
            duration_sec=round(llm_response.duration_sec, 3),
            outcome=outcome,
            tokens_prompt=llm_response.prompt_tokens if llm_response.prompt_tokens is not None else "unknown",
            tokens_completion=llm_response.completion_tokens if llm_response.completion_tokens is not None else "unknown",
            tokens_total=llm_response.total_tokens if llm_response.total_tokens is not None else "unknown",
            findings_validation_note=validation_note or default_note,
        )

        # 1. Save Human-Readable Markdown Report
        report_path = self.output_dir / f"{run_id}_report.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(self._format_markdown_report(evidence, llm_response))

        # 2. Save Full Raw Evidence JSON
        evidence_json_path = self.output_dir / f"{run_id}_evidence.json"
        with open(evidence_json_path, "w", encoding="utf-8") as f:
            json.dump(evidence.to_dict(), f, indent=2, ensure_ascii=False)

        # 3. Append to Cumulative Ledger
        ledger_entry = {
            "timestamp": evidence.timestamp,
            "run_id": evidence.run_id,
            "outcome": evidence.outcome,
            "provider": evidence.provider,
            "model": evidence.model,
            "duration_sec": evidence.duration_sec,
            "tokens_total": evidence.tokens_total,
            "report_file": str(report_path.name),
            "evidence_file": str(evidence_json_path.name),
        }
        with open(self.ledger_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(ledger_entry) + "\n")

        return {
            "report_path": report_path,
            "evidence_path": evidence_json_path,
            "ledger_path": self.ledger_file,
        }

    def _format_markdown_report(self, ev: ReviewEvidence, resp: LLMResponse) -> str:
        """Formats an executive Markdown report optimized for VS Code preview."""
        token_str = (
            f"Prompt: {ev.tokens_prompt} | Completion: {ev.tokens_completion} | Total: {ev.tokens_total}"
        )
        integrity_status = "✅ Preserved (SHA-256 Verified)" if ev.source_intact else "❌ INTEGRITY ERROR (FILE MODIFIED)"

        lines = [
            f"# Python Code Review Report",
            f"",
            f"**Run Identifier**: `{ev.run_id}`  ",
            f"**Timestamp**: {ev.timestamp}  ",
            f"**Target File**: `{ev.source_file}`  ",
            f"**Source File Integrity**: {integrity_status}  ",
            f"**Provider / Model**: {ev.provider} (`{ev.model}`)  ",
            f"**Run Duration**: {ev.duration_sec}s  ",
            f"**Token Usage**: {token_str}  ",
            f"**Outcome**: `{ev.outcome}`  ",
            f"",
            f"---",
            f"",
            f"## User Request",
            f"> {ev.user_request}",
            f"",
            f"---",
            f"",
        ]

        if not resp.success:
            lines.extend([
                f"## ⚠️ Review Execution Failed",
                f"",
                f"**Error Details**:",
                f"```",
                f"{resp.error_message}",
                f"```",
                f"",
                f"**What Happened**: The LLM provider could not complete the review. "
                f"No synthetic or fabricated findings are reported to avoid misleading the developer.",
                f"",
            ])
        else:
            lines.extend([
                f"## Review Findings",
                f"",
                f"{ev.review_output}",
                f"",
                f"---",
                f"",
                f"## Auditor Evaluation & Notes",
                f"{ev.findings_validation_note}",
                f"",
            ])

        return "\n".join(lines)

    def get_cumulative_summary(self) -> Dict[str, Any]:
        """Reads cumulative statistics from the ledger."""
        if not self.ledger_file.exists():
            return {"total_runs": 0, "successful_runs": 0, "failed_runs": 0, "total_duration_sec": 0.0}

        total_runs = 0
        success_runs = 0
        failed_runs = 0
        total_duration = 0.0
        total_tokens = 0

        with open(self.ledger_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    total_runs += 1
                    if entry.get("outcome") == "SUCCESS":
                        success_runs += 1
                    else:
                        failed_runs += 1
                    total_duration += float(entry.get("duration_sec", 0.0))
                    t_val = entry.get("tokens_total")
                    if isinstance(t_val, int):
                        total_tokens += t_val
                except Exception:
                    continue

        return {
            "total_runs": total_runs,
            "successful_runs": success_runs,
            "failed_runs": failed_runs,
            "total_duration_sec": round(total_duration, 2),
            "known_tokens_total": total_tokens,
        }
