# 02: Native Live Web Search and Webpage Content Extraction Tools (web_search, fetch_webpage)

**GitHub Issue:** [#50](https://github.com/AchillesLabs/icarus-agent/issues/50)
**Parent Spec:** [#41](https://github.com/AchillesLabs/icarus-agent/issues/41)

**What to build:** Native agent tools for querying the live internet (web_search) with multi-engine resilience (DuckDuckGo HTML / Brave Search fallback) returning structured results (title, snippet, url), and clean webpage reading (fetch_webpage) extracting readable text from HTML with automatic boilerplate, script, and styling removal.

**Blocked by:** None (can start immediately)

**Status:** closed

## Acceptance criteria

- [x] Implement WebSearchTool registered in agent ToolRegistry querying live search engine without requiring mandatory API keys (DuckDuckGo fallback), returning top formatted results.
- [x] Implement FetchWebpageTool registered in ToolRegistry extracting clean text/markdown from URLs with automatic header/nav/footer/script stripping.
- [x] Enforce request timeouts, content length limits, and anti-abuse user-agent headers to protect token context budgets.
- [x] Inject web tools into default agent workspace registry and conversation prompt loop.
- [x] Automated unit and mock integration tests verify search query parsing, markdown extraction, error handling for HTTP 4xx/5xx, and token truncation.
