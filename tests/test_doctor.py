"""Tests for Doctor diagnostics models and checks."""

from pathlib import Path
from unittest.mock import patch

from icarus_contracts.doctor import DoctorCheckResult, DoctorReport, HealthStatus
from icarus_core.doctor import (
    check_credentials,
    check_database_connectivity,
    check_python_version,
    check_storage_directories,
    check_workspace_integrity,
    run_doctor_checks,
)
from icarus_core.persistence.database import DatabaseManager
from icarus_core.persistence.migrations.runner import MigrationRunner


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


def test_check_database_connectivity_passes_when_migrated(tmp_path: Path):
    db_file = tmp_path / "doctor_test.db"
    db_url = f"sqlite:///{db_file.as_posix()}"
    manager = DatabaseManager(db_url=db_url)
    runner = MigrationRunner()
    runner.run_migrations(db_manager=manager)

    result = check_database_connectivity(db_manager=manager)
    assert result.status == HealthStatus.OK
    assert "head" in result.message.lower()
    assert "sessions" in result.details.lower()


def test_check_database_connectivity_fails_when_unmigrated(tmp_path: Path):
    db_file = tmp_path / "unmigrated.db"
    db_url = f"sqlite:///{db_file.as_posix()}"
    manager = DatabaseManager(db_url=db_url)

    result = check_database_connectivity(db_manager=manager)
    assert result.status == HealthStatus.FAIL
    assert "migration" in result.message.lower() or "table" in result.message.lower()
    assert result.fix_hint is not None


def test_check_credentials_passes_with_masked_key():
    from unittest.mock import MagicMock

    from icarus_contracts import CredentialResult, CredentialSource, IcarusConfig

    mock_resolver = MagicMock()
    mock_resolver.resolve.return_value = CredentialResult(
        provider="grok",
        secret="xai-plaintext-secret-1234",
        source=CredentialSource.KEYRING,
        masked="xai-...1234",
    )
    config = IcarusConfig(default_provider="grok")

    result = check_credentials(resolver=mock_resolver, config=config)
    assert result.status == HealthStatus.OK
    assert "xai-...1234" in result.details
    assert "plaintext" not in result.details
    assert "grok" in result.message


def test_check_credentials_warns_when_missing():
    from unittest.mock import MagicMock

    from icarus_contracts import CredentialResult, CredentialSource, IcarusConfig

    mock_resolver = MagicMock()
    mock_resolver.resolve.return_value = CredentialResult(
        provider="grok",
        secret=None,
        source=CredentialSource.NONE,
        masked=None,
    )
    config = IcarusConfig(default_provider="grok")

    result = check_credentials(resolver=mock_resolver, config=config)
    assert result.status == HealthStatus.WARNING
    assert "no credential found" in result.message.lower()
    assert result.fix_hint is not None
    assert "icarus init" in result.fix_hint.lower()


def test_run_doctor_checks_returns_report(tmp_path: Path):
    # Ensure home has migrated db
    db_file = tmp_path / "icarus.db"
    manager = DatabaseManager(db_url=f"sqlite:///{db_file.as_posix()}")
    MigrationRunner().run_migrations(db_manager=manager)

    report = run_doctor_checks(home_dir=tmp_path)
    assert isinstance(report, DoctorReport)
    assert len(report.checks) >= 5
    check_names = [c.name for c in report.checks]
    assert "Database & Migrations" in check_names
    assert "Credentials & Authentication" in check_names
    assert report.is_healthy is True


def test_check_openrouter_api_reachable_displays_models():
    from unittest.mock import MagicMock

    import httpx
    from icarus_contracts import CredentialResult, CredentialSource, IcarusConfig
    from icarus_core.doctor import check_openrouter_api

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer sk-or-valid-key"
        return httpx.Response(
            200,
            json={
                "data": [
                    {"id": "anthropic/claude-3.5-sonnet", "name": "Claude 3.5 Sonnet"},
                    {"id": "openai/gpt-4o", "name": "GPT-4o"},
                ]
            },
        )

    mock_client = httpx.Client(transport=httpx.MockTransport(handler))
    mock_resolver = MagicMock()
    mock_resolver.resolve.return_value = CredentialResult(
        provider="openrouter",
        secret="sk-or-valid-key",
        source=CredentialSource.KEYRING,
        masked="sk-or-...-key",
    )
    config = IcarusConfig(default_provider="openrouter", model="anthropic/claude-3.5-sonnet")

    result = check_openrouter_api(resolver=mock_resolver, config=config, client=mock_client)
    assert result.status == HealthStatus.OK
    assert "reachable" in result.message.lower()
    assert "2 models" in result.message
    assert "anthropic/claude-3.5-sonnet" in result.details


def test_check_openrouter_api_missing_credentials_warns():
    from unittest.mock import MagicMock

    from icarus_contracts import CredentialResult, CredentialSource, IcarusConfig
    from icarus_core.doctor import check_openrouter_api

    mock_resolver = MagicMock()
    mock_resolver.resolve.return_value = CredentialResult(
        provider="openrouter",
        secret=None,
        source=CredentialSource.NONE,
    )
    config = IcarusConfig(default_provider="openrouter", model="anthropic/claude-3.5-sonnet")

    result = check_openrouter_api(resolver=mock_resolver, config=config)
    assert result.status == HealthStatus.WARNING
    assert "not configured" in result.message.lower()
    assert "anthropic/claude-3.5-sonnet" in result.details


def test_check_openrouter_api_401_fails():
    from unittest.mock import MagicMock

    import httpx
    from icarus_contracts import CredentialResult, CredentialSource, IcarusConfig
    from icarus_core.doctor import check_openrouter_api

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "Invalid API key"}})

    mock_client = httpx.Client(transport=httpx.MockTransport(handler))
    mock_resolver = MagicMock()
    mock_resolver.resolve.return_value = CredentialResult(
        provider="openrouter",
        secret="sk-or-invalid",
        source=CredentialSource.KEYRING,
        masked="sk-or-...-invalid",
    )
    config = IcarusConfig(default_provider="openrouter", model="anthropic/claude-3.5-sonnet")

    result = check_openrouter_api(resolver=mock_resolver, config=config, client=mock_client)
    assert result.status == HealthStatus.FAIL
    assert "authentication failed" in result.message.lower()
    assert result.fix_hint is not None


def test_run_doctor_checks_includes_openrouter_when_configured(tmp_path: Path):
    from unittest.mock import MagicMock

    import httpx
    from icarus_contracts import CredentialResult, CredentialSource, IcarusConfig
    from icarus_core.config import ConfigManager

    db_file = tmp_path / "icarus.db"
    manager = DatabaseManager(db_url=f"sqlite:///{db_file.as_posix()}")
    MigrationRunner().run_migrations(db_manager=manager)

    # Set default_provider to openrouter in config
    cfg_mgr = ConfigManager(config_path=tmp_path / "config.toml")
    cfg = IcarusConfig(default_provider="openrouter", model="anthropic/claude-3.5-sonnet")
    cfg_mgr.save_config(cfg)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"id": "anthropic/claude-3.5-sonnet"}]},
        )

    mock_client = httpx.Client(transport=httpx.MockTransport(handler))
    mock_resolver = MagicMock()
    mock_resolver.resolve.return_value = CredentialResult(
        provider="openrouter",
        secret="sk-or-test",
        source=CredentialSource.KEYRING,
        masked="sk-or-...test",
    )

    report = run_doctor_checks(
        home_dir=tmp_path,
        db_manager=manager,
        resolver=mock_resolver,
        config=cfg,
        openrouter_client=mock_client,
    )
    check_names = [c.name for c in report.checks]
    assert "OpenRouter API Reachability" in check_names
    openrouter_check = next(c for c in report.checks if c.name == "OpenRouter API Reachability")
    assert openrouter_check.status == HealthStatus.OK
    assert "anthropic/claude-3.5-sonnet" in openrouter_check.details
