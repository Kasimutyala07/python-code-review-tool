# Python Code Review Tool 

A command-line and VS Code integrated code review tool that investigates Python source code using Large Language Models (LLMs) and safe Abstract Syntax Tree (AST) analysis.

---

## 🎯 Architecture & Safety Principles

1. **Non-Destructive & Safe Execution**: The tool reads source code strictly through standard text and AST inspection (`ast.parse`). It **never executes, imports, or modifies** the target file.
2. **File Integrity Guarantee**: SHA-256 digests are computed and compared before and after every review to verify that original source files remain 100% unaltered.
3. **Evidence-Based Reporting**: Findings cite exact function names, line numbers, and expressions. The output distinguishes verified code evidence from developer assumptions.
4. **Resilient Failure Handling**: API rate limits (HTTP 429), timeouts, invalid inputs, and blank requests are caught gracefully and logged to an audit ledger.
5. **Zero Overwrite Storage**: Every review produces a unique timestamped report and structured JSON audit file.

---

## 🛠️ Chosen LLM Providers & Free-Tier Selection

This tool supports both free-tier cloud LLM providers and an offline deterministic mock provider:

| Provider | Model | Free-Tier Characteristics | Best Use Case |
| :--- | :--- | :--- | :--- |
| **Google Gemini** | `gemini-1.5-flash` | Generous free tier (15 RPM / 1M tokens/min), massive 1M token context window for large codebases | Primary production review engine |
| **Groq Cloud** | `llama-3.3-70b-versatile` | Ultra-fast inference (~300 tokens/s), free tier with 30 RPM | Real-time interactive reviews |
| **Mock Provider** | `mock-reviewer-v1` | 100% offline, deterministic, zero credentials needed | CI/CD testing, offline evaluation, grading |

---

## 📋 System Requirements & Setup

- **Python Version**: Python 3.11 or newer (compatible with Python standard library)
- **Dependencies**: Standard library only (optional: `rich` for colored terminal UI, `python-dotenv` for `.env` loading)

### Setup Instructions

```bash
# 1. Clone the repository
git clone <your-repo-url>
cd code-review-tool

# 2. (Optional) Set up Python virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install optional dependencies
pip install -r requirements.txt

# 4. Configure API Keys (optional if using mock mode)
cp .env.example .env
# Edit .env and enter your GEMINI_API_KEY or GROQ_API_KEY
```

---

## 💻 Running the Tool via CLI

### Basic Syntax
```bash
python main.py -f <path-to-python-file> -r "<problem-description>"
```

### Assignment Reproduction Commands

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

#### View Cumulative Review Ledger & Usage Totals
```bash
python main.py --summary
```

#### Simulate Failure Mode (Quota Limit / Network Error)
```bash
python main.py -f review-input/order_service.py -r "Review this code" --simulate-failure quota_exceeded
```

---

## 🖥️ VS Code Presentation Guide

This project is pre-configured for VS Code presentation and live demonstration:

### 1. One-Click Tasks (`Ctrl+Shift+B` or `Cmd+Shift+B`)
- Open VS Code Command Palette (`Ctrl+Shift+P` / `Cmd+Shift+P`) → **Tasks: Run Task**.
- Select **"Review Active File in Editor"**: It reviews whatever file you currently have open in the editor.
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

The repository contains automated unit tests covering AST parsing, CLI options, provider failure modes (HTTP 429, timeout, empty response), and source file preservation:

```bash
# Run all tests and generate test_results.txt
python run_tests.py
```

All 12 unit tests pass out of the box with zero external dependencies.

---

## 📁 Repository Structure

```
├── .vscode/
│   ├── launch.json              # VS Code debug profiles
│   ├── settings.json            # Editor and test configurations
│   └── tasks.json               # One-click tasks for VS Code
├── src/
│   ├── __init__.py
│   ├── code_analyzer.py         # AST parsing, symbol ranking, integrity check
│   ├── reviewer.py              # Review orchestration and prompt formatting
│   ├── evidence.py              # Audit logging and Markdown/JSON report storage
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
│   └── test_provider_failures.py# Tests for rate limits, timeouts, and empty responses
├── review-input/
│   ├── order_service.py         # Target Python file under test
│   └── REQUESTS.md              # 3 assignment prompts
├── evidence/                    # Auto-generated review reports, JSON evidence, ledger
├── main.py                      # CLI entrypoint
├── run_tests.py                 # Automated test runner
├── test_results.txt             # Verified test execution results
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

---

## ⚠️ Known Issues & Incomplete Work

- **Live Code Pack Extraction**: The repository includes a representative test version of `order_service.py` reproducing the three test requests. When extracting the official `Week_1_Code_Pack.zip`, drop its files directly into `review-input/` to review the full 1,060-line version.
- **Provider Quota Limits**: Free-tier Gemini and Groq accounts have daily rate limits. When live quotas are exhausted, the tool automatically records the event as `BLOCKED_QUOTA` and prompts the user to switch to `--provider mock` or wait for the quota window to reset.
