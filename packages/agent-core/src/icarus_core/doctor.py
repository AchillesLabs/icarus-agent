"""Environment and system health diagnostic services for Icarus."""

import importlib
import sys
import tempfile
from pathlib import Path

import httpx
from icarus_contracts import IcarusConfig
from icarus_contracts.doctor import DoctorCheckResult, DoctorReport, HealthStatus
from sqlalchemy import inspect

from icarus_core.config import ConfigManager
from icarus_core.credentials import CredentialNotFoundError, CredentialResolver
from icarus_core.paths import get_icarus_home, get_icarus_logs_dir
from icarus_core.persistence.database import DatabaseManager
from icarus_core.persistence.migrations.runner import MigrationRunner

MINIMUM_PYTHON_VERSION = (3, 12)


def check_python_version() -> DoctorCheckResult:
    """Verify that the current Python interpreter meets the minimum version requirement (>=3.12)."""
    current_version = (sys.version_info[0], sys.version_info[1])
    version_str = f"{sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}"

    if current_version >= MINIMUM_PYTHON_VERSION:
        return DoctorCheckResult(
            name="Python Interpreter",
            status=HealthStatus.OK,
            message=f"Python {version_str} is compatible (>= 3.12)",
            details=f"Executable: {sys.executable}",
        )
    return DoctorCheckResult(
        name="Python Interpreter",
        status=HealthStatus.FAIL,
        message=f"Python {version_str} is incompatible with requirement >= 3.12",
        details=f"Executable: {sys.executable}",
        fix_hint="Install Python 3.12 or higher and recreate your virtual environment.",
    )


def check_storage_directories(home_dir: Path | None = None) -> DoctorCheckResult:
    """Verify and initialize local user storage (~/.icarus/ and logs directory)."""
    target_home = home_dir if home_dir is not None else get_icarus_home()
    logs_dir = target_home / "logs" if home_dir is not None else get_icarus_logs_dir()

    try:
        target_home.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)

        # Validate write permissions via temporary sentinel file
        with tempfile.NamedTemporaryFile(dir=target_home, delete=True) as temp_file:
            temp_file.write(b"healthcheck")
            temp_file.flush()

        with tempfile.NamedTemporaryFile(dir=logs_dir, delete=True) as temp_file:
            temp_file.write(b"healthcheck")
            temp_file.flush()

        return DoctorCheckResult(
            name="Storage & Logging Directories",
            status=HealthStatus.OK,
            message=f"Storage directory accessible at {target_home}",
            details=f"Logs directory created at {logs_dir}",
        )
    except Exception as exc:
        return DoctorCheckResult(
            name="Storage & Logging Directories",
            status=HealthStatus.FAIL,
            message=f"Cannot write to storage directory at {target_home}: {exc}",
            fix_hint=f"Ensure your user has write permissions to {target_home}.",
        )


def check_workspace_integrity() -> DoctorCheckResult:
    """Verify that all core workspace packages can be imported cleanly."""
    required_packages = ["icarus_contracts", "icarus_core"]
    loaded = []
    missing = []

    for pkg_name in required_packages:
        try:
            mod = importlib.import_module(pkg_name)
            ver = getattr(mod, "__version__", "unknown")
            loaded.append(f"{pkg_name} ({ver})")
        except Exception as exc:
            missing.append(f"{pkg_name}: {exc}")

    if missing:
        return DoctorCheckResult(
            name="Workspace Integrity",
            status=HealthStatus.FAIL,
            message=f"Failed to load workspace packages: {', '.join(missing)}",
            fix_hint="Run `uv sync --all-packages` to rebuild workspace links.",
        )

    return DoctorCheckResult(
        name="Workspace Integrity",
        status=HealthStatus.OK,
        message=f"Workspace packages loaded cleanly: {', '.join(loaded)}",
    )


def check_database_connectivity(
    db_manager: DatabaseManager | None = None,
    home_dir: Path | None = None,
) -> DoctorCheckResult:
    """Verify database connectivity, table presence, and Alembic migration state."""
    manager = db_manager or (
        DatabaseManager(db_url=f"sqlite:///{(home_dir / 'icarus.db').as_posix()}")
        if home_dir is not None
        else DatabaseManager()
    )

    # 1. Test basic connectivity
    if not manager.is_connected():
        return DoctorCheckResult(
            name="Database & Migrations",
            status=HealthStatus.FAIL,
            message="Database connectivity check failed.",
            details=f"URL: {manager.db_url}",
            fix_hint="Ensure the database file path is writable and not locked.",
        )

    # 2. Check table existence
    try:
        inspector = inspect(manager.engine)
        existing_tables = set(inspector.get_table_names())
        required_tables = {"sessions", "messages", "agent_runs"}
        missing_tables = required_tables - existing_tables
        if missing_tables:
            found = ", ".join(sorted(existing_tables)) if existing_tables else "none"
            return DoctorCheckResult(
                name="Database & Migrations",
                status=HealthStatus.FAIL,
                message=f"Missing required database tables: {', '.join(sorted(missing_tables))}",
                details=f"Found tables: {found}",
                fix_hint="Run `icarus init` or restart CLI to apply automatic schema migrations.",
            )
    except Exception as exc:
        return DoctorCheckResult(
            name="Database & Migrations",
            status=HealthStatus.FAIL,
            message=f"Failed to inspect database tables: {exc}",
            fix_hint="Check database file permissions and integrity.",
        )

    # 3. Check migration revision status
    try:
        runner = MigrationRunner()
        current_rev = runner.get_current_revision(db_manager=manager)
        head_rev = runner.get_head_revision()

        if current_rev != head_rev:
            return DoctorCheckResult(
                name="Database & Migrations",
                status=HealthStatus.FAIL,
                message=f"Database migration revision ({current_rev}) is not at head ({head_rev})",
                details=f"URL: {manager.db_url}",
                fix_hint="Run `icarus init` or restart the CLI to execute pending migrations.",
            )

        return DoctorCheckResult(
            name="Database & Migrations",
            status=HealthStatus.OK,
            message=f"Database connected and migrated to head ({head_rev})",
            details=f"Tables: {', '.join(sorted(existing_tables))}",
        )
    except Exception as exc:
        return DoctorCheckResult(
            name="Database & Migrations",
            status=HealthStatus.FAIL,
            message=f"Failed to verify migration status: {exc}",
            fix_hint="Ensure Alembic migrations in icarus_core are intact.",
        )


def check_credentials(
    resolver: CredentialResolver | None = None,
    config: IcarusConfig | None = None,
    home_dir: Path | None = None,
) -> DoctorCheckResult:
    """Verify presence and accessibility of credentials for the active configured provider."""
    cfg_manager = (
        ConfigManager(config_path=home_dir / "config.toml")
        if home_dir is not None
        else ConfigManager()
    )
    active_config = config or cfg_manager.load_config()
    active_provider = active_config.default_provider

    res = resolver or CredentialResolver()
    cred_result = res.resolve(active_provider)

    if cred_result.is_available:
        return DoctorCheckResult(
            name="Credentials & Authentication",
            status=HealthStatus.OK,
            message=f"Credential configured for provider '{active_provider}'",
            details=f"Key: {cred_result.masked} (source: {cred_result.source.value})",
        )

    err = CredentialNotFoundError(active_provider)
    return DoctorCheckResult(
        name="Credentials & Authentication",
        status=HealthStatus.WARNING,
        message=f"No credential found for default provider '{active_provider}'",
        details="Model generation and chat require valid API credentials.",
        fix_hint=err.fix_hint,
    )


def check_openrouter_api(
    resolver: CredentialResolver | None = None,
    config: IcarusConfig | None = None,
    home_dir: Path | None = None,
    client: httpx.Client | None = None,
    base_url: str = "https://openrouter.ai/api/v1",
) -> DoctorCheckResult:
    """Verify reachability of OpenRouter API and display configured models."""
    cfg_manager = (
        ConfigManager(config_path=home_dir / "config.toml")
        if home_dir is not None
        else ConfigManager()
    )
    active_config = config or cfg_manager.load_config()
    target_model = active_config.model
    res = resolver or CredentialResolver()
    cred = res.resolve("openrouter")

    if not cred.is_available:
        return DoctorCheckResult(
            name="OpenRouter API Reachability",
            status=HealthStatus.WARNING,
            message="OpenRouter credential not configured",
            details=f"Configured model: {target_model}",
            fix_hint="Run `icarus init --provider openrouter` or set OPENROUTER_API_KEY.",
        )

    url = f"{base_url.rstrip('/')}/models"
    headers = {
        "Authorization": f"Bearer {cred.secret}",
        "HTTP-Referer": "https://github.com/AchillesLabs/icarus-agent",
        "X-Title": "Icarus Agent",
    }

    try:
        if client is not None:
            response = client.get(url, headers=headers)
        else:
            with httpx.Client(timeout=5.0) as http_client:
                response = http_client.get(url, headers=headers)

        if response.status_code in {401, 403}:
            return DoctorCheckResult(
                name="OpenRouter API Reachability",
                status=HealthStatus.FAIL,
                message=(
                    f"OpenRouter authentication failed ({response.status_code}): Invalid API key"
                ),
                details=f"Configured model: {target_model}",
                fix_hint="Check your OPENROUTER_API_KEY or run `icarus init` with a valid key.",
            )

        if response.is_error:
            return DoctorCheckResult(
                name="OpenRouter API Reachability",
                status=HealthStatus.FAIL,
                message=f"OpenRouter API returned error status {response.status_code}",
                details=f"Configured model: {target_model}",
                fix_hint="Check OpenRouter service status at https://status.openrouter.ai",
            )

        data = response.json()
        models = data.get("data", [])
        model_count = len(models) if isinstance(models, list) else 0

        model_ids = {m.get("id") for m in models if isinstance(m, dict)}
        model_found_note = " (verified available)" if target_model in model_ids else ""

        return DoctorCheckResult(
            name="OpenRouter API Reachability",
            status=HealthStatus.OK,
            message=f"OpenRouter API reachable ({model_count} models available)",
            details=f"Configured model: {target_model}{model_found_note}",
        )
    except Exception as exc:
        return DoctorCheckResult(
            name="OpenRouter API Reachability",
            status=HealthStatus.FAIL,
            message=f"OpenRouter connection check failed: {exc}",
            details=f"Configured model: {target_model}",
            fix_hint="Check internet connection and OpenRouter service status.",
        )


def run_doctor_checks(
    home_dir: Path | None = None,
    db_manager: DatabaseManager | None = None,
    resolver: CredentialResolver | None = None,
    config: IcarusConfig | None = None,
    openrouter_client: httpx.Client | None = None,
) -> DoctorReport:
    """Run all standard environment diagnostic checks and return an aggregated DoctorReport."""
    cfg_manager = (
        ConfigManager(config_path=home_dir / "config.toml")
        if home_dir is not None
        else ConfigManager()
    )
    active_config = config or cfg_manager.load_config()

    checks = [
        check_python_version(),
        check_storage_directories(home_dir=home_dir),
        check_workspace_integrity(),
        check_database_connectivity(db_manager=db_manager, home_dir=home_dir),
        check_credentials(resolver=resolver, config=active_config, home_dir=home_dir),
    ]

    if active_config.default_provider == "openrouter":
        checks.append(
            check_openrouter_api(
                resolver=resolver,
                config=active_config,
                home_dir=home_dir,
                client=openrouter_client,
            )
        )

    return DoctorReport(checks=checks)
