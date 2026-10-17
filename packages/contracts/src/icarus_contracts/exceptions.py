"""Domain exception hierarchy for LLM providers."""


class ProviderError(Exception):
    """Base exception for all model provider failures."""

    def __init__(
        self, message: str, provider: str | None = None, raw_error: Exception | None = None
    ) -> None:
        self.provider = provider
        self.raw_error = raw_error
        super().__init__(message)


class AuthenticationError(ProviderError):
    """Raised when provider credentials are rejected or invalid (e.g. HTTP 401/403)."""


class RateLimitError(ProviderError):
    """Raised when provider rate limits or quotas are exceeded (e.g. HTTP 429)."""


class ContextLengthExceededError(ProviderError):
    """Raised when prompt and generation exceed model context limits."""


class ProviderUnavailableError(ProviderError):
    """Raised when network disconnects, times out, or upstream service is down (5xx)."""


class WorkspaceJailError(PermissionError):
    """Raised when a file or directory operation attempts to escape the jailed workspace root."""
