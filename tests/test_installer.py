from __future__ import annotations

import os
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1]


def _fake_uv(tmp_path: Path) -> tuple[Path, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "uv.log"
    uv = bin_dir / "uv"
    uv.write_text("#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$UV_LOG\"\n", encoding="utf-8")
    uv.chmod(0o755)
    return bin_dir, log


def test_installer_installs_cli_and_skill_for_both_hosts(tmp_path):
    bin_dir, uv_log = _fake_uv(tmp_path)
    codex_home = tmp_path / "codex"
    claude_home = tmp_path / "claude"
    env = {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        "CODEX_HOME": str(codex_home),
        "CLAUDE_HOME": str(claude_home),
        "UV_LOG": str(uv_log),
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
    }

    result = subprocess.run(
        ["bash", str(PROJECT_ROOT / "install.sh"), "--source", str(PROJECT_ROOT), "--target", "both"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    assert "tool install --force --python 3.12" in uv_log.read_text(encoding="utf-8")
    assert (codex_home / "skills/manage-cookidoo/SKILL.md").is_file()
    assert (claude_home / "skills/manage-cookidoo/SKILL.md").is_file()
    assert os.access(codex_home / "skills/manage-cookidoo/scripts/cookidoo", os.X_OK)
    assert "Installation complete" in result.stdout


def test_installer_dry_run_makes_no_changes(tmp_path):
    bin_dir, uv_log = _fake_uv(tmp_path)
    codex_home = tmp_path / "codex"
    env = {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        "CODEX_HOME": str(codex_home),
        "UV_LOG": str(uv_log),
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
    }

    result = subprocess.run(
        ["bash", str(PROJECT_ROOT / "install.sh"), "--source", str(PROJECT_ROOT), "--dry-run"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    assert not codex_home.exists()
    assert not uv_log.exists()
    assert "Dry run complete; no changes made" in result.stdout


def test_installer_rejects_unknown_target(tmp_path):
    result = subprocess.run(
        ["bash", str(PROJECT_ROOT / "install.sh"), "--target", "chatgpt"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "codex, claude, or both" in result.stderr
