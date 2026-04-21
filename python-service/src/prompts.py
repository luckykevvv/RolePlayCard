from __future__ import annotations

import re
from textwrap import dedent


FIELD_GUIDANCE = {
    "card.name": "给角色卡起一个简洁、好记、可概括整体设定的名称。",
    "card.description": "概括角色卡主题、世界背景和玩法导向，控制在 2-5 句。",
    "characters.*.name": "给该角色起一个符合设定且有辨识度的名字。",
    "characters.*.triggerKeywords": "给出用于触发该角色世界书条目的关键词，使用逗号分隔。",
    "characters.*.age": "输出符合设定的年龄或外观年龄，简洁直接。",
    "characters.*.appearance": "描述外貌，突出发型、服饰、体态和辨识特征。",
    "characters.*.personality": "概括性格特征、核心动机和行为倾向。",
    "characters.*.speakingStyle": "描述该角色的说话方式、语气和词汇习惯。",
    "characters.*.speakingExample": "写一段能体现说话风格的简短示例。",
    "characters.*.background": "概述成长经历、身份设定与关键事件。",
    "opening.greeting": "写一句简洁的角色卡开场问候。",
    "opening.scenario": "概括当前场景，给出时间、地点和氛围。",
    "opening.exampleDialogue": "提供一段体现角色卡整体风格的示例对话。",
    "opening.firstMessage": "写成可直接用于 TavernAI 的首条消息。",
    "worldBook.entries.*.title": "写一个方便检索的世界书条目标题。",
    "worldBook.entries.*.keywords": "给出触发关键词，使用逗号分隔。",
    "worldBook.entries.*.content": "写成独立可读的设定条目内容，避免依赖上下文代词。",
}


def _trim(text: str, limit: int = 900) -> str:
    clean = (text or "").strip()
    if len(clean) <= limit:
        return clean
    return clean[:limit].rstrip() + "..."


def _normalize_field(field: str) -> str:
    return re.sub(r"\.\d+\.", ".*.", f"{field}.").rstrip(".")


def _render_character_context(characters: list[dict]) -> str:
    lines: list[str] = []
    for idx, character in enumerate(characters[:6], start=1):
        lines.extend(
            [
                f"角色{idx} 名称: {_trim(character.get('name', ''), 80)}",
                f"角色{idx} 关键词: {', '.join(character.get('triggerKeywords', []))}",
                f"角色{idx} 外貌: {_trim(character.get('appearance', ''), 180)}",
                f"角色{idx} 性格: {_trim(character.get('personality', ''), 180)}",
                f"角色{idx} 背景: {_trim(character.get('background', ''), 180)}",
            ]
        )
    return "\n".join(line for line in lines if not line.endswith(": "))


def _render_world_book_context(entries: list[dict]) -> str:
    lines: list[str] = []
    for idx, entry in enumerate(entries[:8], start=1):
        lines.extend(
            [
                f"条目{idx} 标题: {_trim(entry.get('title', ''), 80)}",
                f"条目{idx} 触发模式: {'蓝灯常驻' if entry.get('triggerMode') == 'always' else '绿灯关键词'}",
                f"条目{idx} 关键词: {', '.join(entry.get('keywords', []))}",
                f"条目{idx} 内容: {_trim(entry.get('content', ''), 180)}",
            ]
        )
    return "\n".join(line for line in lines if not line.endswith(": "))


def build_context(draft: dict) -> str:
    card = draft.get("card", {})
    opening = draft.get("opening", {})
    characters = draft.get("characters", [])
    world_entries = draft.get("worldBook", {}).get("entries", [])
    parts = [
        f"角色卡名称: {_trim(card.get('name', ''), 120)}",
        f"角色卡描述: {_trim(card.get('description', ''), 320)}",
        f"开场白: {_trim(opening.get('greeting', ''), 220)}",
        f"场景: {_trim(opening.get('scenario', ''), 280)}",
        f"首条消息: {_trim(opening.get('firstMessage', ''), 360)}",
        f"角色数量: {len(characters)}",
        _render_character_context(characters),
        f"世界书条目数量: {len(world_entries)}",
        _render_world_book_context(world_entries),
    ]
    return "\n".join(part for part in parts if part and not part.endswith(": "))


def build_field_prompt(field: str, mode: str, user_input: str, draft: dict) -> str:
    normalized = _normalize_field(field)
    instruction = FIELD_GUIDANCE.get(normalized, "根据已知设定生成当前字段内容。")
    action = "改写并增强" if mode == "rewrite" else "生成"
    return dedent(
        f"""
        你正在协助创建 AI 角色卡（多角色 + 世界书条目模式）。
        任务: {action} 字段 {field}
        要求: {instruction}

        当前字段已有内容:
        {_trim(user_input, 600) or '无'}

        已填写上下文:
        {build_context(draft)}

        输出要求:
        1. 只输出字段正文，不要加标题和解释。
        2. 保持设定一致，避免与已有角色和世界书冲突。
        3. 优先生成可直接粘贴到角色卡中的自然中文。
        """
    ).strip()


def build_image_prompt(draft: dict) -> tuple[str, str]:
    card = draft.get("card", {})
    characters = draft.get("characters", [])
    primary = characters[0] if characters else {}
    style = _trim(draft.get("illustration", {}).get("stylePrompt", ""), 200)
    prompt = dedent(
        f"""
        Character card illustration, high detail, clean composition.
        Card name: {_trim(card.get('name', ''), 80)}
        Card concept: {_trim(card.get('description', ''), 220)}
        Focus character: {_trim(primary.get('name', ''), 80)}
        Age: {_trim(primary.get('age', ''), 60)}
        Appearance: {_trim(primary.get('appearance', ''), 260)}
        Personality vibe: {_trim(primary.get('personality', ''), 220)}
        Background cues: {_trim(primary.get('background', ''), 220)}
        Style preference: {style or 'cinematic anime portrait, expressive lighting, polished illustration'}
        """
    ).strip().replace("\n", " ")
    negative = "low quality, blurry, extra fingers, text, watermark, cropped face, distorted anatomy"
    return prompt, negative
