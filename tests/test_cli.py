from __future__ import annotations

import json

from cookidoo_cli.cli import main
from cookidoo_cli.config import ConfigStore, CookidooConfig


class FakeClient:
    def __init__(self, config):
        self.config = config
        self.calls = []

    async def close(self):
        return None

    async def search(self, query, **kwargs):
        return {"query": query, "filters": kwargs, "results": [{"id": "r1", "name": "Soup"}]}

    async def get_plan(self, day):
        return {"week_containing": day.isoformat(), "days": []}

    async def add_to_plan(self, day, recipe_id, custom=False):
        return {"added": True, "day": day.isoformat(), "recipe_id": recipe_id, "custom": custom}

    async def remove_from_plan(self, day, recipe_id, custom=False):
        return {"removed": True, "day": day.isoformat(), "recipe_id": recipe_id, "custom": custom}

    async def set_recipe_image(self, recipe_id, *, image_bytes, filename, content_type, sha256):
        return {
            "updated": True,
            "recipe_id": recipe_id,
            "image_sha256": sha256,
            "received": {"bytes": len(image_bytes), "filename": filename, "content_type": content_type},
        }


def setup_config(tmp_path):
    path = tmp_path / "config.yaml"
    ConfigStore(path).save(
        CookidooConfig(
            country="us",
            locale="en-US",
            url="https://cookidoo.thermomix.com/foundation/en-US",
            cookie_file=str(tmp_path / "cookies.json"),
            pending_dir=str(tmp_path / "pending"),
        )
    )
    return path


def test_search_emits_json(tmp_path, capsys):
    config = setup_config(tmp_path)
    code = main(["--config", str(config), "search", "soup", "--tm-model", "TM7"], client_factory=FakeClient)
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["ok"] is True
    assert payload["results"][0]["id"] == "r1"


def test_plan_add_is_dry_run_by_default(tmp_path, capsys):
    config = setup_config(tmp_path)
    code = main(["--config", str(config), "plan", "add", "2026-08-03", "r1"], client_factory=FakeClient)
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["dry_run"] is True
    assert payload["confirmation"]["token"]


def test_plan_add_commits_with_matching_confirmation(tmp_path, capsys):
    config = setup_config(tmp_path)
    args = ["--config", str(config), "plan", "add", "2026-08-03", "r1"]
    assert main(args, client_factory=FakeClient) == 0
    dry_run = json.loads(capsys.readouterr().out)
    token = dry_run["confirmation"]["token"]
    assert main([*args, "--confirm", token], client_factory=FakeClient) == 0
    committed = json.loads(capsys.readouterr().out)
    assert committed["dry_run"] is False
    assert committed["added"] is True


def test_plan_confirmation_rejects_changed_recipe(tmp_path, capsys):
    config = setup_config(tmp_path)
    assert main(["--config", str(config), "plan", "add", "2026-08-03", "r1"], client_factory=FakeClient) == 0
    token = json.loads(capsys.readouterr().out)["confirmation"]["token"]
    code = main(
        ["--config", str(config), "plan", "add", "2026-08-03", "r2", "--confirm", token],
        client_factory=FakeClient,
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 2
    assert "Payload changed" in payload["error"]["message"]


def test_invalid_date_is_structured_error(tmp_path, capsys):
    config = setup_config(tmp_path)
    code = main(["--config", str(config), "plan", "show", "tomorrow"], client_factory=FakeClient)
    payload = json.loads(capsys.readouterr().out)
    assert code == 2
    assert payload["error"]["type"] == "input_error"


def test_recipe_validation_does_not_require_config(tmp_path, capsys):
    recipe = tmp_path / "recipe.json"
    recipe.write_text(
        json.dumps({"title": "Toast", "ingredients": ["bread"], "steps": ["Toast bread."], "tm_model": "TM7"}),
        encoding="utf-8",
    )
    code = main(["--config", str(tmp_path / "missing.yaml"), "recipe", "validate", "--file", str(recipe)])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["validation"]["valid"] is True


def test_recipe_set_image_uploads_without_confirmation(tmp_path, capsys):
    config = setup_config(tmp_path)
    image = tmp_path / "dip.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"recipe-image")
    args = ["--config", str(config), "recipe", "set-image", "created-1", "--file", str(image)]

    assert main(args, client_factory=FakeClient) == 0
    committed = json.loads(capsys.readouterr().out)
    assert committed["dry_run"] is False
    assert committed["updated"] is True
    assert committed["received"]["filename"] == "dip.png"


def test_recipe_set_image_can_be_explicitly_previewed(tmp_path, capsys):
    config = setup_config(tmp_path)
    image = tmp_path / "dip.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"recipe-image")
    args = [
        "--config",
        str(config),
        "recipe",
        "set-image",
        "created-1",
        "--file",
        str(image),
        "--dry-run",
    ]

    assert main(args, client_factory=FakeClient) == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["dry_run"] is True
    assert preview["preview"]["image"]["content_type"] == "image/png"
    assert "confirmation" not in preview


def test_recipe_set_image_rejects_unknown_format(tmp_path, capsys):
    config = setup_config(tmp_path)
    image = tmp_path / "dip.txt"
    image.write_text("not an image", encoding="utf-8")
    code = main(
        ["--config", str(config), "recipe", "set-image", "created-1", "--file", str(image)],
        client_factory=FakeClient,
    )
    error = json.loads(capsys.readouterr().out)
    assert code == 2
    assert "PNG, JPEG, or WebP" in error["error"]["message"]
