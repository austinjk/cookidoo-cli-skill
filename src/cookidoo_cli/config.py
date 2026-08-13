from __future__ import annotations

import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

APP_DIR = Path.home() / ".config" / "cookidoo-cli"
DEFAULT_CONFIG_PATH = APP_DIR / "config.yaml"
DEFAULT_COOKIE_PATH = APP_DIR / "cookies.json"
DEFAULT_PENDING_DIR = APP_DIR / "pending"


class UnsafePrivateFileError(PermissionError):
    pass


def cookidoo_host(country: str) -> str:
    normalized = country.lower()
    if not re.fullmatch(r"[a-z]{2}", normalized):
        raise ValueError("Cookidoo country must be a two-letter code")
    return {
        "gb": "cookidoo.co.uk",
        "tr": "cookidoo.com.tr",
        "us": "cookidoo.thermomix.com",
        "vn": "cookidoo.thermomix.vn",
    }.get(normalized, f"cookidoo.{normalized}")


def cookidoo_base_url(country: str, locale: str) -> str:
    return f"https://{cookidoo_host(country)}/foundation/{locale}"


def ensure_private_file(path: Path) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise UnsafePrivateFileError(f"{path} must be readable only by its owner; run chmod 600")


def write_private_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
    finally:
        os.chmod(path, 0o600)


@dataclass(frozen=True)
class CookidooConfig:
    country: str
    locale: str
    url: str
    cookie_file: str = str(DEFAULT_COOKIE_PATH)
    pending_dir: str = str(DEFAULT_PENDING_DIR)
    default_tm_model: str = "TM7"

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> CookidooConfig:
        site = value.get("site") or {}
        return cls(
            country=str(site.get("country") or value.get("country") or "").lower(),
            locale=str(site.get("locale") or value.get("locale") or ""),
            url=str(site.get("url") or value.get("url") or ""),
            cookie_file=str((value.get("cookies") or {}).get("file") or value.get("cookie_file") or DEFAULT_COOKIE_PATH),
            pending_dir=str((value.get("confirmations") or {}).get("directory") or value.get("pending_dir") or DEFAULT_PENDING_DIR),
            default_tm_model=str(value.get("default_tm_model") or "TM7").upper(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "site": {"country": self.country, "locale": self.locale, "url": self.url},
            "cookies": {"file": self.cookie_file},
            "confirmations": {"directory": self.pending_dir},
            "default_tm_model": self.default_tm_model,
        }

    def validate(self) -> None:
        if not self.country or not self.locale or not self.url:
            raise ValueError("Cookidoo site is not configured; run `cookidoo login`")
        parsed = urlparse(self.url)
        expected_host = cookidoo_host(self.country)
        if parsed.scheme != "https" or parsed.hostname != expected_host:
            raise ValueError(f"Cookidoo site URL must use HTTPS on {expected_host}")
        if not parsed.path.startswith(f"/foundation/{self.locale}"):
            raise ValueError(f"Cookidoo site URL must use the configured locale {self.locale}")


class ConfigStore:
    def __init__(self, path: Path | str = DEFAULT_CONFIG_PATH) -> None:
        self.path = Path(path).expanduser()

    def load(self) -> CookidooConfig:
        if not self.path.exists():
            raise FileNotFoundError(f"Config file {self.path} does not exist; run `cookidoo login`")
        ensure_private_file(self.path)
        payload = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict):
            raise TypeError("Cookidoo config must be a mapping")
        config = CookidooConfig.from_dict(payload)
        config.validate()
        return config

    def load_or_none(self) -> CookidooConfig | None:
        try:
            return self.load()
        except FileNotFoundError:
            return None

    def save(self, config: CookidooConfig) -> None:
        config.validate()
        write_private_text(self.path, yaml.safe_dump(config.to_dict(), sort_keys=False))
