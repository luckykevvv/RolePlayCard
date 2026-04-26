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
                "characters": [
                    {
                        "name": "维克",
                        "isUserRole": True,
                        "appearance": "黑色风衣",
                        "personality": "沉稳克制",
                        "speakingExample": "{{user}}: 我们先去哪？\n维克: 先查码头。",
                        "background": "前特工，擅长潜入与情报分析。",
                    },
                    {
                        "name": "露娜",
                        "triggerMode": "always",
                        "appearance": "银发长外套",
                        "personality": "冷静敏锐",
                    },
                ],
                "openings": [
                    {"title": "首屏 1", "firstMessage": "你好。", "scenario": "酒馆"},
                    {"title": "首屏 2", "firstMessage": "又见面了。", "scenario": "街头"},
                ],
                "timeline": {
                    "title": "剧情推进",
                    "enabled": False,
                    "triggerMode": "always",
                    "keywords": ["剧情推进", "主线节点"],
                    "nodes": [
                        {
                            "title": "起点",
                            "timePoint": "开场",
                            "trigger": "玩家进入酒馆",
                            "event": "露娜与玩家碰面并给出任务。",
                            "objective": "建立目标",
                            "conflict": "情报不完整",
                            "outcome": "玩家接取调查线",
                            "nextHook": "前往街头",
                        }
                    ],
                },
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
    assert payload["data"]["description"] == "银发长外套"
    assert payload["data"]["first_mes"] == "你好。"
    assert payload["data"]["alternate_greetings"] == ["又见面了。"]
    assert payload["data"]["character_book"]["entries"]
    user_entry = next(
        (
            entry
            for entry in payload["data"]["character_book"]["entries"]
            if isinstance(entry, dict) and entry.get("comment") == "{{user}}"
        ),
        None,
    )
    assert isinstance(user_entry, dict)
    assert user_entry.get("constant") is True
    user_content = str(user_entry.get("content", ""))
    assert "姓名: {{user}}" in user_content
    assert "背景: 前特工，擅长潜入与情报分析。" in user_content
    assert "维克:" not in user_content
    plot_book_entry = next(
        (entry for entry in payload["data"]["character_book"]["entries"] if entry.get("comment") == "剧情推进"),
        None,
    )
    assert isinstance(plot_book_entry, dict)
    structured_plot = json.loads(plot_book_entry["content"])
    assert structured_plot["guidanceType"] == "plot_progression"
    assert structured_plot["nodes"][0]["title"] == "起点"

    saved_draft = json.loads(roleplaycard)
    assert saved_draft["card"]["name"] == "露娜卡"
    assert any(entry.get("title") == "剧情推进" for entry in saved_draft["worldBook"]["entries"])


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
    assert all(entry["title"] != "剧情推进" for entry in imported_draft["worldBook"]["entries"])
    assert imported_draft["timeline"]["title"] == "剧情推进"
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


def test_import_chara_alternate_greetings_to_openings(tmp_path):
    service = RolePlayCardService(str(tmp_path))
    payload = {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "data": {
            "name": "多首屏测试",
            "scenario": "图书馆",
            "first_mes": "这是主首屏",
            "alternate_greetings": ["这是候选首屏A", "这是候选首屏B"],
        },
    }
    input_path = tmp_path / "multi-openings.json"
    input_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    imported = service.import_character_card_path(str(input_path))
    assert imported["success"] is True
    draft = imported["data"]["draft"]
    assert len(draft["openings"]) == 3
    assert draft["openings"][0]["firstMessage"] == "这是主首屏"
    assert draft["openings"][1]["firstMessage"] == "这是候选首屏A"
    assert draft["openings"][2]["firstMessage"] == "这是候选首屏B"


def test_clear_all_data(tmp_path):
    service = RolePlayCardService(str(tmp_path))
    service.save_draft({"draft": {"card": {"name": "待删除草稿"}}, "saveAs": False})
    service.upload_image_file("temp.png", b"123")
    (tmp_path / "imports").mkdir(parents=True, exist_ok=True)
    (tmp_path / "imports" / "file.bin").write_bytes(b"abc")
    (tmp_path / "exports").mkdir(parents=True, exist_ok=True)
    (tmp_path / "exports" / "file.bin").write_bytes(b"abc")

    cleared = service.clear_all_data()
    assert cleared["success"] is True
    assert service.list_drafts()["data"] == []
    assert (tmp_path / "drafts").exists()
    assert (tmp_path / "cache" / "images").exists()
    assert (tmp_path / "imports").exists()
    assert (tmp_path / "exports").exists()


def test_drafts_are_isolated_by_client_id(tmp_path):
    service = RolePlayCardService(str(tmp_path))
    alice = "alice_client_12345"
    bob = "bob_client_67890"
    service.save_draft({"draft": {"card": {"name": "Alice 草稿"}}, "saveAs": False}, client_id=alice)
    service.save_draft({"draft": {"card": {"name": "Bob 草稿"}}, "saveAs": False}, client_id=bob)

    alice_list = service.list_drafts(client_id=alice)
    bob_list = service.list_drafts(client_id=bob)
    assert alice_list["success"] is True
    assert bob_list["success"] is True
    assert len(alice_list["data"]) == 1
    assert len(bob_list["data"]) == 1
    assert alice_list["data"][0]["name"] == "Alice 草稿"
    assert bob_list["data"][0]["name"] == "Bob 草稿"

    cleared = service.clear_all_data(client_id=alice)
    assert cleared["success"] is True
    assert service.list_drafts(client_id=alice)["data"] == []
    assert len(service.list_drafts(client_id=bob)["data"]) == 1


def test_generate_card_from_story_multiple_characters_and_locations(tmp_path):
    service = RolePlayCardService(str(tmp_path))

    class DummyTextProvider:
        def __init__(self):
            self.calls = 0
            self.prompts = []

        def validate(self, config):
            return True, "ok"

        def generate(self, config, prompt):
            self.calls += 1
            self.prompts.append(prompt)
            if self.calls == 1:
                assert "不同重要时间点/阶段" in prompt
                assert "plotProgression" in prompt
                return json.dumps(
                    {
                        "storySummary": "两位主角共同调查旧案，主要活动地点是仓库与档案馆。",
                        "card": {"name": "长篇小说角色卡", "description": "多角色叙事"},
                        "characters": [
                            {"name": "林夏", "age": "22", "hints": "记者，行动快，擅长追线索"},
                            {"name": "顾沉", "age": "27", "hints": "刑警，稳重理性，重证据"},
                        ],
                        "openings": [
                            {
                                "title": "雨夜调查",
                                "greeting": "我们又见面了。",
                                "scenario": "暴雨中的旧城区",
                                "exampleDialogue": "林夏：线索在仓库。\n顾沉：我先探路。",
                                "firstMessage": "雨声盖过脚步声，你在路灯下看到我向你招手。",
                            }
                        ],
                        "locations": [
                            {
                                "title": "旧城区仓库",
                                "keywords": ["仓库", "旧城区"],
                                "content": "废弃仓库，夜晚常有可疑交易。",
                            },
                            {
                                "title": "中央档案馆",
                                "keywords": ["档案馆", "资料"],
                                "content": "保存城市历史案件卷宗，权限严格。",
                            },
                        ],
                        "plotProgression": {
                            "nodes": [
                                {
                                    "title": "雨夜接触",
                                    "timePoint": "开端",
                                    "trigger": "玩家抵达旧城区",
                                    "event": "林夏与顾沉向玩家说明旧案异动。",
                                    "objective": "建立合作并确定调查方向",
                                    "conflict": "双方对线索来源不完全信任",
                                    "outcome": "决定先查仓库再查档案馆",
                                    "nextHook": "仓库交易记录",
                                },
                                {
                                    "title": "仓库对峙",
                                    "timePoint": "中段",
                                    "trigger": "发现匿名交易痕迹",
                                    "event": "三人确认旧案与走私链条有关。",
                                    "objective": "锁定幕后组织",
                                    "conflict": "线索被人为清理",
                                    "outcome": "转向档案馆核验旧卷宗",
                                    "nextHook": "档案权限异常",
                                },
                                {
                                    "title": "档案揭示",
                                    "timePoint": "后段",
                                    "trigger": "取得核心卷宗",
                                    "event": "核心证据显示旧案被系统性篡改。",
                                    "objective": "形成下一阶段抓捕策略",
                                    "conflict": "对手提前察觉并反制",
                                    "outcome": "主线进入公开对抗阶段",
                                    "nextHook": "寻找内部协助者",
                                },
                            ]
                        },
                    },
                    ensure_ascii=False,
                )
            if self.calls == 2:
                assert "已生成角色（监督输入，必须参考）" in prompt
                assert "[]" in prompt
                assert "这里是一段包含两位主角和两个主要地点的小说内容。" in prompt
                return json.dumps(
                    {
                        "name": "林夏",
                        "age": "22",
                        "triggerKeywords": ["林夏", "记者", "调查"],
                        "appearance": "黑发，短外套",
                        "personality": "冷静执着",
                        "speakingStyle": "简洁直接",
                        "speakingExample": "{{user}}: 先去哪？\n林夏: 先去仓库，线索不会等人。",
                        "background": "城市调查记者",
                    },
                    ensure_ascii=False,
                )
            if self.calls == 3:
                assert "林夏" in prompt
                assert "这里是一段包含两位主角和两个主要地点的小说内容。" in prompt
                return json.dumps(
                    {
                        "name": "顾沉",
                        "age": "27",
                        "triggerKeywords": ["顾沉", "刑警", "证据"],
                        "appearance": "高个，风衣",
                        "personality": "克制理性",
                        "speakingStyle": "平稳低声",
                        "speakingExample": "{{user}}: 现在抓人吗？\n顾沉: 不，证据链先补齐。",
                        "background": "重案组刑警",
                    },
                    ensure_ascii=False,
                )
            raise AssertionError("unexpected extra provider.generate call")

        def list_models(self, config):
            return ["dummy-model"]

    dummy_provider = DummyTextProvider()
    service.providers.text_providers["openai_compatible"] = dummy_provider

    payload = {
        "draft": {"card": {"name": ""}},
        "storyText": "这里是一段包含两位主角和两个主要地点的小说内容。",
        "settings": {
            "textProvider": {
                "provider": "openai_compatible",
                "baseUrl": "https://example.com/v1",
                "apiKey": "test-key",
                "model": "dummy-model",
            }
        },
    }
    result = service.generate_card_from_story(payload)
    assert result["success"] is True
    draft = result["data"]["draft"]
    assert draft["card"]["name"] == "长篇小说角色卡"
    assert len(draft["characters"]) == 2
    assert draft["characters"][0]["name"] == "林夏"
    assert draft["characters"][0]["age"] == "22"
    assert draft["characters"][1]["name"] == "顾沉"
    assert len(draft["worldBook"]["entries"]) == 2
    assert all(entry["triggerMode"] == "keyword" for entry in draft["worldBook"]["entries"])
    assert all(entry["title"] != "剧情推进" for entry in draft["worldBook"]["entries"])
    assert draft["timeline"]["title"] == "剧情推进"
    assert draft["timeline"]["triggerMode"] == "always"
    assert draft["timeline"]["enabled"] is False
    assert len(draft["timeline"]["nodes"]) >= 3
    assert draft["timeline"]["nodes"][0]["parentId"] == ""
    assert draft["timeline"]["nodes"][1]["parentId"] == draft["timeline"]["nodes"][0]["id"]
    assert draft["timeline"]["nodes"][2]["parentId"] == draft["timeline"]["nodes"][1]["id"]
    assert dummy_provider.calls == 3


def test_generate_card_from_story_fallback_plot_progression_when_missing(tmp_path):
    service = RolePlayCardService(str(tmp_path))

    class DummyTextProvider:
        def __init__(self):
            self.calls = 0

        def validate(self, config):
            return True, "ok"

        def generate(self, config, prompt):
            self.calls += 1
            if self.calls == 1:
                return json.dumps(
                    {
                        "storySummary": "一位调查员追查港口失踪案。",
                        "card": {"name": "失踪案追查", "description": "单角色测试"},
                        "characters": [{"name": "阿澈", "age": "24", "hints": "调查员"}],
                        "openings": [
                            {
                                "title": "深夜港口",
                                "greeting": "你来晚了。",
                                "scenario": "暴雨夜的港口仓区",
                                "exampleDialogue": "阿澈：线索在码头。\n你：有人跟踪你吗？",
                                "firstMessage": "你刚靠近堆场，我从暗处把你拽进雨棚。",
                            }
                        ],
                        "locations": [
                            {
                                "title": "北码头仓区",
                                "keywords": ["码头", "仓区"],
                                "content": "夜间货运频繁，监控盲区较多。",
                            }
                        ],
                    },
                    ensure_ascii=False,
                )
            if self.calls == 2:
                assert "剧情推进结构化指导生成器" in prompt
                # 第二次调用：剧情推进结构化指导，故意返回非 JSON 触发 fallback。
                return "not-json"
            if self.calls == 3:
                return json.dumps(
                    {
                        "name": "阿澈",
                        "age": "24",
                        "triggerKeywords": ["阿澈", "调查员"],
                        "appearance": "黑色雨衣，短发",
                        "personality": "谨慎敏锐",
                        "speakingStyle": "低声简短",
                        "speakingExample": "{{user}}: 现在怎么办？\n阿澈: 先看货单，再看人。",
                        "background": "长期追查港口案件",
                    },
                    ensure_ascii=False,
                )
            raise AssertionError("unexpected extra provider.generate call")

        def list_models(self, config):
            return ["dummy-model"]

    dummy_provider = DummyTextProvider()
    service.providers.text_providers["openai_compatible"] = dummy_provider
    payload = {
        "draft": {"card": {"name": ""}},
        "storyText": "短篇小说文本",
        "settings": {
            "textProvider": {
                "provider": "openai_compatible",
                "baseUrl": "https://example.com/v1",
                "apiKey": "test-key",
                "model": "dummy-model",
            }
        },
    }
    result = service.generate_card_from_story(payload)
    assert result["success"] is True
    draft = result["data"]["draft"]
    assert len(draft["worldBook"]["entries"]) == 1
    assert all(entry["title"] != "剧情推进" for entry in draft["worldBook"]["entries"])
    assert draft["openings"]
    assert draft["openings"][0]["firstMessage"].strip()
    assert draft["timeline"]["triggerMode"] == "always"
    assert draft["timeline"]["enabled"] is False
    assert len(draft["timeline"]["nodes"]) >= 3
    assert draft["timeline"]["nodes"][0]["parentId"] == ""
    assert draft["timeline"]["nodes"][1]["parentId"] == draft["timeline"]["nodes"][0]["id"]
    assert draft["timeline"]["nodes"][2]["parentId"] == draft["timeline"]["nodes"][1]["id"]
    assert dummy_provider.calls == 3


def test_generate_card_from_story_segment_mode_enriches_character_details(tmp_path):
    service = RolePlayCardService(str(tmp_path))

    class DummyTextProvider:
        def __init__(self):
            self.calls = 0

        def validate(self, config):
            return True, "ok"

        def generate(self, config, prompt):
            self.calls += 1
            if self.calls == 1:
                assert "长篇分段增量提取" in prompt
                return json.dumps(
                    {
                        "storySummary": "林夏和顾沉在雨夜调查旧案。",
                        "card": {"name": "分段补全测试", "description": "测试首段补全角色详情"},
                        "characters": [
                            {"name": "林夏", "age": "22", "hints": "调查记者", "triggerKeywords": ["林夏", "记者"]},
                            {"name": "顾沉", "age": "27", "hints": "重案组刑警", "triggerKeywords": ["顾沉", "刑警"]},
                        ],
                        "openings": [
                            {
                                "title": "雨夜接触",
                                "greeting": "你终于来了。",
                                "scenario": "暴雨夜的旧城区路口",
                                "exampleDialogue": "林夏：线索在仓库。\n顾沉：先确认撤离路线。",
                                "firstMessage": "雨幕里我把档案袋塞进你怀里，示意你跟上。",
                            }
                        ],
                        "locations": [
                            {"title": "旧城区仓库", "keywords": ["仓库"], "content": "夜间可疑车辆频繁出现。"}
                        ],
                        "plotProgression": {
                            "nodes": [
                                {
                                    "id": "n1",
                                    "title": "雨夜碰头",
                                    "timePoint": "今夜",
                                    "trigger": "玩家抵达路口",
                                    "event": "双方交换旧案线索",
                                    "objective": "确定调查方向",
                                    "conflict": "信息来源不一致",
                                    "outcome": "决定先查仓库",
                                    "nextHook": "仓库暗门",
                                },
                                {
                                    "id": "n2",
                                    "title": "仓库潜入",
                                    "parentId": "n1",
                                    "timePoint": "今夜稍后",
                                    "trigger": "找到暗门入口",
                                    "event": "进入仓库内部侦察",
                                    "objective": "确认交易证据",
                                    "conflict": "巡逻加强",
                                    "outcome": "拍到关键照片",
                                    "nextHook": "档案馆线索",
                                },
                            ]
                        },
                    },
                    ensure_ascii=False,
                )
            if self.calls == 2:
                assert "目标角色：林夏" in prompt
                return json.dumps(
                    {
                        "name": "林夏",
                        "age": "22",
                        "triggerKeywords": ["林夏", "记者", "调查员"],
                        "appearance": "黑短发，防水短外套，肩背相机包",
                        "personality": "行动迅速，警惕性高",
                        "speakingStyle": "节奏快，句子短",
                        "speakingExample": "{{user}}: 先去哪？\n林夏: 先仓库，错过今晚就没线索了。",
                        "background": "城市调查记者，长期追查旧案。",
                    },
                    ensure_ascii=False,
                )
            if self.calls == 3:
                assert "目标角色：顾沉" in prompt
                return json.dumps(
                    {
                        "name": "顾沉",
                        "age": "27",
                        "triggerKeywords": ["顾沉", "刑警", "证据链"],
                        "appearance": "高个风衣，神情冷静，左手常握记录本",
                        "personality": "克制理性，重视证据",
                        "speakingStyle": "语速稳，逻辑清晰",
                        "speakingExample": "{{user}}: 现在收网吗？\n顾沉: 不，证据还差最后一环。",
                        "background": "重案组刑警，负责旧案复核。",
                    },
                    ensure_ascii=False,
                )
            raise AssertionError("unexpected extra provider.generate call")

        def list_models(self, config):
            return ["dummy-model"]

    dummy_provider = DummyTextProvider()
    service.providers.text_providers["openai_compatible"] = dummy_provider
    payload = {
        "draft": {"card": {"name": ""}},
        "storyText": "分段文本：雨夜调查旧案。",
        "segmentMode": True,
        "settings": {
            "textProvider": {
                "provider": "openai_compatible",
                "baseUrl": "https://example.com/v1",
                "apiKey": "test-key",
                "model": "dummy-model",
            }
        },
    }
    result = service.generate_card_from_story(payload)
    assert result["success"] is True
    draft = result["data"]["draft"]
    assert len(draft["characters"]) == 2
    lin_xia = next(item for item in draft["characters"] if item["name"] == "林夏")
    gu_chen = next(item for item in draft["characters"] if item["name"] == "顾沉")
    assert lin_xia["appearance"].strip()
    assert lin_xia["speakingStyle"].strip()
    assert gu_chen["appearance"].strip()
    assert gu_chen["speakingExample"].strip()
    assert dummy_provider.calls == 3


def test_generate_card_from_story_fallback_openings_when_outline_missing_openings(tmp_path):
    service = RolePlayCardService(str(tmp_path))

    class DummyTextProvider:
        def __init__(self):
            self.calls = 0

        def validate(self, config):
            return True, "ok"

        def generate(self, config, prompt):
            self.calls += 1
            if self.calls == 1:
                return json.dumps(
                    {
                        "storySummary": "主角在寒夜中追查关键线索。",
                        "card": {"name": "缺省首屏测试", "description": "测试 fallback openings"},
                        "characters": [{"name": "阿澈", "hints": "调查员"}],
                        "locations": [{"title": "峡谷据点", "keywords": ["峡谷"], "content": "据点设定"}],
                        "plotProgression": {
                            "nodes": [
                                {
                                    "id": "n1",
                                    "title": "追猎开端",
                                    "timePoint": "寒夜当前",
                                    "trigger": "收到线报后出发",
                                    "event": "抵达峡谷外围开始侦察",
                                    "objective": "确认目标动向",
                                    "conflict": "风雪掩盖痕迹",
                                    "outcome": "锁定可疑路线",
                                    "nextHook": "深入峡谷",
                                }
                            ]
                        },
                    },
                    ensure_ascii=False,
                )
            if self.calls == 2:
                return json.dumps(
                    {
                        "name": "阿澈",
                        "triggerKeywords": ["阿澈"],
                        "background": "调查员",
                    },
                    ensure_ascii=False,
                )
            raise AssertionError("unexpected extra provider.generate call")

        def list_models(self, config):
            return ["dummy-model"]

    service.providers.text_providers["openai_compatible"] = DummyTextProvider()
    payload = {
        "draft": {"card": {"name": ""}},
        "storyText": "测试文本",
        "settings": {
            "textProvider": {
                "provider": "openai_compatible",
                "baseUrl": "https://example.com/v1",
                "apiKey": "test-key",
                "model": "dummy-model",
            }
        },
    }
    result = service.generate_card_from_story(payload)
    assert result["success"] is True
    draft = result["data"]["draft"]
    assert draft["openings"]
    opening = draft["openings"][0]
    assert opening["title"].strip()
    assert opening["scenario"].strip()
    assert opening["firstMessage"].strip()


def test_generate_card_from_story_branches_when_same_timepoint(tmp_path):
    service = RolePlayCardService(str(tmp_path))

    class DummyTextProvider:
        def __init__(self):
            self.calls = 0

        def validate(self, config):
            return True, "ok"

        def generate(self, config, prompt):
            self.calls += 1
            if self.calls == 1:
                return json.dumps(
                    {
                        "storySummary": "分叉测试",
                        "card": {"name": "分叉结构测试", "description": "时间线分叉"},
                        "characters": [{"name": "伊芙", "age": "21", "hints": "调查员"}],
                        "openings": [
                            {
                                "title": "开场",
                                "greeting": "开始吧。",
                                "scenario": "雨夜街区",
                                "exampleDialogue": "伊芙：我们分头查。",
                                "firstMessage": "雨夜里你看见我在路口挥手。",
                            }
                        ],
                        "locations": [{"title": "街区", "keywords": ["街区"], "content": "案发现场附近。"}],
                        "plotProgression": {
                            "nodes": [
                                {
                                    "title": "节点A",
                                    "timePoint": "开端",
                                    "trigger": "玩家到场",
                                    "event": "接到主线",
                                    "objective": "建立目标",
                                    "conflict": "线索不足",
                                    "outcome": "进入调查",
                                    "nextHook": "中段A",
                                },
                                {
                                    "title": "节点B1",
                                    "timePoint": "中段",
                                    "trigger": "查第一条线",
                                    "event": "锁定嫌疑人甲",
                                    "objective": "确认动机",
                                    "conflict": "证词矛盾",
                                    "outcome": "出现分支1",
                                    "nextHook": "后段",
                                },
                                {
                                    "title": "节点B2",
                                    "timePoint": "中段",
                                    "trigger": "查第二条线",
                                    "event": "锁定嫌疑人乙",
                                    "objective": "确认不在场证明",
                                    "conflict": "监控缺失",
                                    "outcome": "出现分支2",
                                    "nextHook": "后段",
                                },
                                {
                                    "title": "节点C",
                                    "timePoint": "后段",
                                    "trigger": "合并两条线索",
                                    "event": "逼近真相",
                                    "objective": "收束主线",
                                    "conflict": "对手反制",
                                    "outcome": "终局前夜",
                                    "nextHook": "终局",
                                },
                            ]
                        },
                    },
                    ensure_ascii=False,
                )
            if self.calls == 2:
                return json.dumps(
                    {
                        "name": "伊芙",
                        "age": "21",
                        "triggerKeywords": ["伊芙", "调查员"],
                        "appearance": "短发，风衣",
                        "personality": "冷静",
                        "speakingStyle": "简练",
                        "speakingExample": "{{user}}: 接下来？\n伊芙: 两条线并查。",
                        "background": "调查员",
                    },
                    ensure_ascii=False,
                )
            raise AssertionError("unexpected extra provider.generate call")

        def list_models(self, config):
            return ["dummy-model"]

    dummy_provider = DummyTextProvider()
    service.providers.text_providers["openai_compatible"] = dummy_provider
    payload = {
        "draft": {"card": {"name": ""}},
        "storyText": "分叉小说文本",
        "settings": {
            "textProvider": {
                "provider": "openai_compatible",
                "baseUrl": "https://example.com/v1",
                "apiKey": "test-key",
                "model": "dummy-model",
            }
        },
    }
    result = service.generate_card_from_story(payload)
    assert result["success"] is True
    nodes = result["data"]["draft"]["timeline"]["nodes"]
    assert len(nodes) >= 4

    node_a = nodes[0]
    node_b1 = nodes[1]
    node_b2 = nodes[2]
    node_c = nodes[3]

    assert node_a["parentId"] == ""
    assert node_b1["parentId"] == node_a["id"]
    assert node_b2["parentId"] == node_a["id"]
    assert node_c["parentId"] == node_b1["id"]
    assert dummy_provider.calls == 2


def test_enforce_progression_parenting_starts_new_root_on_flashback_cut(tmp_path):
    service = RolePlayCardService(str(tmp_path))
    nodes = [
        {
            "id": "n1",
            "title": "家破人亡",
            "timePoint": "三年前的冬夜",
            "event": "加油站被洗劫",
        },
        {
            "id": "n2",
            "title": "仇恨发芽",
            "timePoint": "三年前之后数月",
            "event": "她开始追查责任人",
        },
        {
            "id": "n3",
            "title": "任务开启",
            "timePoint": "当前（寒夜）",
            "event": "主线行动正式开始",
        },
        {
            "id": "n4",
            "title": "潜入推进",
            "timePoint": "次日凌晨",
            "event": "进入目标区域",
        },
    ]
    normalized = service._enforce_progression_parenting(nodes)
    assert normalized[0]["parentId"] == ""
    assert normalized[1]["parentId"] == normalized[0]["id"]
    assert normalized[2]["parentId"] == ""
    assert normalized[3]["parentId"] == normalized[2]["id"]


def test_extract_plot_nodes_compacts_overlong_fields(tmp_path):
    service = RolePlayCardService(str(tmp_path))
    payload = {
        "plotProgression": {
            "nodes": [
                {
                    "id": "n1",
                    "title": "这是一个特别特别长而且会超过限制的时间线节点标题，需要被压缩",
                    "timePoint": "三年前那个暴雨不停的夜晚之后的漫长低谷阶段",
                    "trigger": "因为前线指挥官突然下达了多重互相冲突且执行成本很高的临时命令导致局势失控",
                    "event": "她在撤离途中连续遭遇误导、伏击和队内冲突，最终在极端混乱中被迫做出高风险选择并承担后果，整段描述故意写得很长来测试压缩能力",
                    "objective": "在资源严重不足和信息不完整的情况下确保关键目标存活并维持主线推进",
                    "conflict": "外部火力封锁与内部信任崩塌同时发生，任何选择都会带来代价",
                    "outcome": "虽然暂时脱险但失去了关键补给与同伴支持，后续难度显著上升",
                    "nextHook": "转入次日凌晨的前哨站渗透行动并验证关键情报真伪",
                }
            ]
        }
    }
    nodes = service._extract_plot_nodes(payload)
    assert len(nodes) == 1
    node = nodes[0]
    assert len(node["title"]) <= 25
    assert len(node["timePoint"]) <= 25
    assert len(node["trigger"]) <= 49
    assert len(node["event"]) <= 97
    assert len(node["objective"]) <= 57
    assert len(node["conflict"]) <= 57
    assert len(node["outcome"]) <= 57
    assert len(node["nextHook"]) <= 49


def test_normalize_timeline_time_axis_uses_single_baseline_and_format(tmp_path):
    service = RolePlayCardService(str(tmp_path))
    timeline = {
        "title": "剧情推进",
        "nodes": [
            {"id": "n1", "title": "前史", "timePoint": "三年前", "event": "事故发生"},
            {"id": "n2", "title": "转折", "timePoint": "当前/今夜", "event": "任务开始"},
            {"id": "n3", "title": "推进", "timePoint": "次日凌晨", "event": "继续行动"},
        ],
    }
    normalized = service._normalize_timeline_time_axis(timeline)
    assert normalized["timeBaseline"].startswith("T0=")
    assert normalized["timeFormat"] == "T±<offset> | 时间描述"
    points = [node["timePoint"] for node in normalized["nodes"]]
    assert points[0].startswith("T-")
    assert points[1].startswith("T+0D")
    assert points[2].startswith("T+")
    assert all(" | " in point for point in points)


def test_organize_timeline_returns_optional_proposal(tmp_path):
    service = RolePlayCardService(str(tmp_path))

    class DummyTextProvider:
        def validate(self, config):
            return True, "ok"

        def generate(self, config, prompt):
            assert "时间线总编" in prompt
            return json.dumps(
                {
                    "timeBaseline": "T0=当前主线时刻",
                    "timeFormat": "T±<offset> | 时间描述",
                    "nodes": [
                        {
                            "id": "n-old",
                            "title": "当前任务开始",
                            "parentId": "",
                            "timePoint": "当前/今夜",
                            "trigger": "接令",
                            "event": "启动行动",
                            "objective": "进入主线",
                            "conflict": "情报不足",
                            "outcome": "继续推进",
                            "nextHook": "次日追踪",
                        },
                        {
                            "id": "n-old-2",
                            "title": "次日追踪",
                            "parentId": "n-old",
                            "timePoint": "次日凌晨",
                            "trigger": "获得新线索",
                            "event": "前往目标点",
                            "objective": "确认目标",
                            "conflict": "遭遇阻击",
                            "outcome": "保留突破口",
                            "nextHook": "后续收束",
                        },
                    ],
                },
                ensure_ascii=False,
            )

        def list_models(self, config):
            return ["dummy-model"]

    service.providers.text_providers["openai_compatible"] = DummyTextProvider()
    payload = {
        "draft": {
            "timeline": {
                "title": "剧情推进",
                "nodes": [
                    {"id": "n1", "title": "旧节点", "timePoint": "三年前", "event": "旧事件"},
                    {"id": "n2", "title": "旧节点2", "timePoint": "现在", "event": "旧事件2"},
                ],
            }
        },
        "settings": {
            "textProvider": {
                "provider": "openai_compatible",
                "baseUrl": "https://example.com/v1",
                "apiKey": "test-key",
                "model": "dummy-model",
            }
        },
    }
    result = service.organize_timeline(payload)
    assert result["success"] is True
    data = result["data"]
    proposal = data["proposalTimeline"]
    assert proposal["timeBaseline"].startswith("T0=")
    assert proposal["timeFormat"] == "T±<offset> | 时间描述"
    assert len(proposal["nodes"]) == 2
    assert all(" | " in str(node["timePoint"]) for node in proposal["nodes"])
    assert data["summary"]["nodeCountBefore"] == 2
    assert data["summary"]["nodeCountAfter"] == 2


def test_plot_progression_worldbook_entry_migrates_to_timeline(tmp_path):
    service = RolePlayCardService(str(tmp_path))
    payload = {
        "draft": {
            "card": {"name": "迁移测试卡"},
            "worldBook": {
                "entries": [
                    {
                        "title": "剧情推进",
                        "triggerMode": "always",
                        "enabled": False,
                        "keywords": ["剧情推进", "主线节点"],
                        "content": json.dumps(
                            {
                                "guidanceType": "plot_progression",
                                "nodes": [
                                    {
                                        "title": "节点A",
                                        "timePoint": "开端",
                                        "trigger": "遇见关键角色",
                                        "event": "开始调查",
                                        "objective": "确定目标",
                                        "conflict": "信息不足",
                                        "outcome": "进入下一阶段",
                                        "nextHook": "前往仓库",
                                    }
                                ],
                            },
                            ensure_ascii=False,
                        ),
                    },
                    {
                        "title": "普通地点",
                        "keywords": ["仓库"],
                        "content": "一处普通地点。",
                    },
                ]
            },
        },
        "saveAs": False,
    }
    saved = service.save_draft(payload)
    assert saved["success"] is True
    normalized = saved["data"]
    assert normalized["timeline"]["title"] == "剧情推进"
    assert len(normalized["timeline"]["nodes"]) == 1
    assert normalized["timeline"]["nodes"][0]["title"] == "节点A"
    assert all(entry["title"] != "剧情推进" for entry in normalized["worldBook"]["entries"])
    assert len(normalized["worldBook"]["entries"]) == 1


def test_list_text_prefix_prompts(tmp_path):
    service = RolePlayCardService(str(tmp_path))
    prompts_dir = tmp_path / "jailbreak-prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    (prompts_dir / "gpt-4o.txt").write_text("内置破限 A", encoding="utf-8")
    (prompts_dir / "gpt-4.1.txt").write_text("内置破限 B", encoding="utf-8")
    service.text_prefix_prompts_dir = prompts_dir

    result = service.list_text_prefix_prompts()
    assert result["success"] is True
    assert result["data"]["directory"] == str(prompts_dir)
    assert result["data"]["items"] == [
        {"model": "gpt-4.1", "filename": "gpt-4.1.txt"},
        {"model": "gpt-4o", "filename": "gpt-4o.txt"},
    ]


def test_generate_field_uses_builtin_prefix_prompt(tmp_path):
    service = RolePlayCardService(str(tmp_path))
    prompts_dir = tmp_path / "jailbreak-prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    (prompts_dir / "gpt-4o.txt").write_text("这是内置前置词", encoding="utf-8")
    service.text_prefix_prompts_dir = prompts_dir

    class DummyTextProvider:
        def __init__(self):
            self.last_config = {}

        def validate(self, config):
            return True, "ok"

        def generate(self, config, prompt):
            self.last_config = dict(config)
            return "生成结果"

        def list_models(self, config):
            return ["gpt-4o"]

    dummy_provider = DummyTextProvider()
    service.providers.text_providers["openai_compatible"] = dummy_provider

    payload = {
        "field": "card.description",
        "mode": "generate",
        "userInput": "",
        "draft": {"card": {"name": "测试卡", "description": ""}},
        "settings": {
            "textProvider": {
                "provider": "openai_compatible",
                "baseUrl": "https://example.com/v1",
                "apiKey": "test-key",
                "model": "gpt-4o",
                "prefixPromptMode": "builtin",
                "builtinPrefixPromptModel": "gpt-4o",
                "prefixPrompt": "这是自定义兜底词",
            }
        },
    }
    result = service.generate_field(payload)
    assert result["success"] is True
    assert dummy_provider.last_config["prefixPrompt"] == "这是内置前置词"


def test_generate_field_builtin_prefix_fallbacks_to_custom_when_missing(tmp_path):
    service = RolePlayCardService(str(tmp_path))
    prompts_dir = tmp_path / "jailbreak-prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    service.text_prefix_prompts_dir = prompts_dir

    class DummyTextProvider:
        def __init__(self):
            self.last_config = {}

        def validate(self, config):
            return True, "ok"

        def generate(self, config, prompt):
            self.last_config = dict(config)
            return "生成结果"

        def list_models(self, config):
            return ["gpt-4o"]

    dummy_provider = DummyTextProvider()
    service.providers.text_providers["openai_compatible"] = dummy_provider

    payload = {
        "field": "card.description",
        "mode": "generate",
        "userInput": "",
        "draft": {"card": {"name": "测试卡", "description": ""}},
        "settings": {
            "textProvider": {
                "provider": "openai_compatible",
                "baseUrl": "https://example.com/v1",
                "apiKey": "test-key",
                "model": "gpt-4o",
                "prefixPromptMode": "builtin",
                "builtinPrefixPromptModel": "gpt-4o",
                "prefixPrompt": "这是自定义兜底词",
            }
        },
    }
    result = service.generate_field(payload)
    assert result["success"] is True
    assert dummy_provider.last_config["prefixPrompt"] == "这是自定义兜底词"


def test_preview_story_segments_prefers_chapter_then_hard_split(tmp_path):
    service = RolePlayCardService(str(tmp_path))
    long_part = "甲" * 20500
    story_text = f"第1章 雨夜\n{long_part}\n第2章 尾声\n这是第二章内容。"

    result = service.preview_story_segments({"storyText": story_text, "maxCharsPerSegment": 20000})
    assert result["success"] is True
    data = result["data"]
    assert data["segmentationMode"] == "chapter"
    assert len(data["segments"]) >= 3
    assert all(segment["charCount"] <= 20000 for segment in data["segments"])
    assert "第1章" in data["segments"][0]["title"]


def test_preview_story_segments_fallback_to_hard_buffer(tmp_path):
    service = RolePlayCardService(str(tmp_path))
    story_text = "这是没有章节标题的长文本。" + ("乙" * 42000)

    result = service.preview_story_segments({"storyText": story_text, "maxCharsPerSegment": 20000})
    assert result["success"] is True
    data = result["data"]
    assert data["segmentationMode"] == "hard_buffer"
    assert len(data["segments"]) >= 3
    assert all(segment["charCount"] <= 20000 for segment in data["segments"])


def test_preview_story_segments_with_custom_regex(tmp_path):
    service = RolePlayCardService(str(tmp_path))
    story_text = "ACT 1\n第一幕内容\nACT 2\n第二幕内容"
    result = service.preview_story_segments(
        {
            "storyText": story_text,
            "settings": {
                "storySegmentation": {
                    "chapterRegex": r"(?im)^ACT\s+\d+.*$",
                    "maxCharsPerSegment": 20000,
                }
            },
        }
    )
    assert result["success"] is True
    data = result["data"]
    assert data["segmentationMode"] == "chapter"
    assert len(data["segments"]) == 2
    assert data["chapterRegex"] == r"(?im)^ACT\s+\d+.*$"


def test_preview_story_segments_invalid_regex(tmp_path):
    service = RolePlayCardService(str(tmp_path))
    result = service.preview_story_segments(
        {
            "storyText": "第1章 示例",
            "chapterRegex": "(",
        }
    )
    assert result["success"] is False
    assert result["error_code"] == "validation_error"


def test_preview_story_segments_accepts_mistyped_inline_flags(tmp_path):
    service = RolePlayCardService(str(tmp_path))
    story_text = "第一幕：加州军妓\n正文"
    result = service.preview_story_segments(
        {
            "storyText": story_text,
            "chapterRegex": r"(?:imx)^[ \t]*第[0-9零〇一二三四五六七八九十百千两]+幕[^\n\r]*[ \t]*$",
        }
    )
    assert result["success"] is True
    assert result["data"]["segmentationMode"] == "chapter"
    assert len(result["data"]["segments"]) == 1
    assert result["data"]["chapterRegex"].startswith("(?imx)")


def test_preview_story_segments_accepts_mistyped_inline_flags_with_bom_and_spaces(tmp_path):
    service = RolePlayCardService(str(tmp_path))
    story_text = "第一幕：加州军妓\n正文"
    result = service.preview_story_segments(
        {
            "storyText": story_text,
            "chapterRegex": "\ufeff   (?:imx)^[ \\t]*第[0-9零〇一二三四五六七八九十百千两]+幕[^\\n\\r]*[ \\t]*$",
        }
    )
    assert result["success"] is True
    assert result["data"]["segmentationMode"] == "chapter"
    assert len(result["data"]["segments"]) == 1
    assert "(?imx)" in result["data"]["chapterRegex"]


def test_merge_segment_generated_draft_update_existing_policy(tmp_path):
    service = RolePlayCardService(str(tmp_path))
    base_draft = service.save_draft(
        {
            "draft": {
                "card": {"name": "旧卡名", "description": ""},
                "characters": [
                    {
                        "name": "林夏",
                        "triggerKeywords": ["林夏"],
                        "appearance": "黑色风衣",
                        "background": "旧背景",
                    }
                ],
                "worldBook": {
                    "entries": [
                        {
                            "title": "旧城区仓库",
                            "keywords": ["仓库"],
                            "content": "旧内容",
                        }
                    ]
                },
                "timeline": {
                    "nodes": [
                        {
                            "id": "root",
                            "title": "旧节点",
                            "event": "旧事件",
                        }
                    ]
                },
            },
            "saveAs": False,
        }
    )["data"]

    incoming_draft = {
        "card": {"name": "新卡名", "description": "补充描述"},
        "characters": [
            {
                "name": "林夏",
                "triggerKeywords": ["林夏", "记者"],
                "appearance": "红色夹克",
                "age": "22",
                "background": "新背景",
            },
            {
                "name": "顾沉",
                "triggerKeywords": ["顾沉", "刑警"],
                "background": "重案组刑警",
            },
        ],
        "worldBook": {
            "entries": [
                {
                    "title": "旧城区仓库",
                    "keywords": ["旧城区", "仓库"],
                    "content": "新内容",
                },
                {
                    "title": "中央档案馆",
                    "keywords": ["档案馆"],
                    "content": "新地点内容",
                },
            ]
        },
        "timeline": {
            "nodes": [
                {"id": "n1", "title": "第一段", "event": "事件1"},
                {"id": "n2", "parentId": "n1", "title": "第二段", "event": "事件2"},
            ]
        },
    }

    merged, report = service._merge_segment_generated_draft(base_draft, incoming_draft, segment_index=1)
    assert merged["card"]["name"] == "旧卡名"
    assert merged["card"]["description"] == "补充描述"
    assert len(merged["characters"]) == 2
    lin_xia = next(item for item in merged["characters"] if item["name"] == "林夏")
    assert lin_xia["age"] == "22"
    assert lin_xia["appearance"] == "红色夹克"
    assert "记者" in lin_xia["triggerKeywords"]
    assert len(merged["worldBook"]["entries"]) == 2
    warehouse = next(item for item in merged["worldBook"]["entries"] if item["title"] == "旧城区仓库")
    assert warehouse["content"] == "新内容"
    assert "旧城区" in warehouse["keywords"]
    appended_nodes = [node for node in merged["timeline"]["nodes"] if node["id"].startswith("s2_")]
    assert len(appended_nodes) == 2
    child = next(node for node in appended_nodes if node["title"] == "第二段")
    parent = next(node for node in appended_nodes if node["title"] == "第一段")
    assert child["parentId"] == parent["id"]
    assert report["newCharactersCount"] == 1
    assert report["newLocationsCount"] == 1
    assert report["newTimelineNodesCount"] == 2
    assert report["ignoredConflictCount"] == 0


def test_merge_segment_generated_draft_promotes_named_character_and_sets_card_name(tmp_path):
    service = RolePlayCardService(str(tmp_path))
    base_draft = service.save_draft({"draft": {"card": {"name": ""}}, "saveAs": False})["data"]
    incoming_draft = {
        "card": {"name": "", "description": "补充描述"},
        "characters": [
            {
                "name": "林夏",
                "triggerKeywords": ["林夏", "记者"],
                "appearance": "黑色短外套",
                "background": "城市调查记者",
            }
        ],
        "timeline": {"nodes": []},
    }

    merged, _report = service._merge_segment_generated_draft(base_draft, incoming_draft, segment_index=0)
    assert merged["characters"]
    assert merged["characters"][0]["name"] == "林夏"
    assert merged["card"]["name"] == "林夏"


def test_merge_segment_generated_draft_dedup_character_alias_and_timeline(tmp_path):
    service = RolePlayCardService(str(tmp_path))
    base_draft = {
        "card": {"name": "测试卡", "description": ""},
        "characters": [
            {
                "name": "琉塞菲亚",
                "triggerKeywords": ["琉塞菲亚"],
                "appearance": "旧外观",
            }
        ],
        "timeline": {
            "nodes": [
                {
                    "id": "root",
                    "title": "开场",
                    "event": "旧开场",
                    "parentId": "",
                }
            ]
        },
    }
    incoming = {
        "characters": [
            {
                "name": "琉塞菲亚(Luciphira)",
                "triggerKeywords": ["Luciphira", "琉塞菲亚"],
                "appearance": "新外观",
            }
        ],
        "timeline": {
            "nodes": [
                {
                    "id": "n1",
                    "title": "开场",
                    "event": "新开场",
                    "parentId": "",
                },
                {
                    "id": "n2",
                    "title": "冲突",
                    "event": "爆发冲突",
                    "parentId": "n1",
                },
            ]
        },
    }

    merged, report = service._merge_segment_generated_draft(base_draft, incoming, segment_index=2)
    named_characters = [item for item in merged["characters"] if item["name"]]
    assert len(named_characters) == 1
    character = named_characters[0]
    assert character["name"] == "琉塞菲亚(Luciphira)"
    assert character["appearance"] == "新外观"
    assert "Luciphira" in character["triggerKeywords"]

    nodes = merged["timeline"]["nodes"]
    assert len(nodes) == 2
    opening = next(item for item in nodes if item["title"] == "开场")
    conflict = next(item for item in nodes if item["title"] == "冲突")
    assert opening["event"] == "新开场"
    assert conflict["parentId"] == opening["id"]
    assert report["newCharactersCount"] == 0
    assert report["newTimelineNodesCount"] == 1


def test_merge_segment_generated_draft_upserts_openings(tmp_path):
    service = RolePlayCardService(str(tmp_path))
    base_draft = service.save_draft({"draft": {"card": {"name": "测试"}}, "saveAs": False})["data"]
    incoming_first = {
        "openings": [
            {
                "title": "雨夜初遇",
                "greeting": "你来了。",
                "scenario": "暴雨旧城区",
                "exampleDialogue": "她：跟上我。",
                "firstMessage": "雨幕里她朝你招手。",
            }
        ]
    }
    merged_first, _ = service._merge_segment_generated_draft(base_draft, incoming_first, segment_index=0)
    assert merged_first["openings"]
    assert merged_first["openings"][0]["title"] == "雨夜初遇"
    assert merged_first["openings"][0]["firstMessage"] == "雨幕里她朝你招手。"

    incoming_second = {
        "openings": [
            {
                "title": "雨夜初遇",
                "firstMessage": "雨夜里她把卷宗塞进你手里。",
            },
            {
                "title": "档案馆对峙",
                "scenario": "地下档案库",
                "firstMessage": "灯光闪烁，她低声让你别出声。",
            },
        ]
    }
    merged_second, _ = service._merge_segment_generated_draft(merged_first, incoming_second, segment_index=1)
    assert len(merged_second["openings"]) == 2
    first_opening = next(item for item in merged_second["openings"] if item["title"] == "雨夜初遇")
    second_opening = next(item for item in merged_second["openings"] if item["title"] == "档案馆对峙")
    assert first_opening["firstMessage"] == "雨夜里她把卷宗塞进你手里。"
    assert second_opening["firstMessage"] == "灯光闪烁，她低声让你别出声。"


def test_merge_segment_generated_draft_does_not_bridge_flashback_root(tmp_path):
    service = RolePlayCardService(str(tmp_path))
    class BridgeJudgeProvider:
        def generate(self, config, prompt):
            return json.dumps(
                {
                    "decisions": [
                        {"nodeId": "s4_n1", "bridgeToAnchor": False},
                    ]
                },
                ensure_ascii=False,
            )

    base_draft = {
        "timeline": {
            "nodes": [
                {
                    "id": "current",
                    "title": "峡谷追猎",
                    "timePoint": "当前（寒夜）",
                    "event": "正在执行任务",
                    "parentId": "",
                }
            ]
        }
    }
    incoming = {
        "timeline": {
            "nodes": [
                {
                    "id": "n1",
                    "title": "沦落与觉醒",
                    "timePoint": "三年前至数月前",
                    "event": "回忆过去经历",
                    "parentId": "",
                },
                {
                    "id": "n2",
                    "title": "转型清道夫",
                    "timePoint": "妓院被袭后不久",
                    "event": "加入清道夫组织",
                    "parentId": "n1",
                },
            ]
        }
    }
    merged, report = service._merge_segment_generated_draft(
        base_draft,
        incoming,
        segment_index=3,
        provider=BridgeJudgeProvider(),
        runtime_config={"model": "judge"},
    )
    nodes = [item for item in merged["timeline"]["nodes"] if isinstance(item, dict)]
    flashback_root = next(item for item in nodes if item.get("title") == "沦落与觉醒")
    flashback_child = next(item for item in nodes if item.get("title") == "转型清道夫")
    assert flashback_root["parentId"] == ""
    assert flashback_child["parentId"] == flashback_root["id"]
    assert report["newTimelineNodesCount"] == 2


def test_story_segment_api_flow_preview_then_incremental_updates(tmp_path):
    service = RolePlayCardService(str(tmp_path))
    class DummyBridgeJudgeProvider:
        def validate(self, config):
            return True, "ok"

        def list_models(self, config):
            return ["dummy-model"]

        def generate(self, config, prompt):
            return json.dumps(
                {
                    "decisions": [
                        {"nodeId": "s2_n1", "bridgeToAnchor": True},
                        {"nodeId": "s2_n2", "bridgeToAnchor": True},
                    ]
                },
                ensure_ascii=False,
            )

    service.providers.text_providers["openai_compatible"] = DummyBridgeJudgeProvider()
    story_text = "第1章 开场\n这是第一段。\n第2章 对峙\n这是第二段。"
    preview = service.preview_story_segments({"storyText": story_text, "maxCharsPerSegment": 20000})
    assert preview["success"] is True
    segments = preview["data"]["segments"]
    assert len(segments) >= 2

    generated_drafts = [
        {
            "card": {"name": "分段卡", "description": ""},
            "characters": [{"name": "林夏", "triggerKeywords": ["林夏"], "background": "记者"}],
            "worldBook": {"entries": [{"title": "旧城区仓库", "keywords": ["仓库"], "content": "仓库设定"}]},
            "timeline": {"nodes": [{"id": "n1", "title": "开场节点", "event": "开场事件"}]},
        },
        {
            "card": {"name": "分段卡新名", "description": "补充描述"},
            "characters": [
                {"name": "林夏", "triggerKeywords": ["林夏", "调查员"], "background": "新背景"},
                {"name": "顾沉", "triggerKeywords": ["顾沉"], "background": "刑警"},
            ],
            "worldBook": {
                "entries": [
                    {"title": "旧城区仓库", "keywords": ["旧城区"], "content": "仓库新设定"},
                    {"title": "中央档案馆", "keywords": ["档案馆"], "content": "档案馆设定"},
                ]
            },
            "timeline": {
                "nodes": [
                    {"id": "n1", "title": "中段节点", "event": "中段事件"},
                    {"id": "n2", "parentId": "n1", "title": "后段节点", "event": "后段事件"},
                ]
            },
        },
    ]

    call_count = {"value": 0}

    def fake_generate_card_from_story(payload):
        idx = call_count["value"]
        call_count["value"] += 1
        return {
            "success": True,
            "error_code": None,
            "message": "ok",
            "data": {
                "draft": generated_drafts[idx],
                "raw": "{}",
            },
        }

    service.generate_card_from_story = fake_generate_card_from_story  # type: ignore[method-assign]

    base_draft = service.save_draft({"draft": {"card": {"name": ""}}, "saveAs": False})["data"]
    base_draft["storyGenerationState"] = {
        "totalSegments": len(segments),
        "currentSegmentIndex": 0,
        "segmentationMode": preview["data"]["segmentationMode"],
    }

    first = service.generate_card_from_story_segment(
        {
            "draft": base_draft,
            "segmentText": story_text[segments[0]["start"] : segments[0]["end"]],
            "segmentIndex": 0,
            "totalSegments": len(segments),
            "settings": {
                "textProvider": {
                    "provider": "openai_compatible",
                    "baseUrl": "https://example.com/v1",
                    "apiKey": "test-key",
                    "model": "dummy-model",
                }
            },
        }
    )
    assert first["success"] is True
    first_draft = first["data"]["draft"]
    assert first_draft["storyGenerationState"]["currentSegmentIndex"] == 1
    assert first["data"]["segmentReport"]["newCharactersCount"] == 1

    second = service.generate_card_from_story_segment(
        {
            "draft": first_draft,
            "segmentText": story_text[segments[1]["start"] : segments[1]["end"]],
            "segmentIndex": 1,
            "totalSegments": len(segments),
            "settings": {
                "textProvider": {
                    "provider": "openai_compatible",
                    "baseUrl": "https://example.com/v1",
                    "apiKey": "test-key",
                    "model": "dummy-model",
                }
            },
        }
    )
    assert second["success"] is True
    second_draft = second["data"]["draft"]
    assert second_draft["storyGenerationState"]["currentSegmentIndex"] == 2
    named_characters = [item for item in second_draft["characters"] if item["name"]]
    assert len(named_characters) == 2
    assert len(second_draft["worldBook"]["entries"]) == 2
    assert second["data"]["segmentReport"]["newTimelineNodesCount"] == 2
    timeline_nodes = [item for item in second_draft["timeline"]["nodes"] if isinstance(item, dict)]
    opening = next(item for item in timeline_nodes if item.get("title") == "开场节点")
    mid = next(item for item in timeline_nodes if item.get("title") == "中段节点")
    late = next(item for item in timeline_nodes if item.get("title") == "后段节点")
    assert mid["parentId"] == opening["id"]
    assert late["parentId"] == mid["id"]


def test_settings_endpoints_are_stateless_in_web_mode(tmp_path):
    service = RolePlayCardService(str(tmp_path))
    payload = {
        "textProvider": {
            "provider": "openai_compatible",
            "baseUrl": "https://example.com/v1",
            "apiKey": "abc",
            "model": "text-model",
        },
        "imageProvider": {
            "provider": "openai_compatible",
            "baseUrl": "https://img.example.com/v1",
            "apiKey": "img-key",
            "model": "image-model",
        },
    }
    saved = service.save_settings(payload)
    assert saved["success"] is True
    assert saved["data"]["textProvider"]["model"] == "text-model"
    loaded = service.get_settings()
    assert loaded["success"] is True
    assert loaded["data"]["textProvider"]["model"] == ""
    assert loaded["data"]["imageProvider"]["baseUrl"] == "https://api.openai.com/v1"


def test_generate_card_from_story_segment_returns_change_set(tmp_path):
    service = RolePlayCardService(str(tmp_path))

    class DummyBridgeJudgeProvider:
        def validate(self, config):
            return True, "ok"

        def list_models(self, config):
            return ["dummy-model"]

        def generate(self, config, prompt):
            return json.dumps({"decisions": []}, ensure_ascii=False)

    service.providers.text_providers["openai_compatible"] = DummyBridgeJudgeProvider()
    base_draft = {
        "card": {"name": "测试卡"},
        "characters": [{"name": "林夏", "triggerKeywords": ["林夏"]}],
        "worldBook": {"entries": []},
        "timeline": {"nodes": []},
    }

    generated_draft = {
        "card": {"name": "测试卡"},
        "characters": [
            {"name": "林夏", "triggerKeywords": ["林夏", "记者"], "background": "调查记者"},
            {"name": "顾沉", "triggerKeywords": ["顾沉"], "background": "刑警"},
        ],
        "worldBook": {
            "entries": [
                {"title": "旧城区仓库", "keywords": ["仓库"], "content": "仓库设定"},
            ]
        },
        "timeline": {"nodes": [{"id": "n1", "title": "开场", "event": "开场事件"}]},
    }

    def fake_generate_card_from_story(payload):
        return {
            "success": True,
            "error_code": None,
            "message": "ok",
            "data": {"draft": generated_draft, "raw": "{}"},
        }

    service.generate_card_from_story = fake_generate_card_from_story  # type: ignore[method-assign]

    result = service.generate_card_from_story_segment(
        {
            "draft": base_draft,
            "segmentText": "测试分段文本",
            "segmentIndex": 0,
            "totalSegments": 1,
            "settings": {
                "textProvider": {
                    "provider": "openai_compatible",
                    "baseUrl": "https://example.com/v1",
                    "apiKey": "test-key",
                    "model": "dummy-model",
                }
            },
        }
    )
    assert result["success"] is True
    data = result["data"]
    assert isinstance(data, dict)
    change_set = data.get("changeSet", {})
    assert "顾沉" in change_set["characters"]["added"]
    assert "林夏" in change_set["characters"]["updated"]
    assert "旧城区仓库" in change_set["locations"]["added"]
    assert "开场" in change_set["timelineNodes"]["added"]
