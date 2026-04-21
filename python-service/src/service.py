from __future__ import annotations

from pathlib import Path
from typing import Any

from image_tools import embed_tavern_metadata, ensure_png
from models import default_draft, merge_defaults
from prompts import build_field_prompt, build_image_prompt
from providers import ProviderRegistry
from storage import AppStorage


def ok(data: Any = None, message: str = "OK") -> dict[str, Any]:
    return {"success": True, "error_code": None, "message": message, "data": data}


def fail(message: str, error_code: str = "error") -> dict[str, Any]:
    return {"success": False, "error_code": error_code, "message": message, "data": None}


class RolePlayCardService:
    def __init__(self, app_data_dir: str):
        self.storage = AppStorage(app_data_dir)
        self.providers = ProviderRegistry()

    def get_settings(self) -> dict[str, Any]:
        return ok(self.storage.load_settings())

    def save_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        return ok(self.storage.save_settings(settings), "Settings saved.")

    def test_settings(self) -> dict[str, Any]:
        settings = self.storage.load_settings()
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
        draft = merge_defaults(default_draft(), payload["draft"])
        return ok(self.storage.save_draft(draft, save_as=payload.get("saveAs", False)), "Draft saved.")

    def generate_field(self, payload: dict[str, Any]) -> dict[str, Any]:
        settings = self.storage.load_settings()
        config = settings["textProvider"]
        provider = self.providers.get_text_provider(config["provider"])
        valid, detail = provider.validate(config)
        if not valid:
            return fail(detail, "provider_config_invalid")
        prompt = build_field_prompt(payload["field"], payload["mode"], payload.get("userInput", ""), payload["draft"])
        try:
            generated = provider.generate(config, prompt)
        except Exception as exc:  # noqa: BLE001
            return fail(str(exc), "provider_generation_failed")
        return ok({"field": payload["field"], "result": generated, "promptPreview": prompt}, "Field generated.")

    def generate_image_prompt(self, draft: dict[str, Any]) -> dict[str, Any]:
        prompt, negative = build_image_prompt(draft["draft"])
        return ok({"prompt": prompt, "negativePrompt": negative}, "Image prompt generated.")

    def generate_image(self, payload: dict[str, Any]) -> dict[str, Any]:
        settings = self.storage.load_settings()
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

    def export_character_card(self, payload: dict[str, Any]) -> dict[str, Any]:
        draft = payload["draft"]
        image_path = payload["imagePath"]
        output_path = payload["outputPath"]
        if not draft["profile"]["name"].strip():
            return fail("Character name is required.", "validation_error")
        if not draft["opening"]["firstMessage"].strip():
            return fail("First message is required.", "validation_error")
        if not image_path:
            return fail("Image path is required.", "validation_error")

        prepared_path = str(self.storage.cache_images_dir / f"{draft['id']}-export.png")
        ensure_png(image_path, prepared_path)
        embed_tavern_metadata(prepared_path, draft, output_path)
        return ok({"outputPath": output_path}, "Character card exported.")
