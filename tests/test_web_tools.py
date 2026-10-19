"""Unit and mock integration tests for WebSearchTool and FetchWebpageTool."""

from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from icarus_core.tools.web import FetchWebpageTool, HTMLToMarkdownExtractor, WebSearchTool


def test_html_to_markdown_extractor_basic():
    """HTMLToMarkdownExtractor strips scripts/nav and formats headers, links, and lists."""
    html_doc = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Test Page</title>
        <script>alert('bad');</script>
        <style>body { color: red; }</style>
    </head>
    <body>
        <nav><a href="/menu">Menu</a></nav>
        <header><h1>Site Header</h1></header>
        <article>
            <h1>Main Title</h1>
            <p>Welcome to our <b>agent platform</b>. Visit <a href="https://icarus.ai">Icarus AI</a>.</p>
            <ul>
                <li>Autonomous workflows</li>
                <li>Browser automation</li>
            </ul>
        </article>
        <footer><p>&copy; 2026 Company</p></footer>
    </body>
    </html>
    """
    extractor = HTMLToMarkdownExtractor()
    extractor.feed(html_doc)
    md = extractor.get_markdown()

    assert "Site Header" not in md  # inside <header>
    assert "alert" not in md  # inside <script>
    assert "body {" not in md  # inside <style>
    assert "Menu" not in md  # inside <nav>
    assert "# Main Title" in md
    assert "Welcome to our agent platform" in md
    assert "[Icarus AI](https://icarus.ai)" in md
    assert "- Autonomous workflows" in md
    assert "- Browser automation" in md


def test_fetch_webpage_empty_and_invalid_scheme(tmp_path: Path):
    """FetchWebpageTool validates empty URL and invalid schemes."""
    tool = FetchWebpageTool()

    # Empty URL
    res1 = tool.execute({}, workspace_root=tmp_path)
    assert res1.exit_code == 1
    assert "cannot be empty" in res1.error

    # Invalid scheme
    res2 = tool.execute({"url": "ftp://files.example.com"}, workspace_root=tmp_path)
    assert res2.exit_code == 1
    assert "Invalid URL scheme" in res2.error


def test_fetch_webpage_success_and_truncation(tmp_path: Path):
    """FetchWebpageTool fetches HTML and truncates to max_length if budget is exceeded."""
    html_content = "<html><body><h1>News</h1><p>" + ("Important article text. " * 200) + "</p></body></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html_content, headers={"Content-Type": "text/html; charset=utf-8"})

    mock_client = httpx.Client(transport=httpx.MockTransport(handler))
    tool = FetchWebpageTool(client=mock_client)

    result = tool.execute({"url": "https://news.example.com", "max_length": 500}, workspace_root=tmp_path)
    assert result.exit_code == 0
    assert "### Webpage Content: https://news.example.com" in result.output
    assert "Important article text" in result.output
    assert "[Content truncated at 500 characters to protect token budget]" in result.output


def test_fetch_webpage_plain_text(tmp_path: Path):
    """FetchWebpageTool handles text/plain response directly without HTML parser."""
    plain_text = "Line 1 of robots.txt\nDisallow: /admin"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=plain_text, headers={"Content-Type": "text/plain"})

    mock_client = httpx.Client(transport=httpx.MockTransport(handler))
    tool = FetchWebpageTool(client=mock_client)

    result = tool.execute({"url": "https://example.com/robots.txt"}, workspace_root=tmp_path)
    assert result.exit_code == 0
    assert "Disallow: /admin" in result.output


def test_fetch_webpage_http_error(tmp_path: Path):
    """FetchWebpageTool handles HTTP 404/500 errors gracefully as ToolResult."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    mock_client = httpx.Client(transport=httpx.MockTransport(handler))
    tool = FetchWebpageTool(client=mock_client)

    result = tool.execute({"url": "https://example.com/not-found"}, workspace_root=tmp_path)
    assert result.exit_code == 1
    assert "HTTP 404 Error" in result.error


def test_fetch_webpage_timeout(tmp_path: Path):
    """FetchWebpageTool handles network timeouts cleanly."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("Connection timed out")

    mock_client = httpx.Client(transport=httpx.MockTransport(handler))
    tool = FetchWebpageTool(client=mock_client)

    result = tool.execute({"url": "https://slow.example.com"}, workspace_root=tmp_path)
    assert result.exit_code == 1
    assert "timed out" in result.error.lower()


def test_web_search_empty_query(tmp_path: Path):
    """WebSearchTool returns validation error for empty query."""
    tool = WebSearchTool()
    result = tool.execute({"query": ""}, workspace_root=tmp_path)
    assert result.exit_code == 1
    assert "cannot be empty" in result.error


def test_web_search_duckduckgo_parsing(tmp_path: Path):
    """WebSearchTool parses DuckDuckGo HTML results with titles, snippets, and unquoted URLs."""
    ddg_html = """
    <html>
    <body>
        <div class="result">
            <h2 class="result__title">
                <a class="result__title" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.delta.com%2Fflights">Delta Air Lines Flights</a>
            </h2>
            <a class="result__snippet" href="#">Find cheap flights and book tickets directly with Delta.</a>
        </div>
        <div class="result">
            <h2 class="result__title">
                <a class="result__title" href="https://www.united.com">United Airlines</a>
            </h2>
            <a class="result__snippet" href="#">Plan your next vacation with United flights and hotels.</a>
        </div>
    </body>
    </html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/html/"
        return httpx.Response(200, text=ddg_html, headers={"Content-Type": "text/html"})

    mock_client = httpx.Client(transport=httpx.MockTransport(handler))
    tool = WebSearchTool(client=mock_client)

    result = tool.execute({"query": "cheap flights to NYC", "max_results": 2}, workspace_root=tmp_path)
    assert result.exit_code == 0
    assert "### Live Search Results for: \"cheap flights to NYC\"" in result.output
    assert "1. **Delta Air Lines Flights**" in result.output
    assert "https://www.delta.com/flights" in result.output
    assert "Find cheap flights and book tickets" in result.output
    assert "2. **United Airlines**" in result.output
    assert "https://www.united.com" in result.output


def test_web_search_duckduckgo_no_results(tmp_path: Path):
    """WebSearchTool returns informative message when no results are found."""
    empty_html = "<html><body><div class='no-results'>No results found.</div></body></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=empty_html)

    mock_client = httpx.Client(transport=httpx.MockTransport(handler))
    tool = WebSearchTool(client=mock_client)

    result = tool.execute({"query": "kjashdkjasd786asdasd"}, workspace_root=tmp_path)
    assert result.exit_code == 0
    assert "No search results found" in result.output


def test_web_search_brave_api_integration(tmp_path: Path):
    """WebSearchTool uses Brave Search API when BRAVE_API_KEY is configured."""
    brave_json = {
        "web": {
            "results": [
                {
                    "title": "Brave Official Search",
                    "url": "https://brave.com/search",
                    "description": "Private search engine by Brave.",
                }
            ]
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("X-Subscription-Token") == "brave-test-key"
        return httpx.Response(200, json=brave_json)

    mock_client = httpx.Client(transport=httpx.MockTransport(handler))
    tool = WebSearchTool(client=mock_client)

    with patch.dict("os.environ", {"BRAVE_API_KEY": "brave-test-key"}):
        result = tool.execute({"query": "private search"}, workspace_root=tmp_path)
        assert result.exit_code == 0
        assert "Brave Official Search" in result.output
        assert "https://brave.com/search" in result.output
        assert "Private search engine by Brave." in result.output
