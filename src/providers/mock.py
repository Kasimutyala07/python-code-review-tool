"""
Mock LLM Provider for deterministic offline execution, unit testing, and failure simulation.
Simulates realistic reviews and failure conditions without requiring live API keys or network access.
Supports single-file reviews and multi-file repository investigations.
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

        # Extract request text from user prompt for scenario matching
        lower_prompt = user_prompt.lower()
        dev_req = ""
        if "developer request:" in lower_prompt:
            dev_req = lower_prompt.split("developer request:")[1].split("###")[0]
        else:
            dev_req = lower_prompt

        # Scenario A: Insufficient Evidence in Repository
        if "insufficient evidence detected" in lower_prompt or any(
            term in dev_req for term in ["kubernetes", "redis", "stripe", "webhook", "bitcoin", "blockchain"]
        ):
            review_text = (
                "## Code Review Findings: Insufficient Evidence in Repository\n\n"
                "### Section 1: Findings & Relevant Code Evidence\n"
                "- **Status**: **INSUFFICIENT EVIDENCE**\n"
                "- **Investigation Scope**: Scanned Python repository files for relevant symbols and error patterns.\n"
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

        # Scenario B: Empty Cart Checkout Failure
        elif any(w in dev_req for w in ["empty", "cart"]) and any(w in dev_req for w in ["checkout", "fail", "why", "error"]):
            review_text = (
                "## Code Review Findings: Empty Cart Checkout Failure\n\n"
                "### Section 1: Findings & Relevant Code Evidence\n"
                "- **File Path**: `review-input/order_service.py`\n"
                "- **Relevant Class & Method**: `CheckoutRequest.from_dict` (Lines 188-204) and `OrderService.checkout` (Lines 575-591)\n"
                "- **Exact Code Evidence**:\n"
                "  Lines 191-193 in `CheckoutRequest.from_dict`:\n"
                "  ```python\n"
                "  raw_lines = value.get(\"items\")\n"
                "  if not isinstance(raw_lines, list) or not 1 <= len(raw_lines) <= MAX_CART_LINES:\n"
                "      raise ServiceError(f\"Cart must contain 1 to {MAX_CART_LINES} lines\")\n"
                "  ```\n"
                "  Where `MAX_CART_LINES = 40` (Line 34).\n\n"
                "### Section 2: Mechanism & Root Cause Explanation\n"
                "- **Failure Mechanism**:\n"
                "  When a user or client attempts to checkout with an empty cart (`\"items\": []`), `CheckoutRequest.from_dict()` validates the line item count.\n"
                "  Because `len(raw_lines)` is `0`, the condition `1 <= len(raw_lines) <= MAX_CART_LINES` evaluates to `False`.\n"
                "  The enclosing `not` condition inverts this to `True`, triggering:\n"
                "  `raise ServiceError(\"Cart must contain 1 to 40 lines\")`\n"
                "  This immediately aborts checkout execution with HTTP/CLI error exit before reaching `OrderService.checkout()` or generating a database quote.\n"
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
                "  If zero-item promotional orders (e.g. voucher redemptions) should be allowed, adjust the boundary to `0 <= len(raw_lines) <= MAX_CART_LINES` and handle empty line lists in `PricingService.price_lines()`.\n\n"
                "### Section 4: Evidence vs. Assumptions Summary\n"
                "- **Evidence from Source**: Line 192 in `order_service.py` enforces `1 <= len(raw_lines) <= 40`, strictly prohibiting `len(raw_lines) == 0` with `ServiceError`.\n"
                "- **Assumption**: Assumes the client application sends `\"items\": []` when the cart is empty."
            )

        # Scenario C: Order Total Discrepancy (Assignment Request 1)
        elif any(w in dev_req for w in ["mug", "quantity", "three", "30 before tax", "10 each"]) and not any(w in dev_req for w in ["all", "general", "every"]):
            review_text = (
                "## Code Review Findings: Order Total Discrepancy\n\n"
                "### Section 1: Findings & Relevant Code Evidence\n"
                "- **File Path**: `review-input/order_service.py`\n"
                "- **Relevant Location**: `PricingService.quote` (Line 523)\n"
                "- **Source Evidence**: Line 523 computes `subtotal = sum(line.unit_price_cents for line in lines)`.\n"
                "- **Observed Mechanism**: The subtotal generator expression sums `line.unit_price_cents` directly rather than `line.line_total_cents` (or `line.unit_price_cents * line.quantity`). Each line in `request.lines` is priced for exactly 1 unit regardless of requested quantity.\n"
                "- **Calculated Result**: Ordering 3 MUGs ($10.00 each) yields a subtotal of $10.00 instead of $30.00 ($10.00 × 3). With pickup shipping ($0.00) and 10% tax ($1.00), total becomes $11.00 instead of $33.00 ($30.00 + $3.00 tax).\n\n"
                "### Section 2: Mechanism & Root Cause Explanation\n"
                "- Any customer ordering multi-quantity line items is severely undercharged, receiving multiple items for the price of one.\n"
                "- Directly reduces revenue and creates immediate financial and inventory discrepancies upon checkout.\n\n"
                "### Section 3: Suggested Fix & Next Steps\n"
                "- **Suggested Fix**:\n"
                "  Update line 523 in `order_service.py`:\n"
                "  ```python\n"
                "  # Before:\n"
                "  subtotal = sum(line.unit_price_cents for line in lines)\n"
                "  # After:\n"
                "  subtotal = sum(line.line_total_cents for line in lines)\n"
                "  ```\n"
                "- **Next Steps**: Verify if `shipping_cost()` in line 511 should evaluate `subtotal - discount` against `FREE_SHIPPING_CENTS`.\n\n"
                "### Section 4: Evidence vs. Assumptions Summary\n"
                "- **Evidence from Source**: Line 523 sums `line.unit_price_cents` without quantity multiplication. In contrast, line 489 in `price_lines()` correctly computes `line_total_cents = product.price_cents * line.quantity`.\n"
                "- **Assumption**: Assumes each unit in `request.lines` has a quantity >= 1 and that prices are per-unit as defined in `DEMO_PRODUCTS`."
            )

        # Scenario D: Cancelled Order in Sales Report (Assignment Request 2)
        elif any(w in dev_req for w in ["cancel", "cancelled", "sales report"]) and not any(w in dev_req for w in ["all", "general", "every"]):
            review_text = (
                "## Code Review Findings: Cancelled Order in Sales Report\n\n"
                "### Section 1: Findings & Relevant Code Evidence\n"
                "- **File Path**: `review-input/order_service.py`\n"
                "- **Relevant Location**: `ReportingService.sales` (Lines 712-719) and `OrderService.cancel` (Lines 622-637)\n"
                "- **Source Evidence**: The sales query executes:\n"
                "  `SELECT COUNT(*) AS order_count, COALESCE(SUM(total_cents), 0) AS gross_cents ... FROM orders WHERE created_at >= ? AND created_at < ?`\n"
                "  Notice it contains no status condition (e.g., missing `AND status != 'cancelled'`). In contrast, line 749 in `top_products()` explicitly includes `AND o.status != 'cancelled'`.\n"
                "- **Observed Mechanism**: When an order is cancelled via `OrderService.cancel()`, its status is updated to `'cancelled'`. However, `ReportingService.sales()` selects all records matching the date range unconditionally, causing cancelled orders to persist in gross sales and order counts.\n\n"
                "### Section 2: Mechanism & Root Cause Explanation\n"
                "- Distorts financial and operational reporting, reporting phantom revenue and inflated order counts.\n"
                "- Accounting, tax, and audit filings based on this sales report will erroneously count cancelled transactions.\n\n"
                "### Section 3: Suggested Fix & Next Steps\n"
                "- **Suggested Fix**:\n"
                "  Update the SQL query in `ReportingService.sales()` (lines 717-718):\n"
                "  ```python\n"
                "  \"FROM orders WHERE created_at >= ? AND created_at < ? AND status != 'cancelled'\",\n"
                "  ```\n"
                "- **Next Steps**: Additionally inspect line 721 where refunds are joined to orders and filtered by `o.created_at` rather than `r.created_at`.\n\n"
                "### Section 4: Evidence vs. Assumptions Summary\n"
                "- **Evidence from Source**: The SQL query inside `ReportingService.sales` at line 717 queries `FROM orders` without checking the `status` column.\n"
                "- **Assumption**: Assumes management and accounting standards intend cancelled orders to be excluded from daily gross sales figures."
            )

        # Scenario E: General Bug & Safety Audit (Assignment Request 3)
        else:
            review_text = (
                "## Comprehensive Code Review Findings: All Bugs & Safety Audit\n\n"
                "### Section 1: Findings & Relevant Code Evidence\n\n"
                "#### Bug 1 [CRITICAL]: Subtotal Calculation Omits Item Quantity\n"
                "- **File Path**: `review-input/order_service.py`\n"
                "- **Location**: `PricingService.quote` (Line 523)\n"
                "- **Code Evidence**: `subtotal = sum(line.unit_price_cents for line in lines)`\n"
                "- **Evidence**: Although line 489 in `price_lines()` correctly computes `line_total_cents = product.price_cents * line.quantity`, line 523 sums `line.unit_price_cents` directly across cart lines. Quantity is completely omitted from subtotal accumulation.\n"
                "- **Fix**: Change to `subtotal = sum(line.line_total_cents for line in lines)`.\n\n"
                "#### Bug 2 [CRITICAL]: Inventory Duplication via Repeat Cancellation\n"
                "- **File Path**: `review-input/order_service.py`\n"
                "- **Location**: `OrderService.cancel` (Lines 624-637)\n"
                "- **Code Evidence**: Lines 626-627 check `if order['status'] == 'shipped': raise Conflict(...)`, but omit checking `if order['status'] == 'cancelled'`.\n"
                "- **Evidence**: When `cancel()` executes, lines 628-633 execute `UPDATE products SET stock = stock + line['quantity']`. Because already-cancelled orders are not rejected, repeated calls to `cancel()` continuously increment product stock indefinitely.\n"
                "- **Fix**: Add `if order['status'] == 'cancelled': raise Conflict('Order is already cancelled')` or verify `if order['status'] != 'placed': raise Conflict(...)`.\n\n"
                "#### Bug 3 [HIGH]: Cancelled Orders Erroneously Included in Sales Revenue\n"
                "- **File Path**: `review-input/order_service.py`\n"
                "- **Location**: `ReportingService.sales` (Lines 712-719)\n"
                "- **Code Evidence**: `SELECT COUNT(*) AS order_count, COALESCE(SUM(total_cents), 0) AS gross_cents ... FROM orders WHERE created_at >= ? AND created_at < ?`\n"
                "- **Evidence**: The query lacks a filter on order status. In contrast, `top_products()` at line 749 explicitly filters `AND o.status != 'cancelled'`. Daily sales reports aggregate cancelled orders as valid revenue.\n"
                "- **Fix**: Add `AND status != 'cancelled'` to the WHERE clause.\n\n"
                "#### Bug 4 [HIGH]: Refund Date Filter Mismatch Across Accounting Periods\n"
                "- **File Path**: `review-input/order_service.py`\n"
                "- **Location**: `ReportingService.sales` (Lines 720-725)\n"
                "- **Code Evidence**: `SELECT COALESCE(SUM(r.amount_cents), 0) AS refunded_cents FROM refunds r JOIN orders o ON o.order_id = r.order_id WHERE o.created_at >= ? AND o.created_at < ?`\n"
                "- **Evidence**: Refunds are bounded by `o.created_at` (the date the original order was created) rather than `r.created_at` (the date the refund was issued). A refund processed in March for a January order alters January's report rather than March's.\n"
                "- **Fix**: Filter on `r.created_at >= ? AND r.created_at < ?`.\n\n"
                "#### Bug 5 [MEDIUM]: Unused `discount` Parameter in Shipping Calculation\n"
                "- **File Path**: `review-input/order_service.py`\n"
                "- **Location**: `PricingService.shipping_cost` (Lines 511-516)\n"
                "- **Code Evidence**: `def shipping_cost(self, method: str, subtotal: int, discount: int) -> int:` receives `discount`, but line 514 checks `subtotal >= FREE_SHIPPING_CENTS` without subtracting discount.\n"
                "- **Evidence**: Free shipping threshold is granted based on gross subtotal even if a coupon discount brings the payable merchandise below the required free-shipping threshold.\n"
                "- **Fix**: Check `max(subtotal - discount, 0) >= FREE_SHIPPING_CENTS`.\n\n"
                "#### Bug 6 [MEDIUM]: Unhandled `FileExistsError` Crash on Exclusive File Creation\n"
                "- **File Path**: `review-input/order_service.py`\n"
                "- **Location**: `ReportingService.export_orders` (Line 796) and `write_invoice` (Line 976)\n"
                "- **Code Evidence**: `with path.open('x', encoding='utf-8') as stream:`\n"
                "- **Evidence**: Using exclusive creation mode `'x'` raises unhandled `FileExistsError` if the output file already exists, crashing the CLI.\n"
                "- **Fix**: Wrap in `try ... except FileExistsError:` and raise a structured `ServiceError`.\n\n"
                "### Section 2: Mechanism & Root Cause Explanation\n"
                "- **Financial Impact**: Pricing bug 1 causes direct merchant losses by charging multi-item orders at single-unit rates. Reporting bugs 3 and 4 produce inaccurate financial statements and audit discrepancies.\n"
                "- **Operational Impact**: Cancellation bug 2 corrupts inventory ledgers, creating phantom warehouse stock that cannot be fulfilled.\n"
                "- **Reliability Impact**: Unhandled file creation crashes CLI reporting commands without clean error messages.\n\n"
                "### Section 3: Suggested Fix & Next Steps\n"
                "- **Suggested Fixes**: Apply the exact patches listed for Bugs 1 through 6 in Section 1.\n"
                "- **Next Steps**: Run automated regression tests covering multi-quantity checkouts, repeat cancellations, and reporting filters.\n\n"
                "### Section 4: Evidence vs. Assumptions Summary\n"
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
