# Python Code Review Tool 

A command-line and VS Code integrated code review tool that investigates Python source code and multi-file repositories using Large Language Models (LLMs), safe Abstract Syntax Tree (AST) analysis, and built-in AI observability.

---

## 🎯 Architecture & Safety Principles

1. **Non-Destructive & Safe Execution**: The tool reads source code strictly through standard text and AST inspection (`ast.parse`). It **never executes, imports, or modifies** the target file.
2. **Cryptographic Immutability Guarantee**: SHA-256 digests are computed and compared before and after every review across single files or entire repositories to verify that original source files remain 100% unaltered.
3. **Multi-File Repository Investigation**: Automatically indexes `.py` files across a repository, ignoring build artifacts, caches, and virtual environments (`.git`, `venv`, `node_modules`).
4. **Targeted Context Pruning**: Rather than dumping entire repositories and exceeding LLM context windows, the tool ranks files using lexical and AST symbol relevance, extracting only key line windows (up to 150 lines per candidate file).
5. **Insufficient Evidence Safeguard**: If an issue stems from external systems, missing endpoints, or components not present in the scanned code, the tool explicitly flags `INSUFFICIENT EVIDENCE` instead of fabricating or hallucinating explanations.
6. **Built-in AI Observability**: Native OpenTelemetry-style tracing engine records span hierarchies (`search`, `generation`, `pipeline`), latency, token usage, cost estimation, and programmatic prompt-compliance scores to `.reviews/traces.jsonl`.
7. **Evidence-Based Reporting & Zero Overwrite Storage**: Every review produces a unique timestamped Markdown report and structured JSON audit file saved to `evidence/`. Earlier results are never overwritten.

---

## 📋 System Requirements & Setup

- **Python Version**: Python 3.11 or newer (compatible with Python standard library)
- **Dependencies**: Standard library only (optional: `rich` for colored terminal UI, `python-dotenv` for `.env` loading)

### Setup Instructions

```bash
# 1. Clone the repository
git clone https://github.com/Kasimutyala07/python-code-review-tool.git
cd python-code-review-tool

# 2. (Optional) Set up Python virtual environment
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux / macOS:
source venv/bin/activate

# 3. Install optional dependencies for rich terminal UI & .env support
pip install -r requirements.txt

# 4. Configure API Keys (optional if using mock mode)
cp .env.example .env
# Edit .env and enter your GEMINI_API_KEY or GROQ_API_KEY
```

---

## 💻 Running the Tool via CLI

### 1. Single-File Mode
Review a specific Python file:
```bash
python main.py -f <path-to-file.py> -r "<problem-description>"
```

### 2. Multi-File Repository Mode
Investigate an entire repository or folder:
```bash
python main.py -d <path-to-repo> -r "<problem-description>"
```

### 3. Interactive Mode
Launch an interactive prompt for guided file/directory and question entry:
```bash
python main.py -i
```

---

### Core Assignment Reproduction Commands

#### Request 1: Order Total Discrepancy
```bash
python main.py \
  -f review-input/order_service.py \
  -r "I ordered three MUGs at $10 each using pickup, no coupon. The subtotal is $10 and total is $11. I expected $30 before tax. Can you check what is happening?" \
  -p mock
```

#### Request 2: Cancelled Order in Sales Report
```bash
python main.py \
  -f review-input/order_service.py \
  -r "I placed an order, cancelled it, then ran the sales report for that day. It still shows one order and the original sales amount. Please investigate." \
  -p mock
```

#### Request 3: General Code Review & Safety Audit
```bash
python main.py \
  -f review-input/order_service.py \
  -r "Review this code for bugs. Focus on mistakes that could change totals or stock. Explain the most important findings and what I should check next." \
  -p mock
```

---

### 📊 Observability & Audit Commands

#### Inspect Observability Traces
View latency, token consumption, cost estimates, and prompt compliance scores:
```bash
# Display summary table of recent traces
python main.py --traces

# Deep dive into a specific trace or span
python main.py --id <trace_or_span_id>
```

#### View Cumulative Review Ledger
```bash
python main.py --summary
```

#### Simulate Provider Failure Modes (Rate Limits & Network Errors)
Test graceful handling without claiming success:
```bash
# Quota limit (HTTP 429)
python main.py -f review-input/order_service.py -r "Review code" --simulate-failure quota_exceeded

# Timeout
python main.py -f review-input/order_service.py -r "Review code" --simulate-failure timeout
```

---

## 🖥️ VS Code Presentation Guide

This project is pre-configured for VS Code presentation and live demonstration:

### 1. One-Click Tasks (`Ctrl+Shift+B` or `Cmd+Shift+B`)
- Open VS Code Command Palette (`Ctrl+Shift+P` / `Cmd+Shift+P`) → **Tasks: Run Task**.
- Select **"Review Active File in Editor"**: Reviews whatever file you currently have open in the editor.
- Select **"Run All Automated Tests"**: Executes the test suite with a live progress report.
- Select **"Run Assignment Request 1 / 2 / 3"** to instantly demo the three core cases.

### 2. Interactive Debugger (`F5`)
- Press `F5` or navigate to the **Run & Debug** panel (`Ctrl+Shift+D`).
- Choose from preset launch profiles:
  - `▶ Run Review Tool (Interactive)`
  - `▶ Case 1: Order Total Issue`
  - `▶ Case 2: Cancelled Order Issue`
  - `▶ Case 3: General Code Review`
  - `▶ Test Simulated Failure (Quota 429)`
  - `▶ Run Automated Test Suite`

### 3. Split-Screen Review Presentation
- When a review finishes, open the generated report in `evidence/<timestamp>_report.md`.
- Press `Ctrl+K V` (or `Cmd+K V`) to open **Markdown: Open Preview to the Side**.
- Arrange VS Code side-by-side: Source code on the left, generated review report on the right!

---

## 🧪 Automated Testing Suite

The repository contains 21 comprehensive automated unit and integration tests across 4 test suites:
- **`tests/test_analyzer.py`**: AST symbol parsing, docstring extraction, syntax error resilience, and SHA-256 integrity checks.
- **`tests/test_cli.py`**: CLI flag parsing, missing argument handling, and end-to-end execution.
- **`tests/test_provider_failures.py`**: HTTP 429 quota exhaustion, timeouts, empty responses, blank query rejection, and bit-for-bit file preservation.
- **`tests/test_repo_investigation.py`**: Multi-file repository search, relevance scoring, context window pruning, insufficient evidence flagging, and repository-wide tampering detection.

```bash
# Run all 21 tests and update test_results.txt
python run_tests.py
```

All 21 tests pass out of the box with zero external dependencies.

---

## 📁 Repository Structure

```
├── .vscode/
│   ├── launch.json              # VS Code debug profiles
│   ├── settings.json            # Editor and test configurations
│   └── tasks.json               # One-click tasks for VS Code
├── src/
│   ├── __init__.py
│   ├── code_analyzer.py         # AST parsing, symbol ranking, multi-file repo search
│   ├── reviewer.py              # Review orchestrator and prompt synthesis
│   ├── evidence.py              # Audit logging, ledger tracking, and Markdown/JSON storage
│   ├── trace_viewer.py          # Local CLI inspector for recorded observability traces
│   ├── cli.py                   # CLI parser and rich terminal interface
│   └── providers/
│       ├── __init__.py          # Provider factory
│       ├── base.py              # Base LLM class and response data model
│       ├── gemini.py            # Google Gemini free-tier REST client
│       ├── groq.py              # Groq Llama free-tier client
│       └── mock.py              # Deterministic offline provider for tests/demos
├── tests/
│   ├── test_analyzer.py         # Tests for AST analysis and file hashing
│   ├── test_cli.py              # Tests for CLI execution and exit codes
│   ├── test_provider_failures.py# Tests for rate limits, timeouts, and empty responses
│   └── test_repo_investigation.py# Tests for multi-file search, pruning, and observability
├── review-input/
│   ├── order_service.py         # Target Python file under test
│   └── REQUESTS.md              # 3 assignment prompts
├── evidence/                    # Auto-generated review reports, JSON evidence, ledger
├── observability.py             # OpenTelemetry-style span, token, and latency tracing engine
├── main.py                      # CLI root entrypoint
├── run_tests.py                 # Automated test runner
├── test_results.txt             # Verified test execution results (21/21 passing)
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

---
