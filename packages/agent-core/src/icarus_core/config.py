"""Configuration manager for ~/.icarus/config.toml."""

import tomllib
from pathlib import Path
from typing import Any

from icarus_contracts import IcarusConfig

from icarus_core.paths import get_icarus_config_path


class ConfigManager:
    """Manages loading, updating, and saving Icarus settings without persisting secrets."""

    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = config_path if config_path is not None else get_icarus_config_path()
        self._cached_config: IcarusConfig | None = None

    def load_config(self) -> IcarusConfig:
        """Load and validate configuration from disk, returning defaults if not yet created."""
        if not self.config_path.exists():
            self._cached_config = IcarusConfig()
            return self._cached_config

        try:
            content = self.config_path.read_text(encoding="utf-8")
            data = tomllib.loads(content)
            self._cached_config = IcarusConfig.model_validate(data)
            return self._cached_config
        except Exception:
            # Fallback to default if config file is invalid or corrupt
            self._cached_config = IcarusConfig()
            return self._cached_config

    def save_config(self, config: IcarusConfig) -> None:
        """Serialize configuration to TOML and write safely to disk."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Icarus Agent Configuration (~/.icarus/config.toml)",
            "# Secrets are stored securely in the OS keyring, never in plaintext on disk.",
            "",
            f'default_provider = "{config.default_provider}"',
            f'model = "{config.model}"',
            f"temperature = {config.temperature}",
            f"max_turns = {config.max_turns}",
            f"max_tokens_budget = {config.max_tokens_budget}",
            "",
        ]
        self.config_path.write_text("\n".join(lines), encoding="utf-8")
        self._cached_config = config

    def get(self, key: str) -> Any:
        """Retrieve a specific configuration parameter by key name."""
        config = self.load_config()
        if key not in IcarusConfig.model_fields:
            raise KeyError(f"Configuration key '{key}' is invalid or not recognized.")
        return getattr(config, key)

    def set(self, key: str, value: Any) -> IcarusConfig:
        """Set, validate, and persist a single configuration parameter."""
        if key not in IcarusConfig.model_fields:
            raise KeyError(f"Configuration key '{key}' is invalid or not recognized.")

        field_info = IcarusConfig.model_fields[key]
        target_type = field_info.annotation

        # Coerce string inputs from CLI flags to expected types
        coerced_value = value
        if target_type is float:
            try:
                coerced_value = float(value)
            except (ValueError, TypeError) as exc:
                raise ValueError(
                    f"Value '{value}' cannot be converted to float for '{key}'."
                ) from exc
        elif target_type is int:
            try:
                coerced_value = int(value)
            except (ValueError, TypeError) as exc:
                raise ValueError(
                    f"Value '{value}' cannot be converted to int for '{key}'."
                ) from exc
        elif target_type is str:
            coerced_value = str(value)

        current = self.load_config()
        update_dict = current.model_dump()
        update_dict[key] = coerced_value

        # Re-validate against Pydantic schema constraints
        updated_config = IcarusConfig.model_validate(update_dict)
        self.save_config(updated_config)
        return updated_config

    def list_settings(self) -> dict[str, Any]:
        """Return a mapping of all active configuration keys and values."""
        config = self.load_config()
        return config.model_dump()
