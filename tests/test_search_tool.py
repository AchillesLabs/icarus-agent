"""Tests for the workspace search tool: SearchTool."""

import json
from pathlib import Path

from icarus_core.tools.search import SearchTool


def test_search_exact_literal_match(tmp_path: Path):
    """SearchTool finds exact text matches across files in workspace."""
    (tmp_path / "file1.txt").write_text("first line\nhello world\nthird line\n", encoding="utf-8")
    (tmp_path / "file2.py").write_text("def hello():\n    return 'world'\n", encoding="utf-8")
    (tmp_path / "other.txt").write_text("nothing here\n", encoding="utf-8")

    tool = SearchTool()
    result = tool.execute({"query": "hello"}, workspace_root=tmp_path)

    assert result.exit_code == 0
    assert result.error is None
    matches = json.loads(result.output)
    assert len(matches) == 2

    # Verify structured fields
    files = {m["file"] for m in matches}
    assert "file1.txt" in files
    assert "file2.py" in files

    m1 = next(m for m in matches if m["file"] == "file1.txt")
    assert m1["line_number"] == 2
    assert m1["snippet"] == "hello world"

    m2 = next(m for m in matches if m["file"] == "file2.py")
    assert m2["line_number"] == 1
    assert m2["snippet"] == "def hello():"


def test_search_case_sensitivity(tmp_path: Path):
    """SearchTool respects case_sensitive toggle."""
    (tmp_path / "fruits.txt").write_text("Apple\napple\nAPPLE\nbanana\n", encoding="utf-8")

    tool = SearchTool()

    # Case-insensitive by default
    res_ci = tool.execute({"query": "apple"}, workspace_root=tmp_path)
    assert res_ci.exit_code == 0
    matches_ci = json.loads(res_ci.output)
    assert len(matches_ci) == 3
    assert [m["line_number"] for m in matches_ci] == [1, 2, 3]

    # Explicit case-sensitive search for 'Apple'
    res_cs1 = tool.execute({"query": "Apple", "case_sensitive": True}, workspace_root=tmp_path)
    assert res_cs1.exit_code == 0
    matches_cs1 = json.loads(res_cs1.output)
    assert len(matches_cs1) == 1
    assert matches_cs1[0]["line_number"] == 1
    assert matches_cs1[0]["snippet"] == "Apple"

    # Explicit case-sensitive search for 'apple'
    res_cs2 = tool.execute({"query": "apple", "case_sensitive": True}, workspace_root=tmp_path)
    assert res_cs2.exit_code == 0
    matches_cs2 = json.loads(res_cs2.output)
    assert len(matches_cs2) == 1
    assert matches_cs2[0]["line_number"] == 2
    assert matches_cs2[0]["snippet"] == "apple"


def test_search_regex_mode(tmp_path: Path):
    """SearchTool evaluates regular expressions when regex=True."""
    (tmp_path / "data.py").write_text(
        "user_id = 1234\norder_id = 5678\nitem = 'apple'\n",
        encoding="utf-8",
    )

    tool = SearchTool()

    # Regex search
    res_regex = tool.execute(
        {"query": r"(\w+)_id\s*=\s*\d+", "regex": True},
        workspace_root=tmp_path,
    )
    assert res_regex.exit_code == 0
    matches = json.loads(res_regex.output)
    assert len(matches) == 2
    assert matches[0]["snippet"] == "user_id = 1234"
    assert matches[1]["snippet"] == "order_id = 5678"

    # Literal search with regex metacharacters does not match
    res_literal = tool.execute(
        {"query": r"(\w+)_id\s*=\s*\d+", "regex": False},
        workspace_root=tmp_path,
    )
    assert res_literal.exit_code == 0
    assert json.loads(res_literal.output) == []


def test_search_invalid_regex(tmp_path: Path):
    """SearchTool returns structured error on malformed regex syntax."""
    tool = SearchTool()
    res = tool.execute(
        {"query": r"([a-z+", "regex": True},
        workspace_root=tmp_path,
    )
    assert res.exit_code == 1
    assert "invalid regular expression" in res.error.lower()


def test_search_glob_filtering(tmp_path: Path):
    """SearchTool filters files by include_pattern and exclude_pattern."""
    (tmp_path / "main.py").write_text("common_token = 1\n", encoding="utf-8")
    (tmp_path / "main_test.py").write_text("common_token = 2\n", encoding="utf-8")
    (tmp_path / "docs.md").write_text("common_token in docs\n", encoding="utf-8")
    (tmp_path / "styles.css").write_text("/* common_token */\n", encoding="utf-8")

    tool = SearchTool()

    # Include only *.py
    res_py = tool.execute(
        {"query": "common_token", "include_pattern": "*.py"},
        workspace_root=tmp_path,
    )
    assert res_py.exit_code == 0
    matches_py = json.loads(res_py.output)
    files_py = {m["file"] for m in matches_py}
    assert files_py == {"main.py", "main_test.py"}

    # Include *.py but exclude *test*
    res_filtered = tool.execute(
        {"query": "common_token", "include_pattern": "*.py", "exclude_pattern": "*test*"},
        workspace_root=tmp_path,
    )
    assert res_filtered.exit_code == 0
    matches_filtered = json.loads(res_filtered.output)
    assert len(matches_filtered) == 1
    assert matches_filtered[0]["file"] == "main.py"


def test_search_ignores_noise_and_binary(tmp_path: Path):
    """SearchTool ignores noise directories (.git, .venv, etc.) and binary files."""
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("target_token\n", encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "lib.py").write_text("target_token\n", encoding="utf-8")

    # Binary file
    (tmp_path / "binary.bin").write_bytes(b"target_token\x00\x01\x02\x03data")

    # Valid text file
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "valid.py").write_text("target_token\n", encoding="utf-8")

    tool = SearchTool()
    res = tool.execute({"query": "target_token"}, workspace_root=tmp_path)

    assert res.exit_code == 0
    matches = json.loads(res.output)
    assert len(matches) == 1
    assert matches[0]["file"].replace("\\", "/") == "src/valid.py"


def test_search_max_matches_truncation(tmp_path: Path):
    """SearchTool bounds results to default 50 matches and respects custom max_matches."""
    # Create file with 100 matching lines
    content = "\n".join(f"item_{i} match_me" for i in range(100))
    (tmp_path / "large.txt").write_text(content, encoding="utf-8")

    tool = SearchTool()

    # Default limit should cap at 50
    res_default = tool.execute({"query": "match_me"}, workspace_root=tmp_path)
    assert res_default.exit_code == 0
    matches_default = json.loads(res_default.output)
    assert len(matches_default) == 50
    assert matches_default[0]["line_number"] == 1
    assert matches_default[49]["line_number"] == 50

    # Custom limit of 10
    res_custom = tool.execute({"query": "match_me", "max_matches": 10}, workspace_root=tmp_path)
    assert res_custom.exit_code == 0
    matches_custom = json.loads(res_custom.output)
    assert len(matches_custom) == 10

    # Alias 'limit' also supported
    res_alias = tool.execute({"query": "match_me", "limit": 7}, workspace_root=tmp_path)
    assert res_alias.exit_code == 0
    matches_alias = json.loads(res_alias.output)
    assert len(matches_alias) == 7


def test_search_missing_query(tmp_path: Path):
    """SearchTool returns error when query is empty or missing."""
    tool = SearchTool()
    res = tool.execute({}, workspace_root=tmp_path)
    assert res.exit_code == 1
    assert "missing required argument" in res.error.lower()

    res_empty = tool.execute({"query": "   "}, workspace_root=tmp_path)
    assert res_empty.exit_code == 1
    assert "missing required argument" in res_empty.error.lower()


def test_search_workspace_traversal_denied(tmp_path: Path):
    """SearchTool catches WorkspaceJailError and blocks path traversal attempts."""
    workspace = tmp_path / "jail"
    workspace.mkdir()

    tool = SearchTool()
    res = tool.execute({"query": "token", "path": "../outside"}, workspace_root=workspace)
    assert res.exit_code == 1
    assert "escapes workspace" in res.error.lower() or "traversal" in res.error.lower()


def test_search_path_not_found(tmp_path: Path):
    """SearchTool returns error when target path does not exist."""
    tool = SearchTool()
    res = tool.execute({"query": "token", "path": "does_not_exist"}, workspace_root=tmp_path)
    assert res.exit_code == 1
    assert "not found" in res.error.lower()


def test_search_targeted_single_file(tmp_path: Path):
    """SearchTool searches only the target file when path points to a file."""
    (tmp_path / "a.py").write_text("match_target\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("match_target\n", encoding="utf-8")

    tool = SearchTool()
    res = tool.execute({"query": "match_target", "path": "a.py"}, workspace_root=tmp_path)
    assert res.exit_code == 0
    matches = json.loads(res.output)
    assert len(matches) == 1
    assert matches[0]["file"] == "a.py"
