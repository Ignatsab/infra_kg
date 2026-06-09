"""Optional OpenAI-compatible LLM enrichment."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LLMSettings:
    base_url: str
    api_key: str
    model: str

    @classmethod
    def from_env(cls) -> "LLMSettings | None":
        base_url = first_env(
            "LLM_BASE_URL",
            "LLM_URL",
            "LLM_LINK",
            "LLM_ENDPOINT",
            "LLM_API_BASE",
            "OPENAI_BASE_URL",
            "OPENAI_API_BASE",
            "OPENAI_API_BASE_URL",
            "LOCAL_LLM_BASE_URL",
            "LOCAL_LLM_API_BASE",
        )
        api_key = first_env("LLM_API_KEY", "LLM_KEY", "OPENAI_API_KEY", "LOCAL_LLM_API_KEY")
        model = first_env(
            "LLM_MODEL",
            "LLM_MODEL_NAME",
            "OPENAI_MODEL",
            "OPENAI_MODEL_NAME",
            "LOCAL_LLM_MODEL",
            "LOCAL_LLM_MODEL_NAME",
        )
        if not base_url or not api_key or not model:
            return None
        return cls(base_url=base_url.rstrip("/"), api_key=api_key, model=model)


class OpenAICompatibleLLM:
    def __init__(self, settings: LLMSettings) -> None:
        self.settings = settings

    def enrich_application(self, application: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        prompt = (
            "Return compact JSON only with keys topology_summary and role_tags. "
            "role_tags must be a list of 2-5 short lowercase tags. "
            "Summarize the application role from this topology context:\n"
            f"{json.dumps({'application': application, 'context': context}, sort_keys=True)}"
        )
        payload = {
            "model": self.settings.model,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": "You enrich infrastructure graph nodes. Return valid JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
        }
        response = self._post_json("/chat/completions", payload)
        content = response["choices"][0]["message"]["content"]
        parsed = parse_json_object(content)
        summary = str(parsed.get("topology_summary", ""))[:500]
        tags = parsed.get("role_tags", [])
        if not isinstance(tags, list):
            tags = []
        return {
            "llm_summary": summary,
            "llm_tags": [str(tag)[:60] for tag in tags[:5]],
        }

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.settings.base_url}{path}"
        request = urllib.request.Request(
            url=url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.settings.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"LLM enrichment request failed: {exc}") from exc


def first_env(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def parse_json_object(content: str) -> dict[str, Any]:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        return {}
    try:
        parsed = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
