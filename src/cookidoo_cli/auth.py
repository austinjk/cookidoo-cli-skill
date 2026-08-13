from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import ensure_private_file, write_private_text

REQUIRED_COOKIE_NAMES = {"_oauth2_proxy", "v-authenticated"}


@dataclass(frozen=True)
class AuthStatus:
    authenticated: bool
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {"authenticated": self.authenticated, "message": self.message}


class CookieStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path).expanduser()

    def save_entries(self, entries: list[dict[str, Any]]) -> None:
        names = {str(item.get("key") or item.get("name") or "") for item in entries}
        missing = REQUIRED_COOKIE_NAMES - names
        if missing:
            raise ValueError(f"Cookidoo login did not return required session cookies: {sorted(missing)}")
        write_private_text(self.path, json.dumps(entries, indent=2, sort_keys=True))

    def load_entries(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            raise FileNotFoundError(f"Cookie file {self.path} does not exist; run `cookidoo login`")
        ensure_private_file(self.path)
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise TypeError("Cookie file must contain a JSON list")
        return payload

    def status(self) -> AuthStatus:
        try:
            entries = self.load_entries()
        except (FileNotFoundError, PermissionError, TypeError, ValueError, json.JSONDecodeError) as exc:
            return AuthStatus(False, str(exc))
        names = {str(item.get("key") or item.get("name") or "") for item in entries}
        missing = REQUIRED_COOKIE_NAMES - names
        if missing:
            return AuthStatus(False, f"Cookie file is missing required Cookidoo cookies: {sorted(missing)}")
        return AuthStatus(True, "Cookidoo session cookie jar is available")
