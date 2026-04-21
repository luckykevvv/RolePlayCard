from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from models import default_draft, default_settings, merge_defaults, normalize_draft, now_iso


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

    def list_drafts(self) -> list[dict[str, str]]:
        drafts: list[dict[str, str]] = []
        for path in sorted(self.drafts_dir.glob("*.json")):
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

    def load_draft(self, draft_id: str) -> dict[str, Any]:
        path = self.drafts_dir / f"{draft_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Draft {draft_id} not found.")
        with path.open("r", encoding="utf-8") as handle:
            return normalize_draft(json.load(handle))

    def save_draft(self, draft: dict[str, Any], save_as: bool = False) -> dict[str, Any]:
        merged = normalize_draft(draft)
        if save_as:
            merged["id"] = str(uuid4())
            merged["createdAt"] = now_iso()
        merged["updatedAt"] = now_iso()
        path = self.drafts_dir / f"{merged['id']}.json"
        with path.open("w", encoding="utf-8") as handle:
            json.dump(merged, handle, ensure_ascii=False, indent=2)
        return merged
