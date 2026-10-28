#!/usr/bin/env python3
"""
Automated Test Runner
Discovers and executes all unit tests, printing results and saving them to test_results.txt.
"""

import sys
import unittest
from datetime import datetime
from io import StringIO
from pathlib import Path


def run_all_tests():
    project_root = Path(__file__).parent.resolve()
    tests_dir = project_root / "tests"

    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=str(tests_dir), pattern="test_*.py")

    stream = StringIO()
    runner = unittest.TextTestRunner(stream=stream, verbosity=2)

    start_time = datetime.now()
    result = runner.run(suite)
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    output_content = stream.getvalue()

    # Formatted summary
    status_str = "PASSED" if result.wasSuccessful() else "FAILED"
    report_lines = [
        "=" * 70,
        f"TEST EXECUTION RUN - {start_time.strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 70,
        f"Python Version: {sys.version.split()[0]}",
        f"Total Tests Run: {result.testsRun}",
        f"Errors: {len(result.errors)}",
        f"Failures: {len(result.failures)}",
        f"Skipped: {len(result.skipped)}",
        f"Duration: {duration:.3f}s",
        f"Overall Status: {status_str}",
        "-" * 70,
        "Detailed Output:",
        output_content,
        "=" * 70,
    ]

    final_report = "\n".join(report_lines)

    # Save to test_results.txt
    test_results_path = project_root / "test_results.txt"
    test_results_path.write_text(final_report, encoding="utf-8")

    # Also display to terminal
    print(final_report)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
