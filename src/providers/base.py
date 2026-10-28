"""
Base LLM Provider Interface and Response Data Model.
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class LLMResponse:
    """Standardized response from an LLM call."""
    content: str
    raw_response: str
    provider_name: str
    model_name: str
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    duration_sec: float = 0.0
    success: bool = True
    error_message: Optional[str] = None
    status_code: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider_name,
            "model": self.model_name,
            "success": self.success,
            "duration_sec": round(self.duration_sec, 3),
            "tokens": {
                "prompt": self.prompt_tokens if self.prompt_tokens is not None else "unknown",
                "completion": self.completion_tokens if self.completion_tokens is not None else "unknown",
                "total": self.total_tokens if self.total_tokens is not None else "unknown",
            },
            "error": self.error_message,
        }


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, model_name: str, api_key: Optional[str] = None, timeout: int = 45):
        self.model_name = model_name
        self.api_key = api_key
        self.timeout = timeout

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the provider service."""
        pass

    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        """Execute review prompt against LLM API."""
        pass
