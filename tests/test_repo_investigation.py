"""
Unit Tests for Repository-Level Code Investigation, Pruning, Observability & Read-Only Safety.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.code_analyzer import CodeAnalyzer, RepoAnalyzer
from src.providers.mock import MockProvider
from src.reviewer import CodeReviewEngine


class TestRepoInvestigation(unittest.TestCase):

    def setUp(self):
        self.project_root = Path(__file__).parent.parent.resolve()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_dir = Path(self.temp_dir.name) / "test_repo"
        self.repo_dir.mkdir(parents=True, exist_ok=True)
        self.evidence_dir = Path(self.temp_dir.name) / "evidence"

        # Setup sample multi-file repository structure
        (self.repo_dir / "subdir").mkdir(parents=True, exist_ok=True)
        (self.repo_dir / ".git").mkdir(parents=True, exist_ok=True)
        (self.repo_dir / "venv").mkdir(parents=True, exist_ok=True)
        (self.repo_dir / "__pycache__").mkdir(parents=True, exist_ok=True)

        # Python files in repo
        self.checkout_file = self.repo_dir / "checkout.py"
        self.checkout_file.write_text(
            "class CheckoutManager:\n"
            "    def process_checkout(self, cart):\n"
            "        if not cart.items:\n"
            "            raise ValueError('Cart cannot be empty during checkout')\n"
            "        return True\n",
            encoding="utf-8"
        )

        self.inventory_file = self.repo_dir / "subdir" / "inventory.py"
        self.inventory_file.write_text(
            "class InventoryTracker:\n"
            "    def check_stock(self, sku):\n"
            "        return 100\n",
            encoding="utf-8"
        )

        # Files that should be excluded
        (self.repo_dir / ".git" / "git_internal.py").write_text("x = 1\n", encoding="utf-8")
        (self.repo_dir / "venv" / "pip_internal.py").write_text("x = 1\n", encoding="utf-8")
        (self.repo_dir / "notes.txt").write_text("plain text file\n", encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_repo_file_discovery_and_exclusion(self):
        """Verifies only relevant .py files are indexed, ignoring .git, venv, and non-py files."""
        analyzer = RepoAnalyzer(self.repo_dir)
        discovered_rel = [str(f.relative_to(self.repo_dir)).replace("\\", "/") for f in analyzer.discovered_files]

        self.assertIn("checkout.py", discovered_rel)
        self.assertIn("subdir/inventory.py", discovered_rel)
        self.assertEqual(len(discovered_rel), 2)
        self.assertNotIn(".git/git_internal.py", discovered_rel)
        self.assertNotIn("venv/pip_internal.py", discovered_rel)
        self.assertNotIn("notes.txt", discovered_rel)

    def test_repo_immutability_and_tampering_detection(self):
        """Verifies read-only cryptographic SHA256 integrity detection across the repository."""
        analyzer = RepoAnalyzer(self.repo_dir)
        initial_hash = analyzer.get_repo_hash()
        self.assertTrue(analyzer.verify_repo_integrity())

        # Simulate tampering / modifying a file during review
        with open(self.checkout_file, "a", encoding="utf-8") as f:
            f.write("# unauthorized edit\n")

        self.assertFalse(analyzer.verify_repo_integrity())
        new_hash = analyzer.get_repo_hash()
        self.assertNotEqual(initial_hash, new_hash)

    def test_tampering_halts_review_with_error(self):
        """Verifies CodeReviewEngine detects file modifications and aborts without recording successful artifacts."""
        provider = MockProvider()
        engine = CodeReviewEngine(provider=provider, output_dir=self.evidence_dir)

        # Tamper by hooking into provider generate
        original_generate = provider.generate
        def malicious_generate(*args, **kwargs):
            with open(self.checkout_file, "a", encoding="utf-8") as f:
                f.write("# unauthorized modification inside pipeline\n")
            return original_generate(*args, **kwargs)
        provider.generate = malicious_generate

        result = engine.review(self.repo_dir, "Why does checkout fail when the cart is empty?")
        self.assertFalse(result["success"])
        self.assertIn("Repository files were modified", result["error"])

    def test_relevance_search_and_ranking(self):
        """Verifies relevance scoring ranks checkout.py first for checkout-related queries."""
        analyzer = RepoAnalyzer(self.repo_dir)
        results, insufficient = analyzer.search_codebase("Why does checkout fail when the cart is empty?")

        self.assertFalse(insufficient)
        self.assertTrue(len(results) > 0)
        top_match = results[0]
        self.assertEqual(top_match.relative_path, "checkout.py")
        self.assertGreater(top_match.relevance_score, 0)

    def test_insufficient_evidence_flagged(self):
        """Verifies queries about concepts missing from the repo trigger insufficient_evidence=True."""
        analyzer = RepoAnalyzer(self.repo_dir)
        results, insufficient = analyzer.search_codebase("Why does Kubernetes ingress crash on webhook timeout?")

        self.assertTrue(insufficient)

    def test_avoid_sending_entire_repo(self):
        """Verifies build_repo_context extracts targeted snippets and does NOT send full source code."""
        # Create a large source file
        large_code = "\n".join([f"# padding line {i}" for i in range(500)])
        large_code += "\n\ndef checkout_cart(cart):\n    if len(cart) == 0:\n        return False\n    return True\n"
        large_code += "\n".join([f"# trailing line {i}" for i in range(500)])

        large_file = self.repo_dir / "large_service.py"
        large_file.write_text(large_code, encoding="utf-8")

        analyzer = RepoAnalyzer(self.repo_dir)
        results, insufficient = analyzer.search_codebase("Why does checkout_cart fail on empty cart?")
        context = analyzer.build_repo_context("Why does checkout_cart fail on empty cart?", results, insufficient)

        # Verify context is dramatically smaller than entire file
        self.assertLess(len(context), len(large_code) // 2)
        self.assertIn("checkout_cart", context)
        self.assertIn("Lines", context)

    def test_repo_observability_traces(self):
        """Verifies multi-file investigation captures file_search spans, model calls, token usage, and errors."""
        traces_file = Path(".reviews") / "traces.jsonl"
        traces_count_before = 0
        if traces_file.exists():
            traces_count_before = len(traces_file.read_text(encoding="utf-8", errors="replace").splitlines())

        provider = MockProvider()
        engine = CodeReviewEngine(provider=provider, output_dir=self.evidence_dir)
        result = engine.review(self.repo_dir, "Why does checkout fail when the cart is empty?")

        self.assertTrue(result["success"])
        self.assertTrue(result["is_repo_mode"])
        self.assertEqual(result["files_scanned"], 2)

        # Verify traces were logged
        self.assertTrue(traces_file.exists())
        lines = [line.strip() for line in traces_file.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
        self.assertGreater(len(lines), traces_count_before)

        # Parse recent spans
        recent_records = [json.loads(line) for line in lines[traces_count_before:]]
        search_spans = [r for r in recent_records if r.get("name") == "repo_file_search"]
        gen_spans = [r for r in recent_records if r.get("name") == "llm_code_review"]
        pipeline_spans = [r for r in recent_records if r.get("name") == "repo_review_pipeline"]

        self.assertTrue(len(search_spans) >= 1)
        self.assertEqual(search_spans[0].get("span_type"), "search")
        metrics = search_spans[0].get("search_metrics") or search_spans[0].get("outputs", {})
        self.assertEqual(metrics.get("files_scanned"), 2)

        self.assertTrue(len(gen_spans) >= 1)
        self.assertGreater(gen_spans[0].get("tokens", {}).get("total", 0), 0)

        self.assertTrue(len(pipeline_spans) >= 1)

    def test_cli_repo_checkout_investigation(self):
        """Verifies end-to-end CLI execution on review-input repository with checkout request."""
        cmd = [
            sys.executable, "main.py",
            "-d", "review-input",
            "-r", "Why does checkout fail when the cart is empty?",
            "-p", "mock"
        ]
        res = subprocess.run(
            cmd,
            cwd=str(self.project_root),
            capture_output=True,
            text=True,
            errors="replace"
        )
        self.assertEqual(res.returncode, 0)
        output = res.stdout
        self.assertIn("Target Repository: review-input (Multi-file Repository Mode)", output)
        self.assertIn("order_service.py", output)
        self.assertIn("CheckoutRequest.from_dict", output)
        self.assertIn("ServiceError", output)
        self.assertIn("191", output)

    def test_cli_insufficient_evidence_query(self):
        """Verifies CLI execution with an irrelevant query displays insufficient evidence notification."""
        cmd = [
            sys.executable, "main.py",
            "-d", "review-input",
            "-r", "Why does Kubernetes ingress crash on webhook timeout?",
            "-p", "mock"
        ]
        res = subprocess.run(
            cmd,
            cwd=str(self.project_root),
            capture_output=True,
            text=True,
            errors="replace"
        )
        self.assertEqual(res.returncode, 0)
        output = res.stdout
        self.assertTrue("insufficient evidence" in output.lower())


if __name__ == "__main__":
    unittest.main()
