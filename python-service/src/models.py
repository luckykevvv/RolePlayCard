from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from typing import Any
from uuid import uuid4

DEFAULT_CHAPTER_REGEX = (
    r"(?imx)^[ \t]*(第[0-9零〇一二三四五六七八九十百千两]+[章节卷回篇集部幕][^\n\r]*"
    r"|卷[0-9零〇一二三四五六七八九十百千两]+[^\n\r]*"
    r"|幕[0-9零〇一二三四五六七八九十百千两]+[^\n\r]*"
    r"|chapter[ \t]+[0-9ivxlcdm]+[^\n\r]*"
    r"|volume[ \t]+[0-9ivxlcdm]+[^\n\r]*)[ \t]*$"
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_provider_config() -> dict[str, Any]:
    return {
        "provider": "openai_compatible",
        "baseUrl": "https://api.openai.com/v1",
        "apiKey": "",
        "model": "",
        "timeoutMs": 45000,
        "temperature": 0.8,
        "enabled": True,
        "prefixPrompt": "",
        "prefixPromptMode": "custom",
        "builtinPrefixPromptModel": "",
        "extraHeaders": {},
    }


def default_settings() -> dict[str, Any]:
    return {
        "textProvider": default_provider_config(),
        "imageProvider": default_provider_config(),
        "storySegmentation": default_story_segmentation_settings(),
        "exportDirectory": "",
        "recentDirectory": "",
    }


def default_story_segmentation_settings() -> dict[str, Any]:
    return {
        "chapterRegex": DEFAULT_CHAPTER_REGEX,
        "maxCharsPerSegment": 20000,
    }


def default_advanced_options() -> dict[str, Any]:
    return {
        "insertionOrder": 200,
        "triggerProbability": 100,
        "insertionPosition": "after_char",
        "depth": 4,
    }


def default_character_entry() -> dict[str, Any]:
    return {
        "id": str(uuid4()),
        "enabled": True,
        "triggerMode": "keyword",
        "isUserRole": False,
        "name": "",
        "triggerKeywords": [],
        "age": "",
        "appearance": "",
        "personality": "",
        "speakingStyle": "",
        "speakingExample": "",
        "background": "",
        "advanced": default_advanced_options(),
    }


def default_world_book_entry() -> dict[str, Any]:
    return {
        "id": str(uuid4()),
        "enabled": True,
        "triggerMode": "keyword",
        "title": "",
        "keywords": [],
        "content": "",
        "advanced": default_advanced_options(),
    }


def default_opening_entry() -> dict[str, Any]:
    return {
        "id": str(uuid4()),
        "title": "首屏 1",
        "greeting": "",
        "scenario": "",
        "exampleDialogue": "",
        "firstMessage": "",
    }


def default_timeline_node() -> dict[str, Any]:
    return {
        "id": str(uuid4()),
        "parentId": "",
        "title": "",
        "timePoint": "",
        "trigger": "",
        "event": "",
        "objective": "",
        "conflict": "",
        "outcome": "",
        "nextHook": "",
    }


def default_timeline() -> dict[str, Any]:
    return {
        "title": "剧情推进",
        "enabled": False,
        "triggerMode": "always",
        "keywords": ["剧情推进", "主线节点", "剧情走向"],
        "timeBaseline": "T0=当前主线时刻",
        "timeFormat": "T±<offset> | 时间描述",
        "nodes": [],
    }


def default_story_generation_state() -> dict[str, Any]:
    return {
        "totalSegments": 0,
        "currentSegmentIndex": 0,
        "segmentationMode": "hard_buffer",
    }


def default_batch_generation_state() -> dict[str, Any]:
    return {
        "status": "idle",
        "currentSegment": 0,
        "totalSegments": 0,
        "failedSegmentIndex": None,
        "errorMessage": "",
    }


def default_workflow_state() -> dict[str, Any]:
    return {
        "editorMode": "expert",
        "wizardStep": "input",
        "batchGeneration": default_batch_generation_state(),
    }


def default_draft() -> dict[str, Any]:
    timestamp = now_iso()
    opening = default_opening_entry()
    return {
        "id": str(uuid4()),
        "version": 2,
        "sourceType": "roleplaycard",
        "createdAt": timestamp,
        "updatedAt": timestamp,
        "card": {
            "name": "",
            "description": "",
        },
        "characters": [default_character_entry()],
        "opening": deepcopy(opening),  # legacy compatibility for 0.0.1/0.0.2 payloads
        "openings": [opening],
        "worldBook": {
            "entries": [],
        },
        "timeline": default_timeline(),
        "illustration": {
            "originalImagePath": "",
            "generatedImagePath": "",
            "exportImagePath": "",
            "promptSnapshot": "",
            "negativePrompt": "",
            "stylePrompt": "",
        },
        "storyGenerationState": None,
        "workflowState": default_workflow_state(),
    }


def merge_defaults(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_defaults(merged[key], value)
        else:
            merged[key] = value
    return merged


def _split_keywords(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _normalize_timeline_nodes(raw_nodes: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_nodes, list):
        return []
    normalized_nodes: list[dict[str, Any]] = []
    for item in raw_nodes:
        if not isinstance(item, dict):
            continue
        merged = merge_defaults(default_timeline_node(), item)
        merged["id"] = str(merged.get("id", "")).strip() or str(uuid4())
        merged["parentId"] = str(merged.get("parentId", "")).strip()
        merged["title"] = str(merged.get("title", ""))
        merged["timePoint"] = str(merged.get("timePoint", ""))
        merged["trigger"] = str(merged.get("trigger", ""))
        merged["event"] = str(merged.get("event", ""))
        merged["objective"] = str(merged.get("objective", ""))
        merged["conflict"] = str(merged.get("conflict", ""))
        merged["outcome"] = str(merged.get("outcome", ""))
        merged["nextHook"] = str(merged.get("nextHook", ""))
        normalized_nodes.append(merged)

    valid_ids = {node["id"] for node in normalized_nodes}
    for node in normalized_nodes:
        parent_id = str(node.get("parentId", "")).strip()
        if not parent_id or parent_id == node["id"] or parent_id not in valid_ids:
            node["parentId"] = ""
    return normalized_nodes


def _extract_timeline_nodes_from_world_entry_content(content: str) -> list[dict[str, Any]]:
    raw_text = str(content or "")
    if not raw_text:
        return []
    parsed: Any = None
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        parsed = None

    candidate_nodes: Any = []
    if isinstance(parsed, dict):
        if isinstance(parsed.get("nodes"), list):
            candidate_nodes = parsed["nodes"]
        elif isinstance(parsed.get("plotProgression"), dict) and isinstance(parsed["plotProgression"].get("nodes"), list):
            candidate_nodes = parsed["plotProgression"]["nodes"]
    if isinstance(candidate_nodes, list) and len(candidate_nodes) == 0 and isinstance(parsed, dict):
        return []

    normalized: list[dict[str, Any]] = []
    if isinstance(candidate_nodes, list):
        for item in candidate_nodes:
            if not isinstance(item, dict):
                continue
            normalized.append(
                {
                    "title": str(item.get("title", item.get("name", item.get("stage", "")))),
                    "timePoint": str(item.get("timePoint", item.get("time", item.get("timeline", "")))),
                    "trigger": str(item.get("trigger", item.get("triggerCondition", item.get("condition", "")))),
                    "event": str(item.get("event", item.get("keyEvent", item.get("summary", "")))),
                    "objective": str(item.get("objective", item.get("goal", ""))),
                    "conflict": str(item.get("conflict", item.get("obstacle", ""))),
                    "outcome": str(item.get("outcome", item.get("result", ""))),
                    "nextHook": str(item.get("nextHook", item.get("next", item.get("nextStep", "")))),
                    "parentId": str(item.get("parentId", item.get("parent", ""))),
                }
            )
    if normalized:
        return _normalize_timeline_nodes(normalized)

    return _normalize_timeline_nodes([{"title": "主线节点 1", "event": raw_text}])


def normalize_draft(incoming: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize incoming draft data and migrate legacy 0.0.1 schema.
    """

    upgraded = deepcopy(incoming)

    # 0.0.1 profile -> 0.0.2 card + characters.
    if "card" not in upgraded and "profile" in upgraded:
        profile = upgraded.get("profile", {})
        opening = upgraded.get("opening", {})
        character = default_character_entry()
        character["name"] = profile.get("name", "")
        character["triggerMode"] = "keyword"
        character["triggerKeywords"] = [profile.get("name", "").strip()] if profile.get("name", "").strip() else []
        character["age"] = profile.get("age", "")
        character["appearance"] = profile.get("appearance", "")
        character["personality"] = profile.get("personality", "")
        character["speakingStyle"] = profile.get("speakingStyle", "")
        character["speakingExample"] = opening.get("exampleDialogue", "")
        character["background"] = profile.get("background", "")

        upgraded["card"] = {
            "name": profile.get("name", ""),
            "description": "",
        }
        upgraded["characters"] = [character]

    # 0.0.1 worldBook string -> 0.0.2 entries.
    raw_world_book = upgraded.get("worldBook")
    if isinstance(raw_world_book, str):
        text = raw_world_book.strip()
        if text:
            entry = default_world_book_entry()
            entry["triggerMode"] = "always"
            entry["title"] = "世界书摘要"
            entry["content"] = text
            upgraded["worldBook"] = {"entries": [entry]}
        else:
            upgraded["worldBook"] = {"entries": []}

    raw_openings = upgraded.get("openings", [])
    if not isinstance(raw_openings, list):
        raw_openings = []
    if not raw_openings and isinstance(upgraded.get("opening"), dict):
        raw_openings = [upgraded["opening"]]
    if raw_openings:
        upgraded["openings"] = raw_openings

    normalized = merge_defaults(default_draft(), upgraded)
    normalized["version"] = max(2, int(normalized.get("version", 2)))

    # Support both legacy `opening` and new `openings`.
    incoming_openings = normalized.get("openings", [])
    if not isinstance(incoming_openings, list):
        incoming_openings = []
    if not incoming_openings:
        legacy_opening = normalized.get("opening", {})
        if isinstance(legacy_opening, dict):
            incoming_openings = [legacy_opening]

    normalized_openings: list[dict[str, Any]] = []
    for idx, opening in enumerate(incoming_openings, start=1):
        if not isinstance(opening, dict):
            continue
        merged = merge_defaults(default_opening_entry(), opening)
        if not str(merged.get("title", "")).strip():
            merged["title"] = f"首屏 {idx}"
        normalized_openings.append(merged)
    if not normalized_openings:
        normalized_openings = [default_opening_entry()]

    normalized["openings"] = normalized_openings
    normalized["opening"] = merge_defaults(default_opening_entry(), normalized_openings[0])

    # Per-entry normalization.
    normalized_characters: list[dict[str, Any]] = []
    for item in normalized.get("characters", []):
        merged = merge_defaults(default_character_entry(), item)
        merged["triggerKeywords"] = [
            keyword.strip()
            for keyword in (
                merged.get("triggerKeywords")
                if isinstance(merged.get("triggerKeywords"), list)
                else _split_keywords(str(merged.get("triggerKeywords", "")))
            )
            if keyword and keyword.strip()
        ]
        merged["isUserRole"] = bool(merged.get("isUserRole", False))
        normalized_characters.append(merged)
    user_role_found = False
    for character in normalized_characters:
        if not character.get("isUserRole", False):
            continue
        if not user_role_found:
            user_role_found = True
            continue
        character["isUserRole"] = False
    normalized["characters"] = normalized_characters or [default_character_entry()]

    normalized_world_entries: list[dict[str, Any]] = []
    extracted_plot_entry: dict[str, Any] | None = None
    world_book = normalized.get("worldBook", {})
    for entry in world_book.get("entries", []):
        merged = merge_defaults(default_world_book_entry(), entry)
        merged["keywords"] = [
            keyword.strip()
            for keyword in (
                merged.get("keywords")
                if isinstance(merged.get("keywords"), list)
                else _split_keywords(str(merged.get("keywords", "")))
            )
            if keyword and keyword.strip()
        ]
        if str(merged.get("title", "")).strip() == "剧情推进":
            if extracted_plot_entry is None:
                extracted_plot_entry = merged
            continue
        normalized_world_entries.append(merged)
    normalized["worldBook"] = {"entries": normalized_world_entries}

    incoming_timeline = normalized.get("timeline", {})
    timeline = merge_defaults(default_timeline(), incoming_timeline if isinstance(incoming_timeline, dict) else {})

    if extracted_plot_entry is not None:
        if not str(timeline.get("title", "")).strip():
            timeline["title"] = str(extracted_plot_entry.get("title", "")).strip() or "剧情推进"
        if not timeline.get("keywords"):
            timeline["keywords"] = extracted_plot_entry.get("keywords", [])
        timeline["enabled"] = bool(timeline.get("enabled", extracted_plot_entry.get("enabled", False)))
        if not timeline.get("nodes"):
            timeline["nodes"] = _extract_timeline_nodes_from_world_entry_content(str(extracted_plot_entry.get("content", "")))

    timeline["title"] = str(timeline.get("title", "")).strip() or "剧情推进"
    timeline["triggerMode"] = "always"
    timeline["enabled"] = bool(timeline.get("enabled", False))
    timeline["timeBaseline"] = str(timeline.get("timeBaseline", "")).strip() or "T0=当前主线时刻"
    timeline["timeFormat"] = str(timeline.get("timeFormat", "")).strip() or "T±<offset> | 时间描述"
    timeline["keywords"] = [
        keyword.strip()
        for keyword in (
            timeline.get("keywords")
            if isinstance(timeline.get("keywords"), list)
            else _split_keywords(str(timeline.get("keywords", "")))
        )
        if keyword and keyword.strip()
    ]
    if not timeline["keywords"]:
        timeline["keywords"] = ["剧情推进", "主线节点", "剧情走向"]
    timeline["nodes"] = _normalize_timeline_nodes(timeline.get("nodes", []))
    normalized["timeline"] = timeline

    story_state = normalized.get("storyGenerationState")
    if isinstance(story_state, dict):
        merged_state = merge_defaults(default_story_generation_state(), story_state)
        try:
            total_segments = max(0, int(merged_state.get("totalSegments", 0)))
        except (TypeError, ValueError):
            total_segments = 0
        try:
            current_segment = max(0, int(merged_state.get("currentSegmentIndex", 0)))
        except (TypeError, ValueError):
            current_segment = 0
        if total_segments > 0:
            current_segment = min(current_segment, total_segments)
        else:
            current_segment = 0
        segmentation_mode = str(merged_state.get("segmentationMode", "hard_buffer")).strip().lower()
        if segmentation_mode not in {"chapter", "hard_buffer"}:
            segmentation_mode = "hard_buffer"
        normalized["storyGenerationState"] = {
            "totalSegments": total_segments,
            "currentSegmentIndex": current_segment,
            "segmentationMode": segmentation_mode,
        }
    else:
        normalized["storyGenerationState"] = None

    workflow_state = normalized.get("workflowState")
    if isinstance(workflow_state, dict):
        merged_workflow = merge_defaults(default_workflow_state(), workflow_state)
        editor_mode = str(merged_workflow.get("editorMode", "expert")).strip().lower()
        if editor_mode not in {"wizard", "expert"}:
            editor_mode = "expert"
        wizard_step = str(merged_workflow.get("wizardStep", "input")).strip().lower()
        if wizard_step not in {"input", "segments", "review", "export"}:
            wizard_step = "input"
        batch_generation = merged_workflow.get("batchGeneration")
        if isinstance(batch_generation, dict):
            merged_batch = merge_defaults(default_batch_generation_state(), batch_generation)
        else:
            merged_batch = default_batch_generation_state()
        status = str(merged_batch.get("status", "idle")).strip().lower()
        if status not in {"idle", "running", "paused", "completed", "failed"}:
            status = "idle"
        try:
            current_segment = max(0, int(merged_batch.get("currentSegment", 0)))
        except (TypeError, ValueError):
            current_segment = 0
        try:
            total_segments = max(0, int(merged_batch.get("totalSegments", 0)))
        except (TypeError, ValueError):
            total_segments = 0
        if total_segments > 0:
            current_segment = min(current_segment, total_segments)
        failed_index_raw = merged_batch.get("failedSegmentIndex")
        failed_index: int | None
        if failed_index_raw is None or failed_index_raw == "":
            failed_index = None
        else:
            try:
                failed_index = max(0, int(failed_index_raw))
            except (TypeError, ValueError):
                failed_index = None
        normalized["workflowState"] = {
            "editorMode": editor_mode,
            "wizardStep": wizard_step,
            "batchGeneration": {
                "status": status,
                "currentSegment": current_segment,
                "totalSegments": total_segments,
                "failedSegmentIndex": failed_index,
                "errorMessage": str(merged_batch.get("errorMessage", "")),
            },
        }
    else:
        normalized["workflowState"] = default_workflow_state()

    return normalized
