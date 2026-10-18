"""Domain contracts and Pydantic schemas for Icarus Agent."""

from icarus_contracts.config import CredentialResult, CredentialSource, IcarusConfig
from icarus_contracts.doctor import DoctorCheckResult, DoctorReport, HealthStatus
from icarus_contracts.exceptions import (
    AuthenticationError,
    ContextLengthExceededError,
    ProviderError,
    ProviderUnavailableError,
    RateLimitError,
    WorkspaceJailError,
)
from icarus_contracts.provider import (
    CompletionResult,
    DiscoveredModel,
    PromptMessage,
    ProviderCapabilities,
    StreamChunk,
)
from icarus_contracts.session import (
    MessageCreate,
    MessageDTO,
    MessageRole,
    RunCreate,
    RunDTO,
    RunStatus,
    SessionCreate,
    SessionDTO,
    SessionUpdate,
)
from icarus_contracts.tokens import TokenUsage
from icarus_contracts.tools import (
    ToolCall,
    ToolDefinition,
    ToolResult,
    ToolSafetyCategory,
)

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "AuthenticationError",
    "CompletionResult",
    "ContextLengthExceededError",
    "CredentialResult",
    "CredentialSource",
    "DiscoveredModel",
    "DoctorCheckResult",
    "DoctorReport",
    "HealthStatus",
    "IcarusConfig",
    "MessageCreate",
    "MessageDTO",
    "MessageRole",
    "PromptMessage",
    "ProviderCapabilities",
    "ProviderError",
    "ProviderUnavailableError",
    "RateLimitError",
    "RunCreate",
    "RunDTO",
    "RunStatus",
    "SessionCreate",
    "SessionDTO",
    "SessionUpdate",
    "StreamChunk",
    "ToolCall",
    "ToolDefinition",
    "ToolResult",
    "ToolSafetyCategory",
    "TokenUsage",
    "WorkspaceJailError",
]
