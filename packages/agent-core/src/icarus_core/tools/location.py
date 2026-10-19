"""Native agent tool for resolving current geographic location."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx
from icarus_contracts.tools import ToolDefinition, ToolResult, ToolSafetyCategory

from icarus_core.tools.base import BaseTool

logger = logging.getLogger(__name__)


class GetCurrentLocationTool(BaseTool):
    """Tool allowing the agent to resolve current approximate location for 'near me' queries."""

    def __init__(self, cache_ttl_seconds: int = 300) -> None:
        self._cached_result: dict[str, Any] | None = None

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="get_current_location",
            description=(
                "Retrieve the approximate current geographic location (city, region/state, "
                "country, latitude, longitude, postal code, and timezone) of the user or host machine. "
                "Call this tool whenever the user asks for places, hotels, restaurants, services, "
                "weather, or events 'near me' or within their current vicinity."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "ip": {
                        "type": "string",
                        "description": "Optional specific IP address to geolocate. If omitted, geolocates current host.",
                    }
                },
                "additionalProperties": False,
            },
            safety_category=ToolSafetyCategory.SAFE_READ,
        )

    def execute(
        self,
        arguments: dict[str, Any],
        workspace_root: Path | str,
        call_id: str = "direct_call",
    ) -> ToolResult:
        """Resolve current location via environment override or IP geolocation services."""
        # 1. Check for manual location override via environment
        env_override = os.environ.get("ICARUS_DEFAULT_LOCATION")
        if env_override:
            data = {
                "city": env_override,
                "region": "",
                "country": "",
                "source": "environment_override",
            }
            formatted = (
                f"Approximate Current Location (Configured Override):\n• Location: {env_override}"
            )
            return ToolResult(
                call_id=call_id,
                name=self.name,
                output=f"{formatted}\n\n```json\n{json.dumps(data, indent=2)}\n```",
                exit_code=0,
            )

        target_ip = arguments.get("ip") if arguments else None

        # 2. Return cached location if available and no specific IP requested
        if target_ip is None and self._cached_result is not None:
            formatted = self._format_location_output(self._cached_result)
            return ToolResult(
                call_id=call_id,
                name=self.name,
                output=formatted,
                exit_code=0,
            )

        # 3. Query geolocation providers with fallback
        location_data = self._fetch_location_with_fallback(target_ip=target_ip)
        if location_data:
            if target_ip is None:
                self._cached_result = location_data
            formatted = self._format_location_output(location_data)
            return ToolResult(
                call_id=call_id,
                name=self.name,
                output=formatted,
                exit_code=0,
            )

        return ToolResult(
            call_id=call_id,
            name=self.name,
            output=(
                "Unable to determine current geographic location via IP lookup. "
                "Please specify your city or postal code in your query."
            ),
            error="Geolocation lookup failed or timed out.",
            exit_code=1,
        )

    def _fetch_location_with_fallback(self, target_ip: str | None = None) -> dict[str, Any] | None:
        """Query primary and secondary IP geolocation APIs."""
        # Service 1: ipapi.co
        try:
            url = f"https://ipapi.co/{target_ip}/json/" if target_ip else "https://ipapi.co/json/"
            headers = {"User-Agent": "IcarusAgent/1.0"}
            with httpx.Client(timeout=4.0) as client:
                resp = client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    if not data.get("error"):
                        return {
                            "city": data.get("city", ""),
                            "region": data.get("region", ""),
                            "country": data.get("country_name", ""),
                            "country_code": data.get("country_code", ""),
                            "postal": data.get("postal", ""),
                            "latitude": data.get("latitude"),
                            "longitude": data.get("longitude"),
                            "timezone": data.get("timezone", ""),
                            "ip": data.get("ip", ""),
                        }
        except Exception as exc:
            logger.debug("Primary geolocation provider failed: %s", exc)

        # Service 2: ip-api.com fallback
        try:
            url = f"http://ip-api.com/json/{target_ip}" if target_ip else "http://ip-api.com/json/"
            with httpx.Client(timeout=4.0) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("status") == "success":
                        return {
                            "city": data.get("city", ""),
                            "region": data.get("regionName", ""),
                            "country": data.get("country", ""),
                            "country_code": data.get("countryCode", ""),
                            "postal": data.get("zip", ""),
                            "latitude": data.get("lat"),
                            "longitude": data.get("lon"),
                            "timezone": data.get("timezone", ""),
                            "ip": data.get("query", ""),
                        }
        except Exception as exc:
            logger.debug("Secondary geolocation provider failed: %s", exc)

        return None

    def _format_location_output(self, data: dict[str, Any]) -> str:
        """Format resolved location dictionary into readable Markdown text."""
        parts = ["Approximate Current Location:"]
        city = data.get("city")
        region = data.get("region")
        country = data.get("country")
        postal = data.get("postal")
        lat = data.get("latitude")
        lon = data.get("longitude")
        tz = data.get("timezone")

        if city:
            parts.append(f"• City: {city}")
        if region:
            parts.append(f"• Region / State: {region}")
        if country:
            code = f" ({data['country_code']})" if data.get("country_code") else ""
            parts.append(f"• Country: {country}{code}")
        if postal:
            parts.append(f"• Postal Code: {postal}")
        if lat is not None and lon is not None:
            parts.append(f"• Coordinates: {lat}, {lon}")
        if tz:
            parts.append(f"• Timezone: {tz}")

        summary = "\n".join(parts)
        json_block = json.dumps(data, indent=2)
        return f"{summary}\n\n```json\n{json_block}\n```"
