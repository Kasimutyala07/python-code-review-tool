"""
LLM Provider Factory and Client
"""

import os
from typing import Optional

from .base import BaseLLMProvider, LLMResponse
from .gemini import GeminiProvider
from .groq import GroqProvider
from .mock import MockProvider


def get_llm_provider(
    provider_type: Optional[str] = None,
    model_name: Optional[str] = None,
    api_key: Optional[str] = None,
    failure_mode: Optional[str] = None,
) -> BaseLLMProvider:
    """
    Factory function to initialize the requested LLM provider.
    Defaults to Gemini if GEMINI_API_KEY is present, or Groq if GROQ_API_KEY is present.
    If no keys or explicit mock requested, falls back safely to MockProvider.
    """
    provider_type = (provider_type or os.getenv("LLM_PROVIDER", "")).lower()

    if failure_mode:
        return MockProvider(failure_mode=failure_mode)

    if provider_type == "mock":
        return MockProvider(model_name=model_name or "mock-reviewer-v1")

    if provider_type == "groq" or (not provider_type and os.getenv("GROQ_API_KEY")):
        key = api_key or os.getenv("GROQ_API_KEY")
        model = model_name or os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        return GroqProvider(api_key=key, model_name=model)

    if provider_type == "gemini" or (not provider_type and os.getenv("GEMINI_API_KEY")):
        key = api_key or os.getenv("GEMINI_API_KEY")
        model = model_name or os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        return GeminiProvider(api_key=key, model_name=model)

    # If nothing specified or no keys available in environment, use mock provider
    return MockProvider(model_name=model_name or "mock-reviewer-v1")
