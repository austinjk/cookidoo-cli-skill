from __future__ import annotations

import hashlib
import json
import secrets
import stat
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .config import ensure_private_file, write_private_text

DEFAULT_TTL_SECONDS = 15 * 60


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def payload_digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PendingConfirmation:
    token: str
    operation: str
    digest: str
    expires_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "token": self.token,
            "operation": self.operation,
            "payload_sha256": self.digest,
            "expires_at": self.expires_at.isoformat(),
        }


class ConfirmationStore:
    def __init__(self, directory: Path | str, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self.directory = Path(directory).expanduser()
        self.ttl_seconds = ttl_seconds

    def create(self, operation: str, payload: dict[str, Any]) -> PendingConfirmation:
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        mode = stat.S_IMODE(self.directory.stat().st_mode)
        if mode & 0o077:
            raise PermissionError(f"{self.directory} must be accessible only by its owner; run chmod 700")
        self._purge_expired()
        token = f"c_{secrets.token_urlsafe(24)}"
        expires_at = datetime.now(UTC) + timedelta(seconds=self.ttl_seconds)
        record = {
            "token": token,
            "operation": operation,
            "payload": payload,
            "payload_sha256": payload_digest(payload),
            "expires_at": expires_at.isoformat(),
        }
        write_private_text(self.directory / f"{token}.json", json.dumps(record, indent=2, sort_keys=True))
        return PendingConfirmation(token, operation, record["payload_sha256"], expires_at)

    def consume(self, token: str, operation: str, payload: dict[str, Any]) -> PendingConfirmation:
        if not token or "/" in token or "\\" in token:
            raise ValueError("Invalid confirmation token")
        path = self.directory / f"{token}.json"
        if not path.exists():
            raise ValueError("Confirmation token is missing, expired, or already used; run a new dry run")
        ensure_private_file(path)
        record = json.loads(path.read_text(encoding="utf-8"))
        expires_at = datetime.fromisoformat(record["expires_at"])
        if datetime.now(UTC) >= expires_at:
            path.unlink(missing_ok=True)
            raise ValueError("Confirmation token expired; run a new dry run")
        if record.get("operation") != operation:
            raise ValueError("Confirmation token belongs to a different operation")
        digest = payload_digest(payload)
        if record.get("payload_sha256") != digest or record.get("payload") != payload:
            raise ValueError("Payload changed after review; run a new dry run")
        path.unlink()
        return PendingConfirmation(token, operation, digest, expires_at)

    def _purge_expired(self) -> None:
        now = datetime.now(UTC)
        for path in self.directory.glob("*.json"):
            try:
                ensure_private_file(path)
                record = json.loads(path.read_text(encoding="utf-8"))
                expires_at = datetime.fromisoformat(record["expires_at"])
            except (KeyError, PermissionError, ValueError, json.JSONDecodeError):
                continue
            if now >= expires_at:
                path.unlink(missing_ok=True)
