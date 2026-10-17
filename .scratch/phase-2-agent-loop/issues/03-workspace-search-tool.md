# 03: Workspace Search Tool (search) with Regex and Glob Filtering

**What to build:** A high-speed text and regex search tool (`search`) that scans files across the workspace. It supports case sensitivity toggles, file pattern glob filtering (e.g. `*.py`), and bounded result snippets (line numbers and matched text lines) with total match capping to protect context windows. Callable by the model through the tool registry, safe for automated execution within the workspace.

**Blocked by:**
- 02: Tool Contracts and Read-Only Filesystem Tools (read_file, list_dir)

**Status:** ready-for-agent

- [ ] `search` tool implemented under `icarus_core.tools.search` supporting regex and literal text queries.
- [ ] Includes glob inclusion/exclusion filtering (e.g., ignoring `.git/`, `.venv/`, binary files).
- [ ] Results return structured JSON containing file paths, line numbers, and snippets, bounded to a maximum match limit (default 50 matches).
- [ ] Registered as a `SAFE_READ` tool in the tool registry.
- [ ] Comprehensive unit tests verify exact pattern matching, regex mode, glob filtering, and output truncation.
