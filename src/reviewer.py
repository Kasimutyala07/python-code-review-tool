"""
Review Engine Orchestrator
Coordinates AST analysis, prompt synthesis, LLM invocation, integrity checking, and evidence recording.
Instrumented with in-built observability tracing.
"""
from pathlib import Path
from typing import Any, Dict, Optional

from observability import tracer, trace_span
from .code_analyzer import CodeAnalyzer
from .evidence import EvidenceRecorder
from .providers.base import BaseLLMProvider, LLMResponse


SYSTEM_REVIEW_PROMPT = """You are an expert Python code reviewer and software forensics investigator.
Your task is to analyze the supplied Python source code thoroughly to detect and explain all bugs, calculation errors, state inconsistencies, and security flaws.

CRITICAL REVIEW RULES:
1. Base your findings STRICTLY on the supplied code. Cite exact function names, line numbers, and code snippets that support your findings.
2. Systematically audit the code across these key areas:
   - Pricing & Mathematical Computations (item quantity multiplication, discount basis points, taxes, rounding)
   - State Machine & Reentrancy (cancellation, refunds, stock inventory restoration, idempotency)
   - Database Queries & Reporting Metrics (filtering cancelled records, correct timestamp/foreign key attribution)
   - Concurrency & Transactions (atomic blocks, race conditions, isolated table updates)
   - Error Handling & Input Validation (unhandled exceptions like FileExistsError, negative quantities, boundary conditions)
3. Distinguish clearly between verifiable EVIDENCE (facts directly visible in the code) and ASSUMPTIONS/HYPOTHESES.
4. Do NOT claim to have executed the code, run a test suite, verified a fix, or inspected files you did not receive.
5. If the code does not contain sufficient information to be certain, explicitly state what is uncertain and what must be verified next.
6. Structure your response into these 4 clear sections:
   - Section 1: Findings & Relevant Code Evidence (quote exact function names, line numbers, and expressions)
   - Section 2: Mechanism & Impact (explain how each issue causes the reported behavior or affects totals/stock/state)
   - Section 3: Remaining Uncertainty & What to Check Next (state missing information, assumptions, and next investigation steps)
   - Section 4: Evidence vs. Assumptions Summary (explicitly list what is proven from source vs what is assumed)
"""


class CodeReviewEngine:
    """Orchestrates safe, non-destructive code reviews with full telemetry."""

    def __init__(self, provider: BaseLLMProvider, output_dir: str | Path = "evidence"):
        self.provider = provider
        self.recorder = EvidenceRecorder(output_dir=output_dir)

    @trace_span(name="ast_static_analysis")
    def _run_analyzer(self, target_path: Path) -> CodeAnalyzer:
        """Isolated span for AST parsing and initial hashing."""
        return CodeAnalyzer(target_path)

    @trace_span(name="record_evidence_artifacts")
    def _save_evidence(
        self,
        target_path: Path,
        sha_before: str,
        sha_after: str,
        cleaned_request: str,
        user_prompt: str,
        llm_response: LLMResponse,
        validation_note: Optional[str],
    ) -> Dict[str, Any]:
        """Isolated span for evidence and ledger logging."""
        return self.recorder.save_run(
            source_path=target_path,
            source_sha256_before=sha_before,
            source_sha256_after=sha_after,
            user_request=cleaned_request,
            prompt_context=user_prompt,
            llm_response=llm_response,
            validation_note=validation_note,
        )

    def _invoke_llm_traced(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> LLMResponse:
        """
        Manages the generation span to record model parameters,
        prompt/completion tokens, pricing, and latency.
        """
        model_name = getattr(self.provider, "model_name", "unknown-model")
        span = tracer.start_span(
            name="llm_code_review",
            span_type="generation",
            inputs={"system_prompt": system_prompt[:200] + "...", "user_prompt": user_prompt[:300] + "..."},
            metadata={"model": model_name},
        )
        span.model = model_name

        try:
            response: LLMResponse = self.provider.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )

            prompt_tok = getattr(response, "prompt_tokens", 0) or 0
            comp_tok = getattr(response, "completion_tokens", 0) or 0
            total_tok = getattr(response, "total_tokens", 0) or (prompt_tok + comp_tok)

            # Gemini 2.5 Flash pricing benchmark ($0.075 / 1M input, $0.30 / 1M output)
            cost = (prompt_tok * 0.000000075) + (comp_tok * 0.00000030)

            span.tokens = {
                "prompt": prompt_tok,
                "completion": comp_tok,
                "total": total_tok,
            }
            span.cost_usd = round(cost, 6)

            tracer.end_span(
                span,
                outputs={"success": response.success, "duration_sec": response.duration_sec},
                status="success" if response.success else "error",
                error=response.error_message,
            )
            return response
        except Exception as e:
            tracer.end_span(span, status="error", error=str(e))
            raise

    def _evaluate_review_output(self, root_span_id: str, content: str) -> None:
        """Attaches programmatic quality and structure compliance scores to the trace."""
        mandatory_sections = [
            "Section 1: Findings & Relevant Code Evidence",
            "Section 2: Mechanism & Impact",
            "Section 3: Remaining Uncertainty & What to Check Next",
            "Section 4: Evidence vs. Assumptions Summary",
        ]
        
        sections_matched = sum(1 for section in mandatory_sections if section in content)
        compliance_ratio = sections_matched / len(mandatory_sections)

        tracer.attach_score(
            span_id=root_span_id,
            score_name="prompt_rule_compliance",
            value=compliance_ratio,
            comment=f"Matched {sections_matched}/{len(mandatory_sections)} mandatory sections.",
        )

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

        # Start Root Observability Pipeline Span
        root_span = tracer.start_span(
            name="code_review_pipeline",
            span_type="pipeline",
            inputs={"source_file": str(target_path), "request": cleaned_request},
        )

        try:
            # Step 2: Safe Static Analysis (Instrumented Span)
            try:
                analyzer = self._run_analyzer(target_path)
            except Exception as e:
                tracer.end_span(root_span, status="error", error=f"Static analysis failed: {str(e)}")
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

            # Step 4: Invoke Provider (Instrumented Generation Span)
            llm_response: LLMResponse = self._invoke_llm_traced(
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
                err_msg = "CRITICAL ERROR: Source file content was modified during review! Halting."
                tracer.end_span(root_span, status="error", error=err_msg)
                return {
                    "success": False,
                    "error": err_msg,
                    "report_path": None,
                    "evidence_path": None,
                }

            # Step 6: Record Evidence & Artifacts (Instrumented Span)
            artifacts = self._save_evidence(
                target_path=target_path,
                sha_before=sha_before,
                sha_after=sha_after,
                cleaned_request=cleaned_request,
                user_prompt=user_prompt,
                llm_response=llm_response,
                validation_note=validation_note,
            )

            # Step 7: Programmatic Evaluation
            if llm_response.success and llm_response.content:
                self._evaluate_review_output(root_span.span_id, llm_response.content)

            output_summary = {
                "success": llm_response.success,
                "error": llm_response.error_message,
                "llm_response": llm_response,
                "static_findings": [f.to_dict() for f in analyzer.static_findings],
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

            tracer.end_span(
                root_span,
                outputs={"success": llm_response.success, "report_path": str(artifacts["report_path"])},
                status="success" if llm_response.success else "error",
                error=llm_response.error_message,
            )
            return output_summary

        except Exception as exc:
            tracer.end_span(root_span, status="error", error=str(exc))
            raise