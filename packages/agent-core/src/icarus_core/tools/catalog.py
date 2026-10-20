"""Catalog of pre-configured essential integrations and tool connectors."""

from __future__ import annotations

from dataclasses import dataclass, field


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
    # 1. Communication & Personal Productivity
    ToolConnector(
        id="gmail",
        name="Gmail (Search, Read & Send)",
        category="Communication",
        description="Search inbox, read email threads, and send messages with interactive approval (Free Google App Password or OAuth).",
        package="built-in & mcp",
        command="built-in",
        env_vars=["GMAIL_APP_PASSWORD"],
        doc_url="https://myaccount.google.com/apppasswords",
        is_built_in=True,
    ),
    ToolConnector(
        id="calendar",
        name="Google Calendar & Agenda",
        category="Scheduling & Calendar",
        description="Search agenda, view upcoming events, and schedule meetings on your calendar.",
        package="built-in & mcp",
        command="built-in",
        env_vars=["GOOGLE_CALENDAR_TOKEN"],
        doc_url="https://myaccount.google.com/apppasswords",
        is_built_in=True,
    ),
    # 2. 1-Click Ecosystem & Managed OAuth
    ToolConnector(
        id="composio",
        name="Composio Tool Hub (250+ Free Apps)",
        category="App Ecosystem & OAuth",
        description="Connect 250+ apps (Gmail, Calendar, Notion, Jira, Slack, GitHub) with 1-click browser OAuth (no API key hassle).",
        package="composio-core",
        command="npx",
        args=["-y", "composio-core", "mcp"],
        env_vars=["COMPOSIO_API_KEY"],
        doc_url="https://app.composio.dev",
    ),
    # 3. Web & Browser Automation
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
    # 4. Payments & Commerce
    ToolConnector(
        id="stripe",
        name="Stripe Payments & Invoicing",
        category="Finance & Payments",
        description="Create charges, payment links, customer invoices, refund payments, and inspect balances.",
        package="@stripe/mcp",
        command="npx",
        args=["-y", "@stripe/mcp"],
        env_vars=["STRIPE_SECRET_KEY"],
        doc_url="https://dashboard.stripe.com/apikeys",
    ),
    # 5. Developer & Code
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
    # 6. Communication & Messaging
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
    # 7. Maps & Travel
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
    # 8. Built-in Core Essentials
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

CONNECTOR_ALIASES: dict[str, str] = {
    "gmail": "gmail",
    "email": "gmail",
    "mail": "gmail",
    "google-mail": "gmail",
    "gsuite": "gmail",
    "google": "gmail",
    "calendar": "calendar",
    "cal": "calendar",
    "gcal": "calendar",
    "google-calendar": "calendar",
    "composio": "composio",
    "composio-mcp": "composio",
    "apps": "composio",
    "oauth": "composio",
    "browser": "browser",
    "puppeteer": "browser",
    "chrome": "browser",
    "web": "browser",
    "github": "github",
    "gh": "github",
    "git": "github",
    "stripe": "stripe",
    "pay": "stripe",
    "payment": "stripe",
    "payments": "stripe",
    "slack": "slack",
    "maps": "google-maps",
    "google-maps": "google-maps",
    "places": "google-maps",
    "postgres": "postgres",
    "postgresql": "postgres",
    "pg": "postgres",
    "sqlite": "sqlite",
    "sql": "sqlite",
    "weather": "weather",
    "http": "http-request",
    "http-request": "http-request",
    "search": "web-search",
    "web-search": "web-search",
}


def get_connector(connector_id: str) -> ToolConnector | None:
    """Retrieve connector specification by ID or alias."""
    cid = connector_id.lower().strip()
    canonical = CONNECTOR_ALIASES.get(cid, cid)
    for c in ESSENTIAL_CATALOG:
        if c.id.lower() == canonical:
            return c
    return None
