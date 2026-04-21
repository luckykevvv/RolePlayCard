from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from PIL import Image
from PIL.PngImagePlugin import PngInfo


def ensure_png(source_path: str, output_path: str) -> str:
    source = Path(source_path)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        rgba = image.convert("RGBA")
        rgba.save(target, format="PNG")
    return str(target)


def draft_to_tavern_character(draft: dict[str, Any]) -> dict[str, Any]:
    profile = draft["profile"]
    opening = draft["opening"]
    return {
        "name": profile["name"],
        "description": profile["appearance"],
        "personality": profile["personality"],
        "scenario": opening["scenario"],
        "first_mes": opening["firstMessage"],
        "mes_example": opening["exampleDialogue"],
        "creator_notes": draft["worldBook"],
        "system_prompt": "",
        "post_history_instructions": "",
        "tags": ["RolePlayCard"],
    }


def embed_tavern_metadata(source_png: str, draft: dict[str, Any], output_path: str) -> str:
    character_payload = draft_to_tavern_character(draft)
    chara = base64.b64encode(json.dumps(character_payload, ensure_ascii=False).encode("utf-8")).decode("utf-8")
    pnginfo = PngInfo()
    pnginfo.add_text("chara", chara)
    pnginfo.add_text("roleplaycard", json.dumps(draft, ensure_ascii=False))
    with Image.open(source_png) as image:
        image.save(output_path, format="PNG", pnginfo=pnginfo)
    return output_path
