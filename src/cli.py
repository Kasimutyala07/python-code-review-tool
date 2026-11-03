"""
Command Line Interface for Python Code Review Tool.
Supports rich visual output, interactive mode, and scriptable arguments.
"""

import argparse
import os
import sys
from pathlib import Path

# Fix Windows console UTF-8 output encoding for emojis and rich characters
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Local trace viewer support
from .trace_viewer import display_trace_summary, display_trace_detail

def add_trace_subcommand(subparsers):
    trace_parser = subparsers.add_parser("traces", help="Inspect local AI observability traces.")
    trace_parser.add_argument("--limit", type=int, default=15, help="Number of recent records to display.")
    trace_parser.add_argument("--id", type=str, default=None, help="Inspect a specific trace or span ID.")

def handle_trace_command(args):
    target_id = getattr(args, "id", None) or getattr(args, "trace_id", None)
    if target_id:
        display_trace_detail(target_id)
    else:
        display_trace_summary(limit=getattr(args, "limit", 15))

# Load environment variables if .env file exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.markdown import Markdown
    HAS_RICH = True
    console = Console()
except ImportError:
    HAS_RICH = False
    console = None

from .evidence import EvidenceRecorder
from .providers import get_llm_provider
from .reviewer import CodeReviewEngine


def print_msg(msg: str, style: str = "white"):
    if HAS_RICH and console:
        console.print(msg, style=style)
    else:
        print(msg)


def print_error(msg: str):
    if HAS_RICH and console:
        console.print(f"[bold red]ERROR:[/bold red] {msg}")
    else:
        print(f"ERROR: {msg}", file=sys.stderr)


def print_success(msg: str):
    if HAS_RICH and console:
        console.print(f"[bold green]SUCCESS:[/bold green] {msg}")
    else:
        print(f"SUCCESS: {msg}")

def show_summary(output_dir: str):
    recorder = EvidenceRecorder(output_dir=output_dir)
    stats = recorder.get_cumulative_summary()

    if HAS_RICH and console:
        table = Table(title="Review Tool Cumulative Ledger Summary", border_style="cyan")
        table.add_column("Metric", style="bold yellow")
        table.add_column("Value", style="bold white")
        table.add_row("Total Review Runs", str(stats["total_runs"]))
        table.add_row("Successful Reviews", f"[green]{stats['successful_runs']}[/green]")
        table.add_row("Failed Reviews", f"[red]{stats['failed_runs']}[/red]")
        table.add_row("Total Duration (sec)", f"{stats['total_duration_sec']}s")
        table.add_row("Recorded Tokens Used", str(stats["known_tokens_total"]))
        console.print(table)
    else:
        print("\n--- Review Tool Cumulative Ledger Summary ---")
        for k, v in stats.items():
            print(f"{k}: {v}")


def interactive_mode(default_output_dir: str = "evidence"):
    print_msg("\n=== Interactive Python Code Review Tool ===", style="bold cyan")
    print_msg("Type the path to the Python file or repository directory and your question/problem description.\n")

    target_path = input("Enter path to Python file or repository directory (e.g., review-input): ").strip()
    if not target_path:
        print_error("No file or directory provided. Exiting.")
        return 2

    print("\nEnter your review request or problem description (press Enter twice to finish):")
    lines = []
    while True:
        try:
            line = input()
            if not line and lines and not lines[-1]:
                break
            lines.append(line)
        except EOFError:
            break

    request_text = "\n".join(lines).strip()
    if not request_text:
        print_error("Request text cannot be empty. Exiting.")
        return 2

    provider_choice = input("\nProvider [1=Gemini (default), 2=Groq, 3=Mock/Offline]: ").strip()
    provider_map = {"1": "gemini", "2": "groq", "3": "mock"}
    provider_name = provider_map.get(provider_choice, "gemini")

    return run_review(
        file_path=target_path,
        request_text=request_text,
        provider_name=provider_name,
        output_dir=default_output_dir,
    )


def run_review(
    file_path: str,
    request_text: str,
    provider_name: str = "mock",
    model_name: str = None,
    output_dir: str = "evidence",
    failure_mode: str = None,
) -> int:
    """Executes the review and displays results to the user."""
    provider = get_llm_provider(
        provider_type=provider_name,
        model_name=model_name,
        failure_mode=failure_mode,
    )

    target_path = Path(file_path).resolve()
    is_dir = target_path.is_dir()
    target_label = "Target Repository" if is_dir else "Target File"
    mode_label = " (Multi-file Repository Mode)" if is_dir else ""

    if HAS_RICH and console:
        console.print(Panel(
            f"[bold]{target_label}:[/bold] {file_path}{mode_label}\n"
            f"[bold]Provider:[/bold] {provider.provider_name} ({provider.model_name})\n"
            f"[bold]Output Directory:[/bold] {output_dir}\n"
            f"[bold]Request:[/bold] {request_text[:120]}...",
            title="🔍 Initiating Code Investigation",
            border_style="blue",
        ))
    else:
        print(f"\nInitiating review on {file_path}{mode_label} using {provider.provider_name}...")

    engine = CodeReviewEngine(provider=provider, output_dir=output_dir)
    result = engine.review(source_file=file_path, user_request=request_text)

    if not result["success"]:
        print_error(result["error"])
        if result.get("report_path"):
            print_msg(f"Failure audit report saved to: {result['report_path']}")
        return 1

    print_success(f"Review completed successfully in {result['duration_sec']}s!")
    if result.get("is_repo_mode"):
        scanned = result.get("files_scanned", 0)
        selected = result.get("selected_files", [])
        print_msg(f"📁 Repository Scanned: {scanned} files | Selected Candidate Files: {selected}")
        if result.get("insufficient_evidence"):
            print_msg("⚠️  Notice: Insufficient evidence detected in scanned codebase for this query.")

    print_msg(f"📄 Markdown Report saved to: [bold underline]{result['report_path']}[/bold underline]")
    print_msg(f"📊 Audit Evidence JSON saved to: {result['evidence_path']}\n")

    # Display AST static analysis findings table if present
    static_findings = result.get("static_findings", [])
    if static_findings:
        if HAS_RICH and console:
            table = Table(title="🔍 Verified Static AST Bug Pre-Scan", border_style="yellow")
            table.add_column("Severity", style="bold", width=10)
            table.add_column("Location", style="cyan", width=24)
            table.add_column("Symbol", style="white", width=24)
            table.add_column("Verified Bug & Impact", style="dim white")
            for sf in static_findings:
                sev = sf.get("severity", "INFO")
                style = "bold red" if sev == "CRITICAL" else ("bold yellow" if sev == "HIGH" else "bold blue")
                loc = f"{sf.get('file_path', '')}:{sf.get('line_number', '')}" if sf.get('file_path') else f"Line {sf.get('line_number', '')}"
                table.add_row(
                    f"[{style}]{sev}[/{style}]",
                    loc,
                    sf.get("symbol_name", ""),
                    f"[bold]{sf.get('title', '')}[/bold]\n{sf.get('description', '')}",
                )
            console.print(table)
            console.print()
        else:
            print("\n--- Verified Static AST Bug Pre-Scan ---")
            for sf in static_findings:
                loc = f"{sf.get('file_path', '')}:{sf.get('line_number', '')}" if sf.get('file_path') else f"Line {sf.get('line_number', '')}"
                print(f"[{sf.get('severity')}] {loc} in {sf.get('symbol_name')}: {sf.get('title')}")
            print()

    # Display review preview
    if HAS_RICH and console:
        console.print(Panel(
            Markdown(result["llm_response"].content),
            title="📋 Review Findings Summary",
            border_style="green",
        ))
    else:
        print("\n--- Review Findings Preview ---")
        print(result["llm_response"].content[:500] + "\n... [See report file for full text]")

    return 0


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    # Handle 'traces' positional subcommand directly if invoked as: python main.py traces ...
    if argv and argv[0] == "traces":
        trace_p = argparse.ArgumentParser(description="Inspect local AI observability traces.")
        trace_p.add_argument("command", choices=["traces"])
        trace_p.add_argument("--limit", type=int, default=15, help="Number of recent records to display.")
        trace_p.add_argument("--id", type=str, default=None, help="Inspect a specific trace or span ID.")
        t_args = trace_p.parse_args(argv)
        handle_trace_command(t_args)
        return 0

    parser = argparse.ArgumentParser(
        description="Python Code Review Tool — Investigate code bugs and anomalies across files using LLMs."
    )
    parser.add_argument(
        "-f", "--file",
        help="Path to the Python source file or repository directory to review (e.g., review-input/order_service.py)",
    )
    parser.add_argument(
        "-d", "--repo", "--dir",
        dest="repo",
        help="Path to repository or directory to investigate (multi-file repository mode)",
    )
    parser.add_argument(
        "-r", "--request",
        help="Ordinary language description of the problem, error, or 'Review this code for bugs'",
    )
    parser.add_argument(
        "--request-file",
        help="Path to a text file containing the review request",
    )
    parser.add_argument(
        "-p", "--provider",
        choices=["gemini", "groq", "mock"],
        default="mock",
        help="LLM Provider to use (default: mock for deterministic evaluation)",
    )
    parser.add_argument(
        "-m", "--model",
        help="Model name override (e.g., gemini-1.5-flash, llama-3.3-70b-versatile)",
    )
    parser.add_argument(
        "-o", "--output-dir",
        default="evidence",
        help="Directory to save review reports, evidence JSON, and ledger (default: evidence)",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Display cumulative summary of all saved reviews",
    )
    parser.add_argument(
        "--traces",
        action="store_true",
        help="Inspect local AI observability traces",
    )
    parser.add_argument(
        "--trace-id", "--id",
        dest="trace_id",
        type=str,
        default=None,
        help="Inspect a specific trace or span ID",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=15,
        help="Number of recent records to display",
    )
    parser.add_argument(
        "-i", "--interactive",
        action="store_true",
        help="Launch interactive terminal mode",
    )
    parser.add_argument(
        "--simulate-failure",
        choices=["timeout", "quota_exceeded", "server_error", "empty_response"],
        help="Simulate a provider failure mode to test error handling and audit logging",
    )

    args = parser.parse_args(argv)

    if args.traces:
        handle_trace_command(args)
        return 0

    if args.summary:
        show_summary(args.output_dir)
        return 0

    target_path = args.repo or args.file
    if args.interactive or (not target_path and not args.request and not args.request_file):
        code = interactive_mode(default_output_dir=args.output_dir)
        sys.exit(code)

    if not target_path:
        print_error("Missing required argument: --file / -f or --repo / -d")
        parser.print_help()
        sys.exit(2)

    request_text = args.request
    if args.request_file:
        rf = Path(args.request_file)
        if not rf.exists():
            print_error(f"Request file does not exist: {args.request_file}")
            sys.exit(2)
        request_text = rf.read_text(encoding="utf-8")

    if not request_text:
        print_error("Missing review request text. Provide --request '<text>' or --request-file <path>.")
        sys.exit(2)

    code = run_review(
        file_path=target_path,
        request_text=request_text,
        provider_name=args.provider,
        model_name=args.model,
        output_dir=args.output_dir,
        failure_mode=args.simulate_failure,
    )
    return code


if __name__ == "__main__":
    sys.exit(main())
