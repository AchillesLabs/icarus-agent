"""Comprehensive security regression tests for SSRF protection policies."""

from unittest.mock import patch

import httpx
import pytest
from icarus_core.security.url_policy import (
    SSRFProtectionError,
    create_safe_client,
    is_ip_allowed,
    validate_url,
)
from icarus_core.tools.http import HttpRequestTool
from icarus_core.tools.web import FetchWebpageTool


def test_ip_filtering_rules():
    """Verify that private, loopback, link-local, multicast and metadata IPs are blocked."""
    # Loopback
    assert is_ip_allowed("127.0.0.1") is False
    assert is_ip_allowed("127.0.1.10") is False
    assert is_ip_allowed("::1") is False

    # Private
    assert is_ip_allowed("10.0.0.1") is False
    assert is_ip_allowed("172.16.5.1") is False
    assert is_ip_allowed("192.168.1.100") is False
    assert is_ip_allowed("fc00::1") is False

    # Link-local
    assert is_ip_allowed("169.254.0.1") is False
    assert is_ip_allowed("fe80::1") is False

    # Cloud metadata
    assert is_ip_allowed("169.254.169.254") is False
    assert is_ip_allowed("fd00:ec2::254") is False

    # Multicast & Unspecified
    assert is_ip_allowed("224.0.0.1") is False
    assert is_ip_allowed("ff02::1") is False
    assert is_ip_allowed("0.0.0.0") is False

    # Carrier-grade NAT
    assert is_ip_allowed("100.64.0.5") is False

    # Public routable IPs
    assert is_ip_allowed("8.8.8.8") is True
    assert is_ip_allowed("1.1.1.1") is True
    assert is_ip_allowed("93.184.215.14") is True
    assert is_ip_allowed("2606:4700:4700::1111") is True


def test_validate_url_forbidden_schemes():
    """Only HTTP and HTTPS schemes must be allowed."""
    with pytest.raises(SSRFProtectionError, match="Invalid URL scheme"):
        validate_url("file:///etc/passwd")

    with pytest.raises(SSRFProtectionError, match="Invalid URL scheme"):
        validate_url("gopher://127.0.0.1:70")

    with pytest.raises(SSRFProtectionError, match="Invalid URL scheme"):
        validate_url("ftp://server/resource")


def test_validate_url_cloud_metadata_and_localhost():
    """Cloud metadata endpoints and localhost hostnames must fail closed immediately."""
    with pytest.raises(SSRFProtectionError, match="forbidden internal destination"):
        validate_url("http://localhost/admin")

    with pytest.raises(SSRFProtectionError, match="forbidden internal destination"):
        validate_url("http://metadata.google.internal/computeMetadata/v1/")

    with pytest.raises(
        SSRFProtectionError, match="Destination IP .* is private, loopback, or cloud metadata"
    ):
        validate_url("http://169.254.169.254/latest/meta-data/")

    with pytest.raises(
        SSRFProtectionError, match="Destination IP .* is private, loopback, or cloud metadata"
    ):
        validate_url("http://[fd00:ec2::254]/latest/meta-data/")


def test_validate_url_private_ip_literals():
    """Private IP literals must be rejected without DNS lookup."""
    for forbidden in ["127.0.0.1", "10.10.10.10", "192.168.1.1", "172.20.0.1"]:
        with pytest.raises(
            SSRFProtectionError, match="Destination IP .* is private, loopback, or cloud metadata"
        ):
            validate_url(f"http://{forbidden}:8080/api")


def test_validate_url_dns_resolution_failure():
    """Domains resolving to loopback or private IPs must be blocked."""
    fake_addr_info = [
        (2, 1, 6, "", ("127.0.0.1", 80)),
    ]
    with (
        patch("socket.getaddrinfo", return_value=fake_addr_info),
        pytest.raises(SSRFProtectionError, match="resolved to forbidden IP"),
    ):
        validate_url("http://attacker-controlled-rebinding.com/steal")


def test_validate_url_permitted_public():
    """Public domain with valid public IP passes validation."""
    fake_addr_info = [
        (2, 1, 6, "", ("93.184.215.14", 443)),
    ]
    with patch("socket.getaddrinfo", return_value=fake_addr_info):
        safe_url = validate_url("https://example.com/test")
        assert safe_url == "https://example.com/test"


def test_http_request_tool_blocks_ssrf(tmp_path):
    """HttpRequestTool must reject attempts to access loopback or cloud metadata."""
    tool = HttpRequestTool()

    # Direct loopback attempt
    res = tool.execute({"url": "http://127.0.0.1:8000/internal"}, workspace_root=tmp_path)
    assert res.exit_code == 1
    assert "SSRF Protection Error" in res.error

    # Cloud metadata attempt
    res2 = tool.execute({"url": "http://169.254.169.254/latest"}, workspace_root=tmp_path)
    assert res2.exit_code == 1
    assert "SSRF Protection Error" in res2.error


def test_fetch_webpage_tool_blocks_ssrf(tmp_path):
    """FetchWebpageTool must reject attempts to access loopback or cloud metadata."""
    tool = FetchWebpageTool()

    res = tool.execute({"url": "http://127.0.0.1:5000/secret"}, workspace_root=tmp_path)
    assert res.exit_code == 1
    assert "SSRF Protection Error" in res.error


def test_redirect_to_private_ip_is_blocked():
    """create_safe_client event hook must catch and abort SSRF redirects."""

    def redirect_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/initial":
            return httpx.Response(
                302,
                headers={"Location": "http://169.254.169.254/latest/meta-data"},
            )
        return httpx.Response(200, text="Should not reach here")

    mock_transport = httpx.MockTransport(redirect_handler)
    client = create_safe_client(transport=mock_transport, resolve_dns=False)

    with pytest.raises(SSRFProtectionError, match="Destination IP .* is private"):
        client.get("http://safe-domain.org/initial")
