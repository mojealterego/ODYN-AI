import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from odyn_ai.core.rag_memory import RAGMemoryEngine


class FakeEmbedder:
    def __init__(self, **kwargs):
        self.vectors = {
            "fotografia": [1.0, 0.0],
            "aparat": [0.9, 0.1],
            "programowanie": [0.0, 1.0],
        }

    def embed(self, text):
        return self.vectors.get(text, [1.0, 0.0])


class RAGMemoryTests(unittest.TestCase):
    @patch("odyn_ai.core.rag_memory.Llama", FakeEmbedder)
    def test_add_and_retrieve_semantic_memory(self):
        engine = RAGMemoryEngine("fake.gguf")
        self.assertTrue(engine.add_memory("fotografia"))
        self.assertTrue(engine.add_memory("programowanie"))

        result = engine.retrieve_relevant("aparat", top_k=1)
        self.assertIn("fotografia", result)
        self.assertNotIn("programowanie", result)

    @patch("odyn_ai.core.rag_memory.Llama", FakeEmbedder)
    def test_memory_persists_and_reloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "rag.json")
            first = RAGMemoryEngine("fake.gguf", data_path=path)
            first.add_memory("fotografia")

            second = RAGMemoryEngine("fake.gguf", data_path=path)
            self.assertEqual(second.count(), 1)
            self.assertIn("fotografia", second.retrieve_relevant("aparat"))

    @patch("odyn_ai.core.rag_memory.Llama", side_effect=RuntimeError("missing model"))
    def test_unavailable_model_is_safe(self, _mock):
        engine = RAGMemoryEngine("missing.gguf")
        self.assertFalse(engine.available)
        self.assertFalse(engine.add_memory("tekst"))
        self.assertEqual(engine.retrieve_relevant("tekst"), "")

    @patch("odyn_ai.core.rag_memory.Llama", FakeEmbedder)
    def test_clear_removes_memory_and_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "rag.json")
            engine = RAGMemoryEngine("fake.gguf", data_path=path)
            engine.add_memory("fotografia")
            engine.clear()

            self.assertEqual(engine.count(), 0)
            self.assertFalse(Path(path).exists())


if __name__ == "__main__":
    unittest.main()
