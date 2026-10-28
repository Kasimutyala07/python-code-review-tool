"""
Groq Cloud Free-Tier Provider.
Uses ultra-fast Llama-3.3-70b-versatile or Llama-3.1-8b-instant models.
"""

import json
import time
from typing import Optional
import urllib.request
import urllib.error

from .base import BaseLLMProvider, LLMResponse


class GroqProvider(BaseLLMProvider):
    """Groq API Provider (Free tier)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "llama-3.3-70b-versatile",
        timeout: int = 45,
    ):
        super().__init__(model_name=model_name, api_key=api_key, timeout=timeout)

    @property
    def provider_name(self) -> str:
        return "Groq"

    def generate(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        if not self.api_key:
            return LLMResponse(
                content="",
                raw_response="",
                provider_name=self.provider_name,
                model_name=self.model_name,
                success=False,
                error_message="GROQ_API_KEY environment variable is missing or empty.",
            )

        endpoint = "https://api.groq.com/openai/v1/chat/completions"
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "max_tokens": 4096,
        }

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=data_bytes,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            },
            method="POST",
        )

        start_time = time.time()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                elapsed = time.time() - start_time
                status_code = resp.status
                raw_body = resp.read().decode("utf-8")
                parsed = json.loads(raw_body)

                choices = parsed.get("choices", [])
                if not choices:
                    return LLMResponse(
                        content="",
                        raw_response=raw_body,
                        provider_name=self.provider_name,
                        model_name=self.model_name,
                        duration_sec=elapsed,
                        success=False,
                        error_message="Provider returned 0 choices.",
                        status_code=status_code,
                    )

                text_content = choices[0].get("message", {}).get("content", "")
                usage = parsed.get("usage", {})
                prompt_tokens = usage.get("prompt_tokens")
                completion_tokens = usage.get("completion_tokens")
                total_tokens = usage.get("total_tokens")

                if not text_content.strip():
                    return LLMResponse(
                        content="",
                        raw_response=raw_body,
                        provider_name=self.provider_name,
                        model_name=self.model_name,
                        duration_sec=elapsed,
                        success=False,
                        error_message="Received empty text response from Groq.",
                        status_code=status_code,
                    )

                return LLMResponse(
                    content=text_content,
                    raw_response=raw_body,
                    provider_name=self.provider_name,
                    model_name=self.model_name,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    duration_sec=elapsed,
                    success=True,
                    status_code=status_code,
                )

        except urllib.error.HTTPError as he:
            elapsed = time.time() - start_time
            error_body = he.read().decode("utf-8", errors="replace")
            msg = f"HTTP {he.code}: {he.reason}"
            if he.code == 429:
                msg = "Rate limit or free-tier quota exceeded on Groq (HTTP 429)."
            elif he.code in (401, 403):
                msg = f"Invalid or unauthorized GROQ_API_KEY (HTTP {he.code})."

            return LLMResponse(
                content="",
                raw_response=error_body,
                provider_name=self.provider_name,
                model_name=self.model_name,
                duration_sec=elapsed,
                success=False,
                error_message=f"{msg} Raw: {error_body[:200]}",
                status_code=he.code,
            )
        except Exception as e:
            elapsed = time.time() - start_time
            return LLMResponse(
                content="",
                raw_response="",
                provider_name=self.provider_name,
                model_name=self.model_name,
                duration_sec=elapsed,
                success=False,
                error_message=f"Groq API error: {str(e)}",
            )
