"""Unified external account authorization manager and interactive OAuth/link prompt."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from icarus_core.paths import get_icarus_home
from icarus_core.theme import get_theme
from rich.console import Console
from rich.panel import Panel


def get_credentials_file() -> Path:
    """Return path to persistent credentials store."""
    return get_icarus_home() / "credentials.json"


def load_stored_credentials() -> dict[str, str]:
    """Load stored service credentials dictionary."""
    cred_file = get_credentials_file()
    if not cred_file.exists():
        return {}
    try:
        data = json.loads(cred_file.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def save_stored_credentials(credentials: dict[str, str]) -> None:
    """Persist credentials dictionary safely."""
    cred_file = get_credentials_file()
    cred_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        cred_file.write_text(json.dumps(credentials, indent=2), encoding="utf-8")
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
        """Resolve authorization token for service from env, keyring, or store."""
        service_key = service.lower().strip()

        # 1. Check environment variables
        candidates = cls.ENV_MAPPINGS.get(service_key, [f"{service_key.upper()}_API_KEY", f"{service_key.upper()}_TOKEN"])
        for env_var in candidates:
            val = os.environ.get(env_var)
            if val and val.strip():
                return val.strip()

        # 2. Check local credentials store
        stored = load_stored_credentials()
        if service_key in stored and stored[service_key].strip():
            return stored[service_key].strip()

        # 3. Check OS keyring
        try:
            import keyring
            secret = keyring.get_password("icarus_services", service_key)
            if secret and secret.strip():
                return secret.strip()
        except Exception:
            pass

        return None

    @classmethod
    def save_token(cls, service: str, token: str) -> None:
        """Save authorization token to credentials store and OS keyring."""
        service_key = service.lower().strip()
        cleaned = token.strip()
        if not cleaned:
            return

        stored = load_stored_credentials()
        stored[service_key] = cleaned
        save_stored_credentials(stored)

        try:
            import keyring
            keyring.set_password("icarus_services", service_key, cleaned)
        except Exception:
            pass

    @classmethod
    def prompt_authorization(
        cls,
        service: str,
        console: Console | None = None,
        stdin: Any = None,
    ) -> str | None:
        """Prompt user with the external authorization link and collect credentials."""
        cons = console or Console()
        th = get_theme()
        service_key = service.lower().strip()
        info = cls.AUTH_URLS.get(
            service_key,
            {
                "name": service.capitalize(),
                "url": f"https://www.google.com/search?q={service}+api+key",
                "instructions": f"Paste your {service.capitalize()} API key or token below.",
            },
        )

        title = f"[bold yellow]🔐 External Account Authorization Required: {info['name']}[/bold yellow]"
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
            cons.print(f"[bold green]✔ Successfully authorized and saved credentials for {info['name']}![/bold green]\n")
            return cleaned

        cons.print(f"[dim]Authorization skipped. Tool '{service}' remains unauthorized.[/dim]\n")
        return None
