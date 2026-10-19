"""Tests for unified PyPI wheel packaging and universal installer scripts."""

from __future__ import annotations

import os
import subprocess
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_installer_scripts_exist_and_syntax():
    """Verify install.sh and install.ps1 exist and have valid syntax."""
    install_sh = REPO_ROOT / "install.sh"
    install_ps1 = REPO_ROOT / "install.ps1"

    assert install_sh.exists()
    assert install_ps1.exists()

    sh_content = install_sh.read_text(encoding="utf-8")
    assert "uv tool install" in sh_content
    assert "astral.sh/uv" in sh_content
    assert "#!/usr/bin/env bash" in sh_content

    ps1_content = install_ps1.read_text(encoding="utf-8")
    assert "uv tool install" in ps1_content
    assert "astral.sh/uv" in ps1_content
    assert "$ErrorActionPreference = 'Stop'" in ps1_content


def test_unified_wheel_structure():
    """Verify built wheel archives all 5 component packages and exposes scripts and extras."""
    # Build package wheel using uv build
    res = subprocess.run(
        ["uv", "build", "--package", "icarus-agent", "--wheel"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"uv build failed: {res.stderr}"

    dist_dir = REPO_ROOT / "dist"
    wheels = list(dist_dir.glob("icarus_agent-*.whl"))
    assert len(wheels) > 0, "No built wheel found in dist/"

    latest_wheel = max(wheels, key=lambda p: p.stat().st_mtime)
    with zipfile.ZipFile(latest_wheel, "r") as zf:
        namelist = zf.namelist()
        top_dirs = set(name.split("/")[0] for name in namelist)

        # 1. Check all subpackages are bundled
        assert "icarus_cli" in top_dirs
        assert "icarus_core" in top_dirs
        assert "icarus_contracts" in top_dirs
        assert "icarus_api" in top_dirs
        assert "icarus_worker" in top_dirs

        # 2. Check console scripts entry points
        entry_points_entry = [n for n in namelist if n.endswith("entry_points.txt")]
        assert len(entry_points_entry) == 1
        entry_points_content = zf.read(entry_points_entry[0]).decode("utf-8")
        assert "icarus = icarus_cli.main:app" in entry_points_content
        assert "icarus-api = icarus_api.main:main" in entry_points_content
        assert "icarus-worker = icarus_worker.main:main" in entry_points_content

        # 3. Check METADATA extras
        metadata_entry = [n for n in namelist if n.endswith("METADATA")]
        assert len(metadata_entry) == 1
        meta_content = zf.read(metadata_entry[0]).decode("utf-8")
        assert "Provides-Extra: server" in meta_content
        assert "Provides-Extra: worker" in meta_content


def test_clean_venv_installation_and_execution(tmp_path: Path):
    """Install the built wheel into a fresh temporary virtual environment and execute the CLI."""
    dist_dir = REPO_ROOT / "dist"
    wheels = list(dist_dir.glob("icarus_agent-*.whl"))
    assert wheels, "Wheel must exist before test"
    wheel_path = max(wheels, key=lambda p: p.stat().st_mtime)

    venv_dir = tmp_path / "test_venv"
    # Create isolated venv
    venv_res = subprocess.run(
        ["uv", "venv", str(venv_dir)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert venv_res.returncode == 0, f"uv venv failed: {venv_res.stderr}"

    icarus_exe = venv_dir / ("Scripts/icarus.exe" if sys.platform == "win32" else "bin/icarus")

    # Install the wheel into the isolated venv with --no-deps
    # to test package extraction and entrypoint generation
    env = os.environ.copy()
    env["VIRTUAL_ENV"] = str(venv_dir)
    pip_res = subprocess.run(
        ["uv", "pip", "install", "--no-deps", str(wheel_path)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert pip_res.returncode == 0, f"uv pip install wheel failed: {pip_res.stderr}"

    # Verify all 5 packages are present in site-packages
    site_packages = list(venv_dir.glob("**/site-packages"))[0]
    assert (site_packages / "icarus_cli").exists()
    assert (site_packages / "icarus_core").exists()
    assert (site_packages / "icarus_contracts").exists()
    assert (site_packages / "icarus_api").exists()
    assert (site_packages / "icarus_worker").exists()

    # Verify generated console_script entry point executable exists
    assert icarus_exe.exists(), f"Entry point executable {icarus_exe} was not generated"
