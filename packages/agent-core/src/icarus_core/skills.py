"""Dynamic skill discovery, parsing, and scaffolding for Icarus Agent."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from icarus_core.paths import get_icarus_skills_dir


@dataclass
class SkillInfo:
    """Represents a discovered skill with instructions and metadata."""

    name: str
    description: str
    path: Path
    scope: str  # "workspace" or "global"


def _parse_skill_file(skill_file: Path, default_name: str, scope: str) -> SkillInfo:
    """Parse name and description from a SKILL.md file."""
    content = ""
    try:
        content = skill_file.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return SkillInfo(
            name=default_name,
            description="Custom agent skill.",
            path=skill_file,
            scope=scope,
        )

    name = default_name
    description = ""

    # Check for YAML frontmatter
    fm_match = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if fm_match:
        fm_block = fm_match.group(1)
        name_match = re.search(r"^name:\s*([^\n]+)", fm_block, re.MULTILINE)
        if name_match:
            name = name_match.group(1).strip().strip("\"'")

        desc_match = re.search(r"^description:\s*([^\n]+)", fm_block, re.MULTILINE)
        if desc_match:
            description = desc_match.group(1).strip().strip("\"'")

    if not description:
        # Fallback to the first non-header, non-empty line
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        for line in lines:
            if not line.startswith(("#", "---", "name:", "description:")):
                description = line
                break
        if not description:
            description = f"Instructions and workflows for {name}."

    return SkillInfo(
        name=name,
        description=description,
        path=skill_file,
        scope=scope,
    )


def discover_skills(workspace_dir: Path | None = None) -> list[SkillInfo]:
    """Scan workspace and user home directories for available skills.

    Precedence: Workspace (.agents/skills, .icarus/skills) overrides global (~/.icarus/skills).
    """
    discovered: dict[str, SkillInfo] = {}
    ws = (workspace_dir or Path.cwd()).resolve()

    # 1. Global skills (~/.icarus/skills)
    global_dir = get_icarus_skills_dir()
    if global_dir.is_dir():
        for child in sorted(global_dir.iterdir()):
            if child.is_dir():
                skill_md = child / "SKILL.md"
                if skill_md.is_file():
                    skill = _parse_skill_file(skill_md, child.name, scope="global")
                    discovered[skill.name] = skill

    # 2. Workspace skills (.icarus/skills)
    ws_icarus = ws / ".icarus" / "skills"
    if ws_icarus.is_dir():
        for child in sorted(ws_icarus.iterdir()):
            if child.is_dir():
                skill_md = child / "SKILL.md"
                if skill_md.is_file():
                    skill = _parse_skill_file(skill_md, child.name, scope="workspace")
                    discovered[skill.name] = skill

    # 3. Workspace skills (.agents/skills)
    ws_agents = ws / ".agents" / "skills"
    if ws_agents.is_dir():
        for child in sorted(ws_agents.iterdir()):
            if child.is_dir():
                skill_md = child / "SKILL.md"
                if skill_md.is_file():
                    skill = _parse_skill_file(skill_md, child.name, scope="workspace")
                    discovered[skill.name] = skill

    return sorted(discovered.values(), key=lambda s: s.name)


def create_skill(
    name: str,
    description: str,
    workspace_dir: Path | None = None,
    global_scope: bool = False,
) -> Path:
    """Scaffold a new skill directory with a starter SKILL.md file.

    Returns the path to the created SKILL.md.
    """
    clean_name = re.sub(r"[^a-zA-Z0-9_\-]", "-", name.strip().lower()).strip("-")
    if not clean_name:
        raise ValueError(f"Invalid skill name: '{name}'")

    if global_scope:
        base_dir = get_icarus_skills_dir()
    else:
        ws = (workspace_dir or Path.cwd()).resolve()
        base_dir = ws / ".agents" / "skills"

    skill_dir = base_dir / clean_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"

    template = f"""---
name: {clean_name}
description: "{description or f"Workflow instructions for {clean_name}."}"
---

# {clean_name}

## When to use this skill
Describe specific tasks, prompts, or triggers when this skill should be activated.

## Instructions
1. Step-by-step guidance for the agent to execute this workflow.
2. Best practices and safety boundaries.
"""
    skill_file.write_text(template, encoding="utf-8")
    return skill_file
