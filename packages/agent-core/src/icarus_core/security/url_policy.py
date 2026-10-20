"""Comprehensive SSRF protection policy, DNS validation, and safe HTTP client factory."""

from __future__ import annotations

import ipaddress
import logging
import socket
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger("icarus.security.url_policy")

# Well-known cloud metadata and internal hostnames
FORBIDDEN_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "metadata",
    "instance-data",
}

CLOUD_METADATA_IPS = {
    "169.254.169.254",  # AWS/GCP/Azure/OpenStack metadata
    "fd00:ec2::254",    # AWS IPv6 metadata
}


class SSRFProtectionError(ValueError):
    """Raised when an outbound URL violates SSRF security boundaries."""


def is_ip_allowed(ip_str: str, allow_private: bool = False) -> bool:
    """Check if an individual IP address is permissible for outbound requests."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False

    # Block well-known cloud metadata IP addresses unconditionally
    if str(ip) in CLOUD_METADATA_IPS:
        return False

    if allow_private:
        return not (ip.is_multicast or ip.is_unspecified)

    # Block loopback (127.0.0.0/8, ::1)
    if ip.is_loopback:
        return False

    # Block link-local (169.254.0.0/16, fe80::/10)
    if ip.is_link_local:
        return False

    # Block private networks (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, fc00::/7)
    if ip.is_private:
        return False

    # Block multicast, unspecified, reserved
    if ip.is_multicast or ip.is_unspecified or ip.is_reserved:
        return False

    # Carrier-grade NAT (100.64.0.0/10)
    try:
        cgnat = ipaddress.ip_network("100.64.0.0/10")
        if ip in cgnat:
            return False
    except ValueError:
        pass

    return True


def validate_url(
    url: str,
    allow_private: bool = False,
    resolve_dns: bool = True,
) -> str:
    """Validate a destination URL against SSRF policy and resolve DNS addresses.

    Returns the cleaned URL if safe, or raises SSRFProtectionError.
    """
    if not url or not isinstance(url, str):
        raise SSRFProtectionError("URL must be a non-empty string.")

    cleaned = url.strip()
    try:
        parsed = urlparse(cleaned)
    except Exception as exc:
        raise SSRFProtectionError(f"Malformed URL: {exc}") from exc

    if parsed.scheme.lower() not in ("http", "https"):
        raise SSRFProtectionError(
            f"Invalid URL scheme '{parsed.scheme}'. Only HTTP and HTTPS are permitted."
        )

    hostname = parsed.hostname
    if not hostname:
        raise SSRFProtectionError(f"URL '{cleaned}' has no valid hostname.")

    lowered_host = hostname.lower().strip()

    # Block forbidden hostnames
    if lowered_host in FORBIDDEN_HOSTNAMES:
        raise SSRFProtectionError(
            f"Host '{hostname}' is a forbidden internal destination (cloud metadata or localhost)."
        )

    # Check if host is a raw IP literal
    raw_ip = None
    try:
        raw_ip = ipaddress.ip_address(lowered_host)
    except ValueError:
        pass

    if raw_ip is not None:
        if not is_ip_allowed(str(raw_ip), allow_private=allow_private):
            raise SSRFProtectionError(
                f"Destination IP '{raw_ip}' is private, loopback, or cloud metadata and is forbidden."
            )
        return cleaned

    if not resolve_dns:
        return cleaned

    # Resolve hostname via DNS and check every returned IP
    try:
        addr_info = socket.getaddrinfo(
            lowered_host,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            proto=socket.IPPROTO_TCP,
        )
    except socket.gaierror as exc:
        raise SSRFProtectionError(f"DNS resolution failed for host '{hostname}': {exc}") from exc

    resolved_ips = set()
    for item in addr_info:
        sockaddr = item[4]
        ip_addr = sockaddr[0]
        resolved_ips.add(ip_addr)

    if not resolved_ips:
        raise SSRFProtectionError(f"Host '{hostname}' resolved to no IP addresses.")

    for ip_str in resolved_ips:
        if not is_ip_allowed(ip_str, allow_private=allow_private):
            raise SSRFProtectionError(
                f"Host '{hostname}' resolved to forbidden IP '{ip_str}' (private, loopback, or metadata)."
            )

    return cleaned


def create_safe_client(
    timeout: float = 30.0,
    max_redirects: int = 5,
    allow_private: bool = False,
    headers: dict[str, str] | None = None,
    resolve_dns: bool = True,
    transport: httpx.BaseTransport | None = None,
) -> httpx.Client:
    """Instantiate an httpx.Client configured with SSRF redirect validation hooks."""
    def _validate_request_hook(request: httpx.Request) -> None:
        validate_url(str(request.url), allow_private=allow_private, resolve_dns=resolve_dns)

    def _validate_response_hook(response: httpx.Response) -> None:
        location = response.headers.get("Location")
        if location and response.is_redirect:
            redirect_url = str(response.url.join(location))
            validate_url(redirect_url, allow_private=allow_private, resolve_dns=resolve_dns)

    event_hooks: dict[str, list[Any]] = {
        "request": [_validate_request_hook],
        "response": [_validate_response_hook],
    }

    kwargs: dict[str, Any] = {
        "timeout": timeout,
        "follow_redirects": True,
        "max_redirects": max_redirects,
        "event_hooks": event_hooks,
        "headers": headers,
    }
    if transport is not None:
        kwargs["transport"] = transport

    return httpx.Client(**kwargs)


def create_safe_async_client(
    timeout: float = 30.0,
    max_redirects: int = 5,
    allow_private: bool = False,
    headers: dict[str, str] | None = None,
    resolve_dns: bool = True,
    transport: httpx.AsyncBaseTransport | None = None,
) -> httpx.AsyncClient:
    """Instantiate an httpx.AsyncClient configured with SSRF redirect validation hooks."""
    async def _validate_request_hook(request: httpx.Request) -> None:
        validate_url(str(request.url), allow_private=allow_private, resolve_dns=resolve_dns)

    async def _validate_response_hook(response: httpx.Response) -> None:
        location = response.headers.get("Location")
        if location and response.is_redirect:
            redirect_url = str(response.url.join(location))
            validate_url(redirect_url, allow_private=allow_private, resolve_dns=resolve_dns)

    event_hooks: dict[str, list[Any]] = {
        "request": [_validate_request_hook],
        "response": [_validate_response_hook],
    }

    kwargs: dict[str, Any] = {
        "timeout": timeout,
        "follow_redirects": True,
        "max_redirects": max_redirects,
        "event_hooks": event_hooks,
        "headers": headers,
    }
    if transport is not None:
        kwargs["transport"] = transport

    return httpx.AsyncClient(**kwargs)
