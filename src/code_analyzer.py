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
        except SyntaxError as se:
            self.parse_error = f"SyntaxError at line {se.lineno}: {se.msg}"
        except Exception as e:
            self.parse_error = f"AST parse error: {e}"

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

    def extract_context_for_request(self, request_text: str, max_full_lines: int = 350) -> str:
        """
        Builds the code context for the LLM prompt.
        If file is within max_full_lines, supplies the complete source with line numbers.
        Also attaches an architectural symbol index for fast navigation.
        """
        total_lines = len(self.raw_lines)
        outline_parts = ["### FILE STRUCTURAL OUTLINE:"]
        for s in self.symbols:
            outline_parts.append(f"- {s.header_signature}")
        outline_text = "\n".join(outline_parts)

        if total_lines <= max_full_lines:
            code_block = self.format_code_with_line_numbers(1, total_lines)
            return (
                f"{outline_text}\n\n"
                f"### COMPLETE SOURCE CODE ({total_lines} lines):\n"
                f"```python\n{code_block}\n```"
            )

        # For very large files exceeding context limits:
        relevant = self.find_relevant_symbols(request_text, top_k=6)
        extracted_sections = []
        for sym, score in relevant:
            section_code = self.format_code_with_line_numbers(sym.start_line, sym.end_line)
            extracted_sections.append(
                f"#### Symbol: {sym.name} (Lines {sym.start_line}-{sym.end_line}, Match Score: {score:.1f})\n"
                f"```python\n{section_code}\n```"
            )

        return (
            f"{outline_text}\n\n"
            f"### RELEVANT CODE SECTIONS (Extracted for query):\n\n" +
            "\n\n".join(extracted_sections)
        )
