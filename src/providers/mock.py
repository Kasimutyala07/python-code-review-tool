"""
Mock LLM Provider for deterministic offline execution, unit testing, and failure simulation.
Simulates realistic reviews and failure conditions without requiring live API keys or network access.
"""

import time
from typing import Optional

from .base import BaseLLMProvider, LLMResponse


class MockProvider(BaseLLMProvider):
    """Deterministic Mock Provider for tests and offline presentation."""

    def __init__(
        self,
        model_name: str = "mock-reviewer-v1",
        failure_mode: Optional[str] = None,  # 'timeout', 'quota_exceeded', 'server_error', 'empty_response'
        simulated_delay: float = 0.05,
    ):
        super().__init__(model_name=model_name, api_key="mock_key")
        self.failure_mode = failure_mode
        self.simulated_delay = simulated_delay

    @property
    def provider_name(self) -> str:
        return "MockProvider"

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

        # Generate realistic, structured review matching the assignment instructions:
        # 1. The finding and the relevant function, expression or original source lines that support it.
        # 2. How the issue could cause the reported behavior or affect the application.
        # 3. What is uncertain, what information is missing, and what should be checked next.
        # 4. Distinguish evidence from assumptions.

        # Extract request text from user prompt for scenario matching
        lower_prompt = user_prompt.lower()
        dev_req = ""
        if "developer request:" in lower_prompt:
            dev_req = lower_prompt.split("developer request:")[1].split("###")[0]
        else:
            dev_req = lower_prompt

        if any(w in dev_req for w in ["mug", "quantity", "three", "30 before tax", "10 each"]):
            review_text = (
                "## Code Review Findings: Order Total Discrepancy\n\n"
                "### 1. Primary Finding & Source Evidence\n"
                "- **Relevant Location**: `calculate_subtotal` / order pricing calculation function.\n"
                "- **Evidence**: The line multiplying item price appears to omit item quantity, or defaults multiplier to `1` regardless of `item.quantity` (e.g., `subtotal += item.unit_price` instead of `subtotal += item.unit_price * item.quantity`).\n"
                "- **Observed Result**: Ordering 3 MUGs at $10 each produced a subtotal of $10 instead of $30 ($10 × 3). With shipping/pickup ($0) and 10% tax, the total became $11 ($10 + $1) rather than expected $33 ($30 + $3).\n\n"
                "### 2. Impact on Application & System Behavior\n"
                "- Customers ordering multiple quantities of any item are severely undercharged, receiving multiple items for the price of one.\n"
                "- Directly impacts merchant revenue and creates inventory reconciliation discrepancies.\n\n"
                "### 3. Remaining Uncertainty & What to Check Next\n"
                "- **Uncertainty**: Need to verify whether discounts, bundles, or tiered pricing rules interact with `calculate_subtotal`.\n"
                "- **Next Steps**: Inspect line in `calculate_subtotal` or checkout loop where line items are accumulated; check if `item['quantity']` is properly unpacked from the request payload.\n\n"
                "### 4. Evidence vs. Assumptions\n"
                "- **Evidence from Source**: Pricing calculation loop sums unit prices without quantity multiplication.\n"
                "- **Assumption**: Assumes the supplied unit price is per-item and not a bulk package price."
            )
        elif any(w in dev_req for w in ["cancel", "cancelled", "sales report"]):
            review_text = (
                "## Code Review Findings: Cancelled Order in Sales Report\n\n"
                "### 1. Primary Finding & Source Evidence\n"
                "- **Relevant Location**: `generate_sales_report` SQL query / order filtering logic.\n"
                "- **Evidence**: The sales reporting query executes `SELECT sum(total), count(*) FROM orders WHERE date = ?` without a filter on order status (e.g., missing `AND status != 'CANCELLED'`).\n"
                "- **Observed Result**: Even after an order is successfully cancelled via `cancel_order`, the daily sales report queries all records matching the date regardless of status, inflating order counts and gross sales.\n\n"
                "### 2. Impact on Application & System Behavior\n"
                "- Distorts financial and operational reporting, leading to inflated revenue figures and inaccurate reconciliation.\n"
                "- Tax and audit filings based on this report would erroneously include cancelled sales.\n\n"
                "### 3. Remaining Uncertainty & What to Check Next\n"
                "- **Uncertainty**: Does `cancel_order` physically delete rows or perform a soft-delete/status update? Check database schema for `orders.status`.\n"
                "- **Next Steps**: Inspect `generate_sales_report` and add `WHERE status IN ('COMPLETED', 'SHIPPED')` or exclude `'CANCELLED'`.\n\n"
                "### 4. Evidence vs. Assumptions\n"
                "- **Evidence from Source**: The SQL query inside `generate_sales_report` does not check the `status` column.\n"
                "- **Assumption**: Assumes cancelled orders are intended to be omitted from net daily sales figures according to standard accounting rules."
            )
        else:
            review_text = (
                "## Code Review Findings: General Bug & Safety Audit\n\n"
                "### 1. Primary Findings & Source Evidence\n"
                "- **Finding 1 (Stock / Inventory Mutability)**: Inventory decrement is performed outside an atomic transaction block. If an error occurs between payment capture and order commit, stock can be decremented without an order record.\n"
                "- **Finding 2 (Totals & Floating Point Precision)**: Monetary calculations use standard floating-point numbers (`float`) rather than integer cents or `decimal.Decimal`, introducing rounding errors on tax and discount calculations.\n"
                "- **Finding 3 (Discount Validation)**: Coupon codes are applied before checking minimum cart value thresholds, allowing coupons to reduce totals below allowed floors.\n\n"
                "### 2. Impact on Application & System Behavior\n"
                "- Inventory counts can drift over time under concurrent load.\n"
                "- Sub-cent rounding discrepancies accumulate in accounting ledgers.\n\n"
                "### 3. Remaining Uncertainty & What to Check Next\n"
                "- **Uncertainty**: The exact concurrency level and isolation level of SQLite in production.\n"
                "- **Next Steps**: Inspect transaction boundaries around `checkout()`, verify if SQLite `BEGIN IMMEDIATE` or WAL mode is enabled, and review `decimal.Decimal` migration for price computations.\n\n"
                "### 4. Evidence vs. Assumptions\n"
                "- **Evidence from Source**: Direct usage of `float` arithmetic and absence of `with db.transaction():` in checkout flow.\n"
                "- **Assumption**: Assumes multi-threaded or multi-process requests access the database."
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
