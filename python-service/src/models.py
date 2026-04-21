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


def default_draft() -> dict[str, Any]:
    timestamp = now_iso()
    return {
        "id": str(uuid4()),
        "version": 1,
        "createdAt": timestamp,
        "updatedAt": timestamp,
        "profile": {
            "name": "",
            "age": "",
            "gender": "",
            "appearance": "",
            "personality": "",
            "speakingStyle": "",
            "background": "",
        },
        "opening": {
            "greeting": "",
            "scenario": "",
            "exampleDialogue": "",
            "firstMessage": "",
        },
        "worldBook": "",
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
