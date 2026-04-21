from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any
from uuid import uuid4

from PIL import Image, ImageDraw


def clean_text_output(text: str) -> str:
    cleaned = (text or "").strip()
    for marker in ("```", "标题:", "说明:"):
        cleaned = cleaned.replace(marker, "")
    return cleaned.strip()


class TextProvider(ABC):
    @abstractmethod
    def validate(self, config: dict[str, Any]) -> tuple[bool, str]:
        raise NotImplementedError

    @abstractmethod
    def generate(self, config: dict[str, Any], prompt: str) -> str:
        raise NotImplementedError


class ImageProvider(ABC):
    @abstractmethod
    def validate(self, config: dict[str, Any]) -> tuple[bool, str]:
        raise NotImplementedError

    @abstractmethod
    def generate(
        self, config: dict[str, Any], prompt: str, negative_prompt: str, output_dir: Path
    ) -> str:
        raise NotImplementedError


class MockTextProvider(TextProvider):
    def validate(self, config: dict[str, Any]) -> tuple[bool, str]:
        return True, "mock provider ready"

    def generate(self, config: dict[str, Any], prompt: str) -> str:
        content = prompt.split("当前字段已有内容:")[-1].split("已填写上下文:")[0].strip()
        if content == "无":
            content = "根据现有设定生成的角色字段内容。"
        return clean_text_output(f"{content}\n这段内容已由 mock Provider 补全并整理。")


class MockImageProvider(ImageProvider):
    def validate(self, config: dict[str, Any]) -> tuple[bool, str]:
        return True, "mock provider ready"

    def generate(
        self, config: dict[str, Any], prompt: str, negative_prompt: str, output_dir: Path
    ) -> str:
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"{uuid4()}.png"
        image = Image.new("RGB", (768, 1024), color=(243, 231, 217))
        draw = ImageDraw.Draw(image)
        preview = (prompt[:160] + "...") if len(prompt) > 160 else prompt
        draw.multiline_text((40, 60), preview or "Mock Character Image", fill=(60, 40, 28), spacing=12)
        image.save(path, format="PNG")
        return str(path)


class OpenAICompatibleTextProvider(TextProvider):
    def validate(self, config: dict[str, Any]) -> tuple[bool, str]:
        if not config.get("apiKey"):
            return False, "missing apiKey"
        if not config.get("model"):
            return False, "missing model"
        return True, "configuration looks valid"

    def generate(self, config: dict[str, Any], prompt: str) -> str:
        payload = {
            "model": config["model"],
            "messages": [{"role": "user", "content": prompt}],
            "temperature": config.get("temperature", 0.8),
        }
        request = urllib.request.Request(
            f"{config['baseUrl'].rstrip('/')}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {config['apiKey']}",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=config.get("timeoutMs", 45000) / 1000) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"provider_http_error: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"provider_network_error: {exc.reason}") from exc
        content = data["choices"][0]["message"]["content"]
        return clean_text_output(content)


class OpenAICompatibleImageProvider(ImageProvider):
    def validate(self, config: dict[str, Any]) -> tuple[bool, str]:
        if not config.get("apiKey"):
            return False, "missing apiKey"
        if not config.get("model"):
            return False, "missing model"
        return True, "configuration looks valid"

    def generate(
        self, config: dict[str, Any], prompt: str, negative_prompt: str, output_dir: Path
    ) -> str:
        payload = {
            "model": config["model"],
            "prompt": f"{prompt}\nNegative prompt: {negative_prompt}".strip(),
            "size": "1024x1024",
            "response_format": "b64_json",
        }
        request = urllib.request.Request(
            f"{config['baseUrl'].rstrip('/')}/images/generations",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {config['apiKey']}",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=config.get("timeoutMs", 45000) / 1000) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"provider_http_error: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"provider_network_error: {exc.reason}") from exc
        image_bytes = base64.b64decode(data["data"][0]["b64_json"])
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"{uuid4()}.png"
        path.write_bytes(image_bytes)
        return str(path)


class ProviderRegistry:
    def __init__(self) -> None:
        self.text_providers: dict[str, TextProvider] = {
            "mock": MockTextProvider(),
            "openai_compatible": OpenAICompatibleTextProvider(),
        }
        self.image_providers: dict[str, ImageProvider] = {
            "mock": MockImageProvider(),
            "openai_compatible": OpenAICompatibleImageProvider(),
        }

    def get_text_provider(self, provider_name: str) -> TextProvider:
        return self.text_providers[provider_name]

    def get_image_provider(self, provider_name: str) -> ImageProvider:
        return self.image_providers[provider_name]
