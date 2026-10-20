"""Native agent tool for retrieving live weather data and forecasts without API keys."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from icarus_contracts.tools import ToolDefinition, ToolResult, ToolSafetyCategory

from icarus_core.tools.base import BaseTool


class GetWeatherTool(BaseTool):
    """Tool allowing the agent to fetch live weather conditions and forecasts."""

    def __init__(self, timeout: float = 15.0) -> None:
        self.timeout = timeout
        self._definition = ToolDefinition(
            name="get_weather",
            description=(
                "Retrieve real-time weather conditions, temperature, humidity, wind, "
                "and multi-day forecasts for any city or location globally."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City name, postal code, or geographic location (e.g., 'Delhi', 'New York', '122103').",
                    },
                    "days": {
                        "type": "integer",
                        "description": "Number of forecast days to retrieve (1 to 3, default: 2).",
                    },
                },
                "required": ["location"],
            },
            safety_category=ToolSafetyCategory.SAFE_READ,
        )

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    def execute(
        self,
        arguments: dict[str, Any],
        workspace_root: Path | str,
        call_id: str = "direct_call",
    ) -> ToolResult:
        del workspace_root
        location = str(arguments.get("location", "")).strip()
        if not location:
            return ToolResult(
                call_id=call_id,
                name=self.name,
                output="",
                error="Required parameter 'location' is missing or empty.",
                exit_code=1,
            )

        days = int(arguments.get("days", 2))
        days = max(1, min(days, 3))

        encoded_loc = quote(location)
        url = f"https://wttr.in/{encoded_loc}?format=j1"

        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                resp = client.get(url, headers={"User-Agent": "curl/7.88.1"})
                if resp.status_code == 200:
                    data = resp.json()
                    curr = data.get("current_condition", [{}])[0]
                    temp_c = curr.get("temp_C", "N/A")
                    temp_f = curr.get("temp_F", "N/A")
                    desc = curr.get("weatherDesc", [{}])[0].get("value", "N/A")
                    humidity = curr.get("humidity", "N/A")
                    wind_speed = curr.get("windspeedKmph", "N/A")
                    feels_like_c = curr.get("FeelsLikeC", "N/A")

                    output_lines = [
                        f"Current Weather for {location}:",
                        f"  Condition: {desc}",
                        f"  Temperature: {temp_c}°C ({temp_f}°F) [Feels like: {feels_like_c}°C]",
                        f"  Humidity: {humidity}%",
                        f"  Wind Speed: {wind_speed} km/h",
                        "\nForecast:",
                    ]

                    for day_data in data.get("weather", [])[:days]:
                        date = day_data.get("date", "N/A")
                        max_c = day_data.get("maxtempC", "N/A")
                        min_c = day_data.get("mintempC", "N/A")
                        day_desc = (
                            day_data.get("hourly", [{}])[4]
                            .get("weatherDesc", [{}])[0]
                            .get("value", desc)
                        )
                        output_lines.append(
                            f"  • {date}: {day_desc}, High: {max_c}°C, Low: {min_c}°C"
                        )

                    return ToolResult(
                        call_id=call_id,
                        name=self.name,
                        output="\n".join(output_lines),
                        exit_code=0,
                    )
        except Exception:
            pass

        # Fallback to plain text format
        try:
            fallback_url = f"https://wttr.in/{encoded_loc}?0&T"
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                resp = client.get(fallback_url, headers={"User-Agent": "curl/7.88.1"})
                if resp.status_code == 200 and resp.text.strip():
                    return ToolResult(
                        call_id=call_id,
                        name=self.name,
                        output=f"Weather report for {location}:\n{resp.text}",
                        exit_code=0,
                    )
        except Exception as exc:
            return ToolResult(
                call_id=call_id,
                name=self.name,
                output="",
                error=f"Failed to fetch weather for '{location}': {exc}",
                exit_code=1,
            )

        return ToolResult(
            call_id=call_id,
            name=self.name,
            output="",
            error=f"Could not retrieve weather information for '{location}'.",
            exit_code=1,
        )
