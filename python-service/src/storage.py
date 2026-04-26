from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

from models import default_draft, default_settings, merge_defaults, normalize_draft, now_iso

TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class AppStorage:
    def __init__(self, app_data_dir: str):
        self.base_dir = Path(app_data_dir)
        self.settings_path = self.base_dir / "settings.json"
        self.drafts_dir = self.base_dir / "drafts"
        self.cache_images_dir = self.base_dir / "cache" / "images"
        self.logs_dir = self.base_dir / "logs"
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.drafts_dir.mkdir(parents=True, exist_ok=True)
        self.cache_images_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def _normalize_token(self, value: str, label: str) -> str:
        token = str(value or "").strip()
        if not TOKEN_RE.fullmatch(token):
            raise ValueError(f"invalid {label}")
        return token

    def _draft_scope_dir(self, client_id: str) -> Path:
        normalized = self._normalize_token(client_id, "client_id")
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]
        scope = self.drafts_dir / digest
        scope.mkdir(parents=True, exist_ok=True)
        return scope

    def load_settings(self) -> dict[str, Any]:
        if not self.settings_path.exists():
            defaults = default_settings()
            self.save_settings(defaults)
            return defaults
        with self.settings_path.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        return merge_defaults(default_settings(), loaded)

    def save_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        merged = merge_defaults(default_settings(), settings)
        with self.settings_path.open("w", encoding="utf-8") as handle:
            json.dump(merged, handle, ensure_ascii=False, indent=2)
        return merged

    def list_drafts(self, client_id: str = "default") -> list[dict[str, str]]:
        scope_dir = self._draft_scope_dir(client_id)
        drafts: list[dict[str, str]] = []
        for path in sorted(scope_dir.glob("*.json")):
            with path.open("r", encoding="utf-8") as handle:
                draft = normalize_draft(json.load(handle))
            name = draft["card"]["name"].strip()
            if not name:
                name = draft["characters"][0]["name"].strip()
            drafts.append(
                {
                    "id": draft["id"],
                    "name": name,
                    "updatedAt": draft["updatedAt"],
                }
            )
        drafts.sort(key=lambda item: item["updatedAt"], reverse=True)
        return drafts

    def load_draft(self, draft_id: str, client_id: str = "default") -> dict[str, Any]:
        scope_dir = self._draft_scope_dir(client_id)
        draft_key = self._normalize_token(draft_id, "draft_id")
        path = scope_dir / f"{draft_key}.json"
        if not path.exists():
            raise FileNotFoundError(f"Draft {draft_id} not found.")
        with path.open("r", encoding="utf-8") as handle:
            return normalize_draft(json.load(handle))

    def save_draft(self, draft: dict[str, Any], save_as: bool = False, client_id: str = "default") -> dict[str, Any]:
        scope_dir = self._draft_scope_dir(client_id)
        merged = normalize_draft(draft)
        current_id = str(merged.get("id", "")).strip()
        id_invalid = False
        try:
            if current_id:
                self._normalize_token(current_id, "draft_id")
        except ValueError:
            id_invalid = True
        if save_as or id_invalid or not current_id:
            merged["id"] = str(uuid4())
            merged["createdAt"] = now_iso()
        merged["updatedAt"] = now_iso()
        path = scope_dir / f"{merged['id']}.json"
        with path.open("w", encoding="utf-8") as handle:
            json.dump(merged, handle, ensure_ascii=False, indent=2)
        return merged

    def clear_all_data(self, client_id: str = "default") -> dict[str, int]:
        scope_dir = self._draft_scope_dir(client_id)
        removed_items = 0
        if scope_dir.exists():
            for child in scope_dir.iterdir():
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink(missing_ok=True)
                removed_items += 1
        scope_dir.mkdir(parents=True, exist_ok=True)
        return {"removedItems": removed_items}
