"""observability.py - Lightweight, in-built LLM observability engine."""

import contextvars
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from functools import wraps
import json
import os
import time
import uuid

# Context tracking for active span hierarchy
_current_span: contextvars.ContextVar = contextvars.ContextVar(
    "_current_span", default=None
)


@dataclass
class Span:
    trace_id: str
    span_id: str
    name: str
    span_type: str  # "span", "generation", "pipeline", or "search"
    parent_id: str | None = None
    start_time: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    end_time: str | None = None
    duration_ms: float = 0.0
    status: str = "running"
    inputs: dict = field(default_factory=dict)
    outputs: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    # LLM-specific observability fields
    model: str | None = None
    model_parameters: dict | None = None
    tokens: dict | None = None  # prompt, completion, total
    cost_usd: float = 0.0
    error: str | None = None
    # Codebase search observability fields
    search_metrics: dict | None = None  # files_scanned, files_matched, top_files, query_terms


class Tracer:
    """Manages active spans, execution timing, and local persistence."""

    def __init__(self, storage_dir: str = ".reviews"):
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)
        self.log_file = os.path.join(self.storage_dir, "traces.jsonl")
        self.active_spans: list[Span] = []

    def start_span(
        self,
        name: str,
        span_type: str = "span",
        inputs: dict | None = None,
        metadata: dict | None = None,
    ) -> Span:
        parent = _current_span.get()
        trace_id = parent.trace_id if parent else str(uuid.uuid4())
        parent_id = parent.span_id if parent else None

        span = Span(
            trace_id=trace_id,
            span_id=str(uuid.uuid4())[:8],
            name=name,
            span_type=span_type,
            parent_id=parent_id,
            inputs=inputs or {},
            metadata=metadata or {},
        )
        self.active_spans.append(span)
        _current_span.set(span)
        return span

    def end_span(
        self,
        span: Span,
        outputs: dict | None = None,
        status: str = "success",
        error: str | None = None,
    ):
        span.end_time = datetime.now(timezone.utc).isoformat()
        span.status = status
        span.error = error
        if outputs:
            span.outputs = outputs

        # Calculate duration
        start = datetime.fromisoformat(span.start_time)
        end = datetime.fromisoformat(span.end_time)
        span.duration_ms = round((end - start).total_seconds() * 1000, 2)

        # Restore parent span in context
        parent = next(
            (s for s in self.active_spans if s.span_id == span.parent_id), None
        )
        _current_span.set(parent)

        # Append span to JSONL storage
        self._flush_span(span)

    def _flush_span(self, span: Span):
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(span), default=str) + "\n")

    def attach_score(self, span_id: str, score_name: str, value: float, comment: str = ""):
        """Appends evaluation scores to the trace file."""
        record = {
            "record_type": "eval_score",
            "span_id": span_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "score_name": score_name,
            "value": value,
            "comment": comment,
        }
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")


# Global tracer instance
tracer = Tracer()


# Decorators
def trace_span(name: str):
    """Decorator for synchronous non-LLM spans (AST parsing, I/O, regex)."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            span = tracer.start_span(
                name=name,
                span_type="span",
                inputs={"args": [str(a)[:100] for a in args]},
            )
            try:
                result = func(*args, **kwargs)
                out = {}
                if isinstance(result, (dict, list, int, str)):
                    try:
                        out = json.loads(json.dumps({"result": result}, default=str))
                    except Exception:
                        out = {"result": str(result)[:200]}
                tracer.end_span(span, outputs=out, status="success")
                return result
            except Exception as e:
                tracer.end_span(span, status="error", error=str(e))
                raise

        return wrapper

    return decorator


def trace_generation(name: str, model_name: str = "gemini-2.5-flash"):
    """Decorator specifically for LLM calls to capture prompts, tokens, and cost."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            span = tracer.start_span(
                name=name,
                span_type="generation",
                metadata={"model": model_name},
            )
            span.model = model_name
            try:
                # Expecting wrapped function to return: (response_text, usage_metadata)
                response_text, usage = func(*args, **kwargs)

                # Token extraction & pricing estimation (e.g. Gemini 2.5 Flash rates)
                prompt_tokens = getattr(usage, "prompt_token_count", 0) or 0
                output_tokens = getattr(usage, "candidates_token_count", 0) or 0
                total_tokens = getattr(usage, "total_token_count", 0) or (prompt_tokens + output_tokens)

                # Cost estimate: ~$0.075 / 1M prompt, $0.30 / 1M completion
                cost = (prompt_tokens * 0.000000075) + (output_tokens * 0.00000030)

                span.tokens = {
                    "prompt": prompt_tokens,
                    "completion": output_tokens,
                    "total": total_tokens,
                }
                span.cost_usd = round(cost, 6)

                tracer.end_span(
                    span,
                    outputs={"completion": response_text[:200] + "..."},
                    status="success",
                )
                return response_text
            except Exception as e:
                tracer.end_span(span, status="error", error=str(e))
                raise

        return wrapper

    return decorator
