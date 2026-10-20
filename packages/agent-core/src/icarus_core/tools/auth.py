"""Unified external account authorization manager and interactive OAuth/link prompt."""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet
from rich.console import Console
from rich.panel import Panel

from icarus_core.paths import get_icarus_home
from icarus_core.theme import get_theme


def _get_or_create_local_master_key() -> bytes:
    """Retrieve or generate machine-local 32-byte key for local credential vault encryption."""
    key_file = get_icarus_home() / ".credential_key"
    if key_file.exists():
        try:
            content = key_file.read_bytes().strip()
            if content:
                return content
        except Exception:
            pass

    key = Fernet.generate_key()
    key_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(key_file), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with open(fd, "wb") as f:
            f.write(key)
    except Exception:
        key_file.write_bytes(key)
        with contextlib.suppress(Exception):
            os.chmod(key_file, 0o600)
    return key


def get_credentials_file() -> Path:
    """Return path to persistent encrypted credentials store."""
    return get_icarus_home() / "credentials.enc"


def get_legacy_credentials_file() -> Path:
    """Return path to legacy plaintext credentials store."""
    return get_icarus_home() / "credentials.json"


def load_stored_credentials() -> dict[str, str]:
    """Load stored service credentials dictionary with automatic decryption and migration."""
    legacy_file = get_legacy_credentials_file()
    enc_file = get_credentials_file()

    # 1. Automatic migration from legacy plaintext credentials.json
    if legacy_file.exists() and not enc_file.exists():
        try:
            legacy_text = legacy_file.read_text(encoding="utf-8")
            data = json.loads(legacy_text)
            if isinstance(data, dict):
                save_stored_credentials(data)
                legacy_file.write_text(
                    json.dumps(
                        {
                            "_notice": "Credentials migrated to secure encrypted storage credentials.enc"
                        }
                    ),
                    encoding="utf-8",
                )
                with contextlib.suppress(Exception):
                    os.chmod(legacy_file, 0o600)
                return data
        except Exception:
            pass

    if not enc_file.exists():
        return {}

    try:
        raw_ciphertext = enc_file.read_bytes().strip()
        if not raw_ciphertext:
            return {}
        if raw_ciphertext.startswith(b"{"):
            data = json.loads(raw_ciphertext.decode("utf-8"))
            if isinstance(data, dict):
                save_stored_credentials(data)
                return data

        fernet = Fernet(_get_or_create_local_master_key())
        decrypted_bytes = fernet.decrypt(raw_ciphertext)
        data = json.loads(decrypted_bytes.decode("utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def save_stored_credentials(credentials: dict[str, str]) -> None:
    """Persist credentials dictionary encrypted at rest with restricted file permissions."""
    enc_file = get_credentials_file()
    enc_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        fernet = Fernet(_get_or_create_local_master_key())
        serialized = json.dumps(credentials, indent=2).encode("utf-8")
        ciphertext = fernet.encrypt(serialized)

        try:
            fd = os.open(str(enc_file), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with open(fd, "wb") as f:
                f.write(ciphertext)
        except Exception:
            enc_file.write_bytes(ciphertext)
            with contextlib.suppress(Exception):
                os.chmod(enc_file, 0o600)
    except Exception:
        pass


class ToolAuthManager:
    """Manages credentials and interactive authorization for external services."""

    ENV_MAPPINGS: dict[str, list[str]] = {
        "gmail": ["GMAIL_APP_PASSWORD", "GMAIL_TOKEN", "GOOGLE_APP_PASSWORD"],
        "calendar": ["GOOGLE_CALENDAR_TOKEN", "GOOGLE_API_KEY", "GMAIL_APP_PASSWORD"],
        "github": ["GITHUB_PERSONAL_ACCESS_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"],
        "slack": ["SLACK_BOT_TOKEN", "SLACK_TOKEN"],
        "stripe": ["STRIPE_SECRET_KEY", "STRIPE_API_KEY"],
        "brave": ["BRAVE_API_KEY"],
    }

    AUTH_URLS: dict[str, dict[str, str]] = {
        "gmail": {
            "name": "Google / Gmail",
            "url": "https://myaccount.google.com/apppasswords",
            "instructions": (
                "1. Go to Google App Passwords: https://myaccount.google.com/apppasswords\n"
                "2. Create a new app password named 'Icarus Agent'\n"
                "3. Copy the 16-character generated password and paste below."
            ),
        },
        "calendar": {
            "name": "Google Calendar",
            "url": "https://myaccount.google.com/apppasswords",
            "instructions": (
                "1. Open Google Account Security: https://myaccount.google.com/apppasswords\n"
                "2. Generate an app password for 'Icarus Calendar'\n"
                "3. Paste the generated password or API key below."
            ),
        },
        "github": {
            "name": "GitHub",
            "url": "https://github.com/settings/tokens",
            "instructions": (
                "1. Open GitHub Personal Access Tokens: https://github.com/settings/tokens\n"
                "2. Click 'Generate new token (classic)' with repo & issue permissions\n"
                "3. Paste your GitHub token below."
            ),
        },
        "slack": {
            "name": "Slack Workspace",
            "url": "https://api.slack.com/apps",
            "instructions": (
                "1. Go to Slack App Portal: https://api.slack.com/apps\n"
                "2. Create an App or copy your Bot User OAuth Token (xoxb-...)\n"
                "3. Paste your Slack Bot Token below."
            ),
        },
        "stripe": {
            "name": "Stripe Payments",
            "url": "https://dashboard.stripe.com/apikeys",
            "instructions": (
                "1. Open your Stripe Developer Dashboard: https://dashboard.stripe.com/apikeys\n"
                "2. Copy your Secret Key (sk_test_... or sk_live_...)\n"
                "3. Paste your Stripe Secret Key below."
            ),
        },
    }

    @classmethod
    def get_token(cls, service: str) -> str | None:
        """Resolve authorization token for service from env, OS keyring, or encrypted store."""
        service_key = service.lower().strip()

        # 1. Check environment variables
        candidates = cls.ENV_MAPPINGS.get(
            service_key, [f"{service_key.upper()}_API_KEY", f"{service_key.upper()}_TOKEN"]
        )
        for env_var in candidates:
            val = os.environ.get(env_var)
            if val and val.strip():
                return val.strip()

        # 2. Check OS keyring first (preferred secure storage)
        try:
            import keyring

            secret = keyring.get_password("icarus_services", service_key)
            if secret and secret.strip():
                return secret.strip()
        except Exception:
            pass

        # 3. Check encrypted credentials store
        stored = load_stored_credentials()
        if service_key in stored and stored[service_key].strip():
            return stored[service_key].strip()

        return None

    @classmethod
    def get_access_token(cls, service: str) -> str | None:
        """Resolve valid bearer access token for service, unpacking JSON or refreshing OAuth if needed."""
        raw = cls.get_token(service)
        if not raw:
            return None
        raw_str = raw.strip()
        if raw_str.startswith("{"):
            try:
                data = json.loads(raw_str)
                if isinstance(data, dict):
                    if service.lower() == "google" and data.get("refresh_token"):
                        from datetime import UTC, datetime, timedelta

                        expires_at_str = data.get("expires_at")
                        is_expired = False
                        if expires_at_str:
                            try:
                                exp_dt = datetime.fromisoformat(expires_at_str)
                                if datetime.now(UTC) >= exp_dt:
                                    is_expired = True
                            except Exception:
                                pass
                        if is_expired:
                            try:
                                from icarus_core.integrations.google import GoogleOAuthClient

                                client = GoogleOAuthClient()
                                if client.is_configured():
                                    refreshed = client.refresh_access_token(data["refresh_token"])
                                    data["access_token"] = refreshed.get(
                                        "access_token", data["access_token"]
                                    )
                                    if "expires_in" in refreshed:
                                        data["expires_at"] = (
                                            datetime.now(UTC)
                                            + timedelta(seconds=int(refreshed["expires_in"]))
                                        ).isoformat()
                                    cls.save_token(service, json.dumps(data))
                            except Exception:
                                pass
                    return data.get("access_token") or raw_str
            except Exception:
                pass
        return raw_str

    @classmethod
    def save_token(cls, service: str, token: str) -> None:
        """Save authorization token to OS keyring and encrypted credentials store."""
        service_key = service.lower().strip()
        cleaned = token.strip()
        if not cleaned:
            return

        # 1. Prioritize OS keyring
        try:
            import keyring

            keyring.set_password("icarus_services", service_key, cleaned)
        except Exception:
            pass

        # 2. Persist in encrypted local file store
        stored = load_stored_credentials()
        stored[service_key] = cleaned
        save_stored_credentials(stored)

        # 3. Synchronize in-process environment variables if currently active
        candidates = cls.ENV_MAPPINGS.get(
            service_key, [f"{service_key.upper()}_API_KEY", f"{service_key.upper()}_TOKEN"]
        )
        for env_var in candidates:
            if env_var in os.environ:
                os.environ[env_var] = cleaned

    @classmethod
    def delete_token(cls, service: str) -> bool:
        """Delete stored authorization token from OS keyring, encrypted store, and environment."""
        service_key = service.lower().strip()
        deleted = False

        try:
            import keyring

            keyring.delete_password("icarus_services", service_key)
            deleted = True
        except Exception:
            pass

        stored = load_stored_credentials()
        if service_key in stored:
            del stored[service_key]
            save_stored_credentials(stored)
            deleted = True

        candidates = cls.ENV_MAPPINGS.get(
            service_key, [f"{service_key.upper()}_API_KEY", f"{service_key.upper()}_TOKEN"]
        )
        for env_var in candidates:
            if env_var in os.environ:
                del os.environ[env_var]
                deleted = True

        return deleted

    @classmethod
    def has_token(cls, service: str) -> bool:
        """Return True if an authorization token exists for the given service."""
        return cls.get_token(service) is not None

    @classmethod
    def prompt_authorization(
        cls,
        service: str,
        console: Console | None = None,
        stdin: Any = None,
    ) -> str | None:
        """Prompt user with the external authorization link and collect credentials."""
        cons = console or Console()
        get_theme()
        service_key = service.lower().strip()
        info = cls.AUTH_URLS.get(
            service_key,
            {
                "name": service.capitalize(),
                "url": f"https://www.google.com/search?q={service}+api+key",
                "instructions": f"Paste your {service.capitalize()} API key or token below.",
            },
        )

        title = (
            f"[bold yellow]🔐 External Account Authorization Required: {info['name']}[/bold yellow]"
        )
        content = (
            f"[bold white]To let Icarus access your {info['name']} account:[/bold white]\n\n"
            f"[bold cyan]1. Open Authorization Link in your browser:[/bold cyan]\n"
            f"   👉 [bold underline blue]{info['url']}[/bold underline blue]\n\n"
            f"[bold cyan]2. Steps:[/bold cyan]\n"
            f"[dim]{info['instructions']}[/dim]\n"
        )

        panel = Panel(
            content,
            title=title,
            border_style="yellow",
            subtitle="[dim]Your credentials are encrypted & stored locally on this machine[/dim]",
        )
        cons.print(panel)

        prompt_label = f"[bold yellow]Enter token / password for {info['name']} (or press Enter to cancel): [/bold yellow]"
        try:
            if stdin is not None:
                cons.print(prompt_label, end="")
                val = stdin.readline()
            else:
                val = cons.input(prompt_label, password=True)
        except (KeyboardInterrupt, EOFError):
            cons.print("\n[dim]Authorization cancelled by user.[/dim]")
            return None

        cleaned = val.strip()
        if cleaned:
            cls.save_token(service_key, cleaned)
            cons.print(
                f"[bold green]✔ Successfully authorized and saved credentials for {info['name']}![/bold green]\n"
            )
            return cleaned

        cons.print(f"[dim]Authorization skipped. Tool '{service}' remains unauthorized.[/dim]\n")
        return None
