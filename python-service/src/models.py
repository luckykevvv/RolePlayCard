from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_provider_config() -> dict[str, Any]:
    return {
        "provider": "mock",
        "baseUrl": "https://api.openai.com/v1",
        "apiKey": "",
        "model": "",
        "timeoutMs": 45000,
        "temperature": 0.8,
        "enabled": True,
        "extraHeaders": {},
    }


def default_settings() -> dict[str, Any]:
    return {
        "textProvider": default_provider_config(),
        "imageProvider": default_provider_config(),
        "exportDirectory": "",
        "recentDirectory": "",
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


def default_draft() -> dict[str, Any]:
    timestamp = now_iso()
    return {
        "id": str(uuid4()),
        "version": 2,
        "createdAt": timestamp,
        "updatedAt": timestamp,
        "card": {
            "name": "",
            "description": "",
        },
        "characters": [default_character_entry()],
        "opening": {
            "greeting": "",
            "scenario": "",
            "exampleDialogue": "",
            "firstMessage": "",
        },
        "worldBook": {
            "entries": [],
        },
        "illustration": {
            "originalImagePath": "",
            "generatedImagePath": "",
            "exportImagePath": "",
            "promptSnapshot": "",
            "negativePrompt": "",
            "stylePrompt": "",
        },
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

    normalized = merge_defaults(default_draft(), upgraded)
    normalized["version"] = max(2, int(normalized.get("version", 2)))

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
        normalized_characters.append(merged)
    normalized["characters"] = normalized_characters or [default_character_entry()]

    normalized_world_entries: list[dict[str, Any]] = []
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
        normalized_world_entries.append(merged)
    normalized["worldBook"] = {"entries": normalized_world_entries}

    return normalized
