"""Direct BYOK provider adapter for Grok (xAI) using REST and SSE streaming."""

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


class GrokProvider:
    """Direct adapter for Grok / xAI models.

    Supports completions, SSE streaming, and error normalization.
    """

    DEFAULT_BASE_URL = "https://api.x.ai/v1"
    SUPPORTED_MODELS = ["grok-2", "grok-2-latest", "grok-beta", "grok-vision-beta"]

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        client: httpx.AsyncClient | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self._client = client
        self.timeout = timeout

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        return httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
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
                message=f"Grok authentication failed: {message}",
                provider="grok",
            )
        if response.status_code == 429:
            raise RateLimitError(
                message=f"Grok rate limit exceeded: {message}",
                provider="grok",
            )
        if response.status_code == 400 and any(
            kw in lowered for kw in ["context", "length", "token", "too large"]
        ):
            raise ContextLengthExceededError(
                message=f"Grok context length exceeded: {message}",
                provider="grok",
            )
        if response.status_code in {500, 502, 503, 504}:
            raise ProviderUnavailableError(
                message=f"Grok service unavailable ({response.status_code}): {message}",
                provider="grok",
            )
        raise ProviderError(
            message=f"Grok API error ({response.status_code}): {message}",
            provider="grok",
        )

    async def generate(
        self,
        messages: list[PromptMessage],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> CompletionResult:
        """Generate a complete response using xAI chat completions endpoint."""
        target_model = model or "grok-2"
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
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise ProviderUnavailableError(
                message=f"Network error connecting to Grok API: {exc}",
                provider="grok",
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
        """Stream token deltas from xAI SSE chat completions endpoint."""
        target_model = model or "grok-2"
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
                headers={"Authorization": f"Bearer {self.api_key}"},
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
                message=f"Network error during Grok token streaming: {exc}",
                provider="grok",
                raw_error=exc,
            ) from exc

    def get_capabilities(self, model: str | None = None) -> ProviderCapabilities:
        """Return Grok model capabilities and token boundaries."""
        return ProviderCapabilities(
            supported_models=self.SUPPORTED_MODELS,
            max_context_tokens=131072,
            supports_streaming=True,
            supports_tools=True,
            supports_vision=True,
        )
