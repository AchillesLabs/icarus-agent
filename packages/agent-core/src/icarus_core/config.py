import contextlib
import os
import tomllib
from pathlib import Path
from typing import Any

import keyring
from icarus_contracts import IcarusConfig, ServerProfile

from icarus_core.paths import get_icarus_config_path


class ConfigManager:
    """Manages loading, updating, and saving Icarus settings without persisting secrets."""

    SERVER_KEYRING_SERVICE = "icarus-server"

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
            if "servers" in data and isinstance(data["servers"], dict):
                for srv_name, srv_data in data["servers"].items():
                    if isinstance(srv_data, dict) and not srv_data.get("name"):
                        srv_data["name"] = srv_name
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
            f"safety_margin_tokens = {config.safety_margin_tokens}",
            f"output_reserve_tokens = {config.output_reserve_tokens}",
            f"compaction_threshold = {config.compaction_threshold}",
        ]
        if config.active_server:
            lines.append(f'active_server = "{config.active_server}"')

        lines.append("")
        for name, srv in config.servers.items():
            lines.append(f"[servers.{name}]")
            lines.append(f'url = "{srv.url}"')
            lines.append(f"active = {'true' if srv.active else 'false'}")
            lines.append("")

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

    def list_servers(self) -> list[ServerProfile]:
        """Return list of all configured server profiles."""
        cfg = self.load_config()
        return list(cfg.servers.values())

    def get_server(self, name: str) -> ServerProfile | None:
        """Retrieve a specific server profile by name."""
        cfg = self.load_config()
        return cfg.servers.get(name)

    def add_server(
        self,
        name: str,
        url: str,
        api_key: str | None = None,
        active: bool = False,
    ) -> ServerProfile:
        """Add or update a server connection profile and save credentials to keyring."""
        cfg = self.load_config()
        normalized_url = url.rstrip("/")
        if active:
            for s in cfg.servers.values():
                s.active = False
            cfg.active_server = name

        profile = ServerProfile(name=name, url=normalized_url, active=active)
        cfg.servers[name] = profile
        if active or (len(cfg.servers) == 1 and not cfg.active_server):
            cfg.active_server = name
            profile.active = True

        self.save_config(cfg)

        if api_key:
            with contextlib.suppress(Exception):
                keyring.set_password(self.SERVER_KEYRING_SERVICE, name, api_key)

        return profile

    def switch_server(self, name: str) -> ServerProfile:
        """Activate a specific server profile by name."""
        cfg = self.load_config()
        if name not in cfg.servers:
            raise KeyError(f"Server profile '{name}' not found.")

        for s_name, srv in cfg.servers.items():
            srv.active = s_name == name

        cfg.active_server = name
        self.save_config(cfg)
        return cfg.servers[name]

    def remove_server(self, name: str) -> bool:
        """Remove a server profile and its keyring credentials."""
        cfg = self.load_config()
        if name not in cfg.servers:
            return False

        del cfg.servers[name]
        if cfg.active_server == name:
            cfg.active_server = next(iter(cfg.servers.keys()), None)
            if cfg.active_server and cfg.active_server in cfg.servers:
                cfg.servers[cfg.active_server].active = True

        self.save_config(cfg)

        with contextlib.suppress(Exception):
            keyring.delete_password(self.SERVER_KEYRING_SERVICE, name)

        return True

    def get_active_server(self) -> ServerProfile | None:
        """Return the currently active server profile, if any."""
        cfg = self.load_config()
        if cfg.active_server and cfg.active_server in cfg.servers:
            return cfg.servers[cfg.active_server]
        for srv in cfg.servers.values():
            if srv.active:
                return srv
        return None

    def get_server_api_key(self, name: str) -> str | None:
        """Retrieve stored API key for a server profile from environment or OS keyring."""
        env_key = f"ICARUS_SERVER_{name.upper().replace('-', '_')}_API_KEY"
        if env_val := os.getenv(env_key):
            return env_val
        if os.getenv("ICARUS_API_AUTH_TOKEN"):
            return os.getenv("ICARUS_API_AUTH_TOKEN")

        with contextlib.suppress(Exception):
            pw = keyring.get_password(self.SERVER_KEYRING_SERVICE, name)
            if pw:
                return pw
        return None
