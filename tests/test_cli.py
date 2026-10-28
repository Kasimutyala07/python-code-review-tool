"""
Unit Tests for Command Line Interface Execution
"""

import os
import subprocess
import sys
import unittest
from pathlib import Path


class TestCLIExecution(unittest.TestCase):

    def setUp(self):
        self.project_root = Path(__file__).parent.parent.resolve()
        self.env = os.environ.copy()
        self.env["PYTHONIOENCODING"] = "utf-8"

    def test_cli_missing_file_fails(self):
        """Verifies CLI exits with code 2 when required --file argument is missing."""
        cmd = [sys.executable, "main.py", "--request", "Check code"]
        res = subprocess.run(
            cmd,
            cwd=str(self.project_root),
            env=self.env,
            capture_output=True,
            text=True,
            errors="replace"
        )
        self.assertEqual(res.returncode, 2)
        self.assertIn("Missing required argument", res.stderr + res.stdout)

    def test_cli_help_flag(self):
        """Verifies CLI help flag displays options."""
        cmd = [sys.executable, "main.py", "--help"]
        res = subprocess.run(
            cmd,
            cwd=str(self.project_root),
            env=self.env,
            capture_output=True,
            text=True,
            errors="replace"
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("Python Code Review Tool", res.stdout)
        self.assertIn("--file", res.stdout)

    def test_cli_successful_mock_review(self):
        """Verifies CLI runs end-to-end with mock provider and generates reports."""
        target = str(self.project_root / "review-input" / "order_service.py")
        cmd = [
            sys.executable, "main.py",
            "-f", target,
            "-r", "I ordered three MUGs at $10 each. The subtotal is $10.",
            "-p", "mock"
        ]
        res = subprocess.run(
            cmd,
            cwd=str(self.project_root),
            env=self.env,
            capture_output=True,
            text=True,
            errors="replace"
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("Review completed successfully", res.stdout)


if __name__ == "__main__":
    unittest.main()