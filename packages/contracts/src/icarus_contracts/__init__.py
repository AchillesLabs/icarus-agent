"""Domain contracts and Pydantic schemas for Icarus Agent."""

from icarus_contracts.doctor import DoctorCheckResult, DoctorReport, HealthStatus

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "DoctorCheckResult",
    "DoctorReport",
    "HealthStatus",
]
