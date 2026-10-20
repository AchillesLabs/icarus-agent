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


def test_pull_skill_from_local_folder(tmp_path: Path):
    """pull_skill copies a local folder into workspace .agents/skills/."""
    from icarus_core.skills import pull_skill

    source_dir = tmp_path / "external-sources" / "flight-radar"
    source_dir.mkdir(parents=True)
    (source_dir / "SKILL.md").write_text(
        "---\nname: flight-radar\ndescription: Live flight tracking and radar alerts.\n---\n# Flight Radar\n",
        encoding="utf-8",
    )
    (source_dir / "helper.py").write_text("# helper", encoding="utf-8")

    ws = tmp_path / "my-workspace"
    ws.mkdir()

    installed = pull_skill(source=str(source_dir), workspace_dir=ws)
    assert len(installed) == 1
    assert installed[0].name == "flight-radar"
    assert installed[0].description == "Live flight tracking and radar alerts."
    assert (ws / ".agents" / "skills" / "flight-radar" / "SKILL.md").is_file()
    assert (ws / ".agents" / "skills" / "flight-radar" / "helper.py").is_file()


def test_pull_skill_from_raw_url(tmp_path: Path):
    """pull_skill downloads a raw markdown file and extracts name/description."""
    from unittest.mock import MagicMock

    from icarus_core.skills import pull_skill

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = "---\nname: cloud-deploy\ndescription: Automate AWS and GCP deployments.\n---\n# Cloud Deploy\n"
    mock_resp.raise_for_status = MagicMock()
    mock_client.get.return_value = mock_resp

    ws = tmp_path / "my-workspace"
    ws.mkdir()

    installed = pull_skill(
        source="https://raw.githubusercontent.com/org/skills/main/cloud-deploy/SKILL.md",
        workspace_dir=ws,
        http_client=mock_client,
    )

    assert len(installed) == 1
    assert installed[0].name == "cloud-deploy"
    assert installed[0].description == "Automate AWS and GCP deployments."
    dest_file = ws / ".agents" / "skills" / "cloud-deploy" / "SKILL.md"
    assert dest_file.is_file()
    assert "name: cloud-deploy" in dest_file.read_text(encoding="utf-8")


def test_pull_skill_github_blob_url_translates_to_raw(tmp_path: Path):
    """pull_skill detects GitHub web blob URLs and downloads from raw.githubusercontent.com."""
    from unittest.mock import MagicMock

    from icarus_core.skills import pull_skill

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = "---\nname: security-audit\ndescription: Run vulnerability scanner.\n---\n# Security Audit\n"
    mock_resp.raise_for_status = MagicMock()
    mock_client.get.return_value = mock_resp

    ws = tmp_path / "my-workspace"
    ws.mkdir()

    installed = pull_skill(
        source="https://github.com/org/repo/blob/main/skills/security-audit/SKILL.md",
        workspace_dir=ws,
        http_client=mock_client,
    )

    # Verify mock_client was called with raw URL
    mock_client.get.assert_called_once_with(
        "https://raw.githubusercontent.com/org/repo/main/skills/security-audit/SKILL.md"
    )
    assert len(installed) == 1
    assert installed[0].name == "security-audit"


def test_pull_skill_overwrite_protection(tmp_path: Path):
    """pull_skill raises FileExistsError if skill exists and overwrite=False."""
    import pytest
    from icarus_core.skills import pull_skill

    source_dir = tmp_path / "source-skill"
    source_dir.mkdir()
    (source_dir / "SKILL.md").write_text(
        "---\nname: duplicate-skill\ndescription: Test duplicate.\n---\n", encoding="utf-8"
    )

    ws = tmp_path / "my-workspace"
    ws.mkdir()

    # First pull succeeds
    pull_skill(source=str(source_dir), workspace_dir=ws)

    # Second pull without overwrite raises FileExistsError
    with pytest.raises(FileExistsError):
        pull_skill(source=str(source_dir), workspace_dir=ws, overwrite=False)

    # Second pull with overwrite=True succeeds
    pull_skill(source=str(source_dir), workspace_dir=ws, overwrite=True)


def test_pull_skill_from_git_repo(tmp_path: Path):
    """pull_skill clones a git repository and discovers its skills."""
    import subprocess

    from icarus_core.skills import pull_skill

    # Create a dummy git repo
    git_origin = tmp_path / "dummy-remote-repo"
    git_origin.mkdir()
    subprocess.run(["git", "init"], cwd=git_origin, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@icarus.ai"],
        cwd=git_origin,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Icarus Tester"],
        cwd=git_origin,
        check=True,
        capture_output=True,
    )

    skill_folder = git_origin / "skills" / "k8s-operator"
    skill_folder.mkdir(parents=True)
    (skill_folder / "SKILL.md").write_text(
        "---\nname: k8s-operator\ndescription: Manage Kubernetes pods and deployments.\n---\n# K8s\n",
        encoding="utf-8",
    )

    subprocess.run(["git", "add", "."], cwd=git_origin, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial commit"],
        cwd=git_origin,
        check=True,
        capture_output=True,
    )

    ws = tmp_path / "my-workspace"
    ws.mkdir()

    installed = pull_skill(source=str(git_origin), workspace_dir=ws)
    assert len(installed) == 1
    assert installed[0].name == "k8s-operator"
    assert installed[0].description == "Manage Kubernetes pods and deployments."
    dest_file = ws / ".agents" / "skills" / "k8s-operator" / "SKILL.md"
    assert dest_file.is_file()


def test_pull_skill_pasted_command_wrapper(tmp_path: Path):
    """pull_skill handles pasted strings like 'npx skills@latest add owner/repo --skill=foo'."""
    from unittest.mock import patch

    from icarus_core.skills import pull_skill

    ws = tmp_path / "my-workspace"
    ws.mkdir()

    # Mock _pull_from_git_repo to verify clean_source and skill_name passed
    with patch("icarus_core.skills._pull_from_git_repo") as mock_git:
        mock_git.return_value = []
        pull_skill(
            source="npx skills@latest add mattpocock/skills --skill=grill-with-docs",
            workspace_dir=ws,
        )
        mock_git.assert_called_once()
        args, kwargs = mock_git.call_args
        assert args[0] == "https://github.com/mattpocock/skills.git"
        assert kwargs["skill_name"] == "grill-with-docs"
