"""
Unit Tests for AST Code Analyzer and Source Immutability
"""

import tempfile
import unittest
from pathlib import Path

from src.code_analyzer import CodeAnalyzer


class TestCodeAnalyzer(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_file = Path(self.temp_dir.name) / "sample_service.py"
        self.code_content = (
            "import os\n"
            "from math import sqrt\n\n"
            "class Calculator:\n"
            "    def add(self, a, b):\n"
            "        '''Add two numbers.'''\n"
            "        return a + b\n\n"
            "def calculate_total(price, quantity):\n"
            "    '''Calculate total order price.'''\n"
            "    subtotal = price * quantity\n"
            "    return subtotal\n"
        )
        self.test_file.write_text(self.code_content, encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_parses_symbols_safely(self):
        """Verifies AST extraction of classes, functions, and docstrings."""
        analyzer = CodeAnalyzer(self.test_file)
        summary = analyzer.get_file_summary()

        self.assertEqual(summary["total_lines"], 12)
        self.assertFalse(summary["has_parse_error"])
        self.assertEqual(summary["class_count"], 1)

        names = [s.name for s in analyzer.symbols]
        self.assertIn("Calculator", names)
        self.assertIn("Calculator.add", names)
        self.assertIn("calculate_total", names)

    def test_relevance_ranking(self):
        """Verifies relevant symbols are ranked higher for matching queries."""
        analyzer = CodeAnalyzer(self.test_file)
        matches = analyzer.find_relevant_symbols("calculate order total price", top_k=2)

        self.assertTrue(len(matches) > 0)
        top_sym, score = matches[0]
        self.assertEqual(top_sym.name, "calculate_total")
        self.assertGreater(score, 5.0)

    def test_source_integrity_verification(self):
        """Verifies SHA256 hash detects any modification to source file."""
        analyzer = CodeAnalyzer(self.test_file)
        self.assertTrue(analyzer.verify_integrity())

        # Modify file externally
        with open(self.test_file, "a") as f:
            f.write("# unauthorized edit\n")

        self.assertFalse(analyzer.verify_integrity())

    def test_syntax_error_handling(self):
        """Verifies graceful error capture for invalid Python syntax without crashing."""
        broken_file = Path(self.temp_dir.name) / "broken.py"
        broken_file.write_text("def invalid_syntax(:\n    pass\n", encoding="utf-8")

        analyzer = CodeAnalyzer(broken_file)
        self.assertIsNotNone(analyzer.parse_error)
        self.assertIn("SyntaxError", analyzer.parse_error)


if __name__ == "__main__":
    unittest.main()
