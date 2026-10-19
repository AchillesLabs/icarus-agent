"""Dynamic skill discovery, parsing, and scaffolding for Icarus Agent."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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


def _find_skills_in_tree(
    root_dir: Path,
    target_scope: str,
    filter_name: str | None = None,
) -> list[tuple[Path, SkillInfo]]:
    """Find all directories containing SKILL.md under root_dir."""
    results: list[tuple[Path, SkillInfo]] = []
    for skill_file in sorted(root_dir.glob("**/SKILL.md")):
        if ".git" in skill_file.parts:
            continue
        skill_dir = skill_file.parent
        info = _parse_skill_file(skill_file, default_name=skill_dir.name, scope=target_scope)
        if (
            filter_name
            and info.name.lower() != filter_name.lower()
            and skill_dir.name.lower() != filter_name.lower()
        ):
            continue
        results.append((skill_dir, info))
    return results


def _pull_from_raw_url(
    url: str,
    target_base_dir: Path,
    target_scope: str,
    skill_name: str | None = None,
    overwrite: bool = False,
    http_client: Any | None = None,
) -> list[SkillInfo]:
    """Download and install a single SKILL.md from an HTTP/HTTPS raw URL."""
    import httpx

    client = http_client or httpx.Client(timeout=15.0, follow_redirects=True)
    try:
        resp = client.get(url)
        resp.raise_for_status()
        content = resp.text
    except Exception as exc:
        raise RuntimeError(f"Failed to download skill from '{url}': {exc}") from exc

    detected_name = skill_name or ""
    if not detected_name:
        fm_match = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
        if fm_match:
            name_match = re.search(r"^name:\s*([^\n]+)", fm_match.group(1), re.MULTILINE)
            if name_match:
                detected_name = name_match.group(1).strip().strip("\"'")

    if not detected_name:
        parts = [p for p in url.split("/") if p and not p.endswith(".md")]
        detected_name = parts[-1] if parts else "external-skill"

    clean_name = (
        re.sub(r"[^a-zA-Z0-9_\-]", "-", detected_name.strip().lower()).strip("-")
        or "external-skill"
    )
    dest_dir = target_base_dir / clean_name
    if dest_dir.exists():
        if not overwrite:
            raise FileExistsError(
                f"Skill '{clean_name}' already exists at {dest_dir}. Use overwrite=True or --overwrite to replace it."
            )
        import shutil

        shutil.rmtree(dest_dir)

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / "SKILL.md"
    dest_file.write_text(content, encoding="utf-8")
    return [_parse_skill_file(dest_file, default_name=clean_name, scope=target_scope)]


def _pull_from_git_repo(
    repo_url: str,
    target_base_dir: Path,
    target_scope: str,
    skill_name: str | None = None,
    overwrite: bool = False,
    branch: str | None = None,
) -> list[SkillInfo]:
    """Clone a Git repository into a temporary directory and copy discovered skills."""
    import shutil
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        clone_cmd = ["git", "clone", "--depth", "1"]
        if branch:
            clone_cmd.extend(["--branch", branch])
        clone_cmd.extend([repo_url, str(tmp_dir)])

        try:
            subprocess.run(clone_cmd, capture_output=True, text=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            err_msg = ""
            if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
                err_msg = f": {exc.stderr.strip()}"
            raise RuntimeError(f"Failed to clone repository '{repo_url}'{err_msg}") from exc

        # Case A: Root of repo is a skill
        if (tmp_dir / "SKILL.md").is_file():
            fallback = Path(repo_url).stem.removesuffix(".git")
            info = _parse_skill_file(
                tmp_dir / "SKILL.md",
                default_name=skill_name or fallback,
                scope=target_scope,
            )
            name = skill_name or info.name
            clean_name = re.sub(r"[^a-zA-Z0-9_\-]", "-", name.strip().lower()).strip("-") or name
            dest_dir = target_base_dir / clean_name
            if dest_dir.exists():
                if not overwrite:
                    raise FileExistsError(
                        f"Skill '{clean_name}' already exists at {dest_dir}. Use overwrite=True or --overwrite to replace it."
                    )
                shutil.rmtree(dest_dir)
            shutil.copytree(
                tmp_dir,
                dest_dir,
                ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
            )
            return [_parse_skill_file(dest_dir / "SKILL.md", default_name=clean_name, scope=target_scope)]

        # Case B: Multi-skill or nested skills repository
        found = _find_skills_in_tree(tmp_dir, target_scope, skill_name)
        if not found:
            raise ValueError(
                f"No SKILL.md found in repository '{repo_url}'. A valid skill must contain a SKILL.md file."
            )

        installed: list[SkillInfo] = []
        for src_dir, s_info in found:
            dest_name = s_info.name
            clean_name = (
                re.sub(r"[^a-zA-Z0-9_\-]", "-", dest_name.strip().lower()).strip("-") or dest_name
            )
            dest_dir = target_base_dir / clean_name
            if dest_dir.exists():
                if not overwrite:
                    raise FileExistsError(
                        f"Skill '{clean_name}' already exists at {dest_dir}. Use overwrite=True or --overwrite to replace it."
                    )
                shutil.rmtree(dest_dir)
            shutil.copytree(
                src_dir,
                dest_dir,
                ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
            )
            installed.append(
                _parse_skill_file(dest_dir / "SKILL.md", default_name=clean_name, scope=target_scope)
            )
        return installed


def pull_skill(
    source: str,
    workspace_dir: Path | None = None,
    global_scope: bool = False,
    skill_name: str | None = None,
    overwrite: bool = False,
    http_client: Any | None = None,
) -> list[SkillInfo]:
    """Pull and install an external skill from a URL, Git repository, GitHub shorthand, or local path.

    Supported sources:
    1. Direct URL to SKILL.md or raw markdown (e.g. GitHub raw URL, blob URL, or web link)
    2. Git repository URL (e.g. https://github.com/owner/repo.git or https://github.com/owner/repo)
    3. GitHub shorthand (e.g. owner/repo or owner/repo@branch)
    4. Local directory or file path

    Returns:
        List of installed SkillInfo objects.
    """
    clean_source = source.strip()
    if not clean_source:
        raise ValueError("Source cannot be empty.")

    # Strip pasted command wrappers like `npx skills@latest add` or `icarus skills add`
    clean_source = re.sub(
        r"^(?:npx\s+)?skills(?:@\S+)?\s+add\s+", "", clean_source, flags=re.IGNORECASE
    ).strip()
    clean_source = re.sub(
        r"^(?:icarus\s+)?skills\s+(?:pull|install|add)\s+", "", clean_source, flags=re.IGNORECASE
    ).strip()

    # Extract embedded --skill=... or --skill ...
    skill_arg_match = re.search(r"--skill[=\s]+([^\s]+)", clean_source)
    if skill_arg_match:
        if not skill_name:
            skill_name = skill_arg_match.group(1).strip("\"'")
        clean_source = re.sub(r"--skill[=\s]+[^\s]+", "", clean_source).strip()

    # Extract embedded -f or --overwrite
    if re.search(r"(?:^|\s)(-f|--overwrite)(?:\s|$)", clean_source):
        overwrite = True
        clean_source = re.sub(r"(?:^|\s)(-f|--overwrite)(?:\s|$)", " ", clean_source).strip()

    # Extract embedded -g or --global
    if re.search(r"(?:^|\s)(-g|--global)(?:\s|$)", clean_source):
        global_scope = True
        clean_source = re.sub(r"(?:^|\s)(-g|--global)(?:\s|$)", " ", clean_source).strip()

    if global_scope:
        target_base_dir = get_icarus_skills_dir()
        target_scope = "global"
    else:
        ws = (workspace_dir or Path.cwd()).resolve()
        target_base_dir = ws / ".agents" / "skills"
        target_scope = "workspace"

    target_base_dir.mkdir(parents=True, exist_ok=True)

    # 1. Local path check
    local_path = Path(clean_source)
    if local_path.exists():
        import shutil

        if local_path.is_file():
            content = local_path.read_text(encoding="utf-8", errors="replace")
            info = _parse_skill_file(
                local_path, default_name=skill_name or local_path.stem, scope=target_scope
            )
            name = skill_name or info.name
            clean_name = re.sub(r"[^a-zA-Z0-9_\-]", "-", name.strip().lower()).strip("-") or name
            dest_dir = target_base_dir / clean_name
            if dest_dir.exists():
                if not overwrite:
                    raise FileExistsError(
                        f"Skill '{clean_name}' already exists at {dest_dir}. Use overwrite=True or --overwrite to replace it."
                    )
                shutil.rmtree(dest_dir)
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_file = dest_dir / "SKILL.md"
            dest_file.write_text(content, encoding="utf-8")
            return [_parse_skill_file(dest_file, default_name=clean_name, scope=target_scope)]

        if (local_path / "SKILL.md").is_file():
            info = _parse_skill_file(
                local_path / "SKILL.md",
                default_name=skill_name or local_path.name,
                scope=target_scope,
            )
            name = skill_name or info.name
            clean_name = re.sub(r"[^a-zA-Z0-9_\-]", "-", name.strip().lower()).strip("-") or name
            dest_dir = target_base_dir / clean_name
            if dest_dir.exists():
                if not overwrite:
                    raise FileExistsError(
                        f"Skill '{clean_name}' already exists at {dest_dir}. Use overwrite=True or --overwrite to replace it."
                    )
                shutil.rmtree(dest_dir)
            shutil.copytree(
                local_path,
                dest_dir,
                ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
            )
            return [
                _parse_skill_file(dest_dir / "SKILL.md", default_name=clean_name, scope=target_scope)
            ]

        # Nested skills in local directory
        found = _find_skills_in_tree(local_path, target_scope, skill_name)
        if not found:
            raise ValueError(f"No SKILL.md found in '{local_path}'.")

        installed_list: list[SkillInfo] = []
        for src_dir, s_info in found:
            clean_name = (
                re.sub(r"[^a-zA-Z0-9_\-]", "-", s_info.name.strip().lower()).strip("-")
                or s_info.name
            )
            dest_dir = target_base_dir / clean_name
            if dest_dir.exists():
                if not overwrite:
                    raise FileExistsError(
                        f"Skill '{clean_name}' already exists at {dest_dir}. Use overwrite=True or --overwrite to replace it."
                    )
                shutil.rmtree(dest_dir)
            shutil.copytree(
                src_dir,
                dest_dir,
                ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
            )
            installed_list.append(
                _parse_skill_file(dest_dir / "SKILL.md", default_name=clean_name, scope=target_scope)
            )
        return installed_list

    # 2. HTTP/HTTPS URLs
    if clean_source.startswith(("http://", "https://")):
        # Convert GitHub web blob URL to raw URL
        blob_match = re.match(
            r"^https?://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.*)$", clean_source
        )
        if blob_match:
            owner, repo, branch, rel_path = blob_match.groups()
            raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{rel_path}"
            return _pull_from_raw_url(
                raw_url,
                target_base_dir,
                target_scope,
                skill_name,
                overwrite=overwrite,
                http_client=http_client,
            )

        # Direct markdown or raw link
        if clean_source.endswith(".md") or "raw.githubusercontent.com" in clean_source:
            return _pull_from_raw_url(
                clean_source,
                target_base_dir,
                target_scope,
                skill_name,
                overwrite=overwrite,
                http_client=http_client,
            )

        # Git repository URL
        return _pull_from_git_repo(
            clean_source,
            target_base_dir,
            target_scope,
            skill_name=skill_name,
            overwrite=overwrite,
        )

    # 3. GitHub shorthand (owner/repo or owner/repo@branch)
    gh_match = re.match(r"^([\w\-]+)/([\w\-]+)(?:@([\w\.\-]+))?$", clean_source)
    if gh_match:
        owner, repo, branch = gh_match.groups()
        git_url = f"https://github.com/{owner}/{repo}.git"
        return _pull_from_git_repo(
            git_url,
            target_base_dir,
            target_scope,
            skill_name=skill_name,
            overwrite=overwrite,
            branch=branch,
        )

    raise ValueError(
        f"Unrecognized skill source: '{source}'. Please provide a valid Git repository URL, "
        "GitHub shorthand (owner/repo), direct markdown URL, or local path."
    )

