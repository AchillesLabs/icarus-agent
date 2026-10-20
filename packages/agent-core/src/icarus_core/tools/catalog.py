"""Catalog of pre-configured essential integrations and tool connectors."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolConnector:
    """Pre-configured tool connector specification for 1-click or wizard setup."""

    id: str
    name: str
    category: str
    description: str
    package: str
    command: str
    args: list[str] = field(default_factory=list)
    env_vars: list[str] = field(default_factory=list)
    doc_url: str = ""
    is_built_in: bool = False


ESSENTIAL_CATALOG: list[ToolConnector] = [
    # 1. Web & Browser Automation
    ToolConnector(
        id="browser",
        name="Browser Automation (Puppeteer)",
        category="Web & Browser",
        description="Headless Chrome browser automation to visit websites, click buttons, fill forms, and take screenshots.",
        package="@modelcontextprotocol/server-puppeteer",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-puppeteer"],
        doc_url="https://github.com/modelcontextprotocol/servers/tree/main/src/puppeteer",
    ),
    ToolConnector(
        id="brave-search",
        name="Brave Web Search API",
        category="Web & Browser",
        description="Search the web with Brave Search API for news, pages, and rich answers.",
        package="@modelcontextprotocol/server-brave-search",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-brave-search"],
        env_vars=["BRAVE_API_KEY"],
        doc_url="https://brave.com/search/api/",
    ),
    # 2. Payments & Commerce
    ToolConnector(
        id="stripe",
        name="Stripe Payments & Invoicing",
        category="Finance & Payments",
        description="Create charges, payment links, customer invoices, refund payments, and inspect balances.",
        package="@stripe/mcp",
        command="npx",
        args=["-y", "@stripe/mcp"],
        env_vars=["STRIPE_SECRET_KEY"],
        doc_url="https://stripe.com/docs/api",
    ),
    # 3. Developer & Code
    ToolConnector(
        id="github",
        name="GitHub Operations",
        category="Developer & Code",
        description="Interact with GitHub repositories, pull requests, issues, commits, branches, and code search.",
        package="@modelcontextprotocol/server-github",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-github"],
        env_vars=["GITHUB_PERSONAL_ACCESS_TOKEN"],
        doc_url="https://github.com/settings/tokens",
    ),
    ToolConnector(
        id="postgres",
        name="PostgreSQL Database",
        category="Databases",
        description="Inspect schemas, run read queries, and analyze data in a PostgreSQL database.",
        package="@modelcontextprotocol/server-postgres",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-postgres"],
        env_vars=["POSTGRES_CONNECTION_STRING"],
        doc_url="https://github.com/modelcontextprotocol/servers/tree/main/src/postgres",
    ),
    ToolConnector(
        id="sqlite",
        name="SQLite Database",
        category="Databases",
        description="Query, inspect, and analyze local SQLite database files.",
        package="mcp-server-sqlite",
        command="uvx",
        args=["mcp-server-sqlite", "--db-path", "database.db"],
        doc_url="https://github.com/modelcontextprotocol/servers/tree/main/src/sqlite",
    ),
    # 4. Communication & Messaging
    ToolConnector(
        id="slack",
        name="Slack Workspaces",
        category="Communication",
        description="Post messages to channels, reply to threads, and search conversation history in Slack.",
        package="@modelcontextprotocol/server-slack",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-slack"],
        env_vars=["SLACK_BOT_TOKEN", "SLACK_TEAM_ID"],
        doc_url="https://api.slack.com/apps",
    ),
    # 5. Maps & Travel
    ToolConnector(
        id="google-maps",
        name="Google Maps & Places",
        category="Travel & Navigation",
        description="Search places, addresses, routing, elevation, and point-of-interest details.",
        package="@modelcontextprotocol/server-google-maps",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-google-maps"],
        env_vars=["GOOGLE_MAPS_API_KEY"],
        doc_url="https://developers.google.com/maps",
    ),
    # 6. Built-in Core Essentials
    ToolConnector(
        id="http-request",
        name="Universal REST & Webhooks",
        category="APIs & Webhooks",
        description="Send GET/POST/PUT/DELETE requests to any external API, payment link, or booking service.",
        package="built-in",
        command="built-in",
        is_built_in=True,
    ),
    ToolConnector(
        id="weather",
        name="Live Weather & Forecasts",
        category="Travel & Navigation",
        description="Real-time temperature, conditions, and multi-day forecasts for any city worldwide.",
        package="built-in",
        command="built-in",
        is_built_in=True,
    ),
    ToolConnector(
        id="web-search",
        name="Live Internet Search",
        category="Web & Browser",
        description="Search the live internet for up-to-date facts, links, and current information.",
        package="built-in",
        command="built-in",
        is_built_in=True,
    ),
]


def get_connector(connector_id: str) -> ToolConnector | None:
    """Retrieve connector specification by ID."""
    for c in ESSENTIAL_CATALOG:
        if c.id.lower() == connector_id.lower():
            return c
    return None
