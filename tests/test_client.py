from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from yarl import URL

from cookidoo_cli.client import CookidooClient, CookidooError
from cookidoo_cli.config import CookidooConfig
from cookidoo_cli.models import RecipeDraft


class FakeUpstream:
    def __init__(self) -> None:
        self.search_params = None

    async def search_recipes(self, **params):
        self.search_params = params
        return SimpleNamespace(
            recipes=[SimpleNamespace(id=f"r{index}", name=f"Recipe {index}") for index in range(5)]
        )


class FakeHttpError(Exception):
    status = 400


class FakeCreateUpstream:
    api_endpoint = URL("https://cookidoo.thermomix.com")

    def __init__(self, *, fail_patch: bool = False) -> None:
        self.fail_patch = fail_patch
        self.requests = []
        self.removed = []

    async def _request_json(self, method, url, operation, **kwargs):
        self.requests.append((method, str(url), operation, kwargs))
        if method == "post":
            return {"recipeId": "created-1"}
        if self.fail_patch:
            raise FakeHttpError("bad payload")
        return None

    async def remove_custom_recipe(self, recipe_id):
        self.removed.append(recipe_id)


class FakeUploadResponse:
    status = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def text(self):
        return json.dumps({"public_id": "prod/customer/dip", "format": "png"})


class FakeUploadSession:
    def __init__(self):
        self.calls = []

    def post(self, url, *, data):
        self.calls.append((url, data))
        return FakeUploadResponse()


class FakeImageUpstream:
    api_endpoint = URL("https://cookidoo.thermomix.com")

    def __init__(self):
        self._session = FakeUploadSession()
        self.requests = []

    async def _request_json(self, method, url, operation, **kwargs):
        self.requests.append((method, str(url), operation, kwargs))
        if operation == "sign recipe image upload":
            return {"signature": "signed"}
        return None


def test_search_enforces_limit_when_upstream_returns_larger_page(tmp_path):
    config = CookidooConfig(
        country="us",
        locale="en-US",
        url="https://cookidoo.thermomix.com/foundation/en-US",
        cookie_file=str(tmp_path / "cookies.json"),
        pending_dir=str(tmp_path / "pending"),
    )
    upstream = FakeUpstream()
    client = CookidooClient(config, upstream=upstream)

    result = asyncio.run(client.search("soup", limit=2))

    assert upstream.search_params["page_size"] == 2
    assert [recipe["id"] for recipe in result["results"]] == ["r0", "r1"]


def recipe_draft() -> RecipeDraft:
    return RecipeDraft.from_dict(
        {
            "title": "Test dip",
            "ingredients": ["200 g yogurt"],
            "steps": [{"text": "Mix 10 sec/speed 3.", "time_seconds": 10, "speed": 3}],
            "tags": ["test"],
        }
    )


def test_create_waits_for_shell_and_sends_supported_patch(tmp_path, monkeypatch):
    upstream = FakeCreateUpstream()
    client = CookidooClient(
        CookidooConfig(
            country="us",
            locale="en-US",
            url="https://cookidoo.thermomix.com/foundation/en-US",
            cookie_file=str(tmp_path / "cookies.json"),
            pending_dir=str(tmp_path / "pending"),
        ),
        upstream=upstream,
    )
    sleep = AsyncMock()
    monkeypatch.setattr("cookidoo_cli.client.asyncio.sleep", sleep)

    result = asyncio.run(client.create_recipe(recipe_draft()))

    sleep.assert_awaited_once_with(5)
    assert result["id"] == "created-1"
    patch = upstream.requests[1][3]["json"]
    assert patch["yield"] == {"value": 4, "unitText": "portion"}
    assert "tags" not in patch


def test_create_rolls_back_and_reports_patch_status(tmp_path, monkeypatch):
    upstream = FakeCreateUpstream(fail_patch=True)
    client = CookidooClient(
        CookidooConfig(
            country="us",
            locale="en-US",
            url="https://cookidoo.thermomix.com/foundation/en-US",
            cookie_file=str(tmp_path / "cookies.json"),
            pending_dir=str(tmp_path / "pending"),
        ),
        upstream=upstream,
    )
    monkeypatch.setattr("cookidoo_cli.client.asyncio.sleep", AsyncMock())

    with pytest.raises(CookidooError, match=r"update created recipe failed \(HTTP 400\)"):
        asyncio.run(client.create_recipe(recipe_draft()))

    assert upstream.removed == ["created-1"]


def test_set_recipe_image_uploads_then_patches_only_image_fields(tmp_path):
    upstream = FakeImageUpstream()
    client = CookidooClient(
        CookidooConfig(
            country="us",
            locale="en-US",
            url="https://cookidoo.thermomix.com/foundation/en-US",
            cookie_file=str(tmp_path / "cookies.json"),
            pending_dir=str(tmp_path / "pending"),
        ),
        upstream=upstream,
    )

    result = asyncio.run(
        client.set_recipe_image(
            "created-1",
            image_bytes=b"image",
            filename="dip.png",
            content_type="image/png",
            sha256="abc123",
        )
    )

    assert result["image"] == "prod/customer/dip.png"
    assert len(upstream._session.calls) == 1
    assert upstream.requests[0][2] == "sign recipe image upload"
    assert upstream.requests[1][2] == "attach recipe image"
    assert upstream.requests[1][3]["json"] == {
        "image": "prod/customer/dip.png",
        "isImageOwnedByUser": True,
    }
