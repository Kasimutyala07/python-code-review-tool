"""
Unit Tests for Provider Failure Handling, Empty Responses, and Evidence Logging
"""

import tempfile
import unittest
from pathlib import Path

from src.code_analyzer import CodeAnalyzer
from src.evidence import EvidenceRecorder
from src.providers.mock import MockProvider
from src.reviewer import CodeReviewEngine


class TestProviderFailuresAndEvidence(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.evidence_dir = Path(self.temp_dir.name) / "evidence"
        self.source_file = Path(self.temp_dir.name) / "test_service.py"
        self.source_file.write_text("def test(): return 42\n", encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_handles_quota_exceeded_gracefully(self):
        """Verifies HTTP 429 quota exhaustion is captured without claiming success."""
        provider = MockProvider(failure_mode="quota_exceeded")
        engine = CodeReviewEngine(provider=provider, output_dir=self.evidence_dir)
        result = engine.review(self.source_file, "Review this code for bugs")

        self.assertFalse(result["success"])
        self.assertIn("quota exceeded", result["error"].lower())
        self.assertTrue(result["report_path"].exists())

        # Check evidence was recorded as BLOCKED_QUOTA
        ledger_text = (self.evidence_dir / "evidence_ledger.jsonl").read_text()
        self.assertIn("BLOCKED_QUOTA", ledger_text)

    def test_handles_timeout_gracefully(self):
        """Verifies network timeout failure is caught and logged."""
        provider = MockProvider(failure_mode="timeout")
        engine = CodeReviewEngine(provider=provider, output_dir=self.evidence_dir)
        result = engine.review(self.source_file, "Check order totals")

        self.assertFalse(result["success"])
        self.assertIn("timed out", result["error"].lower())

    def test_handles_empty_response_gracefully(self):
        """Verifies empty response from model is rejected and not marked successful."""
        provider = MockProvider(failure_mode="empty_response")
        engine = CodeReviewEngine(provider=provider, output_dir=self.evidence_dir)
        result = engine.review(self.source_file, "Review this code")

        self.assertFalse(result["success"])
        self.assertIn("empty response", result["error"].lower())

    def test_rejects_blank_request(self):
        """Verifies empty or whitespace-only requests are rejected upfront."""
        provider = MockProvider()
        engine = CodeReviewEngine(provider=provider, output_dir=self.evidence_dir)
        result = engine.review(self.source_file, "   ")

        self.assertFalse(result["success"])
        self.assertIn("blank or empty", result["error"].lower())

    def test_source_preservation_guarantee(self):
        """Verifies that the original source code remains bit-for-bit identical before and after review."""
        initial_sha = CodeAnalyzer(self.source_file).initial_hash
        provider = MockProvider()
        engine = CodeReviewEngine(provider=provider, output_dir=self.evidence_dir)

        result = engine.review(self.source_file, "Review this code for bugs")
        self.assertTrue(result["success"])

        final_sha = CodeAnalyzer(self.source_file).initial_hash
        self.assertEqual(initial_sha, final_sha)


if __name__ == "__main__":
    unittest.main()
