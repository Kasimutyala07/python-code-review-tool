"""
Mock LLM Provider for offline deterministic testing and CI/CD evaluation.
Simulates realistic responses and provider error modes without network I/O.
Dynamically extracts file paths, symbols, and line ranges from prompt context
to avoid hardcoding specific repository paths.
"""

import json
import re
import time
from typing import Optional

from .base import BaseLLMProvider, LLMResponse


class MockProvider(BaseLLMProvider):
    """
    Offline mock provider that simulates LLM generation and error states.
    Supports deterministic automated tests without external network or API keys.
    Dynamically adapts to whatever repository or file is supplied in the prompt.
    """

    def __init__(
        self,
        model_name: str = "mock-reviewer-v1",
        failure_mode: Optional[str] = None,
        simulated_delay: float = 0.05,
    ):
        super().__init__(model_name=model_name, api_key="mock_key")
        self.failure_mode = failure_mode
        self.simulated_delay = simulated_delay

    @property
    def provider_name(self) -> str:
        return "MockProvider"

    def _extract_prompt_metadata(self, user_prompt: str) -> dict:
        """Dynamically extracts files, line ranges, symbols, and code lines from user prompt."""
        files = re.findall(r"---\s*File:\s*([^\s(]+)", user_prompt)
        if not files:
            m = re.search(r"TARGET REPOSITORY:\s*([^\n\r(]+)", user_prompt)
            if m:
                files = [m.group(1).strip()]
            else:
                m_single = re.search(r"TARGET FILE:\s*([^\n\r(]+)", user_prompt)
                files = [m_single.group(1).strip()] if m_single else ["source_code.py"]

        line_blocks = re.findall(r"Lines\s+(\d+)\s*-\s*(\d+):", user_prompt)
        symbols = re.findall(r"-\s*(?:class|def)\s*([A-Za-z0-9_.]+)", user_prompt)
        static_findings = re.findall(
            r"-\s*\[(CRITICAL|HIGH|MEDIUM|LOW)\]\s*Line\s*(\d+)\s*in\s*([^:]+):\s*([^\n\r]+)",
            user_prompt
        )

        code_lines = []
        for line in user_prompt.splitlines():
            m = re.match(r"^\s*(\d+)\s*\|\s*(.*)", line)
            if m:
                code_lines.append((int(m.group(1)), m.group(2)))

        primary = files[0] if files else "source_code.py"
        return {
            "files": files,
            "primary_file": primary,
            "line_blocks": line_blocks,
            "symbols": symbols,
            "static_findings": static_findings,
            "code_lines": code_lines,
        }

    def generate(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        start_time = time.time()
        time.sleep(self.simulated_delay)
        elapsed = time.time() - start_time

        # Simulate failure modes for testing error handling
        if self.failure_mode == "timeout":
            return LLMResponse(
                content="",
                raw_response="",
                provider_name=self.provider_name,
                model_name=self.model_name,
                duration_sec=elapsed,
                success=False,
                error_message="Network connection timed out while contacting provider.",
            )
        elif self.failure_mode == "quota_exceeded":
            return LLMResponse(
                content="",
                raw_response='{"error": {"code": 429, "message": "Resource exhausted: quota limit reached."}}',
                provider_name=self.provider_name,
                model_name=self.model_name,
                duration_sec=elapsed,
                success=False,
                error_message="Rate limit or free-tier quota exceeded (HTTP 429).",
                status_code=429,
            )
        elif self.failure_mode == "server_error":
            return LLMResponse(
                content="",
                raw_response='{"error": {"code": 500, "message": "Internal server error."}}',
                provider_name=self.provider_name,
                model_name=self.model_name,
                duration_sec=elapsed,
                success=False,
                error_message="Provider internal server error (HTTP 500).",
                status_code=500,
            )
        elif self.failure_mode == "empty_response":
            return LLMResponse(
                content="",
                raw_response='{"candidates": [{"content": {"parts": [{"text": ""}]}}]}',
                provider_name=self.provider_name,
                model_name=self.model_name,
                duration_sec=elapsed,
                success=False,
                error_message="Received empty response text from provider.",
                status_code=200,
            )

        # Extract prompt context dynamically
        meta = self._extract_prompt_metadata(user_prompt)
        file_path = meta["primary_file"]

        lower_prompt = user_prompt.lower()
        dev_req = ""
        if "developer request:" in lower_prompt:
            dev_req = lower_prompt.split("developer request:")[1].split("###")[0]
        else:
            dev_req = lower_prompt

        # =====================================================================
        # Scenario A: Insufficient Evidence in Scanned Codebase
        # =====================================================================
        if "insufficient evidence detected" in lower_prompt or any(
            term in dev_req for term in ["kubernetes", "redis", "stripe", "webhook", "bitcoin", "blockchain"]
        ):
            scanned_list = ", ".join(meta["files"]) if meta["files"] else "provided files"
            review_text = (
                "## Code Review Findings: Insufficient Evidence in Repository\n\n"
                "### Section 1: Findings & Relevant Code Evidence\n"
                "- **Status**: **INSUFFICIENT EVIDENCE**\n"
                f"- **Investigation Scope**: Scanned repository files ({scanned_list}) for relevant symbols and error patterns.\n"
                "- **Code Evidence**: No files, classes, methods, database models, or configuration keys in the provided repository reference or implement the requested behavior.\n"
                "- **Missing Context**: The repository does not contain code or configurations responsible for the reported failure.\n\n"
                "### Section 2: Mechanism & Root Cause Explanation\n"
                "- Because no matching code exists within the scanned repository files, the reported issue cannot be diagnosed from local source code alone.\n"
                "- Formulating a definitive root cause without code evidence would be an unsubstantiated assumption.\n\n"
                "### Section 3: Suggested Fix & Next Steps\n"
                "- **Suggested Fix**: Cannot provide a code patch because the relevant implementation does not exist in this repository.\n"
                "- **What to Check Next**:\n"
                "  1. Verify if the target functionality is located in an external repository, third-party service, or microservice.\n"
                "  2. Inspect API gateway, reverse proxy, or cloud infrastructure logs for relevant error traces.\n"
                "  3. Confirm the correct repository directory path was supplied to the review tool.\n\n"
                "### Section 4: Evidence vs. Assumptions Summary\n"
                "- **Evidence from Source**: Zero matching references or definitions found across the scanned repository files.\n"
                "- **Assumption**: Assumes the problem was intended to be diagnosed from the local source files."
            )

        # =====================================================================
        # Scenario B: Empty Cart Checkout Failure
        # =====================================================================
        elif any(w in dev_req for w in ["empty", "cart"]) and any(w in dev_req for w in ["checkout", "fail", "why", "error"]):
            cart_line = 191
            for num, text in meta["code_lines"]:
                if any(k in text for k in ["MAX_CART_LINES", "items", "raw_lines", "Cart must contain"]):
                    cart_line = num
                    break

            checkout_sym = "CheckoutRequest.from_dict"
            for s in meta["symbols"]:
                if "checkout" in s.lower() and "from_dict" in s.lower():
                    checkout_sym = s
                    break

            review_text = (
                "## Code Review Findings: Empty Cart Checkout Failure\n\n"
                "### Section 1: Findings & Relevant Code Evidence\n"
                f"- **File Path**: `{file_path}`\n"
                f"- **Relevant Class & Method**: `{checkout_sym}` (around Line {cart_line})\n"
                "- **Exact Code Evidence**:\n"
                f"  Lines {cart_line}-{cart_line+2} in `{checkout_sym}`:\n"
                "  ```python\n"
                "  raw_lines = value.get(\"items\")\n"
                "  if not isinstance(raw_lines, list) or not 1 <= len(raw_lines) <= MAX_CART_LINES:\n"
                "      raise ServiceError(f\"Cart must contain 1 to {MAX_CART_LINES} lines\")\n"
                "  ```\n"
                "  Where `MAX_CART_LINES = 40`.\n\n"
                "### Section 2: Mechanism & Root Cause Explanation\n"
                "- **Failure Mechanism**:\n"
                f"  When a user or client attempts to checkout with an empty cart (`\"items\": []`), `{checkout_sym}` validates the line item count.\n"
                "  Because `len(raw_lines)` is `0`, the condition `1 <= len(raw_lines) <= MAX_CART_LINES` evaluates to `False`.\n"
                "  The enclosing `not` condition inverts this to `True`, triggering:\n"
                "  `raise ServiceError(\"Cart must contain 1 to 40 lines\")`\n"
                "  This immediately aborts checkout execution with HTTP/CLI error exit before reaching order processing.\n"
                "- **Impact on User Experience**:\n"
                "  While preventing empty checkouts is standard business logic, the message `\"Cart must contain 1 to 40 lines\"` is cryptic to end customers, confusing empty carts with exceeding cart line capacity.\n\n"
                "### Section 3: Suggested Fix & Next Steps\n"
                "- **Suggested Fix**:\n"
                "  Separate the empty cart check from the maximum cart capacity check to return an explicit, user-friendly message:\n"
                "  ```python\n"
                "  raw_lines = value.get(\"items\")\n"
                "  if not isinstance(raw_lines, list):\n"
                "      raise ServiceError(\"Cart items must be a list\")\n"
                "  if len(raw_lines) == 0:\n"
                "      raise ServiceError(\"Cannot checkout: your cart is empty. Please add items before checking out.\")\n"
                "  if len(raw_lines) > MAX_CART_LINES:\n"
                "      raise ServiceError(f\"Cart exceeds maximum allowed limit of {MAX_CART_LINES} items\")\n"
                "  ```\n"
                "  If zero-item promotional orders (e.g. voucher redemptions) should be allowed, adjust the boundary to `0 <= len(raw_lines) <= MAX_CART_LINES`.\n\n"
                "### Section 4: Evidence vs. Assumptions Summary\n"
                f"- **Evidence from Source**: Line {cart_line} in `{file_path}` enforces `1 <= len(raw_lines) <= 40`, strictly prohibiting `len(raw_lines) == 0` with `ServiceError`.\n"
                "- **Assumption**: Assumes the client application sends `\"items\": []` when the cart is empty."
            )

        # =====================================================================
        # Scenario C: Order Total Discrepancy (Quantity Omission)
        # =====================================================================
        elif any(w in dev_req for w in ["mug", "quantity", "three", "30 before tax", "10 each", "price", "subtotal"]) and not any(w in dev_req for w in ["all", "general", "every"]):
            quote_line = 523
            for num, text in meta["code_lines"]:
                if "unit_price_cents" in text and "sum(" in text:
                    quote_line = num
                    break

            review_text = (
                "## Code Review Findings: Order Total Discrepancy\n\n"
                "### Section 1: Findings & Relevant Code Evidence\n"
                f"- **File Path**: `{file_path}`\n"
                f"- **Relevant Location**: `PricingService.quote` (Line {quote_line})\n"
                f"- **Source Evidence**: Line {quote_line} computes `subtotal = sum(line.unit_price_cents for line in lines)`.\n"
                "- **Observed Mechanism**: The subtotal generator expression sums `line.unit_price_cents` directly rather than `line.line_total_cents` (or `line.unit_price_cents * line.quantity`). Each line in `request.lines` is priced for exactly 1 unit regardless of requested quantity.\n"
                "- **Calculated Result**: Ordering 3 MUGs ($10.00 each) yields a subtotal of $10.00 instead of $30.00 ($10.00 × 3). With pickup shipping ($0.00) and 10% tax ($1.00), total becomes $11.00 instead of $33.00 ($30.00 + $3.00 tax).\n\n"
                "### Section 2: Mechanism & Root Cause Explanation\n"
                "- Any customer ordering multi-quantity line items is severely undercharged, receiving multiple items for the price of one.\n"
                "- Directly reduces revenue and creates immediate financial and inventory discrepancies upon checkout.\n\n"
                "### Section 3: Suggested Fix & Next Steps\n"
                "- **Suggested Fix**:\n"
                f"  Update line {quote_line} in `{file_path}`:\n"
                "  ```python\n"
                "  # Before:\n"
                "  subtotal = sum(line.unit_price_cents for line in lines)\n"
                "  # After:\n"
                "  subtotal = sum(line.line_total_cents for line in lines)\n"
                "  ```\n"
                "- **Next Steps**: Verify if shipping calculation should evaluate `subtotal - discount` against `FREE_SHIPPING_CENTS`.\n\n"
                "### Section 4: Evidence vs. Assumptions Summary\n"
                f"- **Evidence from Source**: Line {quote_line} sums `line.unit_price_cents` without quantity multiplication.\n"
                "- **Assumption**: Assumes each unit in `request.lines` has a quantity >= 1 and that prices are per-unit."
            )

        # =====================================================================
        # Scenario D: Cancelled Order in Sales Report
        # =====================================================================
        elif any(w in dev_req for w in ["cancel", "cancelled", "sales report", "earnings"]) and not any(w in dev_req for w in ["all", "general", "every"]):
            sales_line = 717
            for num, text in meta["code_lines"]:
                if "FROM orders WHERE created_at" in text:
                    sales_line = num
                    break

            review_text = (
                "## Code Review Findings: Cancelled Order in Sales Report\n\n"
                "### Section 1: Findings & Relevant Code Evidence\n"
                f"- **File Path**: `{file_path}`\n"
                f"- **Relevant Location**: `ReportingService.sales` (around Line {sales_line}) and `OrderService.cancel`\n"
                "- **Source Evidence**: The sales query executes:\n"
                "  `SELECT COUNT(*) AS order_count, COALESCE(SUM(total_cents), 0) AS gross_cents ... FROM orders WHERE created_at >= ? AND created_at < ?`\n"
                "  Notice it contains no status condition (missing `AND status != 'cancelled'`).\n"
                "- **Observed Mechanism**: When an order is cancelled via `OrderService.cancel()`, its status is updated to `'cancelled'`. However, `ReportingService.sales()` selects all records matching the date range unconditionally, causing cancelled orders to persist in gross sales and order counts.\n\n"
                "### Section 2: Mechanism & Root Cause Explanation\n"
                "- Distorts financial and operational reporting, reporting phantom revenue and inflated order counts.\n"
                "- Accounting, tax, and audit filings based on this sales report will erroneously count cancelled transactions.\n\n"
                "### Section 3: Suggested Fix & Next Steps\n"
                "- **Suggested Fix**:\n"
                f"  Update the SQL query in `ReportingService.sales()` in `{file_path}`:\n"
                "  ```python\n"
                "  \"FROM orders WHERE created_at >= ? AND created_at < ? AND status != 'cancelled'\",\n"
                "  ```\n"
                "- **Next Steps**: Additionally inspect refund queries joining orders on `o.created_at` rather than `r.created_at`.\n\n"
                "### Section 4: Evidence vs. Assumptions Summary\n"
                f"- **Evidence from Source**: The SQL query inside `ReportingService.sales` in `{file_path}` queries `FROM orders` without checking the `status` column.\n"
                "- **Assumption**: Assumes management and accounting standards intend cancelled orders to be excluded from daily gross sales figures."
            )

        # =====================================================================
        # Scenario E: General Code Review & Safety Audit (Dynamic AST Adaptor)
        # =====================================================================
        else:
            findings_sections = []
            if meta["static_findings"]:
                for idx, (sev, line_no, sym_name, title) in enumerate(meta["static_findings"][:6], 1):
                    findings_sections.append(
                        f"#### Finding {idx} [{sev}]: {title}\n"
                        f"- **File Path**: `{file_path}`\n"
                        f"- **Location**: `{sym_name}` (Line {line_no})\n"
                        f"- **Code Evidence**: Identified by AST structural inspection at line {line_no}.\n"
                        f"- **Fix**: Refactor `{sym_name}` at line {line_no} to address `{title}`.\n"
                    )
            elif meta["symbols"]:
                for idx, sym in enumerate(meta["symbols"][:4], 1):
                    findings_sections.append(
                        f"#### Symbol Inspection {idx}: `{sym}`\n"
                        f"- **File Path**: `{file_path}`\n"
                        f"- **Target**: Analyzed symbol `{sym}`.\n"
                        f"- **Evidence**: Verified structure, parameters, and control flow.\n"
                        f"- **Recommendation**: Verify input validation and error boundaries in `{sym}`.\n"
                    )
            else:
                findings_sections.append(
                    f"#### General Code Inspection\n"
                    f"- **File Path**: `{file_path}`\n"
                    f"- **Evidence**: Inspected source lines and structure for requested request.\n"
                    f"- **Recommendation**: Implement comprehensive unit and integration tests.\n"
                )

            findings_text = "\n".join(findings_sections)
            review_text = (
                f"## Comprehensive Code Review Findings: Safety & Logic Audit\n\n"
                f"### Section 1: Findings & Relevant Code Evidence\n\n"
                f"{findings_text}\n"
                f"### Section 2: Mechanism & Root Cause Explanation\n"
                f"- Scanned `{file_path}` across identified methods and classes.\n"
                f"- Validated control flow, data transformations, and state persistence.\n"
                f"- Financial, concurrency, and validation boundaries require strict typing and test coverage.\n\n"
                f"### Section 3: Suggested Fix & Next Steps\n"
                f"- Apply the recommended fixes to `{file_path}`.\n"
                f"- Add unit tests targeting edge cases, empty payloads, and exception handling.\n\n"
                f"### Section 4: Evidence vs. Assumptions Summary\n"
                f"- **Evidence from Source**: Extracted from AST parse trees and source lines in `{file_path}`.\n"
                f"- **Assumption**: Assumes standard Python runtime and production business rules."
            )

        simulated_prompt_tokens = len(user_prompt.split()) * 2
        simulated_completion_tokens = len(review_text.split()) * 2
        total_tokens = simulated_prompt_tokens + simulated_completion_tokens

        return LLMResponse(
            content=review_text,
            raw_response=f'{{"mock_generated_text": "{review_text[:100]}...", "model": "{self.model_name}"}}',
            provider_name=self.provider_name,
            model_name=self.model_name,
            prompt_tokens=simulated_prompt_tokens,
            completion_tokens=simulated_completion_tokens,
            total_tokens=total_tokens,
            duration_sec=elapsed,
            success=True,
            status_code=200,
        )
