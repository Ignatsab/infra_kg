"""Embedding providers for graph retrieval text."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from infra_kg.env import load_dotenv

TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_.:-]+")


class EmbeddingProvider(Protocol):
    @property
    def dimensions(self) -> int | None:
        ...

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ...


@dataclass(frozen=True)
class OpenAIEmbeddingSettings:
    base_url: str
    api_key: str
    model: str
    dimensions: int | None = None
    batch_size: int = 32
    timeout_seconds: int = 120

    @classmethod
    def from_env(cls, env_path: str = ".env") -> "OpenAIEmbeddingSettings | None":
        load_dotenv(env_path)
        base_url = first_env(
            "EMBEDDING_BASE_URL",
            "EMBEDDING_URL",
            "EMBEDDING_LINK",
            "EMBEDDING_ENDPOINT",
            "EMBEDDING_API",
            "EMBEDDING_API_BASE",
            "OPENAI_BASE_URL",
            "OPENAI_API_BASE",
            "OPENAI_API_BASE_URL",
            "LLM_BASE_URL",
            "LLM_URL",
            "LLM_LINK",
            "LLM_ENDPOINT",
            "LLM_API_BASE",
            "LOCAL_LLM_BASE_URL",
            "LOCAL_LLM_API_BASE",
        )
        api_key = first_env(
            "EMBEDDING_API_KEY",
            "EMBEDDING_KEY",
            "OPENAI_API_KEY",
            "LLM_API_KEY",
            "LLM_KEY",
            "LOCAL_LLM_API_KEY",
        )
        model = first_env(
            "EMBEDDING_MODEL",
            "EMBEDDING_MODEL_NAME",
            "OPENAI_EMBEDDING_MODEL",
            "LOCAL_EMBEDDING_MODEL",
            "LLM_EMBEDDING_MODEL",
            "LLM_MODEL",
            "LLM_MODEL_NAME",
            "OPENAI_MODEL",
            "OPENAI_MODEL_NAME",
            "LOCAL_LLM_MODEL",
            "LOCAL_LLM_MODEL_NAME",
        )
        dimensions_raw = first_env("EMBEDDING_DIMENSIONS", "OPENAI_EMBEDDING_DIMENSIONS")
        dimensions = int(dimensions_raw) if dimensions_raw and dimensions_raw.isdigit() else None
        batch_size = positive_int_env("EMBEDDING_BATCH_SIZE", default=32)
        timeout_seconds = positive_int_env("EMBEDDING_TIMEOUT_SECONDS", default=120)
        if not base_url or not api_key or not model:
            return None
        return cls(
            base_url=normalize_embedding_base_url(base_url),
            api_key=api_key,
            model=model,
            dimensions=dimensions,
            batch_size=batch_size,
            timeout_seconds=timeout_seconds,
        )


class OpenAICompatibleEmbeddingProvider:
    def __init__(self, settings: OpenAIEmbeddingSettings) -> None:
        self.settings = settings
        self._dimensions = settings.dimensions

    @property
    def dimensions(self) -> int | None:
        return self._dimensions

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        embeddings: list[list[float]] = []
        for batch in chunked(texts, self.settings.batch_size):
            embeddings.extend(self._embed_batch(batch))
        return embeddings

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        payload: dict[str, object] = {
            "model": self.settings.model,
            "input": texts,
        }
        if self.settings.dimensions:
            payload["dimensions"] = self.settings.dimensions

        response = self._post_json("/embeddings", payload)
        data = sorted(response.get("data", []), key=lambda item: item.get("index", 0))
        embeddings = [[float(value) for value in item["embedding"]] for item in data]
        if len(embeddings) != len(texts):
            raise RuntimeError(f"Embedding endpoint returned {len(embeddings)} embeddings for {len(texts)} inputs")
        if embeddings:
            self._dimensions = len(embeddings[0])
        return embeddings

    def _post_json(self, path: str, payload: dict[str, object]) -> dict[str, object]:
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
            with urllib.request.urlopen(request, timeout=self.settings.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Embedding request failed: {exc}") from exc


class HashEmbeddingProvider:
    """Deterministic local embedding for plumbing tests, not semantic retrieval."""

    def __init__(self, dimensions: int = 64) -> None:
        if dimensions < 8:
            raise ValueError("Hash embedding dimensions must be at least 8")
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(text) for text in texts]

    def embed_text(self, text: str) -> list[float]:
        vector = [0.0 for _ in range(self._dimensions)]
        for token in TOKEN_PATTERN.findall(text.lower()):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self._dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [round(value / norm, 6) for value in vector]


def embedding_provider_from_choice(
    choice: str,
    *,
    dimensions: int = 64,
    env_path: str = ".env",
) -> EmbeddingProvider | None:
    if choice == "none":
        return None
    if choice == "hash":
        return HashEmbeddingProvider(dimensions=dimensions)
    if choice == "openai":
        settings = OpenAIEmbeddingSettings.from_env(env_path)
        if settings is None:
            raise RuntimeError(
                "Embedding provider requested but EMBEDDING_BASE_URL, EMBEDDING_API_KEY, "
                "and EMBEDDING_MODEL were not found"
            )
        return OpenAICompatibleEmbeddingProvider(settings)
    raise ValueError(f"Unknown embedding provider: {choice}")


def first_env(*names: str) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def positive_int_env(name: str, *, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def normalize_embedding_base_url(raw_url: str) -> str:
    url = raw_url.strip().rstrip("/")
    for suffix in ("/embeddings", "/chat/completions"):
        if url.endswith(suffix):
            return url[: -len(suffix)].rstrip("/")
    return url


def chunked(items: list[str], size: int) -> list[list[str]]:
    return [items[index : index + size] for index in range(0, len(items), size)]
