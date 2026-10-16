"""Architectural boundary tests enforcing module decoupling rules."""

import ast
from pathlib import Path


def get_all_imports_in_dir(directory: Path) -> list[tuple[Path, str]]:
    """Scan all Python files in a directory and return (file_path, imported_module_name)."""
    imports: list[tuple[Path, str]] = []
    for py_file in directory.rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append((py_file, alias.name))
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append((py_file, node.module))
    return imports


def test_contracts_has_zero_internal_package_dependencies():
    """packages/contracts must never import icarus_core or icarus_cli."""
    contracts_dir = Path("packages/contracts/src/icarus_contracts")
    assert contracts_dir.exists(), "Contracts package directory must exist"

    forbidden_roots = {"icarus_core", "icarus_cli"}
    imports = get_all_imports_in_dir(contracts_dir)

    for py_file, mod in imports:
        root_mod = mod.split(".")[0]
        assert root_mod not in forbidden_roots, (
            f"Boundary violation in {py_file}: imports forbidden module '{mod}'"
        )


def test_agent_core_never_imports_presentation_or_cli():
    """packages/agent-core must never import icarus_cli, typer, click, or fastapi."""
    core_dir = Path("packages/agent-core/src/icarus_core")
    assert core_dir.exists(), "Agent core package directory must exist"

    forbidden_roots = {"icarus_cli", "typer", "click", "fastapi"}
    imports = get_all_imports_in_dir(core_dir)

    for py_file, mod in imports:
        root_mod = mod.split(".")[0]
        assert root_mod not in forbidden_roots, (
            f"Boundary violation in {py_file}: imports forbidden presentation module '{mod}'"
        )
