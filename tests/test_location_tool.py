"""Tests for GetCurrentLocationTool and geolocation resolution."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from icarus_contracts.tools import ToolSafetyCategory
from icarus_core.tools.location import GetCurrentLocationTool
from icarus_core.tools.registry import create_default_registry


def test_location_tool_definition():
    """Verify tool metadata, name, schema, and safety category."""
    tool = GetCurrentLocationTool()
    definition = tool.definition

    assert definition.name == "get_current_location"
    assert "geographic location" in definition.description
    assert definition.safety_category == ToolSafetyCategory.SAFE_READ
    assert "ip" in definition.parameters["properties"]


def test_location_tool_environment_override(monkeypatch, tmp_path: Path):
    """Setting ICARUS_DEFAULT_LOCATION short-circuits network calls."""
    monkeypatch.setenv("ICARUS_DEFAULT_LOCATION", "Austin, TX, USA")
    tool = GetCurrentLocationTool()

    result = tool.execute(arguments={}, workspace_root=tmp_path)
    assert result.exit_code == 0
    assert "Austin, TX, USA" in result.output
    assert "environment_override" in result.output


def test_location_tool_primary_success(tmp_path: Path):
    """Primary provider ipapi.co returns valid city and region."""
    tool = GetCurrentLocationTool()
    mock_payload = {
        "city": "Seattle",
        "region": "Washington",
        "country_name": "United States",
        "country_code": "US",
        "postal": "98101",
        "latitude": 47.6062,
        "longitude": -122.3321,
        "timezone": "America/Los_Angeles",
        "ip": "1.2.3.4",
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_payload

    with patch("httpx.Client.get", return_value=mock_resp) as mock_get:
        result = tool.execute(arguments={}, workspace_root=tmp_path)
        assert result.exit_code == 0
        assert "Seattle" in result.output
        assert "Washington" in result.output
        assert "United States (US)" in result.output
        assert "America/Los_Angeles" in result.output
        assert mock_get.called


def test_location_tool_fallback_success(tmp_path: Path):
    """Secondary provider ip-api.com is called when primary fails."""
    tool = GetCurrentLocationTool()
    mock_resp_fallback = MagicMock()
    mock_resp_fallback.status_code = 200
    mock_resp_fallback.json.return_value = {
        "status": "success",
        "city": "London",
        "regionName": "England",
        "country": "United Kingdom",
        "countryCode": "GB",
        "zip": "SW1A 1AA",
        "lat": 51.5074,
        "lon": -0.1278,
        "timezone": "Europe/London",
        "query": "8.8.8.8",
    }

    # First call raises, second call returns mock_resp_fallback
    with patch(
        "httpx.Client.get",
        side_effect=[Exception("ipapi connection failed"), mock_resp_fallback],
    ):
        result = tool.execute(arguments={"ip": "8.8.8.8"}, workspace_root=tmp_path)
        assert result.exit_code == 0
        assert "London" in result.output
        assert "United Kingdom (GB)" in result.output


def test_location_tool_caching(tmp_path: Path):
    """Repeated calls with no IP return cached result without hitting network again."""
    tool = GetCurrentLocationTool()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "city": "Tokyo",
        "region": "Tokyo",
        "country_name": "Japan",
        "country_code": "JP",
    }

    with patch("httpx.Client.get", return_value=mock_resp) as mock_get:
        res1 = tool.execute(arguments={}, workspace_root=tmp_path)
        assert res1.exit_code == 0
        assert "Tokyo" in res1.output
        assert mock_get.call_count == 1

        # Second call: uses cache
        res2 = tool.execute(arguments={}, workspace_root=tmp_path)
        assert res2.exit_code == 0
        assert "Tokyo" in res2.output
        assert mock_get.call_count == 1


def test_location_tool_failure(tmp_path: Path):
    """Total failure produces graceful error message."""
    tool = GetCurrentLocationTool()

    with patch("httpx.Client.get", side_effect=Exception("Network unreachable")):
        result = tool.execute(arguments={}, workspace_root=tmp_path)
        assert result.exit_code == 1
        assert "Unable to determine current geographic location" in result.output


def test_registry_includes_location_tool():
    """create_default_registry automatically registers get_current_location."""
    reg = create_default_registry(load_mcp=False)
    assert reg.has("get_current_location")
    tool = reg.get("get_current_location")
    assert isinstance(tool, GetCurrentLocationTool)
