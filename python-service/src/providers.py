from __future__ import annotations

import base64
import json
import re
import socket
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any
from uuid import uuid4


RETRYABLE_HTTP_STATUS = {408, 409, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524}


def clean_text_output(text: str) -> str:
    cleaned = str(text or "")
    for marker in ("```", "标题:", "说明:"):
        cleaned = cleaned.replace(marker, "")
    return cleaned


def compose_text_prompt(config: dict[str, Any], prompt: str) -> str:
    prefix_prompt = str(config.get("prefixPrompt", ""))
    main_prompt = str(prompt or "")
    if not prefix_prompt:
        return main_prompt
    if not main_prompt:
        return prefix_prompt
    return f"{prefix_prompt}\n\n{main_prompt}"


class TextProvider(ABC):
    @abstractmethod
    def validate(self, config: dict[str, Any]) -> tuple[bool, str]:
        raise NotImplementedError

    @abstractmethod
    def generate(self, config: dict[str, Any], prompt: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def list_models(self, config: dict[str, Any]) -> list[str]:
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

    @abstractmethod
    def list_models(self, config: dict[str, Any]) -> list[str]:
        raise NotImplementedError


def _openai_request_json(
    config: dict[str, Any],
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    max_retries = max(0, int(config.get("retryCount", 2)))
    attempts = max_retries + 1
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return _openai_request_json_once(config, method, path, payload)
        except RuntimeError as exc:
            last_error = exc
            message = str(exc)
            retryable = any(
                marker in message
                for marker in (
                    "provider_timeout:",
                    "provider_http_error: upstream timeout (524)",
                    "provider_http_error: status=408",
                    "provider_http_error: status=409",
                    "provider_http_error: status=429",
                    "provider_http_error: status=500",
                    "provider_http_error: status=502",
                    "provider_http_error: status=503",
                    "provider_http_error: status=504",
                    "provider_http_error: status=520",
                    "provider_http_error: status=521",
                    "provider_http_error: status=522",
                    "provider_http_error: status=523",
                    "provider_http_error: status=524",
                    "provider_network_error:",
                )
            )
            if not retryable or attempt >= attempts - 1:
                raise
            time.sleep(0.8 * (2**attempt))
    if last_error is not None:
        raise last_error
    raise RuntimeError("provider_generation_failed: unknown provider error")


def _summarize_http_error(detail: str, status_code: int) -> str:
    title_match = re.search(r"<title>(.*?)</title>", detail, flags=re.IGNORECASE | re.DOTALL)
    title = title_match.group(1).strip() if title_match else ""
    code_match = re.search(r"Error code\s*(\d+)", detail, flags=re.IGNORECASE)
    cloudflare_code = code_match.group(1) if code_match else ""
    if status_code == 524 or cloudflare_code == "524" or "timeout occurred" in title.lower():
        return "provider_http_error: upstream timeout (524)"
    compact_title = re.sub(r"\s+", " ", title)[:200] if title else ""
    if compact_title:
        return f"provider_http_error: status={status_code} title={compact_title}"
    compact_detail = re.sub(r"\s+", " ", detail)[:300]
    return f"provider_http_error: status={status_code} detail={compact_detail}"


def _openai_request_json_once(
    config: dict[str, Any],
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        # Avoid Cloudflare 1010 blocks on default Python-urllib signature.
        "User-Agent": "RolePlayCard/0.0.3 (+https://localhost)",
        "Authorization": f"Bearer {config['apiKey']}",
    }
    extra_headers = config.get("extraHeaders", {})
    if isinstance(extra_headers, dict):
        for key, value in extra_headers.items():
            if isinstance(key, str) and isinstance(value, str) and key.strip():
                headers[key.strip()] = value
    timeout_raw = config.get("timeoutMs", 45000)
    try:
        timeout_ms = float(timeout_raw)
    except (TypeError, ValueError):
        timeout_ms = 45000.0
    timeout_ms = max(1000.0, timeout_ms)
    timeout_seconds = timeout_ms / 1000.0
    request = urllib.request.Request(
        f"{config['baseUrl'].rstrip('/')}{path}",
        data=body,
        method=method,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        if exc.code in RETRYABLE_HTTP_STATUS:
            if exc.code == 524:
                raise RuntimeError("provider_http_error: upstream timeout (524)") from exc
            raise RuntimeError(f"provider_http_error: status={exc.code}") from exc
        summarized = _summarize_http_error(detail, exc.code)
        raise RuntimeError(summarized) from exc
    except TimeoutError as exc:
        raise RuntimeError(f"provider_timeout: request timed out after {int(timeout_seconds * 1000)}ms") from exc
    except socket.timeout as exc:
        raise RuntimeError(f"provider_timeout: request timed out after {int(timeout_seconds * 1000)}ms") from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            raise RuntimeError(f"provider_timeout: request timed out after {int(timeout_seconds * 1000)}ms") from exc
        raise RuntimeError(f"provider_network_error: {exc.reason}") from exc


class OpenAICompatibleTextProvider(TextProvider):
    def validate(self, config: dict[str, Any]) -> tuple[bool, str]:
        if not config.get("baseUrl"):
            return False, "missing baseUrl"
        if not config.get("apiKey"):
            return False, "missing apiKey"
        return True, "configuration looks valid"

    def generate(self, config: dict[str, Any], prompt: str) -> str:
        if not config.get("model"):
            raise RuntimeError("provider_config_invalid: missing model")
        merged_prompt = compose_text_prompt(config, prompt)
        payload = {
            "model": config["model"],
            "messages": [{"role": "user", "content": merged_prompt}],
            "temperature": config.get("temperature", 0.8),
        }
        data = _openai_request_json(config, "POST", "/chat/completions", payload)
        content = data["choices"][0]["message"]["content"]
        return clean_text_output(content)

    def list_models(self, config: dict[str, Any]) -> list[str]:
        if not config.get("baseUrl"):
            raise RuntimeError("provider_config_invalid: missing baseUrl")
        if not config.get("apiKey"):
            raise RuntimeError("provider_config_invalid: missing apiKey")
        data = _openai_request_json(config, "GET", "/models")
        models = data.get("data", [])
        ids = [str(item.get("id", "")).strip() for item in models if isinstance(item, dict)]
        return sorted({item for item in ids if item})


class OpenAICompatibleImageProvider(ImageProvider):
    def validate(self, config: dict[str, Any]) -> tuple[bool, str]:
        if not config.get("baseUrl"):
            return False, "missing baseUrl"
        if not config.get("apiKey"):
            return False, "missing apiKey"
        return True, "configuration looks valid"

    def generate(
        self, config: dict[str, Any], prompt: str, negative_prompt: str, output_dir: Path
    ) -> str:
        if not config.get("model"):
            raise RuntimeError("provider_config_invalid: missing model")
        payload = {
            "model": config["model"],
            "prompt": f"{prompt}\nNegative prompt: {negative_prompt}".strip(),
            "size": "1024x1024",
            "response_format": "b64_json",
        }
        data = _openai_request_json(config, "POST", "/images/generations", payload)
        image_bytes = base64.b64decode(data["data"][0]["b64_json"])
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"{uuid4()}.png"
        path.write_bytes(image_bytes)
        return str(path)

    def list_models(self, config: dict[str, Any]) -> list[str]:
        if not config.get("baseUrl"):
            raise RuntimeError("provider_config_invalid: missing baseUrl")
        if not config.get("apiKey"):
            raise RuntimeError("provider_config_invalid: missing apiKey")
        data = _openai_request_json(config, "GET", "/models")
        models = data.get("data", [])
        ids = [str(item.get("id", "")).strip() for item in models if isinstance(item, dict)]
        return sorted({item for item in ids if item})


class ProviderRegistry:
    def __init__(self) -> None:
        self.text_providers: dict[str, TextProvider] = {
            "openai_compatible": OpenAICompatibleTextProvider(),
        }
        self.image_providers: dict[str, ImageProvider] = {
            "openai_compatible": OpenAICompatibleImageProvider(),
        }

    def get_text_provider(self, provider_name: str) -> TextProvider:
        normalized = "openai_compatible" if provider_name == "mock" else provider_name
        if normalized not in self.text_providers:
            raise KeyError(f"unsupported_text_provider: {provider_name}")
        return self.text_providers[normalized]

    def get_image_provider(self, provider_name: str) -> ImageProvider:
        normalized = "openai_compatible" if provider_name == "mock" else provider_name
        if normalized not in self.image_providers:
            raise KeyError(f"unsupported_image_provider: {provider_name}")
        return self.image_providers[normalized]
