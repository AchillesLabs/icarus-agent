"""Direct aggregator provider adapter for OpenRouter with streaming and error normalization."""

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
from icarus_contracts import (
    AuthenticationError,
    CompletionResult,
    ContextLengthExceededError,
    PromptMessage,
    ProviderCapabilities,
    ProviderError,
    ProviderUnavailableError,
    RateLimitError,
    StreamChunk,
)


class OpenRouterProvider:
    """Aggregator adapter for OpenRouter providing multi-model access through a single API key."""

    DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
    DEFAULT_MODEL = "anthropic/claude-3.5-sonnet"
    DEFAULT_SITE_URL = "https://github.com/AchillesLabs/icarus-agent"
    DEFAULT_APP_NAME = "Icarus Agent"

    SUPPORTED_MODELS = [
        "anthropic/claude-3.5-sonnet",
        "openai/gpt-4o",
        "openai/gpt-4o-mini",
        "meta-llama/llama-3.1-70b-instruct",
        "google/gemini-pro-1.5",
        "mistralai/mistral-large",
    ]

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        client: httpx.AsyncClient | None = None,
        timeout: float = 60.0,
        site_url: str = DEFAULT_SITE_URL,
        app_name: str = DEFAULT_APP_NAME,
    ) -> None:
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self._client = client
        self.timeout = timeout
        self.site_url = site_url
        self.app_name = app_name

    def _get_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.site_url,
            "X-Title": self.app_name,
        }

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        return httpx.AsyncClient(
            headers=self._get_headers(),
            timeout=self.timeout,
        )

    def _format_messages(self, messages: list[PromptMessage]) -> list[dict[str, str]]:
        formatted = []
        for m in messages:
            role_str = m.role.value if hasattr(m.role, "value") else str(m.role)
            item: dict[str, str] = {"role": role_str, "content": m.content}
            if m.name:
                item["name"] = m.name
            formatted.append(item)
        return formatted

    def _handle_error_response(self, response: httpx.Response) -> None:
        try:
            body = response.json()
            message = body.get("error", {}).get("message", response.text)
        except Exception:
            message = response.text or f"HTTP status {response.status_code}"

        lowered = message.lower()
        if response.status_code in {401, 403}:
            raise AuthenticationError(
                message=f"OpenRouter authentication failed: {message}",
                provider="openrouter",
            )
        if response.status_code == 429:
            raise RateLimitError(
                message=f"OpenRouter rate limit exceeded: {message}",
                provider="openrouter",
            )
        if response.status_code == 400 and any(
            kw in lowered for kw in ["context", "length", "token", "too large", "window"]
        ):
            raise ContextLengthExceededError(
                message=f"OpenRouter context length exceeded: {message}",
                provider="openrouter",
            )
        if response.status_code in {500, 502, 503, 504}:
            raise ProviderUnavailableError(
                message=f"OpenRouter service unavailable ({response.status_code}): {message}",
                provider="openrouter",
            )
        raise ProviderError(
            message=f"OpenRouter API error ({response.status_code}): {message}",
            provider="openrouter",
        )

    async def generate(
        self,
        messages: list[PromptMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> CompletionResult:
        """Generate a complete non-streaming completion from OpenRouter."""
        target_model = model or self.DEFAULT_MODEL
        payload: dict[str, Any] = {
            "model": target_model,
            "messages": self._format_messages(messages),
            "temperature": temperature,
            "stream": False,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        url = f"{self.base_url}/chat/completions"
        client = self._get_client()

        try:
            response = await client.post(
                url,
                json=payload,
                headers=self._get_headers(),
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise ProviderUnavailableError(
                message=f"Network error connecting to OpenRouter API: {exc}",
                provider="openrouter",
                raw_error=exc,
            ) from exc

        if response.is_error:
            self._handle_error_response(response)

        data = response.json()
        choice = data["choices"][0]
        return CompletionResult(
            content=choice["message"]["content"],
            model=data.get("model", target_model),
            finish_reason=choice.get("finish_reason", "stop"),
            usage=data.get("usage"),
        )

    async def stream(
        self,
        messages: list[PromptMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Stream token deltas from OpenRouter SSE chat completions endpoint."""
        target_model = model or self.DEFAULT_MODEL
        payload: dict[str, Any] = {
            "model": target_model,
            "messages": self._format_messages(messages),
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        url = f"{self.base_url}/chat/completions"
        client = self._get_client()

        try:
            async with client.stream(
                "POST",
                url,
                json=payload,
                headers=self._get_headers(),
            ) as response:
                if response.is_error:
                    await response.aread()
                    self._handle_error_response(response)

                async for line in response.aiter_lines():
                    cleaned = line.strip()
                    if not cleaned or not cleaned.startswith("data:"):
                        continue
                    data_str = cleaned[5:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk_dict = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    choices = chunk_dict.get("choices", [])
                    if not choices:
                        continue
                    choice = choices[0]
                    delta_text = choice.get("delta", {}).get("content", "")
                    finish_reason = choice.get("finish_reason")
                    yield StreamChunk(
                        delta=delta_text,
                        finish_reason=finish_reason,
                        usage=chunk_dict.get("usage"),
                    )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise ProviderUnavailableError(
                message=f"Network error during OpenRouter token streaming: {exc}",
                provider="openrouter",
                raw_error=exc,
            ) from exc

    def get_capabilities(self, model: str | None = None) -> ProviderCapabilities:
        """Return OpenRouter capabilities and limits."""
        return ProviderCapabilities(
            supported_models=self.SUPPORTED_MODELS,
            max_context_tokens=200000,
            supports_streaming=True,
            supports_tools=True,
            supports_vision=True,
        )
