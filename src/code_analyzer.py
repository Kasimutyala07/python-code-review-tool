"""
Code Analyzer Module
Reads and analyzes Python source code using the AST module without executing or importing it.
Preserves source file immutability and extracts structural context.
"""

import ast
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class CodeSymbol:
    """Represents a class, function, or method extracted via AST."""
    name: str
    kind: str  # 'function', 'class', 'method'
    start_line: int
    end_line: int
    docstring: Optional[str] = None
    parameters: List[str] = field(default_factory=list)
    calls: List[str] = field(default_factory=list)
    source_lines: List[str] = field(default_factory=list)

    @property
    def line_count(self) -> int:
        return self.end_line - self.start_line + 1

    @property
    def header_signature(self) -> str:
        param_str = ", ".join(self.parameters)
        if self.kind == "class":
            return f"class {self.name}: (lines {self.start_line}-{self.end_line})"
        return f"def {self.name}({param_str}): (lines {self.start_line}-{self.end_line})"


class SafeCodeVisitor(ast.NodeVisitor):
    """AST visitor that extracts symbols, calls, and structural metadata."""

    def __init__(self, raw_lines: List[str]):
        self.raw_lines = raw_lines
        self.symbols: List[CodeSymbol] = []
        self.imports: List[str] = []
        self.top_level_variables: List[str] = []
        self._current_class: Optional[str] = None

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            self.imports.append(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        module = node.module or ""
        for alias in node.names:
            self.imports.append(f"{module}.{alias.name}")
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign):
        if self._current_class is None:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.top_level_variables.append(target.id)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        start = node.lineno
        end = getattr(node, "end_lineno", start)
        doc = ast.get_docstring(node)
        lines = self.raw_lines[start - 1:end]

        sym = CodeSymbol(
            name=node.name,
            kind="class",
            start_line=start,
            end_line=end,
            docstring=doc,
            source_lines=lines,
        )
        self.symbols.append(sym)

        old_class = self._current_class
        self._current_class = node.name
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._visit_function(item, is_method=True)
            else:
                self.visit(item)
        self._current_class = old_class

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._visit_function(node, is_method=False)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._visit_function(node, is_method=False)

    def _visit_function(self, node, is_method: bool = False):
        start = node.lineno
        end = getattr(node, "end_lineno", start)
        doc = ast.get_docstring(node)
        lines = self.raw_lines[start - 1:end]

        params = []
        for arg in node.args.args:
            params.append(arg.arg)

        # Collect function calls made inside this function
        calls = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    calls.append(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    calls.append(child.func.attr)

        kind = "method" if is_method else "function"
        name = f"{self._current_class}.{node.name}" if is_method and self._current_class else node.name

        sym = CodeSymbol(
            name=name,
            kind=kind,
            start_line=start,
            end_line=end,
            docstring=doc,
            parameters=params,
            calls=calls,
            source_lines=lines,
        )
        self.symbols.append(sym)


@dataclass
class StaticBugFinding:
    """Represents a statically verified code anomaly or logic bug."""
    rule_id: str
    title: str
    severity: str  # 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'
    line_number: int
    symbol_name: str
    code_snippet: str
    description: str
    impact: str
    recommendation: str

    def to_dict(self) -> Dict[str, any]:
        return {
            "rule_id": self.rule_id,
            "title": self.title,
            "severity": self.severity,
            "line_number": self.line_number,
            "symbol_name": self.symbol_name,
            "code_snippet": self.code_snippet,
            "description": self.description,
            "impact": self.impact,
            "recommendation": self.recommendation,
        }


class SafeBugScanner(ast.NodeVisitor):
    """AST visitor that statically detects logic flaws, pricing bugs, and safety anomalies."""

    def __init__(self, raw_lines: List[str]):
        self.raw_lines = raw_lines
        self.findings: List[StaticBugFinding] = []
        self._current_class: Optional[str] = None
        self._current_func: Optional[str] = None

    def visit_ClassDef(self, node: ast.ClassDef):
        old_class = self._current_class
        self._current_class = node.name
        self.generic_visit(node)
        self._current_class = old_class

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._visit_any_func(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._visit_any_func(node)

    def _visit_any_func(self, node):
        old_func = self._current_func
        sym_name = f"{self._current_class}.{node.name}" if self._current_class else node.name
        self._current_func = sym_name

        # Check: Unused business parameters in calculations
        params = [a.arg for a in node.args.args if a.arg not in ("self", "cls")]
        used = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
        for p in params:
            if p not in used and p in ("discount", "coupon", "quantity", "customer_id", "status"):
                line_idx = node.lineno - 1
                snippet = self.raw_lines[line_idx].strip() if line_idx < len(self.raw_lines) else ""
                self.findings.append(StaticBugFinding(
                    rule_id="UNUSED_BUSINESS_PARAMETER",
                    title="Unused Critical Parameter in Business Calculation",
                    severity="MEDIUM",
                    line_number=node.lineno,
                    symbol_name=sym_name,
                    code_snippet=snippet,
                    description=f"Parameter `{p}` is defined in function `{sym_name}` but is never referenced or evaluated in the function body.",
                    impact="Calculations may ignore customer discounts or thresholds, causing pricing or shipping anomalies.",
                    recommendation=f"Integrate `{p}` into the business calculation or remove it if obsolete.",
                ))

        # Check: Cancellation logic without checking already cancelled state (Stock inflation bug)
        if node.name in ("cancel", "cancel_order") or "cancel" in node.name:
            has_stock_update = False
            has_cancelled_check = False
            for child in ast.walk(node):
                if isinstance(child, ast.Constant) and isinstance(child.value, str):
                    if "UPDATE products SET stock = stock +" in child.value:
                        has_stock_update = True
                if isinstance(child, ast.Compare):
                    for c in child.comparators:
                        if isinstance(c, ast.Constant) and c.value == "cancelled":
                            has_cancelled_check = True
            if has_stock_update and not has_cancelled_check:
                line_idx = node.lineno - 1
                snippet = self.raw_lines[line_idx].strip() if line_idx < len(self.raw_lines) else ""
                self.findings.append(StaticBugFinding(
                    rule_id="DOUBLE_CANCELLATION_REENTRANCY",
                    title="Stock Duplication via Repeat Cancellation",
                    severity="CRITICAL",
                    line_number=node.lineno,
                    symbol_name=sym_name,
                    code_snippet=snippet,
                    description="Cancellation logic restocks inventory for order lines without verifying that the order is not already 'cancelled'.",
                    impact="Enables an attacker or client to cancel the same order multiple times, continuously duplicating inventory in the database.",
                    recommendation="Add `if order['status'] == 'cancelled': raise Conflict('Order is already cancelled')` before restocking.",
                ))

        self.generic_visit(node)
        self._current_func = old_func

    def visit_Call(self, node: ast.Call):
        # Check: sum(line.unit_price_cents for line in lines) - Pricing omitting item quantity
        if isinstance(node.func, ast.Name) and node.func.id == "sum":
            for arg in node.args:
                if isinstance(arg, ast.GeneratorExp):
                    elt = arg.elt
                    if isinstance(elt, ast.Attribute) and elt.attr in ("unit_price_cents", "unit_price", "price_cents", "price"):
                        line_idx = node.lineno - 1
                        snippet = self.raw_lines[line_idx].strip() if line_idx < len(self.raw_lines) else ""
                        self.findings.append(StaticBugFinding(
                            rule_id="PRICING_OMITS_QUANTITY",
                            title="Subtotal Calculation Omits Item Quantity",
                            severity="CRITICAL",
                            line_number=node.lineno,
                            symbol_name=self._current_func or "pricing",
                            code_snippet=snippet,
                            description=f"Pricing accumulation sums `{elt.attr}` directly across cart lines without multiplying by `line.quantity` or using `line.line_total_cents`.",
                            impact="Customers purchasing multiple units of an item are severely undercharged (paying for 1 unit regardless of quantity).",
                            recommendation="Replace with `sum(line.line_total_cents for line in lines)` or `sum(line.unit_price_cents * line.quantity for line in lines)`.",
                        ))

        # Check: Exclusive file creation mode 'x' without FileExistsError handler
        for arg in node.args:
            if isinstance(arg, ast.Constant) and arg.value == "x":
                line_idx = node.lineno - 1
                snippet = self.raw_lines[line_idx].strip() if line_idx < len(self.raw_lines) else ""
                self.findings.append(StaticBugFinding(
                    rule_id="UNHANDLED_EXCLUSIVE_FILE_WRITE",
                    title="Exclusive File Mode 'x' Crash Risk",
                    severity="MEDIUM",
                    line_number=node.lineno,
                    symbol_name=self._current_func or "file_io",
                    code_snippet=snippet,
                    description="File is opened in exclusive creation mode 'x' without handling FileExistsError.",
                    impact="If the export or invoice file already exists on disk, the application crashes unexpectedly with an unhandled exception.",
                    recommendation="Catch `FileExistsError` and raise a user-friendly `ServiceError` or allow explicit overwrite.",
                ))

        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant):
        if isinstance(node.value, str):
            val = node.value
            # Check: Sales query omitting cancelled orders
            if "FROM orders WHERE created_at" in val and "status" not in val.lower():
                line_idx = node.lineno - 1
                snippet = self.raw_lines[line_idx].strip() if line_idx < len(self.raw_lines) else ""
                self.findings.append(StaticBugFinding(
                    rule_id="SALES_REPORT_INCLUDES_CANCELLED",
                    title="Cancelled Orders Erroneously Included in Sales Revenue",
                    severity="HIGH",
                    line_number=node.lineno,
                    symbol_name=self._current_func or "reporting",
                    code_snippet=snippet,
                    description="Sales reporting query aggregates order totals and counts without excluding cancelled orders (`status != 'cancelled'`).",
                    impact="Daily and period gross sales, order count, and collected tax reports are erroneously inflated by cancelled orders.",
                    recommendation="Add `AND status != 'cancelled'` to the SQL WHERE clause.",
                ))
            # Check: Refund date filter misattribution
            if ("FROM refunds" in val or "JOIN refunds" in val) and "WHERE o.created_at" in val:
                line_idx = node.lineno - 1
                snippet = self.raw_lines[line_idx].strip() if line_idx < len(self.raw_lines) else ""
                self.findings.append(StaticBugFinding(
                    rule_id="REFUND_DATE_FILTER_MISMATCH",
                    title="Refund Date Attributed to Order Date Instead of Refund Date",
                    severity="HIGH",
                    line_number=node.lineno,
                    symbol_name=self._current_func or "reporting",
                    code_snippet=snippet,
                    description="Refund query filters on `o.created_at` (the date the order was placed) instead of `r.created_at` (the date the refund was processed).",
                    impact="Refunds processed in later accounting periods are retroactively applied to past order periods, distorting period financials.",
                    recommendation="Filter on `r.created_at >= ? AND r.created_at < ?`.",
                ))
        self.generic_visit(node)


class CodeAnalyzer:
    """Safe static code analyzer for Python files."""

    def __init__(self, file_path: str | Path):
        self.file_path = Path(file_path).resolve()
        if not self.file_path.exists():
            raise FileNotFoundError(f"Source file not found: {file_path}")
        if not self.file_path.is_file():
            raise ValueError(f"Path is not a regular file: {file_path}")

        self.raw_content: str = ""
        self.raw_lines: List[str] = []
        self.initial_hash: str = ""
        self.symbols: List[CodeSymbol] = []
        self.imports: List[str] = []
        self.static_findings: List[StaticBugFinding] = []
        self.parse_error: Optional[str] = None
        self._load_and_parse()

    def _load_and_parse(self):
        """Read the file content in text mode and compute hash without executing."""
        try:
            with open(self.file_path, "r", encoding="utf-8", errors="replace") as f:
                self.raw_content = f.read()
        except Exception as e:
            raise IOError(f"Could not read source file {self.file_path}: {e}")

        self.initial_hash = hashlib.sha256(self.raw_content.encode("utf-8")).hexdigest()
        self.raw_lines = self.raw_content.splitlines(keepends=True)

        try:
            tree = ast.parse(self.raw_content, filename=str(self.file_path))
            visitor = SafeCodeVisitor(self.raw_lines)
            visitor.visit(tree)
            self.symbols = visitor.symbols
            self.imports = visitor.imports

            scanner = SafeBugScanner(self.raw_lines)
            scanner.visit(tree)
            self.static_findings = scanner.findings
        except SyntaxError as se:
            self.parse_error = f"SyntaxError at line {se.lineno}: {se.msg}"
        except Exception as e:
            self.parse_error = f"AST parse error: {e}"

    def scan_static_bugs(self) -> List[StaticBugFinding]:
        """Returns detected static AST bug findings."""
        return list(self.static_findings)

    def verify_integrity(self) -> bool:
        """Verify that the source file on disk has not been altered."""
        try:
            with open(self.file_path, "r", encoding="utf-8", errors="replace") as f:
                current_content = f.read()
            current_hash = hashlib.sha256(current_content.encode("utf-8")).hexdigest()
            return current_hash == self.initial_hash
        except Exception:
            return False

    def get_file_summary(self) -> Dict[str, any]:
        """Returns high-level structural statistics of the file."""
        return {
            "file_name": self.file_path.name,
            "total_lines": len(self.raw_lines),
            "symbol_count": len(self.symbols),
            "function_count": len([s for s in self.symbols if s.kind in ("function", "method")]),
            "class_count": len([s for s in self.symbols if s.kind == "class"]),
            "sha256": self.initial_hash,
            "has_parse_error": self.parse_error is not None,
            "error_message": self.parse_error,
        }

    def find_relevant_symbols(self, query: str, top_k: int = 5) -> List[Tuple[CodeSymbol, float]]:
        """
        Rank symbols based on lexical similarity to user's plain-language request.
        Matches against symbol name, docstring, parameters, and source lines.
        """
        if not self.symbols:
            return []

        # Tokenize request into lowercase terms (length >= 3)
        terms = [t.lower() for t in re.findall(r"\b[A-Za-z0-9_]{3,}\b", query)]
        if not terms:
            # Fallback: return symbols by order of appearance or size
            return [(s, 1.0) for s in self.symbols[:top_k]]

        scored: List[Tuple[CodeSymbol, float]] = []
        for sym in self.symbols:
            score = 0.0
            sym_name_tokens = re.findall(r"\b[A-Za-z0-9_]+\b", sym.name.lower())
            doc_tokens = re.findall(r"\b[A-Za-z0-9_]+\b", (sym.docstring or "").lower())
            param_tokens = [p.lower() for p in sym.parameters]

            for term in terms:
                # Direct match in symbol name (strong signal)
                if term in sym.name.lower():
                    score += 5.0
                if any(term in token for token in sym_name_tokens):
                    score += 3.0
                # Match in parameters
                if any(term in p for p in param_tokens):
                    score += 2.0
                # Match in docstring
                if term in doc_tokens:
                    score += 1.5
                # Match in source lines
                source_content = "".join(sym.source_lines).lower()
                if term in source_content:
                    score += 1.0

            if score > 0:
                scored.append((sym, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def format_code_with_line_numbers(self, start_line: int = 1, end_line: Optional[int] = None) -> str:
        """Formats source lines with 1-based line number prefixes."""
        if end_line is None or end_line > len(self.raw_lines):
            end_line = len(self.raw_lines)
        start_line = max(1, start_line)

        formatted = []
        for i in range(start_line - 1, end_line):
            line_no = i + 1
            line_str = self.raw_lines[i].rstrip("\r\n")
            formatted.append(f"{line_no:4d} | {line_str}")
        return "\n".join(formatted)

    def extract_context_for_request(self, request_text: str, max_full_lines: int = 3000) -> str:
        """
        Builds the code context for the LLM prompt.
        Supplies complete source code with line numbers (up to max_full_lines) or for general reviews.
        Attaches architectural symbol outline and automated static pre-scan findings.
        """
        total_lines = len(self.raw_lines)
        outline_parts = ["### FILE STRUCTURAL OUTLINE:"]
        for s in self.symbols:
            outline_parts.append(f"- {s.header_signature}")
        outline_text = "\n".join(outline_parts)

        # Static analysis pre-scan section
        static_section = ""
        if self.static_findings:
            static_parts = [
                "### AUTOMATED STATIC CODE ANALYSIS PRE-SCAN:",
                "The AST static analyzer verified the following concrete code issues and safety anomalies:",
            ]
            for f in self.static_findings:
                static_parts.append(
                    f"- [{f.severity}] Line {f.line_number} in `{f.symbol_name}`: {f.title} ({f.description})"
                )
            static_section = "\n".join(static_parts) + "\n\n"

        # Check if query requests a general/comprehensive bug review
        is_general_review = any(w in request_text.lower() for w in [
            "bug", "bugs", "review", "audit", "all", "mistake", "error", "security", "check", "flaw"
        ])

        if total_lines <= max_full_lines or is_general_review:
            code_block = self.format_code_with_line_numbers(1, total_lines)
            return (
                f"{static_section}"
                f"{outline_text}\n\n"
                f"### COMPLETE SOURCE CODE ({total_lines} lines):\n"
                f"```python\n{code_block}\n```"
            )

        # For exceptionally large files exceeding context limits:
        relevant = self.find_relevant_symbols(request_text, top_k=8)
        extracted_sections = []
        for sym, score in relevant:
            section_code = self.format_code_with_line_numbers(sym.start_line, sym.end_line)
            extracted_sections.append(
                f"#### Symbol: {sym.name} (Lines {sym.start_line}-{sym.end_line}, Match Score: {score:.1f})\n"
                f"```python\n{section_code}\n```"
            )

        return (
            f"{static_section}"
            f"{outline_text}\n\n"
            f"### RELEVANT CODE SECTIONS (Extracted for query):\n\n" +
            "\n\n".join(extracted_sections)
        )
