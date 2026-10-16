"""Doctor diagnostic models and health status types."""

from enum import StrEnum

from pydantic import BaseModel, Field


class HealthStatus(StrEnum):
    """Health check outcome status."""

    OK = "ok"
    WARNING = "warning"
    FAIL = "fail"


class DoctorCheckResult(BaseModel):
    """Result of a single diagnostic check."""

    name: str
    status: HealthStatus
    message: str
    details: str | None = None
    fix_hint: str | None = None


class DoctorReport(BaseModel):
    """Aggregated health report across all diagnostic checks."""

    checks: list[DoctorCheckResult] = Field(default_factory=list)

    @property
    def is_healthy(self) -> bool:
        """Return True if no check has failed."""
        return all(check.status != HealthStatus.FAIL for check in self.checks)
