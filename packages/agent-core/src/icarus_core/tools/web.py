"""Native agent tools for live web search and webpage content extraction."""

from __future__ import annotations

import html
import os
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
from icarus_contracts.tools import ToolDefinition, ToolResult, ToolSafetyCategory

from icarus_core.tools.base import BaseTool

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36 IcarusAgent/0.1.0"
)


class HTMLToMarkdownExtractor(HTMLParser):
    """Cleanly extracts readable text/markdown from HTML documents.

    Strips boilerplate elements (scripts, styles, navigation, headers, footers)
    and formats headings, links, paragraphs, and list items.
    """

    IGNORED_TAGS = {
        "script",
        "style",
        "noscript",
        "svg",
        "head",
        "iframe",
        "nav",
        "footer",
        "header",
        "button",
        "form",
        "input",
        "select",
        "textarea",
    }

    BLOCK_TAGS = {
        "p",
        "div",
        "article",
        "section",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "tr",
        "blockquote",
        "pre",
    }

    def __init__(self) -> None:
        super().__init__()
        self._pieces: list[str] = []
        self._ignore_depth = 0
        self._current_link_url: str | None = None
        self._current_link_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_lower = tag.lower()
        if tag_lower in self.IGNORED_TAGS:
            self._ignore_depth += 1
            return
        if self._ignore_depth > 0:
            return

        if tag_lower in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(tag_lower[1])
            self._pieces.append(f"\n\n{'#' * level} ")
        elif tag_lower == "li":
            self._pieces.append("\n- ")
        elif tag_lower == "br":
            self._pieces.append("\n")
        elif tag_lower in self.BLOCK_TAGS:
            self._pieces.append("\n\n")
        elif tag_lower == "a":
            attrs_dict = dict(attrs)
            href = attrs_dict.get("href")
            if href and not href.startswith(("javascript:", "#")):
                self._current_link_url = href
                self._current_link_text = []

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        if tag_lower in self.IGNORED_TAGS:
            if self._ignore_depth > 0:
                self._ignore_depth -= 1
            return
        if self._ignore_depth > 0:
            return

        if tag_lower == "a" and self._current_link_url:
            link_text = "".join(self._current_link_text).strip()
            if link_text:
                self._pieces.append(f"[{link_text}]({self._current_link_url})")
            self._current_link_url = None
            self._current_link_text = []
        elif tag_lower in self.BLOCK_TAGS:
            self._pieces.append("\n")

    def handle_data(self, data: str) -> None:
        if self._ignore_depth > 0:
            return
        text = data.replace("\r", "")
        if self._current_link_url is not None:
            self._current_link_text.append(text)
        else:
            self._pieces.append(text)

    def get_markdown(self) -> str:
        """Return the cleaned, normalized markdown text."""
        raw = "".join(self._pieces)
        decoded = html.unescape(raw)
        # Collapse multiple horizontal whitespace while preserving single space
        collapsed = re.sub(r"[ \t]+", " ", decoded)
        # Collapse 3 or more newlines into 2 newlines
        collapsed = re.sub(r"\n{3,}", "\n\n", collapsed)
        # Strip each line and strip whole document
        lines = [line.strip() for line in collapsed.split("\n")]
        return "\n".join(lines).strip()


class DuckDuckGoHtmlParser(HTMLParser):
    """Parses search results from DuckDuckGo HTML search page."""

    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict[str, str]] = []
        self._current_title: list[str] = []
        self._current_snippet: list[str] = []
        self._current_url: str = ""
        self._in_title = False
        self._in_snippet = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        classes = attrs_dict.get("class", "").split()

        if tag == "a" and "result__snippet" in classes:
            self._in_snippet = True
        elif tag == "a" and "result__url" in classes:
            pass
        elif (tag == "a" and "result__title" in classes) or (
            tag == "a" and "result__snippet" not in classes and any("title" in c for c in classes)
        ):
            self._in_title = True
            href = attrs_dict.get("href", "")
            if href:
                # Unwrap duckduckgo redirect link if present (/l/?uddg=...)
                if "uddg=" in href:
                    parsed = urlparse(href)
                    qs = parse_qs(parsed.query)
                    self._current_url = qs.get("uddg", [href])[0]
                else:
                    self._current_url = href
        elif tag in ("h2", "h3") and any("title" in c for c in classes):
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if self._in_title and tag in ("a", "h2", "h3"):
            self._in_title = False
        elif self._in_snippet and tag in ("a", "div", "td"):
            self._in_snippet = False
            title = "".join(self._current_title).strip()
            snippet = "".join(self._current_snippet).strip()
            if title and self._current_url:
                self.results.append(
                    {
                        "title": title,
                        "url": self._current_url,
                        "snippet": snippet or "No snippet provided.",
                    }
                )
            self._current_title = []
            self._current_snippet = []
            self._current_url = ""

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._current_title.append(data)
        elif self._in_snippet:
            self._current_snippet.append(data)


class WebSearchTool(BaseTool):
    """Tool for searching the live internet and retrieving formatted results."""

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="web_search",
            description=(
                "Search the live internet for up-to-date facts, current events, flight prices, "
                "hotel availability, documentation, and real-world queries. "
                "Returns structured results with titles, source URLs, and descriptive snippets."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query keywords (e.g. 'flight prices NYC to London' or 'Python 3.12 release notes').",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of search results to return (default 5, max 10).",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
            safety_category=ToolSafetyCategory.SAFE_READ,
        )

    def execute(
        self,
        arguments: dict[str, Any],
        workspace_root: Path | str,
        call_id: str = "direct_call",
    ) -> ToolResult:
        query = str(arguments.get("query", "")).strip()
        if not query:
            return ToolResult(
                call_id=call_id,
                name="web_search",
                output="",
                error="Parameter 'query' cannot be empty.",
                exit_code=1,
            )

        max_results = min(max(int(arguments.get("max_results", 5)), 1), 10)

        # 1. Check for Brave Search API Key if configured
        brave_key = os.getenv("BRAVE_API_KEY")
        if brave_key:
            res = self._search_brave(query, max_results, brave_key, call_id)
            if res is not None:
                return res

        # 2. Universal DuckDuckGo HTML search fallback (no API key required)
        return self._search_duckduckgo(query, max_results, call_id)

    def _search_brave(
        self, query: str, max_results: int, api_key: str, call_id: str
    ) -> ToolResult | None:
        """Execute query using official Brave Search API."""
        url = "https://api.search.brave.com/res/v1/web/search"
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": api_key,
            "User-Agent": DEFAULT_USER_AGENT,
        }
        params = {"q": query, "count": max_results}
        try:
            client = self._client or httpx.Client(timeout=10.0)
            should_close = self._client is None
            try:
                resp = client.get(url, headers=headers, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    web_results = data.get("web", {}).get("results", [])
                    if web_results:
                        lines = [f'### Live Search Results for: "{query}"\n']
                        for i, r in enumerate(web_results[:max_results], 1):
                            title = r.get("title", "No Title")
                            url_val = r.get("url", "")
                            description = r.get("description", "")
                            lines.append(
                                f"{i}. **{title}**\n   URL: {url_val}\n   Snippet: {description}\n"
                            )
                        return ToolResult(
                            call_id=call_id,
                            name="web_search",
                            output="\n".join(lines).strip(),
                            exit_code=0,
                        )
            finally:
                if should_close:
                    client.close()
        except Exception:
            pass
        return None

    def _search_duckduckgo(self, query: str, max_results: int, call_id: str) -> ToolResult:
        """Execute query using DuckDuckGo HTML endpoint without requiring API keys."""
        url = "https://html.duckduckgo.com/html/"
        headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        data = {"q": query}

        try:
            client = self._client or httpx.Client(timeout=10.0, follow_redirects=True)
            should_close = self._client is None
            try:
                resp = client.post(url, headers=headers, data=data)
                if resp.status_code != 200:
                    return ToolResult(
                        call_id=call_id,
                        name="web_search",
                        output="",
                        error=f"Search service returned HTTP {resp.status_code}.",
                        exit_code=1,
                    )

                parser = DuckDuckGoHtmlParser()
                parser.feed(resp.text)

                if not parser.results:
                    return ToolResult(
                        call_id=call_id,
                        name="web_search",
                        output=f'No search results found for query: "{query}".',
                        exit_code=0,
                    )

                top_results = parser.results[:max_results]
                lines = [f'### Live Search Results for: "{query}"\n']
                for i, r in enumerate(top_results, 1):
                    lines.append(
                        f"{i}. **{r['title']}**\n   URL: {r['url']}\n   Snippet: {r['snippet']}\n"
                    )

                return ToolResult(
                    call_id=call_id,
                    name="web_search",
                    output="\n".join(lines).strip(),
                    exit_code=0,
                )
            finally:
                if should_close:
                    client.close()
        except httpx.TimeoutException:
            return ToolResult(
                call_id=call_id,
                name="web_search",
                output="",
                error=f"Web search timed out after 10.0 seconds while querying: '{query}'.",
                exit_code=1,
            )
        except Exception as exc:
            return ToolResult(
                call_id=call_id,
                name="web_search",
                output="",
                error=f"Web search failed: {exc}",
                exit_code=1,
            )


class FetchWebpageTool(BaseTool):
    """Tool for fetching and extracting readable text content from any web URL."""

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="fetch_webpage",
            description=(
                "Fetch and extract clean readable text from any web URL. "
                "Automatically removes boilerplate HTML, navigation menus, ads, and scripts, "
                "returning readable markdown content within token context limits."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The full HTTP/HTTPS URL of the webpage to fetch.",
                    },
                    "max_length": {
                        "type": "integer",
                        "description": "Maximum character length of the extracted content (default 8000, max 25000).",
                        "default": 8000,
                    },
                },
                "required": ["url"],
            },
            safety_category=ToolSafetyCategory.SAFE_READ,
        )

    def execute(
        self,
        arguments: dict[str, Any],
        workspace_root: Path | str,
        call_id: str = "direct_call",
    ) -> ToolResult:
        raw_url = str(arguments.get("url", "")).strip()
        if not raw_url:
            return ToolResult(
                call_id=call_id,
                name="fetch_webpage",
                output="",
                error="Parameter 'url' cannot be empty.",
                exit_code=1,
            )

        parsed_url = urlparse(raw_url)
        if parsed_url.scheme not in ("http", "https"):
            return ToolResult(
                call_id=call_id,
                name="fetch_webpage",
                output="",
                error=f"Invalid URL scheme '{parsed_url.scheme}'. Only http and https URLs are allowed.",
                exit_code=1,
            )

        max_length = min(max(int(arguments.get("max_length", 8000)), 500), 25000)

        headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

        try:
            client = self._client or httpx.Client(timeout=12.0, follow_redirects=True)
            should_close = self._client is None
            try:
                resp = client.get(raw_url, headers=headers)
                if resp.status_code >= 400:
                    return ToolResult(
                        call_id=call_id,
                        name="fetch_webpage",
                        output="",
                        error=f"HTTP {resp.status_code} Error fetching '{raw_url}': {resp.reason_phrase}",
                        exit_code=1,
                    )

                content_type = resp.headers.get("content-type", "").lower()
                if "text/plain" in content_type:
                    extracted = resp.text.strip()
                else:
                    extractor = HTMLToMarkdownExtractor()
                    extractor.feed(resp.text)
                    extracted = extractor.get_markdown()

                if not extracted:
                    extracted = "No readable content extracted from webpage."

                # Enforce max_length to protect token budget
                was_truncated = False
                if len(extracted) > max_length:
                    extracted = extracted[:max_length]
                    was_truncated = True

                result_output = f"### Webpage Content: {raw_url}\n\n{extracted}"
                if was_truncated:
                    result_output += f"\n\n[Content truncated at {max_length:,} characters to protect token budget]"

                return ToolResult(
                    call_id=call_id,
                    name="fetch_webpage",
                    output=result_output,
                    exit_code=0,
                )
            finally:
                if should_close:
                    client.close()
        except httpx.TimeoutException:
            return ToolResult(
                call_id=call_id,
                name="fetch_webpage",
                output="",
                error=f"Request to '{raw_url}' timed out after 12.0 seconds.",
                exit_code=1,
            )
        except Exception as exc:
            return ToolResult(
                call_id=call_id,
                name="fetch_webpage",
                output="",
                error=f"Failed to fetch webpage '{raw_url}': {exc}",
                exit_code=1,
            )
