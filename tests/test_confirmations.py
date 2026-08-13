from __future__ import annotations

import os

import pytest

from cookidoo_cli.confirmations import ConfirmationStore, payload_digest


def test_confirmation_is_private_payload_bound_and_single_use(tmp_path):
    store = ConfirmationStore(tmp_path / "pending")
    payload = {"recipe_id": "abc", "day": "2026-08-03"}
    confirmation = store.create("plan.add", payload)
    assert confirmation.token.startswith("c_")
    path = tmp_path / "pending" / f"{confirmation.token}.json"
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert confirmation.digest == payload_digest(payload)
    consumed = store.consume(confirmation.token, "plan.add", payload)
    assert consumed.digest == confirmation.digest
    assert not path.exists()
    with pytest.raises(ValueError, match="missing"):
        store.consume(confirmation.token, "plan.add", payload)


def test_confirmation_rejects_changed_payload_without_consuming(tmp_path):
    store = ConfirmationStore(tmp_path / "pending")
    confirmation = store.create("recipe.delete", {"recipe_id": "a"})
    with pytest.raises(ValueError, match="Payload changed"):
        store.consume(confirmation.token, "recipe.delete", {"recipe_id": "b"})
    assert (tmp_path / "pending" / f"{confirmation.token}.json").exists()


def test_confirmation_rejects_different_operation(tmp_path):
    store = ConfirmationStore(tmp_path / "pending")
    payload = {"recipe_id": "a"}
    confirmation = store.create("recipe.delete", payload)
    with pytest.raises(ValueError, match="different operation"):
        store.consume(confirmation.token, "plan.remove", payload)


def test_confirmation_rejects_expired_token(tmp_path):
    store = ConfirmationStore(tmp_path / "pending", ttl_seconds=-1)
    payload = {"recipe_id": "a"}
    confirmation = store.create("recipe.delete", payload)
    with pytest.raises(ValueError, match="expired"):
        store.consume(confirmation.token, "recipe.delete", payload)


def test_confirmation_rejects_path_traversal(tmp_path):
    store = ConfirmationStore(tmp_path / "pending")
    with pytest.raises(ValueError, match="Invalid"):
        store.consume("../token", "x", {})


def test_confirmation_rejects_broad_directory_permissions(tmp_path):
    directory = tmp_path / "pending"
    directory.mkdir(mode=0o755)
    with pytest.raises(PermissionError, match="chmod 700"):
        ConfirmationStore(directory).create("x", {})


def test_create_purges_expired_confirmation_files(tmp_path):
    store = ConfirmationStore(tmp_path / "pending", ttl_seconds=-1)
    expired = store.create("old", {})
    assert (tmp_path / "pending" / f"{expired.token}.json").exists()
    store = ConfirmationStore(tmp_path / "pending")
    store.create("new", {})
    assert not (tmp_path / "pending" / f"{expired.token}.json").exists()
