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

        if any(w in dev_req for w in ["mug", "quantity", "three", "30 before tax", "10 each"]) and not any(w in dev_req for w in ["all", "general", "every"]):
            review_text = (
                "## Code Review Findings: Order Total Discrepancy\n\n"
                "### 1. Primary Finding & Source Evidence\n"
                "- **Relevant Location**: `PricingService.quote` (Line 523)\n"
                "- **Source Evidence**: Line 523 computes `subtotal = sum(line.unit_price_cents for line in lines)`.\n"
                "- **Observed Mechanism**: The subtotal generator expression sums `line.unit_price_cents` directly rather than `line.line_total_cents` (or `line.unit_price_cents * line.quantity`). Each line in `request.lines` is priced for exactly 1 unit regardless of requested quantity.\n"
                "- **Calculated Result**: Ordering 3 MUGs ($10.00 each) yields a subtotal of $10.00 instead of $30.00 ($10.00 × 3). With pickup shipping ($0.00) and 10% tax ($1.00), total becomes $11.00 instead of $33.00 ($30.00 + $3.00 tax).\n\n"
                "### 2. Impact on Application & System Behavior\n"
                "- Any customer ordering multi-quantity line items is severely undercharged, receiving multiple items for the price of one.\n"
                "- Directly reduces revenue and creates immediate financial and inventory discrepancies upon checkout.\n\n"
                "### 3. Remaining Uncertainty & What to Check Next\n"
                "- **Uncertainty**: Are coupons and shipping thresholds intended to evaluate net merchandise or gross subtotal?\n"
                "- **Next Steps**: Update line 523 to `subtotal = sum(line.line_total_cents for line in lines)`. Verify if `shipping_cost()` in line 511 should evaluate `subtotal - discount` against `FREE_SHIPPING_CENTS`.\n\n"
                "### 4. Evidence vs. Assumptions\n"
                "- **Evidence from Source**: Line 523 sums `line.unit_price_cents` without quantity multiplication. In contrast, line 489 in `price_lines()` correctly computes `line_total_cents = product.price_cents * line.quantity`.\n"
                "- **Assumption**: Assumes each unit in `request.lines` has a quantity >= 1 and that prices are per-unit as defined in `DEMO_PRODUCTS`."
            )
        elif any(w in dev_req for w in ["cancel", "cancelled", "sales report"]) and not any(w in dev_req for w in ["all", "general", "every"]):
            review_text = (
                "## Code Review Findings: Cancelled Order in Sales Report\n\n"
                "### 1. Primary Finding & Source Evidence\n"
                "- **Relevant Location**: `ReportingService.sales` (Lines 712-719) and `OrderService.cancel` (Lines 622-637)\n"
                "- **Source Evidence**: The sales query executes:\n"
                "  `SELECT COUNT(*) AS order_count, COALESCE(SUM(total_cents), 0) AS gross_cents ... FROM orders WHERE created_at >= ? AND created_at < ?`\n"
                "  Notice it contains no status condition (e.g., missing `AND status != 'cancelled'`). In contrast, line 749 in `top_products()` explicitly includes `AND o.status != 'cancelled'`.\n"
                "- **Observed Mechanism**: When an order is cancelled via `OrderService.cancel()`, its status is updated to `'cancelled'`. However, `ReportingService.sales()` selects all records matching the date range unconditionally, causing cancelled orders to persist in gross sales and order counts.\n\n"
                "### 2. Impact on Application & System Behavior\n"
                "- Distorts financial and operational reporting, reporting phantom revenue and inflated order counts.\n"
                "- Accounting, tax, and audit filings based on this sales report will erroneously count cancelled transactions.\n\n"
                "### 3. Remaining Uncertainty & What to Check Next\n"
                "- **Uncertainty**: Should refunds on cancelled orders be included if any were issued prior to cancellation?\n"
                "- **Next Steps**: Add `AND status != 'cancelled'` to line 717. Additionally, inspect line 721 where refunds are joined to orders and filtered by `o.created_at` rather than `r.created_at`.\n\n"
                "### 4. Evidence vs. Assumptions\n"
                "- **Evidence from Source**: The SQL query inside `ReportingService.sales` at line 717 queries `FROM orders` without checking the `status` column.\n"
                "- **Assumption**: Assumes management and accounting standards intend cancelled orders to be excluded from daily gross sales figures."
            )
        else:
            review_text = (
                "## Comprehensive Code Review Findings: All Bugs & Safety Audit\n\n"
                "### 1. Primary Findings & Relevant Code Evidence\n\n"
                "#### Bug 1 [CRITICAL]: Subtotal Calculation Omits Item Quantity\n"
                "- **Location**: `PricingService.quote` (Line 523)\n"
                "- **Code Evidence**: `subtotal = sum(line.unit_price_cents for line in lines)`\n"
                "- **Evidence**: Although line 489 in `price_lines()` correctly computes `line_total_cents = product.price_cents * line.quantity`, line 523 sums `line.unit_price_cents` directly across cart lines. Quantity is completely omitted from subtotal accumulation.\n"
                "- **Fix**: Change to `subtotal = sum(line.line_total_cents for line in lines)`.\n\n"
                "#### Bug 2 [CRITICAL]: Inventory Duplication via Repeat Cancellation\n"
                "- **Location**: `OrderService.cancel` (Lines 624-637)\n"
                "- **Code Evidence**: Lines 626-627 check `if order['status'] == 'shipped': raise Conflict(...)`, but omit checking `if order['status'] == 'cancelled'`.\n"
                "- **Evidence**: When `cancel()` executes, lines 628-633 execute `UPDATE products SET stock = stock + line['quantity']`. Because already-cancelled orders are not rejected, repeated calls to `cancel()` continuously increment product stock indefinitely.\n"
                "- **Fix**: Add `if order['status'] == 'cancelled': raise Conflict('Order is already cancelled')` or verify `if order['status'] != 'placed': raise Conflict(...)`.\n\n"
                "#### Bug 3 [HIGH]: Cancelled Orders Erroneously Included in Sales Revenue\n"
                "- **Location**: `ReportingService.sales` (Lines 712-719)\n"
                "- **Code Evidence**: `SELECT COUNT(*) AS order_count, COALESCE(SUM(total_cents), 0) AS gross_cents ... FROM orders WHERE created_at >= ? AND created_at < ?`\n"
                "- **Evidence**: The query lacks a filter on order status. In contrast, `top_products()` at line 749 explicitly filters `AND o.status != 'cancelled'`. Daily sales reports aggregate cancelled orders as valid revenue.\n"
                "- **Fix**: Add `AND status != 'cancelled'` to the WHERE clause.\n\n"
                "#### Bug 4 [HIGH]: Refund Date Filter Mismatch Across Accounting Periods\n"
                "- **Location**: `ReportingService.sales` (Lines 720-725)\n"
                "- **Code Evidence**: `SELECT COALESCE(SUM(r.amount_cents), 0) AS refunded_cents FROM refunds r JOIN orders o ON o.order_id = r.order_id WHERE o.created_at >= ? AND o.created_at < ?`\n"
                "- **Evidence**: Refunds are bounded by `o.created_at` (the date the original order was created) rather than `r.created_at` (the date the refund was issued). A refund processed in March for a January order alters January's report rather than March's.\n"
                "- **Fix**: Filter on `r.created_at >= ? AND r.created_at < ?`.\n\n"
                "#### Bug 5 [MEDIUM]: Unused `discount` Parameter in Shipping Calculation\n"
                "- **Location**: `PricingService.shipping_cost` (Lines 511-516)\n"
                "- **Code Evidence**: `def shipping_cost(self, method: str, subtotal: int, discount: int) -> int:` receives `discount`, but line 514 checks `subtotal >= FREE_SHIPPING_CENTS` without subtracting discount.\n"
                "- **Evidence**: Free shipping threshold is granted based on gross subtotal even if a coupon discount brings the payable merchandise below the required free-shipping threshold.\n"
                "- **Fix**: Check `max(subtotal - discount, 0) >= FREE_SHIPPING_CENTS`.\n\n"
                "#### Bug 6 [MEDIUM]: Unhandled `FileExistsError` Crash on Exclusive File Creation\n"
                "- **Location**: `ReportingService.export_orders` (Line 796) and `write_invoice` (Line 976)\n"
                "- **Code Evidence**: `with path.open('x', encoding='utf-8') as stream:`\n"
                "- **Evidence**: Using exclusive creation mode `'x'` raises unhandled `FileExistsError` if the output file already exists, crashing the CLI.\n"
                "- **Fix**: Wrap in `try ... except FileExistsError:` and raise a structured `ServiceError`.\n\n"
                "### 2. Mechanism & Impact on Application & System Behavior\n"
                "- **Financial Impact**: Pricing bug 1 causes direct merchant losses by charging multi-item orders at single-unit rates. Reporting bugs 3 and 4 produce inaccurate financial statements and audit discrepancies.\n"
                "- **Operational Impact**: Cancellation bug 2 corrupts inventory ledgers, creating phantom warehouse stock that cannot be fulfilled.\n"
                "- **Reliability Impact**: Unhandled file creation crashes CLI reporting commands without clean error messages.\n\n"
                "### 3. Remaining Uncertainty & What to Check Next\n"
                "- **Uncertainty**: Does SQLite operate in WAL mode in production? The connection initialization (line 330) uses standard rollback journal without `PRAGMA journal_mode = WAL`.\n"
                "- **Next Steps**: Run automated regression tests covering multi-quantity checkouts, repeat cancellations, and reporting filters.\n\n"
                "### 4. Evidence vs. Assumptions Summary\n"
                "- **Evidence from Source**: Lines 523, 626-635, 713, 721, 514, and 796/976 contain verifiable logic and syntax issues directly visible in the AST and source text.\n"
                "- **Assumption**: Assumes intended business rules mandate excluding cancelled orders from sales and that free shipping applies to net subtotal."
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
