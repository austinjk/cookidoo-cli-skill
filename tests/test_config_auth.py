from __future__ import annotations

import json
import os

import pytest

from cookidoo_cli.auth import CookieStore
from cookidoo_cli.config import ConfigStore, CookidooConfig, UnsafePrivateFileError


def test_config_round_trip_is_private(tmp_path):
    path = tmp_path / "config.yaml"
    config = CookidooConfig(
        country="us",
        locale="en-US",
        url="https://cookidoo.thermomix.com/foundation/en-US",
        cookie_file=str(tmp_path / "cookies.json"),
        pending_dir=str(tmp_path / "pending"),
    )
    ConfigStore(path).save(config)
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert ConfigStore(path).load() == config


def test_config_rejects_non_https(tmp_path):
    config = CookidooConfig(country="us", locale="en-US", url="http://example.test")
    with pytest.raises(ValueError, match="HTTPS"):
        ConfigStore(tmp_path / "config.yaml").save(config)


def test_config_rejects_untrusted_login_host(tmp_path):
    config = CookidooConfig(country="us", locale="en-US", url="https://evil.example/foundation/en-US")
    with pytest.raises(ValueError, match="cookidoo.thermomix.com"):
        ConfigStore(tmp_path / "config.yaml").save(config)


def test_config_rejects_mismatched_locale_path(tmp_path):
    config = CookidooConfig(
        country="us",
        locale="en-US",
        url="https://cookidoo.thermomix.com/foundation/de-DE",
    )
    with pytest.raises(ValueError, match="locale"):
        ConfigStore(tmp_path / "config.yaml").save(config)


def test_config_rejects_group_readable_file(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("site: {}", encoding="utf-8")
    path.chmod(0o640)
    with pytest.raises(UnsafePrivateFileError):
        ConfigStore(path).load()


def test_cookie_store_round_trip(tmp_path):
    path = tmp_path / "cookies.json"
    entries = [
        {"key": "_oauth2_proxy", "value": "secret-a", "domain": ".example.test", "path": "/"},
        {"key": "v-authenticated", "value": "secret-b", "domain": ".example.test", "path": "/"},
    ]
    store = CookieStore(path)
    store.save_entries(entries)
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert store.load_entries() == entries
    assert store.status().authenticated is True


def test_cookie_store_rejects_incomplete_login(tmp_path):
    store = CookieStore(tmp_path / "cookies.json")
    with pytest.raises(ValueError, match="required"):
        store.save_entries([{"key": "_oauth2_proxy", "value": "a"}])


def test_cookie_status_rejects_broad_permissions(tmp_path):
    path = tmp_path / "cookies.json"
    path.write_text(json.dumps([]), encoding="utf-8")
    path.chmod(0o644)
    status = CookieStore(path).status()
    assert status.authenticated is False
    assert "chmod 600" in status.message
