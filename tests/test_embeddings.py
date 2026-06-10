from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from infra_kg.embeddings import OpenAIEmbeddingSettings, normalize_embedding_base_url


class EmbeddingSettingsTest(unittest.TestCase):
    def test_embedding_specific_aliases_are_read_from_env(self) -> None:
        with patch.dict(
            os.environ,
            {
                "EMBEDDING_LINK": "https://proxy.example.test/v1/embeddings",
                "EMBEDDING_KEY": "secret",
                "EMBEDDING_MODEL": "text-embedding-model",
                "EMBEDDING_BATCH_SIZE": "7",
                "EMBEDDING_TIMEOUT_SECONDS": "9",
            },
            clear=True,
        ):
            settings = OpenAIEmbeddingSettings.from_env("/tmp/missing-env")

        self.assertIsNotNone(settings)
        assert settings is not None
        self.assertEqual("https://proxy.example.test/v1", settings.base_url)
        self.assertEqual("secret", settings.api_key)
        self.assertEqual("text-embedding-model", settings.model)
        self.assertEqual(7, settings.batch_size)
        self.assertEqual(9, settings.timeout_seconds)

    def test_llm_env_can_be_used_as_fallback(self) -> None:
        with patch.dict(
            os.environ,
            {
                "LLM_LINK": "https://proxy.example.test/v1",
                "LLM_KEY": "secret",
                "LLM_MODEL": "local-embedding-capable-model",
            },
            clear=True,
        ):
            settings = OpenAIEmbeddingSettings.from_env("/tmp/missing-env")

        self.assertIsNotNone(settings)
        assert settings is not None
        self.assertEqual("https://proxy.example.test/v1", settings.base_url)
        self.assertEqual("secret", settings.api_key)
        self.assertEqual("local-embedding-capable-model", settings.model)

    def test_embedding_endpoint_url_is_normalized(self) -> None:
        self.assertEqual(
            "https://proxy.example.test/v1",
            normalize_embedding_base_url("https://proxy.example.test/v1/embeddings"),
        )


if __name__ == "__main__":
    unittest.main()
