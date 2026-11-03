"""
Code Analyzer Module
Reads and analyzes Python source code using the AST module without executing or importing it.
Preserves source file immutability and extracts structural context.
Supports single-file AST inspection and multi-file repository investigation.
"""

import ast
import hashlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


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

        stopwords = {
            "why", "does", "do", "did", "when", "the", "a", "an", "is", "are", "was", "were",
            "what", "how", "can", "you", "in", "to", "for", "with", "of", "and", "or", "it",
            "this", "that", "at", "by", "from", "be", "have", "has", "had", "please", "check",
            "investigate", "explain", "tell", "me", "could", "should", "would", "where", "on",
            "off", "out", "into", "about", "against", "between", "through", "during", "before",
            "after", "above", "below", "under", "up", "down", "over", "again", "further", "then",
            "once", "here", "there", "all", "any", "both", "each", "few", "more", "most", "other",
            "some", "such", "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very",
            "will", "just", "now"
        }
        # Tokenize request into lowercase terms (length >= 3) excluding stopwords
        raw_terms = [t.lower() for t in re.findall(r"\b[A-Za-z0-9_]{3,}\b", query)]
        terms = [t for t in raw_terms if t not in stopwords]
        if not terms:
            terms = raw_terms[:5]
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


# =====================================================================
# Multi-File Repository Analysis & Search (Avoids full-repo flooding)
# =====================================================================

@dataclass
class RepoSearchResult:
    """Represents a matched file in a multi-file repository search."""
    file_path: Path
    relative_path: str
    relevance_score: float
    matched_symbols: List[Tuple[CodeSymbol, float]]
    matched_lines: List[Tuple[int, str]]  # line_no, content
    analyzer: CodeAnalyzer
    distinct_terms_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "relative_path": self.relative_path,
            "relevance_score": round(self.relevance_score, 2),
            "matched_symbol_names": [s.name for s, _ in self.matched_symbols],
            "matched_line_count": len(self.matched_lines),
        }


class RepoAnalyzer:
    """
    Safe read-only multi-file repository code investigator.
    Discovers files, tracks hashes for immutability, conducts cross-file relevance search,
    and extracts targeted context without overwhelming LLM context window.
    """
    DEFAULT_IGNORE_DIRS = {
        ".git", ".github", ".venv", "venv", "env", "ENV", "__pycache__",
        ".pytest_cache", ".vscode", ".idea", "node_modules", "build", "dist",
        ".eggs", ".reviews", "evidence", "review-outputs"
    }

    def __init__(self, repo_dir: str | Path, ignore_patterns: Optional[Set[str]] = None):
        self.repo_dir = Path(repo_dir).resolve()
        if not self.repo_dir.exists():
            raise FileNotFoundError(f"Repository directory does not exist: {repo_dir}")
        if not self.repo_dir.is_dir():
            raise ValueError(f"Target path is not a directory: {repo_dir}")

        self.ignore_dirs = set(ignore_patterns) if ignore_patterns else self.DEFAULT_IGNORE_DIRS
        self.discovered_files: List[Path] = []
        self.initial_hashes: Dict[Path, str] = {}
        self._analyzers: Dict[Path, CodeAnalyzer] = {}
        self._scan_and_hash()

    def _scan_and_hash(self):
        """Recursively scan for Python files and record SHA-256 hashes."""
        for root, dirs, files in os.walk(self.repo_dir):
            dirs[:] = [d for d in dirs if d not in self.ignore_dirs and not d.startswith(".")]
            for file in sorted(files):
                if file.endswith(".py"):
                    full_path = Path(root) / file
                    try:
                        # Avoid huge generated files > 1.5MB
                        if full_path.stat().st_size <= 1_500_000:
                            self.discovered_files.append(full_path)
                            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                                content = f.read()
                            sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
                            self.initial_hashes[full_path] = sha
                    except Exception:
                        continue

    def compute_current_repo_hash(self) -> str:
        """Computes current cumulative SHA-256 of all discovered Python files."""
        parts = []
        for p in sorted(self.discovered_files):
            try:
                with open(p, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                h = hashlib.sha256(content.encode("utf-8")).hexdigest()
                parts.append(f"{str(p)}:{h}")
            except Exception:
                parts.append(f"{str(p)}:missing")
        return hashlib.sha256("".join(parts).encode("utf-8")).hexdigest()

    def get_repo_hash(self) -> str:
        """Deterministic cumulative SHA-256 of all discovered Python files."""
        return self.compute_current_repo_hash()

    def verify_repo_integrity(self) -> bool:
        """Verify that NO files in the repository were modified during review."""
        for path, expected_hash in self.initial_hashes.items():
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                current_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                if current_hash != expected_hash:
                    return False
            except Exception:
                return False
        return True

    def get_analyzer(self, file_path: Path) -> CodeAnalyzer:
        """Lazy loads or returns cached CodeAnalyzer for a file."""
        if file_path not in self._analyzers:
            self._analyzers[file_path] = CodeAnalyzer(file_path)
        return self._analyzers[file_path]

    def search_codebase(self, query: str, max_files: int = 4) -> Tuple[List[RepoSearchResult], bool]:
        """
        Search repository for files and symbols relevant to plain-English query.
        Returns: (results_list, insufficient_evidence_flag)
        """
        stopwords = {
            "why", "does", "do", "did", "when", "the", "a", "an", "is", "are", "was", "were",
            "what", "how", "can", "you", "in", "to", "for", "with", "of", "and", "or", "it",
            "this", "that", "at", "by", "from", "be", "have", "has", "had", "please", "check",
            "investigate", "explain", "tell", "me", "could", "should", "would", "where", "on",
            "off", "out", "into", "about", "against", "between", "through", "during", "before",
            "after", "above", "below", "under", "up", "down", "over", "again", "further", "then",
            "once", "here", "there", "all", "any", "both", "each", "few", "more", "most", "other",
            "some", "such", "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very",
            "will", "just", "now"
        }
        raw_terms = re.findall(r"\b[A-Za-z0-9_]{2,}\b", query.lower())
        terms = [t for t in raw_terms if t not in stopwords]
        if not terms:
            terms = raw_terms[:5]

        term_patterns = {t: re.compile(rf"\b{re.escape(t)}\b", re.IGNORECASE) for t in terms}

        results: List[RepoSearchResult] = []

        for fpath in self.discovered_files:
            try:
                rel_path = str(fpath.relative_to(self.repo_dir)).replace("\\", "/")
            except ValueError:
                rel_path = fpath.name

            analyzer = self.get_analyzer(fpath)
            file_score = 0.0
            matched_distinct_terms: Set[str] = set()

            # 1. Path score (e.g. 'order', 'checkout', 'cart' in file name)
            rel_lower = rel_path.lower()
            for t, pat in term_patterns.items():
                if pat.search(rel_lower):
                    file_score += 8.0
                    matched_distinct_terms.add(t)

            # 2. Symbol score (methods/functions/classes matching terms)
            matched_syms = analyzer.find_relevant_symbols(query, top_k=5)
            for sym, s_score in matched_syms:
                file_score += s_score
                for t, pat in term_patterns.items():
                    if pat.search(sym.name):
                        matched_distinct_terms.add(t)

            # 3. Content matching lines
            matched_lines: List[Tuple[int, str]] = []
            for idx, line in enumerate(analyzer.raw_lines):
                matches_in_line = [t for t, pat in term_patterns.items() if pat.search(line)]
                if matches_in_line:
                    matched_lines.append((idx + 1, line.rstrip("\r\n")))
                    file_score += 1.5 * len(matches_in_line)
                    for m in matches_in_line:
                        matched_distinct_terms.add(m)
                    # Extra weight if line contains error/exception/fail/empty indicators
                    line_lower = line.lower()
                    if any(kw in line_lower for kw in ("raise", "error", "exception", "serviceerror", "fail", "empty", "conflict")):
                        file_score += 3.0

            # 4. AST static bug findings match
            for finding in analyzer.static_findings:
                for t, pat in term_patterns.items():
                    if pat.search(finding.title) or pat.search(finding.description):
                        file_score += 5.0
                        matched_distinct_terms.add(t)

            if file_score > 0.0:
                results.append(RepoSearchResult(
                    file_path=fpath,
                    relative_path=rel_path,
                    relevance_score=file_score,
                    matched_symbols=matched_syms,
                    matched_lines=matched_lines,
                    analyzer=analyzer,
                    distinct_terms_count=len(matched_distinct_terms),
                ))

        results.sort(key=lambda r: r.relevance_score, reverse=True)
        top_results = results[:max_files]

        # Domain-specific terms (excluding generic problem/action words)
        generic_words = {
            "crash", "error", "fail", "failed", "failing", "exception", "bug", "problem",
            "issue", "broken", "why", "what", "how", "fix", "check", "code"
        }
        domain_terms = [t for t in terms if t not in generic_words]

        # Determine if evidence is insufficient:
        # - No files matched
        # - Or top file has very low score (< 5.0)
        # - Or none of the domain-specific terms matched in the repository
        # - Or query has >= 3 domain terms and fewer than 2 matched without symbol matches
        insufficient_evidence = False
        if not top_results:
            insufficient_evidence = True
        else:
            top = top_results[0]
            matched_terms_in_top = set(
                t for t, pat in term_patterns.items()
                if pat.search(top.relative_path) or
                any(pat.search(s.name) for s, _ in top.matched_symbols) or
                any(pat.search(line) for _, line in top.matched_lines)
            )
            matched_domain_terms = [dt for dt in domain_terms if dt in matched_terms_in_top]

            matched_domain_count = len(matched_domain_terms)

            if top.relevance_score < 5.0:
                insufficient_evidence = True
            elif domain_terms and matched_domain_count == 0:
                insufficient_evidence = True
            elif len(domain_terms) >= 2 and (matched_domain_count / len(domain_terms)) < 0.5:
                insufficient_evidence = True
            elif len(domain_terms) >= 3 and matched_domain_count < 2:
                insufficient_evidence = True
            elif len(terms) >= 3 and top.distinct_terms_count < 2:
                insufficient_evidence = True

        return top_results, insufficient_evidence

    def build_repo_context(
        self,
        query: str,
        search_results: List[RepoSearchResult],
        insufficient_evidence: bool = False,
        max_lines_per_file: int = 150,
    ) -> str:
        """
        Builds targeted, cross-file prompt context.
        AVOIDS SENDING THE ENTIRE REPOSITORY by extracting only relevant symbols
        and line windows from top-scoring files.
        """
        total_scanned = len(self.discovered_files)
        parts = [
            f"### REPOSITORY STRUCTURE OVERVIEW:",
            f"- Total Python files scanned: {total_scanned}",
            f"- Targeted files selected for query: {len(search_results)}",
        ]

        if insufficient_evidence or not search_results:
            parts.append(
                "\n⚠️ SEARCH RESULT: INSUFFICIENT EVIDENCE DETECTED.\n"
                "The repository search found no high-confidence matching symbols or statements for this request.\n"
                "You MUST explicitly report that there is insufficient evidence in the repository to explain or diagnose this issue, "
                "and advise the developer on what external files, endpoints, or configurations should be checked next."
            )
            return "\n".join(parts)

        parts.append("\n### EXTRACTED RELEVANT CODE ACROSS FILES (Targeted Snippets):\n")

        for res in search_results:
            parts.append(f"--- File: {res.relative_path} (Relevance Score: {res.relevance_score:.1f}) ---")
            parts.append("Key Symbols in File:")
            for s in res.analyzer.symbols[:6]:
                parts.append(f"  - {s.header_signature}")

            # Extract focused line windows around matches
            lines_to_include: Set[int] = set()
            for sym, _ in res.matched_symbols[:3]:
                sym_len = sym.end_line - sym.start_line + 1
                if sym_len <= 80:
                    lines_to_include.update(range(sym.start_line, sym.end_line + 1))
                else:
                    lines_to_include.update(range(sym.start_line, min(sym.start_line + 50, sym.end_line + 1)))

            # Add matched line windows (±5 lines around match)
            for lineno, _ in res.matched_lines[:8]:
                for l in range(max(1, lineno - 5), min(len(res.analyzer.raw_lines) + 1, lineno + 6)):
                    lines_to_include.add(l)

            # Cap total lines per file to prevent prompt explosion
            sorted_lines = sorted(lines_to_include)[:max_lines_per_file]

            if sorted_lines:
                ranges = []
                range_start = sorted_lines[0]
                prev = sorted_lines[0]
                for l in sorted_lines[1:]:
                    if l == prev + 1:
                        prev = l
                    else:
                        ranges.append((range_start, prev))
                        range_start = l
                        prev = l
                ranges.append((range_start, prev))

                for start, end in ranges:
                    snippet = res.analyzer.format_code_with_line_numbers(start, end)
                    parts.append(f"\nLines {start}-{end}:\n```python\n{snippet}\n```")
            else:
                sample = res.analyzer.format_code_with_line_numbers(1, min(40, len(res.analyzer.raw_lines)))
                parts.append(f"\nHeader Preview (Lines 1-40):\n```python\n{sample}\n```")

            parts.append("")

        return "\n".join(parts)
