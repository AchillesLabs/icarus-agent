"""Tests for dynamic skill discovery, management, and scaffolding."""

from pathlib import Path

from icarus_core.skills import create_skill, discover_skills


def test_discover_skills_empty_when_no_dirs(tmp_path: Path):
    """When no skill directories exist, discover_skills returns an empty list."""
    skills = discover_skills(workspace_dir=tmp_path)
    # Filter to only workspace skills to isolate test
    workspace_skills = [s for s in skills if s.scope == "workspace"]
    assert workspace_skills == []


def test_discover_skills_from_workspace_agents_skills(tmp_path: Path):
    """discover_skills detects skills inside .agents/skills/<name>/SKILL.md."""
    skill_dir = tmp_path / ".agents" / "skills" / "my-test-skill"
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        "---\nname: my-test-skill\ndescription: A test skill for code generation.\n---\n# Instructions\n",
        encoding="utf-8",
    )

    skills = discover_skills(workspace_dir=tmp_path)
    matching = [s for s in skills if s.name == "my-test-skill"]
    assert len(matching) == 1
    assert matching[0].description == "A test skill for code generation."
    assert matching[0].scope == "workspace"
    assert matching[0].path == skill_file


def test_discover_skills_fallback_when_no_frontmatter(tmp_path: Path):
    """When SKILL.md lacks YAML frontmatter, fallback to directory name and first non-empty line."""
    skill_dir = tmp_path / ".agents" / "skills" / "simple-skill"
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        "# Simple Skill\nThis skill helps with simple automation.", encoding="utf-8"
    )

    skills = discover_skills(workspace_dir=tmp_path)
    matching = [s for s in skills if s.name == "simple-skill"]
    assert len(matching) == 1
    assert (
        "Simple Skill" in matching[0].description or "simple automation" in matching[0].description
    )


def test_create_skill_scaffolds_skill_md(tmp_path: Path):
    """create_skill creates the directory and writes a starter SKILL.md."""
    target_path = create_skill(
        name="web-scraper",
        description="Scrapes product details from web pages.",
        workspace_dir=tmp_path,
        global_scope=False,
    )

    assert target_path.exists()
    assert target_path.name == "SKILL.md"
    content = target_path.read_text(encoding="utf-8")
    assert "name: web-scraper" in content
    assert "Scrapes product details from web pages." in content
    assert "# web-scraper" in content
