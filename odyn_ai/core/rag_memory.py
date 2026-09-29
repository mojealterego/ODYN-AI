from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from llama_cpp import Llama
from sklearn.metrics.pairwise import cosine_similarity


class RAGMemoryEngine:
    """Local semantic episodic memory backed by a GGUF embedding model."""

    def __init__(
        self,
        embedding_model_path: str,
        *,
        data_path: str | None = None,
        n_ctx: int = 2048,
    ) -> None:
        self.embedding_model_path = embedding_model_path
        self.data_path = Path(data_path) if data_path else None
        self.embedder: Llama | None = None
        self.memory_store: list[dict[str, Any]] = []

        print("🐦‍⬛ ODYN AI: Inicjalizacja Pamięci Wektorowej RAG 2.0...")
        try:
            self.embedder = Llama(
                model_path=embedding_model_path,
                embedding=True,
                n_ctx=n_ctx,
                verbose=False,
            )
            self._load()
        except Exception as exc:
            print(f"⚠️ Błąd inicjalizacji RAG: {exc}")
            self.embedder = None

    @property
    def available(self) -> bool:
        return self.embedder is not None

    def _load(self) -> None:
        if not self.data_path or not self.data_path.exists():
            return
        try:
            raw = json.loads(self.data_path.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                return
            self.memory_store = [
                {"text": item["text"], "vector": np.asarray(item["vector"], dtype=np.float32).reshape(1, -1)}
                for item in raw
                if isinstance(item, dict) and isinstance(item.get("text"), str) and item.get("vector")
            ]
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            self.memory_store = []

    def _persist(self) -> None:
        if not self.data_path:
            return
        self.data_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [
            {"text": item["text"], "vector": item["vector"].reshape(-1).tolist()}
            for item in self.memory_store
        ]
        self.data_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def _embed(self, text: str) -> np.ndarray:
        if not self.embedder:
            raise RuntimeError("Model embeddingowy RAG nie jest dostępny.")
        vector = np.asarray(self.embedder.embed(text), dtype=np.float32)
        return vector.reshape(1, -1)

    def add_memory(self, text: str) -> bool:
        """Embed and store an episodic memory. Returns False when RAG is unavailable."""
        text = text.strip()
        if not text or not self.embedder:
            return False

        vector = self._embed(text)
        self.memory_store.append({"text": text, "vector": vector})
        self._persist()
        print("✅ Zapisano wspomnienie w wektorowej pamięci epizodycznej.")
        return True

    def retrieve_relevant(self, query: str, top_k: int = 2) -> str:
        """Return the top semantic memories as an injectable RAG context."""
        if not self.embedder or not self.memory_store or top_k <= 0:
            return ""

        query_vector = self._embed(query)
        scored = [
            (
                float(cosine_similarity(query_vector, memory["vector"])[0][0]),
                memory["text"],
            )
            for memory in self.memory_store
        ]
        scored.sort(key=lambda item: item[0], reverse=True)

        context = "\n".join(text for _, text in scored[:top_k])
        return f"\n[PAMIĘĆ EPIZODYCZNA RAG]: {context}\n" if context else ""

    def clear(self) -> None:
        """Clear in-memory and persisted episodic memory."""
        self.memory_store.clear()
        if self.data_path:
            try:
                self.data_path.unlink()
            except FileNotFoundError:
                pass

    def count(self) -> int:
        return len(self.memory_store)
