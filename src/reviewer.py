"""
Review Engine Orchestrator
Coordinates AST analysis, prompt synthesis, LLM invocation, integrity checking, and evidence recording.
"""

from pathlib import Path
from typing import Any, Dict, Optional

from .code_analyzer import CodeAnalyzer
from .evidence import EvidenceRecorder
from .providers.base import BaseLLMProvider, LLMResponse


SYSTEM_REVIEW_PROMPT = """You are an expert Python code reviewer and software forensics investigator.
Your task is to analyze the supplied Python source code in response to a developer's request.

CRITICAL REVIEW RULES:
1. Base your findings STRICTLY on the supplied code. Cite exact function names, line numbers, or code snippets that support your findings.
2. Distinguish clearly between verifiable EVIDENCE (facts directly visible in the code) and ASSUMPTIONS/HYPOTHESES.
3. Do NOT claim to have executed the code, run a test suite, verified a fix, or inspected files you did not receive.
4. If the code does not contain sufficient information to be certain, explicitly state what is uncertain and what must be verified next.
5. Structure your response into these 4 clear sections:
   - Section 1: Findings & Relevant Code Evidence (quote exact function names, line numbers, and expressions)
   - Section 2: Mechanism & Impact (explain how the issue causes the reported behavior or affects totals/stock/state)
   - Section 3: Remaining Uncertainty & What to Check Next (state missing information, assumptions, and next investigation steps)
   - Section 4: Evidence vs. Assumptions Summary (explicitly list what is proven from source vs what is assumed)
"""


class CodeReviewEngine:
    """Orchestrates safe, non-destructive code reviews."""

    def __init__(self, provider: BaseLLMProvider, output_dir: str | Path = "evidence"):
        self.provider = provider
        self.recorder = EvidenceRecorder(output_dir=output_dir)

    def review(
        self,
        source_file: str | Path,
        user_request: str,
        validation_note: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes a code review on the target Python file.
        Returns a dictionary containing execution status, report paths, and model output.
        """
        target_path = Path(source_file).resolve()

        # Step 1: Input Validation
        if not target_path.exists():
            return {
                "success": False,
                "error": f"Target file does not exist: {source_file}",
                "report_path": None,
                "evidence_path": None,
            }
        if not target_path.is_file():
            return {
                "success": False,
                "error": f"Target path is not a file: {source_file}",
                "report_path": None,
                "evidence_path": None,
            }

        cleaned_request = user_request.strip() if user_request else ""
        if not cleaned_request:
            return {
                "success": False,
                "error": "User request is blank or empty. Please describe a problem or enter a review request.",
                "report_path": None,
                "evidence_path": None,
            }

        # Step 2: Safe Static Analysis (No execution or import)
        try:
            analyzer = CodeAnalyzer(target_path)
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to analyze source file: {str(e)}",
                "report_path": None,
                "evidence_path": None,
            }

        sha_before = analyzer.initial_hash

        # Step 3: Build Prompt Context
        code_context = analyzer.extract_context_for_request(cleaned_request)
        user_prompt = (
            f"TARGET FILE: {target_path.name} (SHA-256: {sha_before[:12]}...)\n"
            f"TOTAL LINES: {len(analyzer.raw_lines)}\n\n"
            f"DEVELOPER REQUEST:\n{cleaned_request}\n\n"
            f"{code_context}\n\n"
            f"Please conduct your thorough review following the 4 mandatory sections."
        )

        # Step 4: Invoke Provider
        llm_response: LLMResponse = self.provider.generate(
            system_prompt=SYSTEM_REVIEW_PROMPT,
            user_prompt=user_prompt,
        )

        # Step 5: Verify Source File Integrity
        is_intact = analyzer.verify_integrity()
        try:
            with open(target_path, "r", encoding="utf-8", errors="replace") as f:
                sha_after = CodeAnalyzer(target_path).initial_hash
        except Exception:
            sha_after = "unknown"

        if not is_intact or sha_before != sha_after:
            return {
                "success": False,
                "error": "CRITICAL ERROR: Source file content was modified during review! Halting.",
                "report_path": None,
                "evidence_path": None,
            }

        # Step 6: Record Evidence & Artifacts
        artifacts = self.recorder.save_run(
            source_path=target_path,
            source_sha256_before=sha_before,
            source_sha256_after=sha_after,
            user_request=cleaned_request,
            prompt_context=user_prompt,
            llm_response=llm_response,
            validation_note=validation_note,
        )

        return {
            "success": llm_response.success,
            "error": llm_response.error_message,
            "llm_response": llm_response,
            "report_path": artifacts["report_path"],
            "evidence_path": artifacts["evidence_path"],
            "ledger_path": artifacts["ledger_path"],
            "duration_sec": llm_response.duration_sec,
            "tokens": {
                "prompt": llm_response.prompt_tokens,
                "completion": llm_response.completion_tokens,
                "total": llm_response.total_tokens,
            },
        }
