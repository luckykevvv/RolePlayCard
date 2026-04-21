from __future__ import annotations

import base64
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from image_tools import embed_tavern_metadata, ensure_png, import_character_card
from models import default_settings, merge_defaults, normalize_draft
from prompts import build_field_prompt, build_image_prompt
from providers import ProviderRegistry
from storage import AppStorage


def ok(data: Any = None, message: str = "OK") -> dict[str, Any]:
    return {"success": True, "error_code": None, "message": message, "data": data}


def fail(message: str, error_code: str = "error") -> dict[str, Any]:
    return {"success": False, "error_code": error_code, "message": message, "data": None}


def _safe_filename(base: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff\- ]+", "", base).strip()
    return cleaned or "character-card"


class RolePlayCardService:
    def __init__(self, app_data_dir: str):
        self.storage = AppStorage(app_data_dir)
        self.providers = ProviderRegistry()
        self.imports_dir = self.storage.base_dir / "imports"
        self.exports_dir = self.storage.base_dir / "exports"
        self.imports_dir.mkdir(parents=True, exist_ok=True)
        self.exports_dir.mkdir(parents=True, exist_ok=True)

    def _settings_from_payload(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if payload and isinstance(payload.get("settings"), dict):
            return merge_defaults(default_settings(), payload["settings"])
        return default_settings()

    def get_settings(self) -> dict[str, Any]:
        return ok(default_settings())

    def save_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        merged = merge_defaults(default_settings(), settings)
        return ok(merged, "Settings accepted. Persist this in browser cookie.")

    def test_settings(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        settings = self._settings_from_payload(payload)
        results = []
        for key, getter in (
            ("textProvider", self.providers.get_text_provider),
            ("imageProvider", self.providers.get_image_provider),
        ):
            config = settings[key]
            provider = getter(config["provider"])
            valid, detail = provider.validate(config)
            results.append({"provider": config["provider"], "ok": valid, "detail": detail})
        return ok(results)

    def list_drafts(self) -> dict[str, Any]:
        return ok(self.storage.list_drafts())

    def load_draft(self, draft_id: str) -> dict[str, Any]:
        try:
            return ok(self.storage.load_draft(draft_id))
        except FileNotFoundError as exc:
            return fail(str(exc), "draft_not_found")

    def save_draft(self, payload: dict[str, Any]) -> dict[str, Any]:
        draft = normalize_draft(payload["draft"])
        return ok(self.storage.save_draft(draft, save_as=payload.get("saveAs", False)), "Draft saved.")

    def generate_field(self, payload: dict[str, Any]) -> dict[str, Any]:
        settings = self._settings_from_payload(payload)
        config = settings["textProvider"]
        provider = self.providers.get_text_provider(config["provider"])
        valid, detail = provider.validate(config)
        if not valid:
            return fail(detail, "provider_config_invalid")
        draft = normalize_draft(payload["draft"])
        prompt = build_field_prompt(payload["field"], payload["mode"], payload.get("userInput", ""), draft)
        try:
            generated = provider.generate(config, prompt)
        except Exception as exc:  # noqa: BLE001
            return fail(str(exc), "provider_generation_failed")
        return ok({"field": payload["field"], "result": generated, "promptPreview": prompt}, "Field generated.")

    def generate_image_prompt(self, draft: dict[str, Any]) -> dict[str, Any]:
        normalized = normalize_draft(draft["draft"])
        prompt, negative = build_image_prompt(normalized)
        return ok({"prompt": prompt, "negativePrompt": negative}, "Image prompt generated.")

    def generate_image(self, payload: dict[str, Any]) -> dict[str, Any]:
        settings = self._settings_from_payload(payload)
        config = settings["imageProvider"]
        provider = self.providers.get_image_provider(config["provider"])
        valid, detail = provider.validate(config)
        if not valid:
            return fail(detail, "provider_config_invalid")
        try:
            image_path = provider.generate(
                config,
                payload["prompt"],
                payload.get("negativePrompt", ""),
                self.storage.cache_images_dir,
            )
        except Exception as exc:  # noqa: BLE001
            return fail(str(exc), "provider_generation_failed")
        return ok({"imagePath": image_path, "prompt": payload["prompt"]}, "Image generated.")

    def resolve_image_path(self, image_path: str) -> Path:
        candidate = Path(image_path).resolve()
        base = self.storage.base_dir.resolve()
        if base not in candidate.parents and candidate != base:
            raise ValueError("Image path is outside app data directory.")
        if not candidate.exists():
            raise FileNotFoundError("Image file not found.")
        return candidate

    def upload_image_file(self, filename: str, file_bytes: bytes) -> dict[str, Any]:
        extension = Path(filename).suffix.lower()
        if extension not in {".png", ".jpg", ".jpeg", ".webp"}:
            extension = ".png"
        output = self.storage.cache_images_dir / f"{uuid4()}{extension}"
        output.write_bytes(file_bytes)
        return {"path": str(output)}

    def export_character_card_download(self, payload: dict[str, Any]) -> dict[str, Any]:
        draft = normalize_draft(payload["draft"])
        image_path = str(payload.get("imagePath", "")).strip()
        card_name = draft["card"]["name"].strip() or draft["characters"][0]["name"].strip()
        if not card_name:
            return fail("Card name is required.", "validation_error")
        if not draft["opening"]["firstMessage"].strip():
            return fail("First message is required.", "validation_error")
        if not image_path:
            return fail("Image path is required.", "validation_error")

        resolved_image = self.resolve_image_path(image_path)
        prepared_path = self.storage.cache_images_dir / f"{draft['id']}-export.png"
        ensure_png(str(resolved_image), str(prepared_path))
        output_path = self.exports_dir / f"{uuid4()}.png"
        embed_tavern_metadata(str(prepared_path), draft, str(output_path))
        encoded = base64.b64encode(output_path.read_bytes()).decode("utf-8")
        filename = f"{_safe_filename(card_name)}.png"
        return ok({"filename": filename, "imageBase64": encoded}, "Character card exported.")

    def import_character_card_path(self, input_path: str) -> dict[str, Any]:
        try:
            imported = import_character_card(input_path)
        except Exception as exc:  # noqa: BLE001
            return fail(str(exc), "import_failed")
        draft = normalize_draft(imported)
        if not draft["card"]["name"].strip() and draft["characters"]:
            draft["card"]["name"] = draft["characters"][0]["name"]
        if Path(input_path).suffix.lower() == ".png":
            draft["illustration"]["originalImagePath"] = input_path
            draft["illustration"]["generatedImagePath"] = ""
            draft["illustration"]["exportImagePath"] = input_path
        return ok({"draft": draft, "sourcePath": input_path}, "Character card imported.")

    def import_character_card_file(self, filename: str, file_bytes: bytes) -> dict[str, Any]:
        extension = Path(filename).suffix.lower() or ".bin"
        temp_path = self.imports_dir / f"{uuid4()}{extension}"
        temp_path.write_bytes(file_bytes)
        result = self.import_character_card_path(str(temp_path))
        if result["success"] and extension == ".png" and result["data"]:
            result["data"]["draft"]["illustration"]["originalImagePath"] = str(temp_path)
            result["data"]["draft"]["illustration"]["generatedImagePath"] = ""
            result["data"]["draft"]["illustration"]["exportImagePath"] = str(temp_path)
        return result
