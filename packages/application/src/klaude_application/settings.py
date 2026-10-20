"""Small, typed compare-and-set seam for shared nonsecret chat preferences."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from klaude_core.settings_store import (
    SettingsConflictError,
    atomic_write_private,
    read_settings,
    settings_lock,
)

SettingKey = Literal["activity_updates", "composer_mode"]
SettingValue = bool | Literal["standard", "vim"]
_MISSING = object()


@dataclass(frozen=True)
class SettingView:
    key: SettingKey
    value: SettingValue
    revision: str


class ChatSettings:
    """Coordinate allowlisted fields with the existing terminal settings writer."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @staticmethod
    def _project(document: dict, key: SettingKey) -> tuple[SettingValue, object]:
        if key == "composer_mode":
            raw = document.get("composer_mode", _MISSING)
            return ("vim" if raw == "vim" else "standard", raw)
        if key == "activity_updates":
            display = document.get("display", {})
            if not isinstance(display, dict):
                raise ValueError("display settings are invalid")
            raw = display.get("activity_updates", _MISSING)
            legacy = display.get("reasoning_activity", _MISSING)
            effective = raw if isinstance(raw, bool) else legacy
            return (effective if isinstance(effective, bool) else True,
                    (raw, legacy) if raw is _MISSING else raw)
        raise ValueError("unsupported setting")

    @staticmethod
    def _revision(raw: object) -> str:
        def safe(value: object) -> object:
            if value is _MISSING:
                return {"missing": True}
            if isinstance(value, tuple):
                return [safe(item) for item in value]
            return value

        payload = json.dumps(safe(raw), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @classmethod
    def _view(cls, document: dict, key: SettingKey) -> SettingView:
        value, raw = cls._project(document, key)
        return SettingView(key, value, cls._revision(raw))

    def read(self, key: SettingKey) -> SettingView:
        # The file is atomically replaced; read_settings sees one complete version.
        return self._view(read_settings(self.path), key)

    def patch(
        self, key: SettingKey, value: SettingValue, *, expected_revision: str,
        request_id: str | None = None,
    ) -> SettingView:
        if key == "activity_updates":
            if type(value) is not bool:
                raise ValueError("activity_updates must be a boolean")
        elif key == "composer_mode":
            if value not in ("standard", "vim") or not isinstance(value, str):
                raise ValueError("composer_mode must be standard or vim")
        else:
            raise ValueError("unsupported setting")
        if request_id is not None and (
            not isinstance(request_id, str) or not 0 < len(request_id) <= 128
            or not request_id.isascii() or not request_id.isprintable()
            or any(character.isspace() for character in request_id)
        ):
            raise ValueError("invalid request ID")
        fingerprint = hashlib.sha256(json.dumps(
            [key, value, expected_revision], ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        with settings_lock(self.path):
            document = read_settings(self.path)
            receipts = document.get("_application_chat_setting_receipts", {})
            if not isinstance(receipts, dict):
                raise OSError("Settings receipts are invalid; repair before saving")
            if request_id is not None and request_id in receipts:
                prior = receipts[request_id]
                if not isinstance(prior, dict) or prior.get("fingerprint") != fingerprint:
                    raise ValueError("request ID already used with different input")
                stored = prior.get("result")
                if not isinstance(stored, dict) or stored.get("key") != key:
                    raise OSError("Settings receipt is invalid; repair before saving")
                return SettingView(key, stored["value"], stored["revision"])
            if self._view(document, key).revision != expected_revision:
                raise SettingsConflictError("Setting changed; reload and retry")
            if key == "activity_updates":
                display = document.setdefault("display", {})
                display["activity_updates"] = value
            else:
                document["composer_mode"] = value
            result = self._view(document, key)
            if request_id is not None:
                receipts[request_id] = {
                    "fingerprint": fingerprint,
                    "result": {"key": key, "value": result.value,
                               "revision": result.revision},
                }
                document["_application_chat_setting_receipts"] = receipts
            atomic_write_private(
                self.path, json.dumps(document, indent=2, ensure_ascii=False) + "\n"
            )
            return result
