#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from infra_kg.env import load_dotenv
from infra_kg.llm import LLMSettings


BASE_URL_NAMES = [
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
]
API_KEY_NAMES = ["LLM_API_KEY", "LLM_KEY", "OPENAI_API_KEY", "LOCAL_LLM_API_KEY"]
MODEL_NAMES = [
    "LLM_MODEL",
    "LLM_MODEL_NAME",
    "OPENAI_MODEL",
    "OPENAI_MODEL_NAME",
    "LOCAL_LLM_MODEL",
    "LOCAL_LLM_MODEL_NAME",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Safely check OpenAI-compatible LLM .env settings.")
    parser.add_argument("--env-path", default=".env", help="Path to .env file.")
    args = parser.parse_args()

    env_path = Path(args.env_path)
    print(f"Checking env file: {env_path.resolve()}")
    print(f"Exists: {env_path.exists()}")
    load_dotenv(env_path)

    report_group("base URL", BASE_URL_NAMES)
    report_group("API key", API_KEY_NAMES, secret=True)
    report_group("model", MODEL_NAMES)

    settings = LLMSettings.from_env()
    if settings is None:
        print("\nResult: missing one or more required LLM settings")
        print("Use variables like:")
        print("LLM_BASE_URL=https://your-proxy.example.com/v1")
        print("LLM_API_KEY=...")
        print("LLM_MODEL=your-chat-model")
        raise SystemExit(1)

    print("\nResult: LLM settings found")
    print(f"Base URL: {settings.base_url}")
    print(f"Model: {settings.model}")
    print("API key: present")


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
