"""
Google Gemini Free-Tier Provider.
Uses standard HTTP REST API to ensure no complex external SDK dependencies.
Handles quota limits (429), timeouts, and structured token counting.
"""

import json
import time
from typing import Optional
import urllib.request
import urllib.error

from .base import BaseLLMProvider, LLMResponse


class GeminiProvider(BaseLLMProvider):
    """Google Gemini API Provider (Free tier)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gemini-1.5-flash",
        timeout: int = 45,
    ):
        super().__init__(model_name=model_name, api_key=api_key, timeout=timeout)

    @property
    def provider_name(self) -> str:
        return "Google Gemini"

    def generate(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        if not self.api_key:
            return LLMResponse(
                content="",
                raw_response="",
                provider_name=self.provider_name,
                model_name=self.model_name,
                success=False,
                error_message="GEMINI_API_KEY environment variable is missing or empty.",
            )

        endpoint = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent"
            f"?key={self.api_key}"
        )

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}],
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 4096,
            },
        }

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=data_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        start_time = time.time()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                elapsed = time.time() - start_time
                status_code = resp.status
                raw_body = resp.read().decode("utf-8")
                parsed = json.loads(raw_body)

                # Extract text
                candidates = parsed.get("candidates", [])
                if not candidates:
                    return LLMResponse(
                        content="",
                        raw_response=raw_body,
                        provider_name=self.provider_name,
                        model_name=self.model_name,
                        duration_sec=elapsed,
                        success=False,
                        error_message="Provider returned 0 candidates or blocked response.",
                        status_code=status_code,
                    )

                first_candidate = candidates[0]
                finish_reason = first_candidate.get("finishReason", "UNKNOWN")
                parts = first_candidate.get("content", {}).get("parts", [])
                text_content = "".join(p.get("text", "") for p in parts)

                # Token usage metadata
                usage = parsed.get("usageMetadata", {})
                prompt_tokens = usage.get("promptTokenCount")
                completion_tokens = usage.get("candidatesTokenCount")
                total_tokens = usage.get("totalTokenCount")

                if not text_content.strip():
                    return LLMResponse(
                        content="",
                        raw_response=raw_body,
                        provider_name=self.provider_name,
                        model_name=self.model_name,
                        duration_sec=elapsed,
                        success=False,
                        error_message=f"Received empty response text from provider (finishReason: {finish_reason}).",
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
                msg = "Rate limit or free-tier quota exceeded (HTTP 429). Please wait before retrying."
            elif he.code == 400 or he.code == 403:
                msg = f"Authentication/Permission error (HTTP {he.code}). Check your GEMINI_API_KEY."

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
        except urllib.error.URLError as ue:
            elapsed = time.time() - start_time
            return LLMResponse(
                content="",
                raw_response="",
                provider_name=self.provider_name,
                model_name=self.model_name,
                duration_sec=elapsed,
                success=False,
                error_message=f"Network connection failed: {ue.reason}",
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
                error_message=f"Unexpected error calling Gemini API: {str(e)}",
            )
