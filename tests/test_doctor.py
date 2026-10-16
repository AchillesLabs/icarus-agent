"""Tests for Doctor diagnostics models and checks."""

from pathlib import Path
from unittest.mock import patch

from icarus_contracts.doctor import DoctorCheckResult, DoctorReport, HealthStatus
from icarus_core.doctor import (
    check_python_version,
    check_storage_directories,
    check_workspace_integrity,
    run_doctor_checks,
)


def test_doctor_report_is_healthy_when_all_pass():
    report = DoctorReport(
        checks=[
            DoctorCheckResult(name="Python", status=HealthStatus.OK, message="v3.12+"),
            DoctorCheckResult(name="Dir", status=HealthStatus.WARNING, message="Warning"),
        ]
    )
    assert report.is_healthy is True


def test_doctor_report_is_unhealthy_when_any_fail():
    report = DoctorReport(
        checks=[
            DoctorCheckResult(name="Python", status=HealthStatus.OK, message="v3.12+"),
            DoctorCheckResult(name="Dir", status=HealthStatus.FAIL, message="Error writing"),
        ]
    )
    assert report.is_healthy is False


def test_check_python_version_passes_on_current_python():
    result = check_python_version()
    assert result.status == HealthStatus.OK
    assert "compatible" in result.message.lower()


def test_check_python_version_fails_below_312():
    with patch("sys.version_info", (3, 11, 0, "final", 0)), patch("sys.version", "3.11.0"):
        result = check_python_version()
        assert result.status == HealthStatus.FAIL
        assert "incompatible" in result.message.lower()
        assert result.fix_hint is not None


def test_check_storage_directories_creates_logs_dir(tmp_path: Path):
    target_home = tmp_path / "custom_icarus"
    result = check_storage_directories(home_dir=target_home)
    assert result.status == HealthStatus.OK
    assert target_home.exists()
    assert (target_home / "logs").exists()


def test_check_workspace_integrity():
    result = check_workspace_integrity()
    assert result.status == HealthStatus.OK
    assert "workspace packages loaded" in result.message.lower()


def test_run_doctor_checks_returns_report(tmp_path: Path):
    report = run_doctor_checks(home_dir=tmp_path)
    assert isinstance(report, DoctorReport)
    assert len(report.checks) >= 3
    assert report.is_healthy is True
