"""Hierarchical credential resolution pipeline and OS keyring integration."""

import contextlib
import os

import keyring
from icarus_contracts import CredentialResult, CredentialSource


def mask_secret(secret: str | None) -> str | None:
    """Mask sensitive API keys for safe display in logs and diagnostic outputs."""
    if not secret:
        return None
    cleaned = secret.strip()
    if not cleaned:
        return None
    if len(cleaned) <= 8:
        return f"{cleaned[0]}***{cleaned[-1]}"
    return f"{cleaned[:4]}...{cleaned[-4:]}"


class CredentialNotFoundError(Exception):
    """Raised when no valid credential can be resolved across any configured tiers."""

    def __init__(self, provider: str, message: str | None = None) -> None:
        self.provider = provider
        env_names = CredentialResolver.get_env_var_candidates(provider)
        env_hint = " or ".join(env_names)
        self.fix_hint = (
            f"Run `icarus init` to securely save your API key in the OS keyring, "
            f"or set environment variable {env_hint}."
        )
        msg = message or f"No API credential found for provider '{provider}'. {self.fix_hint}"
        super().__init__(msg)


class CredentialResolver:
    """Resolves credentials through a strict 4-tier precedence hierarchy:

    1. Explicit CLI argument (--api-key)
    2. Environment variables (e.g. XAI_API_KEY, OPENROUTER_API_KEY, ICARUS_API_KEY)
    3. OS Keyring (service='icarus', username=provider)
    4. Actionable error report.
    """

    SERVICE_NAME = "icarus"

    @classmethod
    def get_env_var_candidates(cls, provider: str) -> list[str]:
        """Return the prioritized list of environment variable names for a provider."""
        normalized = provider.lower().strip()
        if normalized in {"grok", "xai"}:
            return ["XAI_API_KEY", "ICARUS_API_KEY"]
        if normalized == "groq":
            return ["GROQ_API_KEY", "ICARUS_API_KEY"]
        if normalized == "openrouter":
            return ["OPENROUTER_API_KEY", "ICARUS_API_KEY"]
        return [
            f"ICARUS_{normalized.upper()}_API_KEY",
            f"{normalized.upper()}_API_KEY",
            "ICARUS_API_KEY",
        ]

    def resolve(self, provider: str, cli_arg: str | None = None) -> CredentialResult:
        """Resolve API credential using the 4-tier hierarchy."""
        normalized_provider = provider.lower().strip()

        # Tier 1: CLI Argument
        if cli_arg is not None and len(cli_arg.strip()) > 0:
            secret = cli_arg.strip()
            return CredentialResult(
                provider=normalized_provider,
                secret=secret,
                source=CredentialSource.CLI_ARG,
                masked=mask_secret(secret),
            )

        # Tier 2: Environment Variables
        for env_var in self.get_env_var_candidates(normalized_provider):
            env_val = os.environ.get(env_var)
            if env_val is not None and len(env_val.strip()) > 0:
                secret = env_val.strip()
                return CredentialResult(
                    provider=normalized_provider,
                    secret=secret,
                    source=CredentialSource.ENV_VAR,
                    masked=mask_secret(secret),
                )

        # Tier 3: OS Keyring
        try:
            keyring_val = keyring.get_password(self.SERVICE_NAME, normalized_provider)
            if keyring_val is not None and len(keyring_val.strip()) > 0:
                secret = keyring_val.strip()
                return CredentialResult(
                    provider=normalized_provider,
                    secret=secret,
                    source=CredentialSource.KEYRING,
                    masked=mask_secret(secret),
                )
        except Exception:
            # Headless or missing keyring daemon should fall through gracefully
            pass

        # Tier 4: Missing
        return CredentialResult(
            provider=normalized_provider,
            secret=None,
            source=CredentialSource.NONE,
            masked=None,
        )

    def resolve_or_raise(self, provider: str, cli_arg: str | None = None) -> CredentialResult:
        """Resolve credential or raise CredentialNotFoundError with actionable fix hint."""
        result = self.resolve(provider=provider, cli_arg=cli_arg)
        if not result.is_available:
            raise CredentialNotFoundError(provider=provider)
        return result

    def store(self, provider: str, secret: str) -> None:
        """Securely persist an API credential to the OS keyring."""
        normalized_provider = provider.lower().strip()
        keyring.set_password(self.SERVICE_NAME, normalized_provider, secret.strip())

    def delete(self, provider: str) -> None:
        """Remove a credential from the OS keyring."""
        normalized_provider = provider.lower().strip()
        with contextlib.suppress(Exception):
            keyring.delete_password(self.SERVICE_NAME, normalized_provider)

    def get_masked(self, provider: str, cli_arg: str | None = None) -> str | None:
        """Convenience method to return only the masked representation if available."""
        return self.resolve(provider=provider, cli_arg=cli_arg).masked
