from __future__ import annotations

from textwrap import dedent


FIELD_GUIDANCE = {
    "profile.name": "给出一个适合该角色设定、便于记忆且有辨识度的中文姓名。",
    "profile.age": "输出符合设定的年龄或外观年龄，简洁直接。",
    "profile.gender": "输出角色性别或性别表达方式，简洁直接。",
    "profile.appearance": "描述外貌，突出发型、服饰、气质、体态和辨识度特征。",
    "profile.personality": "概括性格特征、核心驱动力和情绪表达方式。",
    "profile.speakingStyle": "描述说话风格、措辞习惯、语气和交流偏好。",
    "profile.background": "概述成长经历、职业身份和关键事件。",
    "opening.greeting": "写一句简洁的角色问候，用于首屏展示。",
    "opening.scenario": "概括当前故事场景，给出时间、地点和氛围。",
    "opening.exampleDialogue": "提供一段体现角色风格的示例对话。",
    "opening.firstMessage": "写成可直接给 TavernAI 使用的首条角色消息。",
}


def _trim(text: str, limit: int = 900) -> str:
    clean = (text or "").strip()
    if len(clean) <= limit:
        return clean
    return clean[:limit].rstrip() + "..."


def build_context(draft: dict) -> str:
    profile = draft["profile"]
    opening = draft["opening"]
    world_book = _trim(draft.get("worldBook", ""), 700)
    parts = [
        f"姓名: {_trim(profile['name'], 120)}",
        f"年龄: {_trim(profile['age'], 80)}",
        f"性别: {_trim(profile['gender'], 80)}",
        f"外貌: {_trim(profile['appearance'], 300)}",
        f"性格: {_trim(profile['personality'], 300)}",
        f"说话风格: {_trim(profile['speakingStyle'], 240)}",
        f"背景: {_trim(profile['background'], 320)}",
        f"开场白: {_trim(opening['greeting'], 220)}",
        f"场景: {_trim(opening['scenario'], 280)}",
        f"首条消息: {_trim(opening['firstMessage'], 360)}",
        f"世界书摘要: {world_book}",
    ]
    return "\n".join(part for part in parts if not part.endswith(": "))


def build_field_prompt(field: str, mode: str, user_input: str, draft: dict) -> str:
    instruction = FIELD_GUIDANCE.get(field, "根据已知角色设定生成当前字段内容。")
    action = "改写并增强" if mode == "rewrite" else "生成"
    return dedent(
        f"""
        你正在协助创建 AI 角色卡。
        任务: {action} 字段 {field}
        要求: {instruction}

        当前字段已有内容:
        {_trim(user_input, 500) or '无'}

        已填写上下文:
        {build_context(draft)}

        输出要求:
        1. 只输出字段正文，不要加标题和解释。
        2. 保持设定一致，避免与上下文冲突。
        3. 优先生成可直接粘贴到角色卡中的自然中文。
        """
    ).strip()


def build_image_prompt(draft: dict) -> tuple[str, str]:
    profile = draft["profile"]
    style = _trim(draft["illustration"].get("stylePrompt", ""), 200)
    prompt = dedent(
        f"""
        Character portrait, high detail, clean composition.
        Name: {_trim(profile['name'], 80)}
        Age: {_trim(profile['age'], 60)}
        Gender expression: {_trim(profile['gender'], 60)}
        Appearance: {_trim(profile['appearance'], 260)}
        Personality vibe: {_trim(profile['personality'], 220)}
        Background cues: {_trim(profile['background'], 220)}
        Style preference: {style or 'cinematic anime portrait, expressive lighting, polished illustration'}
        """
    ).strip().replace("\n", " ")
    negative = "low quality, blurry, extra fingers, text, watermark, cropped face, distorted anatomy"
    return prompt, negative
