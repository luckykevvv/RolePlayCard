from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

from PIL import Image

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from service import RolePlayCardService


def test_save_and_load_draft(tmp_path):
    service = RolePlayCardService(str(tmp_path))
    payload = {"draft": {"profile": {"name": "测试角色"}}, "saveAs": False}
    save_result = service.save_draft(payload)
    assert save_result["success"] is True

    draft_id = save_result["data"]["id"]
    load_result = service.load_draft(draft_id)
    assert load_result["success"] is True
    assert load_result["data"]["profile"]["name"] == "测试角色"


def test_export_character_card_embeds_tavern_metadata(tmp_path):
    service = RolePlayCardService(str(tmp_path))
    draft = service.save_draft({"draft": {"profile": {"name": "露娜"}, "opening": {"firstMessage": "你好。"}}, "saveAs": False})["data"]

    image_path = tmp_path / "source.png"
    Image.new("RGBA", (32, 32), (255, 0, 0, 255)).save(image_path, format="PNG")

    output_path = tmp_path / "character.png"
    result = service.export_character_card(
        {"draft": draft, "imagePath": str(image_path), "outputPath": str(output_path)}
    )
    assert result["success"] is True

    with Image.open(output_path) as exported:
        chara = exported.text["chara"]

    decoded = json.loads(base64.b64decode(chara).decode("utf-8"))
    assert decoded["name"] == "露娜"
