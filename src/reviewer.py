"""
Review Engine Orchestrator
Coordinates AST analysis, multi-file repository search, prompt synthesis,
LLM invocation, cryptographic integrity checking, and evidence recording.
Instrumented with in-built observability tracing.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
import time

from observability import tracer, trace_span
from .code_analyzer import CodeAnalyzer, RepoAnalyzer, RepoSearchResult
from .evidence import EvidenceRecorder
from .providers.base import BaseLLMProvider, LLMResponse


# Model pricing table per 1M tokens (Input USD, Output USD)
PRICING_TABLE = {
    "gemini-2.5-flash": (0.075, 0.30),
    "gemini-1.5-pro": (1.25, 5.00),
    "default": (0.10, 0.40),
}

SYSTEM_REVIEW_PROMPT = """You are an expert Python code reviewer and software forensics investigator.
Your task is to analyze Python code across a repository or source file in response to a developer's request.

CRITICAL REVIEW RULES:
1. Base your findings STRICTLY on the supplied code.
2. Cite exact relative FILE PATHS, FUNCTION/CLASS NAMES, and 1-based LINE NUMBERS for all findings and code references.
3. Explain how the issue causes the reported behavior or error, step by step.
4. Provide a concrete SUGGESTED FIX with code snippets or diffs.
5. If there is NOT enough evidence in the scanned code to explain the issue, you MUST explicitly state:
   "INSUFFICIENT EVIDENCE: The scanned code does not contain sufficient information to determine [reason]..."
   and explain what files, configurations, or inputs are missing and what must be verified next.
6. Distinguish clearly between verifiable EVIDENCE (facts directly visible in the code) and ASSUMPTIONS/HYPOTHESES.
7. Do NOT claim to have executed the code, run a test suite, verified a fix, or inspected files you did not receive.
8. Structure your response into these 4 clear sections:
   - Section 1: Findings & Relevant Code Evidence (cite exact file paths, line numbers, function names, and expressions)
   - Section 2: Mechanism & Root Cause Explanation (how the issue causes the behavior or exception)
   - Section 3: Suggested Fix & Next Steps (concrete code fix/diff, remaining uncertainty, what to check next)
   - Section 4: Evidence vs. Assumptions Summary (distinguish verifiable facts from assumptions, or state insufficient evidence)
"""


class CodeReviewEngine:
    """Orchestrates safe, non-destructive code reviews with full telemetry."""

    def __init__(self, provider: BaseLLMProvider, output_dir: str | Path = "evidence"):
        self.provider = provider
        self.recorder = EvidenceRecorder(output_dir=output_dir)

    def _calculate_cost(self, model_name: str, prompt_tok: int, comp_tok: int) -> float:
        """Calculates approximate request cost based on active model rates."""
        rates = PRICING_TABLE.get(model_name.lower(), PRICING_TABLE["default"])
        input_cost = (prompt_tok / 1_000_000) * rates[0]
        output_cost = (comp_tok / 1_000_000) * rates[1]
        return round(input_cost + output_cost, 6)

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
        """Manages generation span recording parameters, token metrics, latency, and costs."""
        model_name = getattr(self.provider, "model_name", "unknown-model")
        span = tracer.start_span(
            name="llm_code_review",
            span_type="generation",
            inputs={
                "system_prompt_preview": system_prompt[:150] + "...",
                "user_prompt_len": len(user_prompt),
                "user_prompt_preview": user_prompt[:250] + "...",
            },
            metadata={"model": model_name},
        )
        span.model = model_name

        try:
            start_t = time.perf_counter()
            response: LLMResponse = self.provider.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
            elapsed_sec = round(time.perf_counter() - start_t, 3)

            prompt_tok = getattr(response, "prompt_tokens", 0) or 0
            comp_tok = getattr(response, "completion_tokens", 0) or 0
            total_tok = getattr(response, "total_tokens", 0) or (prompt_tok + comp_tok)

            span.tokens = {
                "prompt": prompt_tok,
                "completion": comp_tok,
                "total": total_tok,
            }
            span.cost_usd = self._calculate_cost(model_name, prompt_tok, comp_tok)

            tracer.end_span(
                span,
                outputs={
                    "success": response.success,
                    "duration_sec": getattr(response, "duration_sec", elapsed_sec),
                    "token_count": total_tok,
                },
                status="success" if response.success else "error",
                error=response.error_message,
            )
            return response
        except Exception as e:
            tracer.end_span(span, status="error", error=str(e))
            raise

    def _evaluate_review_output(self, root_span_id: str, content: str) -> None:
        """Attaches programmatic quality and structure compliance scores to the trace."""
        mandatory_indicators = [
            ("section 1", "findings"),
            ("section 2", "mechanism"),
            ("section 3", "fix"),
            ("section 4", "evidence"),
        ]

        lower_content = content.lower()
        matched = 0
        for sec_num, topic in mandatory_indicators:
            if sec_num in lower_content or topic in lower_content:
                matched += 1

        compliance_ratio = matched / len(mandatory_indicators)
        tracer.attach_score(
            span_id=root_span_id,
            score_name="prompt_rule_compliance",
            value=compliance_ratio,
            comment=f"Matched {matched}/{len(mandatory_indicators)} mandatory response sections.",
        )

    def review(
        self,
        source_file: str | Path,
        user_request: str,
        validation_note: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes a non-destructive code review on a single file or an entire repository.
        """
        target_path = Path(source_file).resolve()

        if not target_path.exists():
            return {
                "success": False,
                "error": f"Target path does not exist: {source_file}",
                "report_path": None,
                "evidence_path": None,
            }

        cleaned_request = user_request.strip() if user_request else ""
        if not cleaned_request:
            return {
                "success": False,
                "error": "User request is blank or empty. Please describe an issue or query.",
                "report_path": None,
                "evidence_path": None,
            }

        is_directory_mode = target_path.is_dir()
        pipeline_span_name = "repo_review_pipeline" if is_directory_mode else "file_review_pipeline"

        root_span = tracer.start_span(
            name=pipeline_span_name,
            span_type="pipeline",
            inputs={"target_path": str(target_path), "request": cleaned_request},
        )

        try:
            if is_directory_mode:
                # ---------------------------------------------------------
                # Directory / Repository Mode
                # ---------------------------------------------------------
                repo_analyzer = RepoAnalyzer(target_path)
                sha_before = repo_analyzer.get_repo_hash()

                search_span = tracer.start_span(
                    name="repo_file_search",
                    span_type="search",
                    inputs={"repo_path": str(target_path), "query": cleaned_request},
                )
                try:
                    search_results, insufficient_evidence = repo_analyzer.search_codebase(
                        query=cleaned_request,
                        max_files=5,
                    )
                    top_files = [r.relative_path for r in search_results]
                    search_span.search_metrics = {
                        "files_scanned": len(repo_analyzer.discovered_files),
                        "files_matched": len(search_results),
                        "top_files": top_files,
                        "insufficient_evidence": insufficient_evidence,
                    }
                    tracer.end_span(
                        search_span,
                        outputs={"files_matched": len(search_results), "top_files": top_files},
                        status="success",
                    )
                except Exception as se_err:
                    tracer.end_span(search_span, status="error", error=f"File search failed: {se_err}")
                    raise

                code_context = repo_analyzer.build_repo_context(
                    query=cleaned_request,
                    search_results=search_results,
                    insufficient_evidence=insufficient_evidence,
                )

                user_prompt = (
                    f"TARGET REPOSITORY: {target_path.name} (SHA-256 Digest: {sha_before[:12]}...)\n"
                    f"FILES SCANNED: {len(repo_analyzer.discovered_files)}\n\n"
                    f"DEVELOPER REQUEST:\n{cleaned_request}\n\n"
                    f"{code_context}\n\n"
                    f"Please conduct your thorough investigation following the 4 mandatory sections."
                )

                llm_response = self._invoke_llm_traced(SYSTEM_REVIEW_PROMPT, user_prompt)

                # Post-analysis immutability check
                if not repo_analyzer.verify_repo_integrity():
                    sha_after = repo_analyzer.get_repo_hash()
                    err_msg = "CRITICAL ERROR: Repository files were modified during review execution."
                    tracer.end_span(root_span, status="error", error=err_msg)
                    return {"success": False, "error": err_msg, "report_path": None, "evidence_path": None}
                sha_after = sha_before

                static_findings = [
                    {**finding.to_dict(), "file_path": res.relative_path}
                    for res in search_results
                    for finding in res.analyzer.static_findings
                ]
                selected_files = top_files

            else:
                # ---------------------------------------------------------
                # Single-File Mode
                # ---------------------------------------------------------
                try:
                    analyzer = self._run_analyzer(target_path)
                except Exception as e:
                    tracer.end_span(root_span, status="error", error=f"Static analysis failed: {str(e)}")
                    return {"success": False, "error": f"Failed to parse source file: {str(e)}", "report_path": None, "evidence_path": None}

                sha_before = analyzer.initial_hash
                code_context = analyzer.extract_context_for_request(cleaned_request)

                user_prompt = (
                    f"TARGET FILE: {target_path.name} (SHA-256: {sha_before[:12]}...)\n"
                    f"TOTAL LINES: {len(analyzer.raw_lines)}\n\n"
                    f"DEVELOPER REQUEST:\n{cleaned_request}\n\n"
                    f"{code_context}\n\n"
                    f"Please conduct your thorough review following the 4 mandatory sections."
                )

                llm_response = self._invoke_llm_traced(SYSTEM_REVIEW_PROMPT, user_prompt)

                # Verify single-file integrity without re-instantiating analyzer
                if not analyzer.verify_integrity():
                    err_msg = "CRITICAL ERROR: Source file content was modified during review."
                    tracer.end_span(root_span, status="error", error=err_msg)
                    return {"success": False, "error": err_msg, "report_path": None, "evidence_path": None}
                sha_after = sha_before

                static_findings = [f.to_dict() for f in analyzer.static_findings]
                selected_files = [target_path.name]
                insufficient_evidence = False

            # Persist Evidence
            artifacts = self._save_evidence(
                target_path=target_path,
                sha_before=sha_before,
                sha_after=sha_after,
                cleaned_request=cleaned_request,
                user_prompt=user_prompt,
                llm_response=llm_response,
                validation_note=validation_note,
            )

            # Compliance evaluation
            if llm_response.success and llm_response.content:
                self._evaluate_review_output(root_span.span_id, llm_response.content)

            output_summary = {
                "success": llm_response.success,
                "is_repo_mode": is_directory_mode,
                "files_scanned": len(repo_analyzer.discovered_files) if is_directory_mode else 1,
                "selected_files": selected_files,
                "insufficient_evidence": insufficient_evidence,
                "error": llm_response.error_message,
                "llm_response": llm_response,
                "static_findings": static_findings,
                "report_path": artifacts.get("report_path"),
                "evidence_path": artifacts.get("evidence_path"),
                "ledger_path": artifacts.get("ledger_path"),
                "duration_sec": llm_response.duration_sec,
                "tokens": {
                    "prompt": llm_response.prompt_tokens,
                    "completion": llm_response.completion_tokens,
                    "total": llm_response.total_tokens,
                },
            }

            tracer.end_span(
                root_span,
                outputs={"success": llm_response.success, "report_path": str(artifacts.get("report_path"))},
                status="success" if llm_response.success else "error",
                error=llm_response.error_message,
            )
            return output_summary

        except Exception as exc:
            tracer.end_span(root_span, status="error", error=str(exc))
            raise