from __future__ import annotations

import re
from typing import Any, Callable


def _normalize_identity(value: Any) -> str:
    text = str(value or "").strip().casefold()
    if not text:
        return ""
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", text)
    return text


def _character_key(item: dict[str, Any]) -> str:
    name = str(item.get("name", "")).strip()
    return _normalize_identity(name)


def _location_key(item: dict[str, Any]) -> str:
    title = str(item.get("title", "")).strip()
    return _normalize_identity(title)


def _timeline_key(item: dict[str, Any]) -> str:
    node_id = str(item.get("id", "")).strip()
    if node_id:
        return f"id:{node_id}"
    title = _normalize_identity(item.get("title", ""))
    time_point = _normalize_identity(item.get("timePoint", ""))
    event = _normalize_identity(item.get("event", ""))
    merged = "|".join(part for part in (title, time_point, event) if part)
    return f"fallback:{merged}"


def _entity_signature(item: dict[str, Any], fields: tuple[str, ...]) -> str:
    return "\n".join(str(item.get(field, "")).strip() for field in fields)


def _to_dict_by_key(items: Any, key_builder: Callable[[dict[str, Any]], str]) -> dict[str, dict[str, Any]]:
    mapped: dict[str, dict[str, Any]] = {}
    if not isinstance(items, list):
        return mapped
    for raw in items:
        if not isinstance(raw, dict):
            continue
        key = key_builder(raw)
        if not key:
            continue
        mapped[key] = raw
    return mapped


def build_segment_change_set(before_draft: dict[str, Any], after_draft: dict[str, Any]) -> dict[str, Any]:
    before_characters = _to_dict_by_key(before_draft.get("characters", []), _character_key)
    after_characters = _to_dict_by_key(after_draft.get("characters", []), _character_key)
    character_added: list[str] = []
    character_updated: list[str] = []
    for key, item in after_characters.items():
        label = str(item.get("name", "")).strip()
        if not label:
            continue
        before = before_characters.get(key)
        if before is None:
            character_added.append(label)
            continue
        before_signature = _entity_signature(
            before,
            ("name", "triggerKeywords", "age", "appearance", "personality", "speakingStyle", "speakingExample", "background"),
        )
        after_signature = _entity_signature(
            item,
            ("name", "triggerKeywords", "age", "appearance", "personality", "speakingStyle", "speakingExample", "background"),
        )
        if before_signature != after_signature:
            character_updated.append(label)

    before_locations = _to_dict_by_key(before_draft.get("worldBook", {}).get("entries", []), _location_key)
    after_locations = _to_dict_by_key(after_draft.get("worldBook", {}).get("entries", []), _location_key)
    location_added: list[str] = []
    location_updated: list[str] = []
    for key, item in after_locations.items():
        label = str(item.get("title", "")).strip()
        if not label:
            continue
        before = before_locations.get(key)
        if before is None:
            location_added.append(label)
            continue
        before_signature = _entity_signature(before, ("title", "keywords", "content"))
        after_signature = _entity_signature(item, ("title", "keywords", "content"))
        if before_signature != after_signature:
            location_updated.append(label)

    before_timeline = _to_dict_by_key(before_draft.get("timeline", {}).get("nodes", []), _timeline_key)
    after_timeline = _to_dict_by_key(after_draft.get("timeline", {}).get("nodes", []), _timeline_key)
    timeline_added: list[str] = []
    timeline_updated: list[str] = []
    for key, item in after_timeline.items():
        label = str(item.get("title", "")).strip() or str(item.get("id", "")).strip() or "未命名节点"
        before = before_timeline.get(key)
        if before is None:
            timeline_added.append(label)
            continue
        before_signature = _entity_signature(
            before,
            ("title", "timePoint", "trigger", "event", "objective", "conflict", "outcome", "nextHook", "parentId"),
        )
        after_signature = _entity_signature(
            item,
            ("title", "timePoint", "trigger", "event", "objective", "conflict", "outcome", "nextHook", "parentId"),
        )
        if before_signature != after_signature:
            timeline_updated.append(label)

    return {
        "characters": {"added": character_added, "updated": character_updated},
        "locations": {"added": location_added, "updated": location_updated},
        "timelineNodes": {"added": timeline_added, "updated": timeline_updated},
    }


def decide_bridge_nodes_with_llm(
    *,
    anchor_node: dict[str, Any] | None,
    candidate_nodes: list[dict[str, Any]],
    provider: Any | None,
    runtime_config: dict[str, Any] | None,
    build_prompt: Callable[..., str],
    parse_json: Callable[[str], dict[str, Any] | None],
) -> set[str]:
    if not anchor_node or not candidate_nodes:
        return set()
    candidate_ids = {str(node.get("id", "")).strip() for node in candidate_nodes if str(node.get("id", "")).strip()}
    if not candidate_ids:
        return set()
    if provider is None or not runtime_config:
        return candidate_ids

    prompt = build_prompt(anchor_node=anchor_node, candidate_nodes=candidate_nodes)
    try:
        generated = provider.generate(runtime_config, prompt)
    except Exception:
        return candidate_ids

    parsed = parse_json(generated)
    if not isinstance(parsed, dict):
        return candidate_ids

    raw_decisions = parsed.get("decisions", [])
    bridged: set[str] = set()
    has_valid_decision = False
    if isinstance(raw_decisions, list):
        for item in raw_decisions:
            if not isinstance(item, dict):
                continue
            node_id = str(item.get("nodeId", "")).strip()
            if not node_id or node_id not in candidate_ids:
                continue
            has_valid_decision = True
            if bool(item.get("bridgeToAnchor", False)):
                bridged.add(node_id)
    if not has_valid_decision:
        return candidate_ids
    return bridged
