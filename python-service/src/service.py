from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from image_tools import embed_tavern_metadata, ensure_png, import_character_card
from models import (
    DEFAULT_CHAPTER_REGEX,
    default_character_entry,
    default_opening_entry,
    default_settings,
    default_timeline,
    default_timeline_node,
    default_world_book_entry,
    merge_defaults,
    normalize_draft,
)
from prompts import (
    build_character_from_story_prompt,
    build_field_prompt,
    build_image_prompt,
    build_plot_progression_prompt,
    build_story_outline_prompt,
    build_story_outline_prompt_segment,
    build_timeline_bridge_decision_prompt,
    build_timeline_organize_prompt,
)
from providers import ProviderRegistry
from segment_merge import build_segment_change_set, decide_bridge_nodes_with_llm
from storage import AppStorage


def ok(data: Any = None, message: str = "OK") -> dict[str, Any]:
    return {"success": True, "error_code": None, "message": message, "data": data}


def fail(message: str, error_code: str = "error") -> dict[str, Any]:
    return {"success": False, "error_code": error_code, "message": message, "data": None}


def _safe_filename(base: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff\- ]+", "", base).strip()
    return cleaned or "character-card"


def _primary_opening(draft: dict[str, Any]) -> dict[str, Any]:
    openings = draft.get("openings", [])
    if isinstance(openings, list):
        for item in openings:
            if isinstance(item, dict):
                return item
    opening = draft.get("opening", {})
    return opening if isinstance(opening, dict) else {}


def _extract_json_object(raw_text: str) -> dict[str, Any] | None:
    text = str(raw_text or "")
    if not text:
        return None
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    stripped = text.strip()
    if stripped.lower().startswith("json"):
        after_tag = stripped[4:].lstrip()
        try:
            parsed = json.loads(after_tag)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        start = 0
        end = len(text) - 1
    else:
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            return parsed

    in_string = False
    escape = False
    depth = 0
    obj_start = -1
    for index, char in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            if depth == 0:
                obj_start = index
            depth += 1
            continue
        if char == "}":
            if depth <= 0:
                continue
            depth -= 1
            if depth == 0 and obj_start != -1:
                candidate = text[obj_start : index + 1]
                try:
                    parsed = json.loads(candidate)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    return parsed
                obj_start = -1
    return None


def _split_keywords(raw: Any) -> list[str]:
    if isinstance(raw, list):
        values = [str(item) for item in raw]
    else:
        values = re.split(r"[,\n，]", str(raw or ""))
    return [item for item in values if item]


CHAPTER_TITLE_PATTERN = re.compile(DEFAULT_CHAPTER_REGEX)

SPLIT_BREAK_CHARS = {"\n", "。", "！", "？", "!", "?", "；", ";"}

TIMELINE_FIELD_LIMITS: dict[str, int] = {
    "title": 24,
    "timePoint": 24,
    "trigger": 48,
    "event": 96,
    "objective": 56,
    "conflict": 56,
    "outcome": 56,
    "nextHook": 48,
}

PAST_DISTANT_HINTS = (
    "很久以前",
    "多年以前",
    "童年",
    "往昔",
    "过往",
    "旧日",
    "当年",
    "曾经",
    "回忆",
)
PRESENT_HINTS = ("现在", "当前", "此刻", "当下", "眼下", "此时", "今夜", "今晨", "今日", "此夜")
TIMELINE_TIME_FORMAT_LABEL = "T±<offset> | 时间描述"
CHINESE_DIGIT_MAP: dict[str, int] = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
CHINESE_UNIT_MAP: dict[str, int] = {"十": 10, "百": 100, "千": 1000}


def _normalize_identity(value: Any) -> str:
    text = str(value or "").strip().casefold()
    if not text:
        return ""
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", text)
    return text


def _merge_keyword_lists(existing_raw: Any, incoming_raw: Any) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for source in (existing_raw, incoming_raw):
        items = source if isinstance(source, list) else _split_keywords(source)
        for item in items:
            text = str(item).strip()
            if not text:
                continue
            key = _normalize_identity(text) or text.casefold()
            if key in seen:
                continue
            seen.add(key)
            merged.append(text)
    return merged


def _name_alias_candidates(raw_name: Any) -> list[str]:
    name = str(raw_name or "").strip()
    if not name:
        return []
    aliases: list[str] = []
    seen: set[str] = set()

    def push(value: str) -> None:
        normalized = _normalize_identity(value)
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        aliases.append(normalized)

    push(name)
    for part in re.split(r"[\s,/|、·()（）\[\]【】<>《》]+", name):
        push(part)
    return aliases


def _is_probably_same_identity(left: str, right: str) -> bool:
    if not left or not right:
        return False
    if left == right:
        return True
    short, long = (left, right) if len(left) <= len(right) else (right, left)
    return len(short) >= 2 and short in long


def _prefer_name(existing_name: str, incoming_name: str) -> str:
    current = str(existing_name or "").strip()
    newer = str(incoming_name or "").strip()
    if not newer:
        return current
    if not current:
        return newer
    if len(newer) > len(current):
        return newer
    return current


def _is_generic_opening_title(title: Any) -> bool:
    text = str(title or "").strip()
    if not text:
        return True
    return re.fullmatch(r"首屏\s*\d+", text) is not None


def _is_blank_opening(opening: dict[str, Any]) -> bool:
    return not any(
        [
            str(opening.get("greeting", "")).strip(),
            str(opening.get("scenario", "")).strip(),
            str(opening.get("exampleDialogue", "")).strip(),
            str(opening.get("firstMessage", "")).strip(),
        ]
    )


def _is_blank_character_entry(character: dict[str, Any]) -> bool:
    trigger_keywords = character.get("triggerKeywords", [])
    has_keywords = bool(_split_keywords(trigger_keywords))
    return not any(
        [
            str(character.get("name", "")).strip(),
            has_keywords,
            str(character.get("age", "")).strip(),
            str(character.get("appearance", "")).strip(),
            str(character.get("personality", "")).strip(),
            str(character.get("speakingStyle", "")).strip(),
            str(character.get("speakingExample", "")).strip(),
            str(character.get("background", "")).strip(),
        ]
    )


def _opening_identity_key(opening: dict[str, Any]) -> str:
    title = str(opening.get("title", "")).strip()
    if title and not _is_generic_opening_title(title):
        return f"title:{_normalize_identity(title)}"
    first_message = str(opening.get("firstMessage", "")).strip()
    if first_message:
        return f"first:{_normalize_identity(first_message[:80])}"
    scenario = str(opening.get("scenario", "")).strip()
    if scenario:
        return f"scene:{_normalize_identity(scenario[:60])}"
    return ""


def _normalize_inline_flag_prefix(pattern: str) -> str:
    # User may mistakenly type `(?:imx)` instead of `(?imx)`.
    text = str(pattern or "")
    body = text[1:] if text.startswith("\ufeff") else text
    stripped = body.lstrip()
    matched = re.match(r"^\(\?:([aiLmsux]+)\)(.*)$", stripped, flags=re.S)
    if matched:
        flags = matched.group(1)
        rest = matched.group(2)
        return f"(?{flags}){rest}"
    return text


def _compact_text(value: Any, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text or len(text) <= limit:
        return text
    if limit <= 1:
        return "…"
    head_limit = limit - 1
    floor = max(8, int(head_limit * 0.6))
    boundary = -1
    for token in ("。", "！", "？", "；", "，", ",", ";", "!", "?"):
        pos = text.rfind(token, floor, head_limit + 1)
        if pos > boundary:
            boundary = pos
    if boundary >= floor:
        head = text[: boundary + 1].strip()
    else:
        head = text[:head_limit].rstrip("，,；;:：、 ")
    return f"{head}…"


def _contains_hint(text: str, hints: tuple[str, ...]) -> bool:
    return any(hint in text for hint in hints)


def _looks_like_distant_past(text: str) -> bool:
    if not text:
        return False
    if _contains_hint(text, PAST_DISTANT_HINTS):
        return True
    if re.search(r"[两二三四五六七八九十百千\d]+年前", text):
        return True
    return False


def _looks_like_present_or_forward(text: str) -> bool:
    if not text:
        return False
    if _contains_hint(text, PRESENT_HINTS):
        return True
    if any(token in text for token in ("次日", "翌日", "第二天", "同日", "随后")):
        return True
    return False


def _strip_timeline_time_prefix(raw: str) -> str:
    text = str(raw or "").strip()
    matched = re.match(r"^T[+-](?:\d+[YMDH]|0D|SEQ\d+)(?:[+-]\d+[YMDH])?\s*\|\s*(.+)$", text, flags=re.I)
    if matched:
        return matched.group(1).strip()
    return text


def _parse_chinese_number(raw: str) -> int | None:
    text = str(raw or "").strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    total = 0
    current = 0
    has_digit = False
    for char in text:
        if char in CHINESE_DIGIT_MAP:
            current = CHINESE_DIGIT_MAP[char]
            has_digit = True
            continue
        if char in CHINESE_UNIT_MAP:
            unit = CHINESE_UNIT_MAP[char]
            if current == 0:
                current = 1
            total += current * unit
            current = 0
            has_digit = True
            continue
        return None
    total += current
    if not has_digit:
        return None
    return total


class RolePlayCardService:
    def __init__(self, app_data_dir: str):
        self.storage = AppStorage(app_data_dir)
        self.providers = ProviderRegistry()
        self.imports_dir = self.storage.base_dir / "imports"
        self.exports_dir = self.storage.base_dir / "exports"
        self.text_prefix_prompts_dir = Path(__file__).resolve().parents[2] / "jailbreak-prompts"
        self.imports_dir.mkdir(parents=True, exist_ok=True)
        self.exports_dir.mkdir(parents=True, exist_ok=True)
        self.text_prefix_prompts_dir.mkdir(parents=True, exist_ok=True)

    def _load_builtin_prefix_prompts(self) -> list[dict[str, str]]:
        entries: list[dict[str, str]] = []
        for path in sorted(self.text_prefix_prompts_dir.glob("*.txt"), key=lambda item: item.name.lower()):
            if not path.is_file():
                continue
            model = path.stem
            if not model:
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                content = path.read_text(encoding="utf-8", errors="ignore")
            entries.append(
                {
                    "model": model,
                    "filename": path.name,
                    "content": content,
                }
            )
        return entries

    def _resolve_text_prefix_prompt(self, config: dict[str, Any]) -> str:
        custom_prompt = str(config.get("prefixPrompt", ""))
        mode = str(config.get("prefixPromptMode", "custom")).lower()
        if mode != "builtin":
            return custom_prompt
        candidate = str(config.get("builtinPrefixPromptModel", "")) or str(config.get("model", ""))
        if not candidate:
            return custom_prompt
        by_model = {item["model"].casefold(): item for item in self._load_builtin_prefix_prompts()}
        matched = by_model.get(candidate.casefold())
        if matched is None:
            return custom_prompt
        builtin_prompt = str(matched.get("content", ""))
        return builtin_prompt or custom_prompt

    def _resolve_text_generation_config(self, config: dict[str, Any], include_prefix_prompt: bool = True) -> dict[str, Any]:
        resolved = dict(config)
        resolved["prefixPrompt"] = self._resolve_text_prefix_prompt(config) if include_prefix_prompt else ""
        return resolved

    def _build_structured_runtime_config(self, config: dict[str, Any]) -> dict[str, Any]:
        resolved = self._resolve_text_generation_config(config, include_prefix_prompt=True)
        try:
            temperature = float(resolved.get("temperature", 0.8))
        except (TypeError, ValueError):
            temperature = 0.8
        if temperature > 0.4:
            resolved["temperature"] = 0.4
        return resolved

    def _generate_json_object_with_retry(
        self,
        provider: Any,
        runtime_config: dict[str, Any],
        prompt: str,
        task_name: str,
        max_attempts: int = 3,
    ) -> tuple[dict[str, Any] | None, str]:
        current_prompt = prompt
        last_raw = ""
        for attempt in range(1, max_attempts + 1):
            generated = provider.generate(runtime_config, current_prompt)
            last_raw = generated
            parsed = _extract_json_object(generated)
            if isinstance(parsed, dict):
                return parsed, generated
            if attempt < max_attempts:
                current_prompt = (
                    f"{prompt}\n\n"
                    "上次输出解析失败。请立即重试并严格遵守：\n"
                    "1) 只输出一个 JSON 对象，不要 markdown，不要额外说明；\n"
                    "2) 适当压缩长度，避免被截断；\n"
                    "3) 若不确定字段，使用空字符串或空数组，但必须保持 JSON 完整闭合。"
                )
        raise RuntimeError(f"{task_name} 返回非 JSON 或 JSON 被截断，重试后仍失败。")

    def _normalize_character_from_seed(self, seed: dict[str, Any]) -> dict[str, Any]:
        character = merge_defaults(default_character_entry(), {})
        character["name"] = str(seed.get("name", "")).strip()
        character["age"] = str(seed.get("age", "")).strip()
        keywords = _split_keywords(seed.get("triggerKeywords", []))
        if not keywords and character["name"]:
            keywords = [character["name"]]
        character["triggerKeywords"] = keywords
        character["background"] = str(seed.get("hints", "")).strip()
        return character

    def _extract_character_seeds(self, outline: dict[str, Any], draft: dict[str, Any]) -> list[dict[str, Any]]:
        raw_character_seeds = outline.get("characters", [])
        character_seeds: list[dict[str, Any]] = []
        if isinstance(raw_character_seeds, list):
            for item in raw_character_seeds:
                if not isinstance(item, dict):
                    continue
                seed_name = str(item.get("name", ""))
                if not seed_name:
                    continue
                character_seeds.append(
                    {
                        "name": seed_name,
                        "age": str(item.get("age", "")),
                        "hints": str(item.get("hints", "")),
                        "triggerKeywords": _split_keywords(item.get("triggerKeywords", [])),
                    }
                )
        if not character_seeds:
            for existing in draft.get("characters", []):
                if isinstance(existing, dict) and str(existing.get("name", "")):
                    character_seeds.append({"name": str(existing.get("name", ""))})
        if not character_seeds:
            character_seeds = [{"name": "主角"}]
        return character_seeds

    def _extract_plot_nodes(self, outline: dict[str, Any]) -> list[dict[str, Any]]:
        raw_progression = outline.get("plotProgression", outline.get("plot_progression"))
        raw_nodes: Any = []
        if isinstance(raw_progression, dict):
            raw_nodes = raw_progression.get("nodes", [])
        elif isinstance(raw_progression, list):
            raw_nodes = raw_progression
        elif isinstance(outline.get("plotNodes"), list):
            raw_nodes = outline.get("plotNodes", [])

        nodes: list[dict[str, Any]] = []
        if not isinstance(raw_nodes, list):
            return nodes
        used_ids: set[str] = set()
        for index, item in enumerate(raw_nodes[:6], start=1):
            if not isinstance(item, dict):
                continue
            base_id = str(item.get("id", item.get("nodeId", item.get("key", "")))).strip()
            if not base_id:
                base_id = f"n{index}"
            node_id = base_id
            suffix = 2
            while node_id in used_ids:
                node_id = f"{base_id}_{suffix}"
                suffix += 1
            used_ids.add(node_id)

            node = {
                "id": node_id,
                "title": _compact_text(str(item.get("title", item.get("name", item.get("stage", "")))), TIMELINE_FIELD_LIMITS["title"]),
                "timePoint": _compact_text(
                    str(item.get("timePoint", item.get("time", item.get("timeline", "")))),
                    TIMELINE_FIELD_LIMITS["timePoint"],
                ),
                "trigger": _compact_text(
                    str(item.get("trigger", item.get("triggerCondition", item.get("condition", "")))),
                    TIMELINE_FIELD_LIMITS["trigger"],
                ),
                "event": _compact_text(
                    str(item.get("event", item.get("keyEvent", item.get("summary", "")))),
                    TIMELINE_FIELD_LIMITS["event"],
                ),
                "objective": _compact_text(str(item.get("objective", item.get("goal", ""))), TIMELINE_FIELD_LIMITS["objective"]),
                "conflict": _compact_text(str(item.get("conflict", item.get("obstacle", ""))), TIMELINE_FIELD_LIMITS["conflict"]),
                "outcome": _compact_text(str(item.get("outcome", item.get("result", ""))), TIMELINE_FIELD_LIMITS["outcome"]),
                "nextHook": _compact_text(
                    str(item.get("nextHook", item.get("next", item.get("nextStep", "")))),
                    TIMELINE_FIELD_LIMITS["nextHook"],
                ),
                "parentId": "",
                "_parentRef": str(
                    item.get("parentId", item.get("parentNodeId", item.get("parentTitle", item.get("parent", ""))))
                ).strip(),
            }
            if not any(
                [
                    node["title"],
                    node["timePoint"],
                    node["trigger"],
                    node["event"],
                    node["objective"],
                    node["conflict"],
                    node["outcome"],
                    node["nextHook"],
                ]
            ):
                continue
            if not node["title"]:
                node["title"] = f"节点 {len(nodes) + 1}"
            nodes.append(node)

        id_map = {str(node["id"]): str(node["id"]) for node in nodes}
        title_map = {str(node["title"]): str(node["id"]) for node in nodes if str(node.get("title", ""))}
        for node in nodes:
            parent_ref = str(node.pop("_parentRef", "")).strip()
            if not parent_ref:
                node["parentId"] = ""
                continue
            resolved_parent = ""
            if parent_ref in id_map:
                resolved_parent = id_map[parent_ref]
            elif parent_ref in title_map:
                resolved_parent = title_map[parent_ref]
            if resolved_parent == str(node["id"]):
                resolved_parent = ""
            node["parentId"] = resolved_parent
        return nodes

    def _timeline_time_key(self, node: dict[str, Any], fallback_index: int) -> str:
        raw_time = _normalize_identity(node.get("timePoint", ""))
        return raw_time or f"__index_{fallback_index}"

    def _is_hard_time_break(self, prev_node: dict[str, Any], current_node: dict[str, Any]) -> bool:
        prev_time = str(prev_node.get("timePoint", "")).strip()
        current_time = str(current_node.get("timePoint", "")).strip()
        if not prev_time or not current_time:
            return False
        prev_compact = _normalize_identity(prev_time)
        curr_compact = _normalize_identity(current_time)
        if prev_compact == curr_compact:
            return False

        # Typical flashback -> present cut, e.g. "三年前" followed by "当前/今夜".
        if (
            _looks_like_distant_past(prev_time)
            and not _looks_like_distant_past(current_time)
            and _looks_like_present_or_forward(current_time)
        ):
            return True
        if (
            _looks_like_present_or_forward(prev_time)
            and not _looks_like_distant_past(prev_time)
            and _looks_like_distant_past(current_time)
        ):
            return True
        if ("回忆" in prev_time or "往事" in prev_time) and ("回忆" not in current_time and "往事" not in current_time):
            return True
        return False

    def _enforce_progression_parenting(self, nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not nodes:
            return []

        normalized_nodes: list[dict[str, Any]] = []
        for index, item in enumerate(nodes, start=1):
            node = dict(item)
            node_id = str(node.get("id", "")).strip() or f"n{index}"
            node["id"] = node_id
            for field, limit in TIMELINE_FIELD_LIMITS.items():
                node[field] = _compact_text(node.get(field, ""), limit)
            if not str(node.get("title", "")).strip():
                node["title"] = f"节点 {index}"
            parent_id = str(node.get("parentId", "")).strip()
            node["parentId"] = parent_id
            normalized_nodes.append(node)

        id_to_index = {str(node["id"]): idx for idx, node in enumerate(normalized_nodes)}
        for idx, node in enumerate(normalized_nodes):
            parent_id = str(node.get("parentId", "")).strip()
            if not parent_id:
                node["parentId"] = ""
                continue
            parent_idx = id_to_index.get(parent_id, -1)
            # parent must exist and appear earlier to keep DAG and rendering stability.
            if parent_idx < 0 or parent_idx >= idx or parent_id == str(node["id"]):
                node["parentId"] = ""

        first_id = str(normalized_nodes[0]["id"])
        normalized_nodes[0]["parentId"] = ""
        mainline_parent_id = first_id
        current_group_key = self._timeline_time_key(normalized_nodes[0], 0)
        current_group_parent_id = first_id
        first_time = str(normalized_nodes[0].get("timePoint", "")).strip()
        story_starts_in_distant_past = _looks_like_distant_past(first_time)
        seen_present_phase = _looks_like_present_or_forward(first_time) and not _looks_like_distant_past(first_time)

        for idx in range(1, len(normalized_nodes)):
            node = normalized_nodes[idx]
            prev = normalized_nodes[idx - 1]
            node_id = str(node["id"])
            explicit_parent = str(node.get("parentId", "")).strip()
            node_time = str(node.get("timePoint", "")).strip()
            time_key = self._timeline_time_key(node, idx)
            same_group = time_key == current_group_key
            hard_break = self._is_hard_time_break(prev, node)
            if (
                story_starts_in_distant_past
                and not seen_present_phase
                and _looks_like_present_or_forward(node_time)
                and not _looks_like_distant_past(node_time)
            ):
                hard_break = True

            if not same_group:
                current_group_key = time_key
                current_group_parent_id = mainline_parent_id

            if explicit_parent:
                if hard_break and explicit_parent == str(prev.get("id", "")):
                    node["parentId"] = ""
                    mainline_parent_id = node_id
                    current_group_parent_id = ""
                    continue
                node["parentId"] = explicit_parent
                if not same_group:
                    mainline_parent_id = node_id
                continue

            if hard_break:
                node["parentId"] = ""
                mainline_parent_id = node_id
                current_group_parent_id = ""
                if _looks_like_present_or_forward(node_time) and not _looks_like_distant_past(node_time):
                    seen_present_phase = True
                continue

            if same_group:
                parent_id = current_group_parent_id
                node["parentId"] = "" if not parent_id or parent_id == node_id else parent_id
                if _looks_like_present_or_forward(node_time) and not _looks_like_distant_past(node_time):
                    seen_present_phase = True
                continue

            parent_id = current_group_parent_id
            node["parentId"] = "" if not parent_id or parent_id == node_id else parent_id
            mainline_parent_id = node_id
            if _looks_like_present_or_forward(node_time) and not _looks_like_distant_past(node_time):
                seen_present_phase = True

        return normalized_nodes

    def _infer_time_offset_days(self, raw_time: str) -> int | None:
        text = _strip_timeline_time_prefix(raw_time)
        if not text:
            return None
        compact = re.sub(r"\s+", "", text)

        if re.match(r"^T[+-]", compact, flags=re.I):
            return None
        if _looks_like_present_or_forward(compact) and not _looks_like_distant_past(compact):
            return 0
        if "当晚" in compact or "同夜" in compact or "当日" in compact:
            return 0
        if any(token in compact for token in ("次日", "翌日", "第二天")):
            return 1

        composite = re.search(
            r"([零〇一二两三四五六七八九十百千\d]+)年前.*?([零〇一二两三四五六七八九十百千\d]+)个?月",
            compact,
        )
        if composite:
            year_count = _parse_chinese_number(composite.group(1)) or 0
            month_count = _parse_chinese_number(composite.group(2)) or 0
            return -(year_count * 365) + (month_count * 30)

        year_match = re.search(r"([零〇一二两三四五六七八九十百千\d]+)年前", compact)
        if year_match:
            count = _parse_chinese_number(year_match.group(1))
            if count is not None:
                return -(count * 365)

        month_match = re.search(r"([零〇一二两三四五六七八九十百千\d]+)个?月([前后])", compact)
        if month_match:
            count = _parse_chinese_number(month_match.group(1))
            if count is not None:
                sign = -1 if month_match.group(2) == "前" else 1
                return sign * count * 30

        month_ago_match = re.search(r"([零〇一二两三四五六七八九十百千\d]+)个?月前", compact)
        if month_ago_match:
            count = _parse_chinese_number(month_ago_match.group(1))
            if count is not None:
                return -(count * 30)

        month_later_match = re.search(r"([零〇一二两三四五六七八九十百千\d]+)个?月后", compact)
        if month_later_match:
            count = _parse_chinese_number(month_later_match.group(1))
            if count is not None:
                return count * 30

        day_match = re.search(r"([零〇一二两三四五六七八九十百千\d]+)天([前后])", compact)
        if day_match:
            count = _parse_chinese_number(day_match.group(1))
            if count is not None:
                sign = -1 if day_match.group(2) == "前" else 1
                return sign * count

        day_ago_match = re.search(r"([零〇一二两三四五六七八九十百千\d]+)天前", compact)
        if day_ago_match:
            count = _parse_chinese_number(day_ago_match.group(1))
            if count is not None:
                return -count

        day_later_match = re.search(r"([零〇一二两三四五六七八九十百千\d]+)天后", compact)
        if day_later_match:
            count = _parse_chinese_number(day_later_match.group(1))
            if count is not None:
                return count
        return None

    def _format_relative_offset(self, offset_days: int) -> str:
        if offset_days == 0:
            return "T+0D"
        sign = "+" if offset_days > 0 else "-"
        value = abs(int(offset_days))
        if value % 365 == 0:
            return f"T{sign}{value // 365}Y"
        if value % 30 == 0:
            return f"T{sign}{value // 30}M"
        return f"T{sign}{value}D"

    def _normalize_timeline_time_axis(self, timeline: dict[str, Any]) -> dict[str, Any]:
        normalized_timeline = merge_defaults(default_timeline(), timeline if isinstance(timeline, dict) else {})
        nodes = normalized_timeline.get("nodes", [])
        if not isinstance(nodes, list):
            nodes = []
        if not nodes:
            normalized_timeline["timeBaseline"] = "T0=当前主线时刻"
            normalized_timeline["timeFormat"] = TIMELINE_TIME_FORMAT_LABEL
            normalized_timeline["nodes"] = []
            return normalized_timeline

        baseline_index = 0
        for idx, item in enumerate(nodes):
            if not isinstance(item, dict):
                continue
            label = _strip_timeline_time_prefix(str(item.get("timePoint", "")))
            if _looks_like_present_or_forward(label) and not _looks_like_distant_past(label):
                baseline_index = idx
                break

        guessed_offsets: list[int | None] = []
        for item in nodes:
            if not isinstance(item, dict):
                guessed_offsets.append(None)
                continue
            guessed_offsets.append(self._infer_time_offset_days(str(item.get("timePoint", ""))))

        baseline_abs = guessed_offsets[baseline_index] if guessed_offsets[baseline_index] is not None else 0
        inferred_offsets: list[int] = []
        for idx, guessed in enumerate(guessed_offsets):
            if guessed is not None:
                inferred_offsets.append(int(guessed))
                continue
            inferred_offsets.append(baseline_abs + (idx - baseline_index))

        baseline_node = nodes[baseline_index] if baseline_index < len(nodes) and isinstance(nodes[baseline_index], dict) else {}
        baseline_label = _strip_timeline_time_prefix(
            str(
                baseline_node.get("timePoint")
                or baseline_node.get("title")
                or "当前主线时刻"
            )
        )
        if not baseline_label:
            baseline_label = "当前主线时刻"
        normalized_timeline["timeBaseline"] = f"T0={baseline_label}"
        normalized_timeline["timeFormat"] = TIMELINE_TIME_FORMAT_LABEL

        normalized_nodes: list[dict[str, Any]] = []
        for idx, item in enumerate(nodes):
            if not isinstance(item, dict):
                continue
            node = merge_defaults(default_timeline_node(), item)
            original_label = _strip_timeline_time_prefix(str(node.get("timePoint", ""))) or f"阶段 {idx + 1}"
            relative = inferred_offsets[idx] - baseline_abs
            node["timePoint"] = f"{self._format_relative_offset(relative)} | {original_label}"
            normalized_nodes.append(node)
        normalized_timeline["nodes"] = normalized_nodes
        return normalized_timeline

    def _fallback_plot_nodes(
        self,
        story_summary: str,
        openings: list[dict[str, Any]],
        locations: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        first_opening = openings[0] if openings else {}
        first_location = locations[0] if locations else {}
        second_location = locations[1] if len(locations) > 1 else first_location
        summary = story_summary or "围绕关键人物与核心地点展开的剧情。"
        return [
            {
                "title": "起点建立",
                "timePoint": "故事开端",
                "trigger": "玩家进入故事场景并与关键角色接触",
                "event": summary[:140],
                "objective": "明确主线目标与主要人物关系",
                "conflict": "信息不足或彼此不信任",
                "outcome": "获得第一批线索",
                "nextHook": str(first_opening.get("title", "")) or str(first_location.get("title", "")),
                "parentId": "",
            },
            {
                "title": "中段推进",
                "timePoint": "调查/行动中段",
                "trigger": "第一批线索被验证或遭遇阻碍",
                "event": f"围绕地点 {str(first_location.get('title', '关键地点 A'))} 深挖隐藏信息。",
                "objective": "锁定关键矛盾与对立面",
                "conflict": "误导信息、资源受限或外部压力",
                "outcome": "主线从探索转入对抗",
                "nextHook": str(second_location.get("title", "")) or "更深层真相节点",
                "parentId": "",
            },
            {
                "title": "终局走向",
                "timePoint": "后段/收束阶段",
                "trigger": "关键证据或关键人物态度发生变化",
                "event": "主角方对核心冲突发起决断行动。",
                "objective": "解决核心冲突并形成阶段性结论",
                "conflict": "最终抉择代价与立场冲突",
                "outcome": "形成可持续展开的后续剧情方向",
                "nextHook": "引出后续支线或下一阶段主线",
                "parentId": "",
            },
        ]

    def _opening_has_content(self, opening: dict[str, Any]) -> bool:
        return any(
            [
                str(opening.get("greeting", "")).strip(),
                str(opening.get("scenario", "")).strip(),
                str(opening.get("exampleDialogue", "")).strip(),
                str(opening.get("firstMessage", "")).strip(),
            ]
        )

    def _build_fallback_openings(
        self,
        timeline: dict[str, Any],
        story_summary: str,
        story_text: str,
    ) -> list[dict[str, Any]]:
        opening = merge_defaults(default_opening_entry(), {})
        nodes = timeline.get("nodes", []) if isinstance(timeline, dict) else []
        first_node = nodes[0] if isinstance(nodes, list) and nodes and isinstance(nodes[0], dict) else {}

        title = str(first_node.get("title", "")).strip()
        opening["title"] = title or "首屏 1"

        time_point = str(first_node.get("timePoint", "")).strip()
        trigger = str(first_node.get("trigger", "")).strip()
        event = str(first_node.get("event", "")).strip()
        next_hook = str(first_node.get("nextHook", "")).strip()
        summary = str(story_summary or "").strip()
        source_text = re.sub(r"\s+", " ", str(story_text or "")).strip()

        if time_point:
            opening["greeting"] = f"{time_point}，你来了。"
        else:
            opening["greeting"] = "你来了，我们可以开始。"

        scenario_parts = []
        if time_point:
            scenario_parts.append(f"时间：{time_point}")
        if event:
            scenario_parts.append(f"事件：{event}")
        if trigger:
            scenario_parts.append(f"触发：{trigger}")
        if summary:
            scenario_parts.append(f"背景：{summary[:120]}")
        if not scenario_parts and source_text:
            scenario_parts.append(f"背景：{source_text[:120]}")
        opening["scenario"] = "；".join(scenario_parts)

        example_target = next_hook or first_node.get("objective") or "先确认现场线索，再决定下一步。"
        opening["exampleDialogue"] = f"{{{{user}}}}: 现在该做什么？\n角色: {str(example_target).strip()}"

        first_message_parts = [part for part in [trigger, event, summary[:120], source_text[:120]] if part]
        if first_message_parts:
            opening["firstMessage"] = "。".join(first_message_parts[:2]) + "。"
        else:
            opening["firstMessage"] = "你来到事件现场，气氛紧绷，一切正等待你的下一步行动。"

        return [opening]

    def _build_plot_progression_content(self, timeline: dict[str, Any]) -> str:
        nodes = timeline.get("nodes", []) if isinstance(timeline, dict) else []
        baseline = str(timeline.get("timeBaseline", "")).strip() if isinstance(timeline, dict) else ""
        time_format = str(timeline.get("timeFormat", "")).strip() if isinstance(timeline, dict) else ""
        payload = {
            "guidanceType": "plot_progression",
            "version": "1.0",
            "usage": "按 nodes 顺序推进主线；可根据玩家行为在当前节点内进行分支调整。",
            "timeBaseline": baseline or "T0=当前主线时刻",
            "timeFormat": time_format or TIMELINE_TIME_FORMAT_LABEL,
            "nodes": nodes,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def _build_plot_progression_timeline(
        self,
        progression_payload: dict[str, Any] | None,
        outline: dict[str, Any],
        story_summary: str,
        openings: list[dict[str, Any]],
        locations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        nodes: list[dict[str, Any]] = []
        if isinstance(progression_payload, dict):
            nodes = self._extract_plot_nodes(progression_payload)
        if not nodes:
            nodes = self._extract_plot_nodes(outline)
        if not nodes:
            nodes = self._fallback_plot_nodes(story_summary, openings, locations)
        timeline = merge_defaults(default_timeline(), {})
        timeline["nodes"] = self._enforce_progression_parenting(nodes)
        return self._normalize_timeline_time_axis(timeline)

    def _build_plot_progression_world_entry(self, timeline: dict[str, Any]) -> dict[str, Any]:
        normalized_timeline = merge_defaults(default_timeline(), timeline if isinstance(timeline, dict) else {})
        nodes = normalized_timeline.get("nodes", [])
        if not isinstance(nodes, list):
            nodes = []
        content = self._build_plot_progression_content(normalized_timeline)
        entry = merge_defaults(default_world_book_entry(), {})
        entry["enabled"] = bool(normalized_timeline.get("enabled", False))
        entry["triggerMode"] = "always"
        entry["title"] = str(normalized_timeline.get("title", "剧情推进")) or "剧情推进"
        keywords = normalized_timeline.get("keywords", [])
        if isinstance(keywords, list):
            entry["keywords"] = [str(item) for item in keywords if str(item)]
        else:
            entry["keywords"] = ["剧情推进", "主线节点", "剧情走向"]
        if not entry["keywords"]:
            entry["keywords"] = ["剧情推进", "主线节点", "剧情走向"]
        entry["content"] = content
        return entry

    def _build_export_draft_with_timeline_entry(self, draft: dict[str, Any]) -> dict[str, Any]:
        export_draft = json.loads(json.dumps(draft, ensure_ascii=False))
        world_book = export_draft.get("worldBook", {})
        existing_entries = world_book.get("entries", []) if isinstance(world_book, dict) else []
        filtered_entries: list[dict[str, Any]] = []
        if isinstance(existing_entries, list):
            filtered_entries = [
                entry
                for entry in existing_entries
                if isinstance(entry, dict) and str(entry.get("title", "")).strip() != "剧情推进"
            ]

        timeline_entry = self._build_plot_progression_world_entry(export_draft.get("timeline", {}))
        filtered_entries.append(timeline_entry)
        export_draft.setdefault("worldBook", {})
        export_draft["worldBook"]["entries"] = filtered_entries
        return export_draft

    def _coerce_positive_int(self, raw: Any, default: int, minimum: int = 1, maximum: int = 200000) -> int:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return default
        if value < minimum:
            return minimum
        if value > maximum:
            return maximum
        return value

    def _resolve_chapter_pattern(self, chapter_regex: str | None) -> tuple[re.Pattern[str], str]:
        candidate = str(chapter_regex or "").strip()
        if not candidate:
            candidate = DEFAULT_CHAPTER_REGEX
        candidate = _normalize_inline_flag_prefix(candidate)
        try:
            pattern = re.compile(candidate)
        except re.error as exc:
            raise ValueError(f"chapterRegex 无效: {exc}") from exc
        return pattern, candidate

    def _build_segment_preview_text(self, text: str, limit: int = 120) -> str:
        compact = re.sub(r"\s+", " ", str(text or "")).strip()
        return compact[:limit]

    def _hard_split_ranges(
        self,
        text: str,
        max_chars: int,
        start_offset: int = 0,
        title: str = "",
    ) -> list[dict[str, Any]]:
        if not text:
            return []
        segments: list[dict[str, Any]] = []
        cursor = 0
        text_length = len(text)
        while cursor < text_length:
            boundary = min(cursor + max_chars, text_length)
            if boundary < text_length:
                search_min = max(cursor + int(max_chars * 0.6), cursor + 1)
                for index in range(boundary, search_min - 1, -1):
                    char_before = text[index - 1]
                    if char_before in SPLIT_BREAK_CHARS:
                        boundary = index
                        break
            if boundary <= cursor:
                boundary = min(cursor + max_chars, text_length)
            segments.append(
                {
                    "title": title,
                    "start": start_offset + cursor,
                    "end": start_offset + boundary,
                }
            )
            cursor = boundary
        return segments

    def _segment_story_by_chapter(self, story_text: str, chapter_pattern: re.Pattern[str]) -> list[dict[str, Any]]:
        chapter_headers = list(chapter_pattern.finditer(story_text))
        if not chapter_headers:
            return []
        segments: list[dict[str, Any]] = []
        first_header_start = chapter_headers[0].start()
        if first_header_start > 0:
            leading_text = story_text[:first_header_start]
            if leading_text.strip():
                segments.append(
                    {
                        "title": "前置内容",
                        "start": 0,
                        "end": first_header_start,
                    }
                )
        for index, header in enumerate(chapter_headers):
            start = header.start()
            end = chapter_headers[index + 1].start() if index + 1 < len(chapter_headers) else len(story_text)
            chapter_text = story_text[start:end]
            if not chapter_text.strip():
                continue
            raw_title = header.group(1) if header.lastindex and header.lastindex >= 1 else header.group(0)
            title = str(raw_title or "").strip() or f"章节 {index + 1}"
            segments.append({"title": title, "start": start, "end": end})
        return segments

    def _segment_story_text(
        self,
        story_text: str,
        max_chars_per_segment: int,
        chapter_pattern: re.Pattern[str] = CHAPTER_TITLE_PATTERN,
    ) -> tuple[str, list[dict[str, Any]]]:
        chapter_segments = self._segment_story_by_chapter(story_text, chapter_pattern)
        segmentation_mode = "chapter" if chapter_segments else "hard_buffer"
        base_segments = chapter_segments if chapter_segments else [{"title": "分段", "start": 0, "end": len(story_text)}]
        segments: list[dict[str, Any]] = []
        for segment in base_segments:
            start = int(segment["start"])
            end = int(segment["end"])
            title = str(segment.get("title", "")).strip()
            text = story_text[start:end]
            split_parts = self._hard_split_ranges(text, max_chars_per_segment, start_offset=start, title=title)
            if len(split_parts) <= 1:
                segments.extend(split_parts)
                continue
            part_total = len(split_parts)
            for idx, part in enumerate(split_parts, start=1):
                part_title = title or "分段"
                part["title"] = f"{part_title}（{idx}/{part_total}）"
                segments.append(part)
        segment_infos: list[dict[str, Any]] = []
        for index, segment in enumerate(segments):
            seg_start = int(segment.get("start", 0))
            seg_end = int(segment.get("end", seg_start))
            if seg_end <= seg_start:
                continue
            segment_text = story_text[seg_start:seg_end]
            title = str(segment.get("title", "")).strip() or f"分段 {index + 1}"
            segment_infos.append(
                {
                    "segmentIndex": index,
                    "title": title,
                    "start": seg_start,
                    "end": seg_end,
                    "charCount": seg_end - seg_start,
                    "preview": self._build_segment_preview_text(segment_text),
                }
            )
        return segmentation_mode, segment_infos

    def _new_segment_report(self) -> dict[str, int]:
        return {
            "newCharactersCount": 0,
            "newLocationsCount": 0,
            "newTimelineNodesCount": 0,
            "ignoredConflictCount": 0,
        }

    def _merge_card_meta_incremental(
        self,
        base_draft: dict[str, Any],
        incoming_draft: dict[str, Any],
        report: dict[str, int],
    ) -> None:
        base_card = base_draft.get("card", {})
        incoming_card = incoming_draft.get("card", {})
        if not isinstance(base_card, dict) or not isinstance(incoming_card, dict):
            return
        for field in ("name", "description"):
            current = str(base_card.get(field, "")).strip()
            new_value = str(incoming_card.get(field, "")).strip()
            if not new_value:
                continue
            if field == "name":
                base_card[field] = _prefer_name(current, new_value)
                continue
            if current != new_value:
                base_card[field] = new_value

    def _merge_characters_incremental(
        self,
        base_draft: dict[str, Any],
        incoming_draft: dict[str, Any],
        report: dict[str, int],
    ) -> None:
        base_characters = base_draft.get("characters", [])
        incoming_characters = incoming_draft.get("characters", [])
        if not isinstance(base_characters, list):
            base_characters = []
        if not isinstance(incoming_characters, list):
            incoming_characters = []
        base_draft["characters"] = base_characters

        key_to_character: dict[str, dict[str, Any]] = {}
        for character in base_characters:
            if not isinstance(character, dict):
                continue
            candidates = _name_alias_candidates(character.get("name", ""))
            for key in candidates:
                key_to_character.setdefault(key, character)
            for keyword in _split_keywords(character.get("triggerKeywords", [])):
                for key in _name_alias_candidates(keyword):
                    key_to_character.setdefault(key, character)

        for incoming in incoming_characters:
            if not isinstance(incoming, dict):
                continue
            candidate = merge_defaults(default_character_entry(), incoming)
            name = str(candidate.get("name", "")).strip()
            incoming_candidates = _name_alias_candidates(name)
            for keyword in _split_keywords(candidate.get("triggerKeywords", [])):
                incoming_candidates.extend(_name_alias_candidates(keyword))
            deduped_candidates: list[str] = []
            seen_candidates: set[str] = set()
            for key in incoming_candidates:
                if key in seen_candidates:
                    continue
                seen_candidates.add(key)
                deduped_candidates.append(key)

            existing: dict[str, Any] | None = None
            for key in deduped_candidates:
                mapped = key_to_character.get(key)
                if isinstance(mapped, dict):
                    existing = mapped
                    break
            if existing is None:
                for key, mapped in key_to_character.items():
                    if not isinstance(mapped, dict):
                        continue
                    if any(_is_probably_same_identity(key, candidate_key) for candidate_key in deduped_candidates):
                        existing = mapped
                        break

            if existing is None:
                base_characters.append(candidate)
                for key in deduped_candidates:
                    key_to_character.setdefault(key, candidate)
                report["newCharactersCount"] += 1
                continue

            existing["name"] = _prefer_name(str(existing.get("name", "")), name)
            existing["triggerKeywords"] = _merge_keyword_lists(
                existing.get("triggerKeywords", []),
                candidate.get("triggerKeywords", []),
            )
            for field in ("age", "appearance", "personality", "speakingStyle", "speakingExample", "background"):
                new_value = str(candidate.get(field, "")).strip()
                if new_value:
                    existing[field] = new_value

            refreshed_candidates = _name_alias_candidates(existing.get("name", ""))
            for keyword in _split_keywords(existing.get("triggerKeywords", [])):
                refreshed_candidates.extend(_name_alias_candidates(keyword))
            for key in refreshed_candidates:
                key_to_character[key] = existing

        named_characters = [
            item
            for item in base_characters
            if isinstance(item, dict) and str(item.get("name", "")).strip()
        ]
        if named_characters:
            non_blank = [
                item
                for item in base_characters
                if isinstance(item, dict) and not _is_blank_character_entry(item)
            ]
            blank = [
                item
                for item in base_characters
                if isinstance(item, dict) and _is_blank_character_entry(item)
            ]
            base_draft["characters"] = non_blank + (blank[:1] if blank else [])

    def _merge_world_entries_incremental(
        self,
        base_draft: dict[str, Any],
        incoming_draft: dict[str, Any],
        report: dict[str, int],
    ) -> None:
        world_book = base_draft.get("worldBook", {})
        incoming_world_book = incoming_draft.get("worldBook", {})
        if not isinstance(world_book, dict):
            world_book = {"entries": []}
            base_draft["worldBook"] = world_book
        if not isinstance(incoming_world_book, dict):
            incoming_world_book = {"entries": []}
        entries = world_book.get("entries", [])
        incoming_entries = incoming_world_book.get("entries", [])
        if not isinstance(entries, list):
            entries = []
        if not isinstance(incoming_entries, list):
            incoming_entries = []
        world_book["entries"] = entries

        key_to_entry: dict[str, dict[str, Any]] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            title_key = _normalize_identity(entry.get("title", ""))
            if title_key and title_key not in key_to_entry:
                key_to_entry[title_key] = entry

        for incoming_entry in incoming_entries:
            if not isinstance(incoming_entry, dict):
                continue
            candidate = merge_defaults(default_world_book_entry(), incoming_entry)
            title = str(candidate.get("title", "")).strip()
            title_key = _normalize_identity(title)
            existing = key_to_entry.get(title_key) if title_key else None
            if existing is None:
                entries.append(candidate)
                if title_key:
                    key_to_entry[title_key] = candidate
                report["newLocationsCount"] += 1
                continue

            existing["title"] = _prefer_name(str(existing.get("title", "")), title)
            existing["keywords"] = _merge_keyword_lists(existing.get("keywords", []), candidate.get("keywords", []))
            current_content = str(existing.get("content", "")).strip()
            new_content = str(candidate.get("content", "")).strip()
            if new_content:
                if current_content != new_content:
                    existing["content"] = new_content

    def _merge_openings_incremental(
        self,
        base_draft: dict[str, Any],
        incoming_draft: dict[str, Any],
    ) -> None:
        base_openings = base_draft.get("openings", [])
        incoming_openings = incoming_draft.get("openings", [])
        if not isinstance(base_openings, list):
            base_openings = []
        if not isinstance(incoming_openings, list):
            incoming_openings = []

        normalized_base: list[dict[str, Any]] = []
        for item in base_openings:
            if not isinstance(item, dict):
                continue
            normalized_base.append(merge_defaults(default_opening_entry(), item))

        normalized_incoming: list[dict[str, Any]] = []
        for item in incoming_openings:
            if not isinstance(item, dict):
                continue
            opening = merge_defaults(default_opening_entry(), item)
            if _is_blank_opening(opening):
                continue
            normalized_incoming.append(opening)

        if normalized_incoming and all(_is_blank_opening(item) for item in normalized_base):
            normalized_base = []

        key_to_opening: dict[str, dict[str, Any]] = {}
        for opening in normalized_base:
            key = _opening_identity_key(opening)
            if key and key not in key_to_opening:
                key_to_opening[key] = opening

        for candidate in normalized_incoming:
            key = _opening_identity_key(candidate)
            existing = key_to_opening.get(key) if key else None
            if existing is None:
                normalized_base.append(candidate)
                if key:
                    key_to_opening[key] = candidate
                continue
            for field in ("title", "greeting", "scenario", "exampleDialogue", "firstMessage"):
                new_value = str(candidate.get(field, "")).strip()
                if new_value:
                    existing[field] = new_value
            refreshed_key = _opening_identity_key(existing)
            if refreshed_key:
                key_to_opening[refreshed_key] = existing

        if not normalized_base:
            normalized_base = [default_opening_entry()]

        base_draft["openings"] = normalized_base
        base_draft["opening"] = merge_defaults(default_opening_entry(), normalized_base[0])

    def _timeline_node_identity_key(self, node: dict[str, Any]) -> str:
        title_key = _normalize_identity(node.get("title", ""))
        if title_key:
            return f"title:{title_key}"
        event_key = _normalize_identity(node.get("event", ""))
        time_key = _normalize_identity(node.get("timePoint", ""))
        combo = f"{time_key}|{event_key}".strip("|")
        return f"event:{combo}" if combo else ""

    def _pick_timeline_anchor_id(self, nodes: list[dict[str, Any]]) -> str:
        valid_nodes = [node for node in nodes if isinstance(node, dict)]
        if not valid_nodes:
            return ""
        children: dict[str, int] = {}
        for node in valid_nodes:
            node_id = str(node.get("id", "")).strip()
            if node_id:
                children.setdefault(node_id, 0)
        for node in valid_nodes:
            parent_id = str(node.get("parentId", "")).strip()
            if parent_id and parent_id in children:
                children[parent_id] += 1
        for node in reversed(valid_nodes):
            node_id = str(node.get("id", "")).strip()
            if node_id and children.get(node_id, 0) == 0:
                return node_id
        return str(valid_nodes[-1].get("id", "")).strip()

    def _append_timeline_nodes_incremental(
        self,
        base_draft: dict[str, Any],
        incoming_draft: dict[str, Any],
        segment_index: int,
        report: dict[str, int],
        provider: Any | None = None,
        runtime_config: dict[str, Any] | None = None,
    ) -> None:
        base_timeline = merge_defaults(default_timeline(), base_draft.get("timeline", {}))
        incoming_timeline = merge_defaults(default_timeline(), incoming_draft.get("timeline", {}))
        base_nodes = base_timeline.get("nodes", [])
        incoming_nodes = incoming_timeline.get("nodes", [])
        if not isinstance(base_nodes, list):
            base_nodes = []
        if not isinstance(incoming_nodes, list):
            incoming_nodes = []

        existing_nodes_before_merge = [node for node in base_nodes if isinstance(node, dict)]
        segment_anchor_id = self._pick_timeline_anchor_id(existing_nodes_before_merge)
        segment_anchor_node = next(
            (
                node
                for node in existing_nodes_before_merge
                if str(node.get("id", "")).strip() == segment_anchor_id
            ),
            None,
        )
        existing_ids = {str(item.get("id", "")) for item in base_nodes if isinstance(item, dict)}
        id_map: dict[str, str] = {}
        key_to_node: dict[str, dict[str, Any]] = {}
        touched_nodes: list[tuple[dict[str, Any], str, bool]] = []
        bridge_candidates: list[dict[str, Any]] = []
        for node in base_nodes:
            if not isinstance(node, dict):
                continue
            key = self._timeline_node_identity_key(node)
            if key and key not in key_to_node:
                key_to_node[key] = node

        prefix = f"s{segment_index + 1}_"

        for index, item in enumerate(incoming_nodes, start=1):
            if not isinstance(item, dict):
                continue
            node = merge_defaults(default_timeline_node(), item)
            original_id = str(node.get("id", "")).strip() or f"n{index}"
            source_parent_id = str(node.get("parentId", "")).strip()
            key = self._timeline_node_identity_key(node)
            existing = key_to_node.get(key) if key else None
            if existing is not None:
                for field in ("title", "timePoint", "trigger", "event", "objective", "conflict", "outcome", "nextHook"):
                    new_value = str(node.get(field, "")).strip()
                    if new_value:
                        existing[field] = new_value
                id_map[original_id] = str(existing.get("id", "")).strip()
                touched_nodes.append((existing, source_parent_id, False))
                continue

            new_id_base = f"{prefix}{original_id}"
            new_id = new_id_base
            suffix = 2
            while new_id in existing_ids:
                new_id = f"{new_id_base}_{suffix}"
                suffix += 1
            existing_ids.add(new_id)
            id_map[original_id] = new_id
            node["id"] = new_id
            node["parentId"] = ""
            base_nodes.append(node)
            touched_nodes.append((node, source_parent_id, True))
            if key:
                key_to_node[key] = node
            report["newTimelineNodesCount"] += 1

        for node, parent_ref, is_new in touched_nodes:
            parent_ref = str(parent_ref).strip()
            resolved_parent_id = id_map.get(parent_ref, "")
            if resolved_parent_id and resolved_parent_id != str(node.get("id", "")):
                node["parentId"] = resolved_parent_id
                continue
            if parent_ref:
                if is_new and segment_anchor_id and segment_anchor_id != str(node.get("id", "")):
                    bridge_candidates.append(node)
                continue
            if is_new and segment_anchor_id and segment_anchor_id != str(node.get("id", "")):
                if not str(node.get("parentId", "")).strip():
                    bridge_candidates.append(node)

        decided_bridge_ids = decide_bridge_nodes_with_llm(
            anchor_node=segment_anchor_node,
            candidate_nodes=bridge_candidates,
            provider=provider,
            runtime_config=runtime_config,
            build_prompt=build_timeline_bridge_decision_prompt,
            parse_json=_extract_json_object,
        )
        for node in bridge_candidates:
            node_id = str(node.get("id", "")).strip()
            if not node_id or node_id not in decided_bridge_ids:
                continue
            if segment_anchor_id and segment_anchor_id != node_id:
                node["parentId"] = segment_anchor_id

        base_timeline["nodes"] = self._enforce_progression_parenting(base_nodes)
        timeline_title = str(incoming_timeline.get("title", "")).strip()
        if timeline_title:
            base_timeline["title"] = timeline_title
        incoming_baseline = str(incoming_timeline.get("timeBaseline", "")).strip()
        incoming_format = str(incoming_timeline.get("timeFormat", "")).strip()
        if incoming_baseline:
            base_timeline["timeBaseline"] = incoming_baseline
        if incoming_format:
            base_timeline["timeFormat"] = incoming_format
        base_draft["timeline"] = self._normalize_timeline_time_axis(base_timeline)

    def _merge_segment_generated_draft(
        self,
        base_draft: dict[str, Any],
        incoming_draft: dict[str, Any],
        segment_index: int,
        provider: Any | None = None,
        runtime_config: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, int]]:
        merged = normalize_draft(base_draft)
        incoming = normalize_draft(incoming_draft)
        report = self._new_segment_report()
        self._merge_card_meta_incremental(merged, incoming, report)
        self._merge_characters_incremental(merged, incoming, report)
        self._merge_openings_incremental(merged, incoming)
        self._merge_world_entries_incremental(merged, incoming, report)
        self._append_timeline_nodes_incremental(
            merged,
            incoming,
            segment_index,
            report,
            provider=provider,
            runtime_config=runtime_config,
        )
        merged_card = merged.get("card", {})
        if isinstance(merged_card, dict) and not str(merged_card.get("name", "")).strip():
            for character in merged.get("characters", []):
                if not isinstance(character, dict):
                    continue
                name = str(character.get("name", "")).strip()
                if name:
                    merged_card["name"] = name
                    break
        merged["sourceType"] = "roleplaycard"
        return normalize_draft(merged), report

    def _settings_from_payload(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if payload and isinstance(payload.get("settings"), dict):
            return merge_defaults(default_settings(), payload["settings"])
        return default_settings()

    def get_settings(self) -> dict[str, Any]:
        return ok(default_settings(), "Server-side settings disabled in web mode.")

    def save_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        merged = merge_defaults(default_settings(), settings if isinstance(settings, dict) else {})
        return ok(merged, "Server-side settings disabled in web mode.")

    def list_text_prefix_prompts(self) -> dict[str, Any]:
        entries = self._load_builtin_prefix_prompts()
        items = [{"model": item["model"], "filename": item["filename"]} for item in entries]
        return ok({"directory": str(self.text_prefix_prompts_dir), "items": items})

    def test_settings(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        settings = self._settings_from_payload(payload)
        results = []
        for key, getter in (
            ("textProvider", self.providers.get_text_provider),
            ("imageProvider", self.providers.get_image_provider),
        ):
            config = settings[key]
            try:
                provider = getter(config["provider"])
                valid, detail = provider.validate(config)
            except KeyError:
                valid, detail = False, f"unsupported provider: {config.get('provider')}"
            results.append({"provider": config["provider"], "ok": valid, "detail": detail})
        return ok(results)

    def test_text_provider(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        settings = self._settings_from_payload(payload)
        config = settings["textProvider"]
        try:
            provider = self.providers.get_text_provider(config["provider"])
        except KeyError:
            return fail(f"unsupported provider: {config.get('provider')}", "provider_config_invalid")
        valid, detail = provider.validate(config)
        if not valid:
            return fail(detail, "provider_config_invalid")
        try:
            models = provider.list_models(config)
        except Exception as exc:  # noqa: BLE001
            return fail(str(exc), "provider_model_list_failed")
        return ok({"provider": config["provider"], "detail": detail, "models": models}, "Text provider connected.")

    def test_image_provider(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        settings = self._settings_from_payload(payload)
        config = settings["imageProvider"]
        try:
            provider = self.providers.get_image_provider(config["provider"])
        except KeyError:
            return fail(f"unsupported provider: {config.get('provider')}", "provider_config_invalid")
        valid, detail = provider.validate(config)
        if not valid:
            return fail(detail, "provider_config_invalid")
        try:
            models = provider.list_models(config)
        except Exception as exc:  # noqa: BLE001
            return fail(str(exc), "provider_model_list_failed")
        return ok({"provider": config["provider"], "detail": detail, "models": models}, "Image provider connected.")

    def list_drafts(self, client_id: str = "default") -> dict[str, Any]:
        try:
            return ok(self.storage.list_drafts(client_id))
        except ValueError as exc:
            return fail(str(exc), "validation_error")

    def clear_all_data(self, client_id: str = "default") -> dict[str, Any]:
        try:
            result = self.storage.clear_all_data(client_id)
        except ValueError as exc:
            return fail(str(exc), "validation_error")
        self.imports_dir.mkdir(parents=True, exist_ok=True)
        self.exports_dir.mkdir(parents=True, exist_ok=True)
        return ok(result, "Current user's stored data cleared.")

    def load_draft(self, draft_id: str, client_id: str = "default") -> dict[str, Any]:
        try:
            return ok(self.storage.load_draft(draft_id, client_id))
        except FileNotFoundError as exc:
            return fail(str(exc), "draft_not_found")
        except ValueError as exc:
            return fail(str(exc), "validation_error")

    def save_draft(self, payload: dict[str, Any], client_id: str = "default") -> dict[str, Any]:
        draft = normalize_draft(payload["draft"])
        try:
            saved = self.storage.save_draft(draft, save_as=payload.get("saveAs", False), client_id=client_id)
        except ValueError as exc:
            return fail(str(exc), "validation_error")
        return ok(saved, "Draft saved.")

    def preview_story_segments(self, payload: dict[str, Any]) -> dict[str, Any]:
        story_text = str(payload.get("storyText", ""))
        if not story_text.strip():
            return fail("storyText is required", "validation_error")
        settings = self._settings_from_payload(payload)
        segmentation_settings = settings.get("storySegmentation", {}) if isinstance(settings, dict) else {}
        default_max_chars = self._coerce_positive_int(
            segmentation_settings.get("maxCharsPerSegment"),
            default=20000,
            minimum=500,
        )
        max_chars_per_segment = self._coerce_positive_int(
            payload.get("maxCharsPerSegment"),
            default=default_max_chars,
            minimum=500,
        )
        chapter_regex = str(payload.get("chapterRegex", "")).strip()
        if not chapter_regex:
            chapter_regex = str(segmentation_settings.get("chapterRegex", "")).strip()
        try:
            chapter_pattern, resolved_chapter_regex = self._resolve_chapter_pattern(chapter_regex)
        except ValueError as exc:
            return fail(str(exc), "validation_error")
        segmentation_mode, segments = self._segment_story_text(
            story_text,
            max_chars_per_segment,
            chapter_pattern=chapter_pattern,
        )
        if not segments:
            return fail("无法从 storyText 中切分出有效段落。", "validation_error")
        return ok(
            {
                "segmentationMode": segmentation_mode,
                "maxCharsPerSegment": max_chars_per_segment,
                "chapterRegex": resolved_chapter_regex,
                "segments": segments,
            },
            "Story segments preview generated.",
        )

    def generate_field(self, payload: dict[str, Any]) -> dict[str, Any]:
        settings = self._settings_from_payload(payload)
        config = settings["textProvider"]
        if not str(config.get("model", "")):
            return fail("missing model", "provider_config_invalid")
        try:
            provider = self.providers.get_text_provider(config["provider"])
        except KeyError:
            return fail(f"unsupported provider: {config.get('provider')}", "provider_config_invalid")
        valid, detail = provider.validate(config)
        if not valid:
            return fail(detail, "provider_config_invalid")
        draft = normalize_draft(payload["draft"])
        prompt = build_field_prompt(payload["field"], payload["mode"], payload.get("userInput", ""), draft)
        runtime_config = self._resolve_text_generation_config(config)
        try:
            generated = provider.generate(runtime_config, prompt)
        except Exception as exc:  # noqa: BLE001
            return fail(str(exc), "provider_generation_failed")
        return ok({"field": payload["field"], "result": generated, "promptPreview": prompt}, "Field generated.")

    def organize_timeline(self, payload: dict[str, Any]) -> dict[str, Any]:
        draft = normalize_draft(payload.get("draft", {}))
        timeline = merge_defaults(default_timeline(), draft.get("timeline", {}))
        raw_nodes = timeline.get("nodes", [])
        if not isinstance(raw_nodes, list) or len(raw_nodes) == 0:
            return fail("当前没有可整理的时间线节点。", "validation_error")

        settings = self._settings_from_payload(payload)
        config = dict(settings["textProvider"])
        if not str(config.get("model", "")).strip():
            return fail("missing model", "provider_config_invalid")
        try:
            provider = self.providers.get_text_provider(config["provider"])
        except KeyError:
            return fail(f"unsupported provider: {config.get('provider')}", "provider_config_invalid")
        valid, detail = provider.validate(config)
        if not valid:
            return fail(detail, "provider_config_invalid")
        runtime_config = self._build_structured_runtime_config(config)

        prompt = build_timeline_organize_prompt(timeline=timeline, draft=draft)
        try:
            parsed, _generated = self._generate_json_object_with_retry(
                provider=provider,
                runtime_config=runtime_config,
                prompt=prompt,
                task_name="时间线整理",
                max_attempts=3,
            )
        except Exception as exc:  # noqa: BLE001
            return fail(str(exc), "provider_generation_failed")

        if not isinstance(parsed, dict):
            return fail("模型返回非 JSON，无法解析。", "provider_generation_failed")

        parsed_nodes = parsed.get("nodes")
        if not isinstance(parsed_nodes, list):
            nested = parsed.get("timeline", {})
            if isinstance(nested, dict) and isinstance(nested.get("nodes"), list):
                parsed_nodes = nested.get("nodes")
        if not isinstance(parsed_nodes, list):
            return fail("时间线整理结果缺少 nodes。", "provider_generation_failed")

        extracted_nodes = self._extract_plot_nodes({"plotProgression": {"nodes": parsed_nodes}})
        if not extracted_nodes:
            return fail("时间线整理结果为空，请重试。", "provider_generation_failed")

        proposal_timeline = merge_defaults(default_timeline(), timeline)
        proposal_timeline["nodes"] = self._enforce_progression_parenting(extracted_nodes)
        requested_baseline = str(parsed.get("timeBaseline", "")).strip()
        requested_format = str(parsed.get("timeFormat", "")).strip()
        if requested_baseline:
            proposal_timeline["timeBaseline"] = requested_baseline
        if requested_format:
            proposal_timeline["timeFormat"] = requested_format
        proposal_timeline = self._normalize_timeline_time_axis(proposal_timeline)

        roots = 0
        for item in proposal_timeline.get("nodes", []):
            if isinstance(item, dict) and not str(item.get("parentId", "")).strip():
                roots += 1
        return ok(
            {
                "proposalTimeline": proposal_timeline,
                "summary": {
                    "nodeCountBefore": len(raw_nodes),
                    "nodeCountAfter": len(proposal_timeline.get("nodes", [])),
                    "rootCountAfter": roots,
                    "baseline": str(proposal_timeline.get("timeBaseline", "")),
                    "format": str(proposal_timeline.get("timeFormat", "")),
                },
            },
            "Timeline organize proposal generated.",
        )

    def generate_card_from_story_segment(self, payload: dict[str, Any]) -> dict[str, Any]:
        segment_text = str(payload.get("segmentText", ""))
        if not segment_text.strip():
            return fail("segmentText is required", "validation_error")
        segment_index = self._coerce_positive_int(payload.get("segmentIndex"), default=0, minimum=0, maximum=100000)
        total_segments = self._coerce_positive_int(payload.get("totalSegments"), default=1, minimum=1, maximum=100000)
        base_draft = normalize_draft(payload.get("draft", {}))
        settings = self._settings_from_payload(payload)
        config = dict(settings["textProvider"])
        if not str(config.get("model", "")):
            return fail("missing model", "provider_config_invalid")
        try:
            provider = self.providers.get_text_provider(config["provider"])
        except KeyError:
            return fail(f"unsupported provider: {config.get('provider')}", "provider_config_invalid")
        valid, detail = provider.validate(config)
        if not valid:
            return fail(detail, "provider_config_invalid")
        runtime_config = self._build_structured_runtime_config(config)

        one_shot_result = self.generate_card_from_story(
            {
                "draft": base_draft,
                "storyText": segment_text,
                "settings": settings,
                "segmentMode": True,
            }
        )
        if not one_shot_result.get("success", False):
            return one_shot_result
        data = one_shot_result.get("data", {})
        incoming_draft = normalize_draft(data.get("draft", {}))

        merged_draft, report = self._merge_segment_generated_draft(
            base_draft,
            incoming_draft,
            segment_index,
            provider=provider,
            runtime_config=runtime_config,
        )
        change_set = build_segment_change_set(base_draft, merged_draft)
        existing_state = base_draft.get("storyGenerationState", {})
        existing_current = 0
        existing_mode = "hard_buffer"
        if isinstance(existing_state, dict):
            existing_current = self._coerce_positive_int(existing_state.get("currentSegmentIndex"), default=0, minimum=0)
            mode_candidate = str(existing_state.get("segmentationMode", "hard_buffer")).strip().lower()
            if mode_candidate in {"chapter", "hard_buffer"}:
                existing_mode = mode_candidate
        next_segment_index = max(existing_current, min(segment_index + 1, total_segments))
        merged_draft["storyGenerationState"] = {
            "totalSegments": total_segments,
            "currentSegmentIndex": next_segment_index,
            "segmentationMode": existing_mode,
        }
        return ok(
            {
                "draft": normalize_draft(merged_draft),
                "segmentReport": report,
                "changeSet": change_set,
            },
            "Segment merged into draft.",
        )

    def generate_card_from_story(self, payload: dict[str, Any]) -> dict[str, Any]:
        settings = self._settings_from_payload(payload)
        config = dict(settings["textProvider"])
        if not str(config.get("model", "")):
            return fail("missing model", "provider_config_invalid")
        try:
            provider = self.providers.get_text_provider(config["provider"])
        except KeyError:
            return fail(f"unsupported provider: {config.get('provider')}", "provider_config_invalid")
        valid, detail = provider.validate(config)
        if not valid:
            return fail(detail, "provider_config_invalid")
        segment_mode = bool(payload.get("segmentMode", False))
        runtime_config = (
            self._build_structured_runtime_config(config)
            if segment_mode
            else self._resolve_text_generation_config(config, include_prefix_prompt=True)
        )

        story_text = str(payload.get("storyText", ""))
        if not story_text:
            return fail("storyText is required", "validation_error")

        draft = normalize_draft(payload["draft"])
        outline_prompt = (
            build_story_outline_prompt_segment(story_text, draft)
            if segment_mode
            else build_story_outline_prompt(story_text, draft)
        )
        try:
            outline, generated_outline = self._generate_json_object_with_retry(
                provider,
                runtime_config,
                outline_prompt,
                task_name="故事结构提取",
                max_attempts=3,
            )
        except Exception as exc:  # noqa: BLE001
            return fail(str(exc), "provider_generation_failed")
        if not outline:
            return fail("模型返回非 JSON，无法解析。", "provider_generation_failed")

        story_summary = str(outline.get("storySummary", ""))

        card = outline.get("card", {})
        if isinstance(card, dict):
            draft["card"]["name"] = str(card.get("name", draft["card"]["name"]))
            draft["card"]["description"] = str(card.get("description", draft["card"]["description"]))

        character_seeds = self._extract_character_seeds(outline, draft)

        raw_openings = outline.get("openings", [])
        normalized_openings: list[dict[str, Any]] = []
        if isinstance(raw_openings, list):
            for index, item in enumerate(raw_openings, start=1):
                if not isinstance(item, dict):
                    continue
                opening = merge_defaults(default_opening_entry(), {})
                opening["title"] = str(item.get("title", f"时间点 {index}")) or f"时间点 {index}"
                opening["greeting"] = str(item.get("greeting", ""))
                opening["scenario"] = str(item.get("scenario", ""))
                opening["exampleDialogue"] = str(item.get("exampleDialogue", ""))
                opening["firstMessage"] = str(item.get("firstMessage", ""))
                if any(
                    [
                        opening["greeting"],
                        opening["scenario"],
                        opening["exampleDialogue"],
                        opening["firstMessage"],
                    ]
                ):
                    normalized_openings.append(opening)
        if normalized_openings:
            draft["openings"] = normalized_openings
            draft["opening"] = normalized_openings[0]

        raw_locations = outline.get("locations", [])
        normalized_locations: list[dict[str, Any]] = []
        if isinstance(raw_locations, list):
            for item in raw_locations:
                if not isinstance(item, dict):
                    continue
                entry = merge_defaults(default_world_book_entry(), {})
                entry["triggerMode"] = "keyword"
                entry["title"] = str(item.get("title", ""))
                entry["keywords"] = _split_keywords(item.get("keywords", []))
                entry["content"] = str(item.get("content", ""))
                if entry["title"] and entry["content"]:
                    normalized_locations.append(entry)

        plot_openings = normalized_openings if normalized_openings else (
            draft.get("openings", []) if isinstance(draft.get("openings", []), list) else []
        )
        progression_payload: dict[str, Any] | None = outline if self._extract_plot_nodes(outline) else None
        if progression_payload is None:
            progression_prompt = build_plot_progression_prompt(
                story_text=story_text,
                story_summary=story_summary,
                characters=character_seeds,
                openings=plot_openings,
                locations=normalized_locations,
                draft=draft,
            )
            try:
                generated_progression = provider.generate(runtime_config, progression_prompt)
                parsed_progression = _extract_json_object(generated_progression)
                if isinstance(parsed_progression, dict):
                    progression_payload = parsed_progression
            except Exception:
                progression_payload = None

        plot_timeline = self._build_plot_progression_timeline(
            progression_payload=progression_payload,
            outline=outline,
            story_summary=story_summary,
            openings=plot_openings,
            locations=normalized_locations,
        )
        draft["timeline"] = plot_timeline
        if not normalized_openings:
            normalized_openings = self._build_fallback_openings(
                timeline=plot_timeline,
                story_summary=story_summary,
                story_text=story_text,
            )
            draft["openings"] = normalized_openings
            draft["opening"] = normalized_openings[0]
        combined_entries = [entry for entry in normalized_locations if str(entry.get("title", "")) != "剧情推进"]
        draft["worldBook"]["entries"] = combined_entries

        normalized_characters: list[dict[str, Any]] = []
        character_raw_outputs: list[str] = []
        character_limit = 6 if segment_mode else 12
        for seed in character_seeds[:character_limit]:
            character_prompt = build_character_from_story_prompt(
                target_character=seed,
                previous_characters=normalized_characters,
                story_summary=story_summary,
                story_text=story_text,
                draft=draft,
            )

            generated_character = ""
            parsed_character: dict[str, Any] = {}
            try:
                if segment_mode:
                    parsed_candidate, generated_character = self._generate_json_object_with_retry(
                        provider=provider,
                        runtime_config=runtime_config,
                        prompt=character_prompt,
                        task_name=f"分段角色补全:{str(seed.get('name', '角色'))[:24]}",
                        max_attempts=2,
                    )
                    if isinstance(parsed_candidate, dict):
                        parsed_character = parsed_candidate
                else:
                    generated_character = provider.generate(runtime_config, character_prompt)
                    maybe_parsed = _extract_json_object(generated_character)
                    if isinstance(maybe_parsed, dict):
                        parsed_character = maybe_parsed
            except Exception:
                parsed_character = {}
            character_raw_outputs.append(generated_character)

            if segment_mode and not parsed_character:
                character = self._normalize_character_from_seed(seed)
                if character["name"]:
                    normalized_characters.append(character)
                continue

            character = merge_defaults(default_character_entry(), {})
            character["name"] = str(parsed_character.get("name", seed.get("name", "")))
            character["age"] = str(parsed_character.get("age", seed.get("age", "")))
            keywords = _split_keywords(parsed_character.get("triggerKeywords", []))
            if not keywords:
                keywords = _split_keywords(seed.get("triggerKeywords", []))
            if not keywords and character["name"]:
                keywords = [character["name"]]
            character["triggerKeywords"] = keywords
            character["appearance"] = str(parsed_character.get("appearance", ""))
            character["personality"] = str(parsed_character.get("personality", ""))
            character["speakingStyle"] = str(parsed_character.get("speakingStyle", ""))
            character["speakingExample"] = str(parsed_character.get("speakingExample", ""))
            character["background"] = str(parsed_character.get("background", seed.get("hints", "")))
            if character["name"]:
                normalized_characters.append(character)
        if normalized_characters:
            draft["characters"] = normalized_characters

        if not draft["card"]["name"] and draft["characters"]:
            draft["card"]["name"] = draft["characters"][0]["name"]

        normalized_draft = normalize_draft(draft)
        normalized_draft["sourceType"] = "roleplaycard"
        normalized_draft["storyGenerationState"] = None
        raw_bundle = json.dumps(
            {"outline": generated_outline, "characterCalls": character_raw_outputs},
            ensure_ascii=False,
        )
        return ok({"draft": normalized_draft, "raw": raw_bundle}, "Card generated from story.")

    def generate_image_prompt(self, draft: dict[str, Any]) -> dict[str, Any]:
        normalized = normalize_draft(draft["draft"])
        prompt, negative = build_image_prompt(normalized)
        return ok({"prompt": prompt, "negativePrompt": negative}, "Image prompt generated.")

    def generate_image(self, payload: dict[str, Any]) -> dict[str, Any]:
        settings = self._settings_from_payload(payload)
        config = settings["imageProvider"]
        if not str(config.get("model", "")).strip():
            return fail("missing model", "provider_config_invalid")
        try:
            provider = self.providers.get_image_provider(config["provider"])
        except KeyError:
            return fail(f"unsupported provider: {config.get('provider')}", "provider_config_invalid")
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
        export_draft = self._build_export_draft_with_timeline_entry(draft)
        image_path = str(payload.get("imagePath", "")).strip()
        card_name = export_draft["card"]["name"].strip() or export_draft["characters"][0]["name"].strip()
        primary_opening = _primary_opening(export_draft)
        if not card_name:
            return fail("Card name is required.", "validation_error")
        if not str(primary_opening.get("firstMessage", "")).strip():
            return fail("First message is required.", "validation_error")
        if not image_path:
            return fail("Image path is required.", "validation_error")

        resolved_image = self.resolve_image_path(image_path)
        prepared_path = self.storage.cache_images_dir / f"{export_draft['id']}-export.png"
        ensure_png(str(resolved_image), str(prepared_path))
        output_path = self.exports_dir / f"{uuid4()}.png"
        embed_tavern_metadata(str(prepared_path), export_draft, str(output_path))
        encoded = base64.b64encode(output_path.read_bytes()).decode("utf-8")
        filename = f"{_safe_filename(card_name)}.png"
        return ok({"filename": filename, "imageBase64": encoded}, "Character card exported.")

    def import_character_card_path(self, input_path: str) -> dict[str, Any]:
        try:
            imported = import_character_card(input_path)
        except Exception as exc:  # noqa: BLE001
            return fail(str(exc), "import_failed")
        source_type = str(imported.get("__importSource", "external")) if isinstance(imported, dict) else "external"
        if isinstance(imported, dict) and "__importSource" in imported:
            imported = dict(imported)
            imported.pop("__importSource", None)
        draft = normalize_draft(imported)
        draft["sourceType"] = source_type
        if not draft["card"]["name"].strip() and draft["characters"]:
            draft["card"]["name"] = draft["characters"][0]["name"]
        if Path(input_path).suffix.lower() == ".png":
            draft["illustration"]["originalImagePath"] = input_path
            draft["illustration"]["generatedImagePath"] = ""
            draft["illustration"]["exportImagePath"] = input_path
        if source_type == "external":
            draft["characters"] = [draft["characters"][0]]
        return ok({"draft": draft, "sourcePath": input_path, "sourceType": source_type}, "Character card imported.")

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
