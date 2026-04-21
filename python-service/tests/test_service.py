from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

from PIL import Image
from PIL.PngImagePlugin import PngInfo

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from service import RolePlayCardService


def test_save_and_load_draft(tmp_path):
    service = RolePlayCardService(str(tmp_path))
    payload = {
        "draft": {
            "card": {"name": "测试角色卡"},
            "characters": [{"name": "测试角色", "triggerKeywords": ["测试角色"]}],
        },
        "saveAs": False,
    }
    save_result = service.save_draft(payload)
    assert save_result["success"] is True

    draft_id = save_result["data"]["id"]
    load_result = service.load_draft(draft_id)
    assert load_result["success"] is True
    assert load_result["data"]["card"]["name"] == "测试角色卡"
    assert load_result["data"]["characters"][0]["name"] == "测试角色"


def test_export_character_card_embeds_tavern_metadata(tmp_path):
    service = RolePlayCardService(str(tmp_path))
    draft = service.save_draft(
        {
            "draft": {
                "card": {"name": "露娜卡"},
                "characters": [{"name": "露娜", "triggerMode": "always"}],
                "opening": {"firstMessage": "你好。"},
            },
            "saveAs": False,
        }
    )["data"]

    image_path = tmp_path / "source.png"
    Image.new("RGBA", (32, 32), (255, 0, 0, 255)).save(image_path, format="PNG")

    result = service.export_character_card_download({"draft": draft, "imagePath": str(image_path)})
    assert result["success"] is True
    output_path = tmp_path / "decoded.png"
    output_path.write_bytes(base64.b64decode(result["data"]["imageBase64"]))

    with Image.open(output_path) as exported:
        chara = exported.text["chara"]
        roleplaycard = exported.text["roleplaycard"]

    payload = json.loads(base64.b64decode(chara).decode("utf-8"))
    assert payload["spec"] == "chara_card_v2"
    assert payload["data"]["name"] == "露娜卡"
    assert payload["data"]["character_book"]["entries"]

    saved_draft = json.loads(roleplaycard)
    assert saved_draft["card"]["name"] == "露娜卡"


def test_import_character_card_from_exported_png(tmp_path):
    service = RolePlayCardService(str(tmp_path))
    draft = service.save_draft(
        {
            "draft": {
                "card": {"name": "导入测试卡"},
                "characters": [{"name": "艾拉", "triggerKeywords": ["艾拉", "Ayla"]}],
                "opening": {"firstMessage": "欢迎来到测试世界。"},
                "worldBook": {
                    "entries": [
                        {
                            "title": "组织设定",
                            "keywords": ["公会"],
                            "content": "公会负责发布悬赏。",
                        }
                    ]
                },
            },
            "saveAs": False,
        }
    )["data"]

    image_path = tmp_path / "source.png"
    Image.new("RGBA", (64, 64), (0, 0, 0, 255)).save(image_path, format="PNG")
    export_result = service.export_character_card_download({"draft": draft, "imagePath": str(image_path)})
    assert export_result["success"] is True
    output_path = tmp_path / "importable.png"
    output_path.write_bytes(base64.b64decode(export_result["data"]["imageBase64"]))

    imported = service.import_character_card_path(str(output_path))
    assert imported["success"] is True
    imported_draft = imported["data"]["draft"]
    assert imported_draft["card"]["name"] == "导入测试卡"
    assert imported_draft["characters"][0]["name"] == "艾拉"
    assert imported_draft["worldBook"]["entries"]
    assert imported_draft["illustration"]["generatedImagePath"] == ""


def test_import_chara_v2_with_dict_worldbook_entries(tmp_path):
    service = RolePlayCardService(str(tmp_path))
    payload = {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "data": {
            "name": "测试导入卡",
            "description": "测试角色",
            "personality": "沉着冷静",
            "first_mes": "你好",
            "character_book": {
                "entries": {
                    "0": {
                        "comment": "组织设定",
                        "keys": ["组织", "联盟"],
                        "content": "这是一个跨城联盟组织。",
                        "enabled": True,
                        "constant": False,
                        "insertion_order": 210,
                    }
                }
            },
        },
    }
    input_path = tmp_path / "import-v2.json"
    input_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    imported = service.import_character_card_path(str(input_path))
    assert imported["success"] is True
    draft = imported["data"]["draft"]
    assert draft["card"]["name"] == "测试导入卡"
    assert draft["worldBook"]["entries"]
    entry = draft["worldBook"]["entries"][0]
    assert entry["title"] == "组织设定"
    assert "组织" in entry["keywords"]


def test_import_png_ccv3_fallback(tmp_path):
    service = RolePlayCardService(str(tmp_path))
    payload = {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "data": {
            "name": "CCV3卡",
            "first_mes": "你好",
            "character_book": {
                "entries": [
                    {
                        "comment": "测试条目",
                        "keys": ["关键词A"],
                        "content": "条目内容",
                    }
                ]
            },
        },
    }
    encoded = base64.b64encode(json.dumps(payload, ensure_ascii=False).encode("utf-8")).decode("utf-8")
    png_path = tmp_path / "ccv3-only.png"
    pnginfo = PngInfo()
    pnginfo.add_text("ccv3", encoded)
    Image.new("RGBA", (24, 24), (255, 255, 255, 255)).save(png_path, format="PNG", pnginfo=pnginfo)

    imported = service.import_character_card_path(str(png_path))
    assert imported["success"] is True
    draft = imported["data"]["draft"]
    assert draft["card"]["name"] == "CCV3卡"
    assert draft["worldBook"]["entries"]


def test_import_chara_v3_entries(tmp_path):
    service = RolePlayCardService(str(tmp_path))
    payload = {
        "spec": "chara_card_v3",
        "spec_version": "3.0",
        "data": {
            "name": "V3卡",
            "first_mes": "hello",
            "character_book": {
                "entries": [
                    {
                        "comment": "V3条目",
                        "keys": ["v3-key"],
                        "content": "v3 content",
                        "enabled": True,
                        "constant": False,
                        "position": "after_char",
                    }
                ]
            },
        },
    }
    encoded = base64.b64encode(json.dumps(payload, ensure_ascii=False).encode("utf-8")).decode("utf-8")
    png_path = tmp_path / "v3.png"
    pnginfo = PngInfo()
    pnginfo.add_text("chara", encoded)
    Image.new("RGBA", (20, 20), (0, 0, 0, 255)).save(png_path, format="PNG", pnginfo=pnginfo)

    imported = service.import_character_card_path(str(png_path))
    assert imported["success"] is True
    draft = imported["data"]["draft"]
    assert draft["card"]["name"] == "V3卡"
    assert len(draft["worldBook"]["entries"]) == 1
