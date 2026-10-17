"""Security validation and boundary jailing for agent tools."""

from __future__ import annotations

from pathlib import Path

from icarus_contracts.exceptions import WorkspaceJailError


def resolve_workspace_path(path: str | Path, workspace_root: Path | str) -> Path:
    """Resolve and validate a path to ensure it is strictly contained within workspace_root.

    Raises WorkspaceJailError if the resolved path attempts to escape workspace boundaries.
    """
    root = Path(workspace_root).resolve()
    target_path = Path(path) if str(path).strip() else Path(".")

    if not target_path.is_absolute():
        resolved = (root / target_path).resolve()
    else:
        resolved = target_path.resolve()

    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise WorkspaceJailError(
            f"Path traversal denied: '{path}' escapes workspace boundary '{root}'."
        ) from exc

    return resolved
