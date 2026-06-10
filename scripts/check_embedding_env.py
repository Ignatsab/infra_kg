#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from infra_kg.embeddings import OpenAIEmbeddingSettings
from infra_kg.env import load_dotenv


BASE_URL_NAMES = [
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
]
API_KEY_NAMES = [
    "EMBEDDING_API_KEY",
    "EMBEDDING_KEY",
    "OPENAI_API_KEY",
    "LLM_API_KEY",
    "LLM_KEY",
    "LOCAL_LLM_API_KEY",
]
MODEL_NAMES = [
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
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Safely check OpenAI-compatible embedding .env settings.")
    parser.add_argument("--env-path", default=".env", help="Path to .env file.")
    args = parser.parse_args()

    env_path = Path(args.env_path)
    print(f"Checking env file: {env_path.resolve()}")
    print(f"Exists: {env_path.exists()}")
    load_dotenv(env_path)

    report_group("base URL", BASE_URL_NAMES)
    report_group("API key", API_KEY_NAMES, secret=True)
    report_group("model", MODEL_NAMES)
    report_group("dimensions", ["EMBEDDING_DIMENSIONS", "OPENAI_EMBEDDING_DIMENSIONS"])
    report_group("batch size", ["EMBEDDING_BATCH_SIZE"])
    report_group("timeout seconds", ["EMBEDDING_TIMEOUT_SECONDS"])

    settings = OpenAIEmbeddingSettings.from_env(str(env_path))
    if settings is None:
        print("\nResult: missing one or more required embedding settings")
        print("Use variables like:")
        print("EMBEDDING_BASE_URL=https://your-proxy.example.com/v1")
        print("EMBEDDING_API_KEY=...")
        print("EMBEDDING_MODEL=your-embedding-model")
        print("\nFallback LLM_* names are also accepted if your proxy uses the same endpoint/model.")
        raise SystemExit(1)

    print("\nResult: embedding settings found")
    print(f"Base URL: {settings.base_url}")
    print(f"Model: {settings.model}")
    print("API key: present")
    print(f"Dimensions: {settings.dimensions or 'endpoint default'}")
    print(f"Batch size: {settings.batch_size}")
    print(f"Timeout seconds: {settings.timeout_seconds}")


def report_group(label: str, names: list[str], *, secret: bool = False) -> None:
    found = [(name, os.environ[name]) for name in names if os.environ.get(name)]
    if not found:
        print(f"{label}: missing")
        return
    name, value = found[0]
    if secret:
        value_text = f"present ({len(value)} chars)"
    else:
        value_text = value
    print(f"{label}: {name} = {value_text}")


if __name__ == "__main__":
    main()
