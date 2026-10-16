"""Domain contracts and Pydantic schemas for Icarus Agent."""

from icarus_contracts.doctor import DoctorCheckResult, DoctorReport, HealthStatus
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

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "DoctorCheckResult",
    "DoctorReport",
    "HealthStatus",
    "MessageCreate",
    "MessageDTO",
    "MessageRole",
    "RunCreate",
    "RunDTO",
    "RunStatus",
    "SessionCreate",
    "SessionDTO",
    "SessionUpdate",
]
