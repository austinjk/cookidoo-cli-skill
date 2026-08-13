from __future__ import annotations

import os
import subprocess
from pathlib import Path

import yaml

SKILL_DIR = Path(__file__).parents[1] / "skills/manage-cookidoo"


def test_skill_has_valid_frontmatter_and_bundled_files():
    skill_text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    _, frontmatter, body = skill_text.split("---", 2)
    metadata = yaml.safe_load(frontmatter)

    assert metadata["name"] == "manage-cookidoo"
    assert "Cookidoo" in metadata["description"]
    assert body.strip()
    assert (SKILL_DIR / "scripts/cookidoo").is_file()
    assert (SKILL_DIR / "references/tm7-capabilities.md").is_file()
    assert (SKILL_DIR / "references/owned-accessories.md").is_file()


def test_skill_contains_no_machine_specific_absolute_paths():
    for path in SKILL_DIR.rglob("*"):
        if path.is_file():
            assert "/Users/" not in path.read_text(encoding="utf-8")


def test_skill_wrapper_delegates_to_installed_cli(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    installed_cli = bin_dir / "cookidoo"
    installed_cli.write_text(
        "#!/bin/sh\nprintf 'delegated:%s\\n' \"$*\"\n",
        encoding="utf-8",
    )
    installed_cli.chmod(0o755)

    result = subprocess.run(
        [str(SKILL_DIR / "scripts/cookidoo"), "search", "ratatouille"],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"},
    )

    assert result.stdout == "delegated:search ratatouille\n"
