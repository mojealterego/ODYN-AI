from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any


class JsonStore:
    """Small atomic JSON store for local ODYN state."""

    def __init__(self, name: str, data_dir: str | os.PathLike[str] | None = None) -> None:
        root = Path(data_dir or os.getenv("ODYN_DATA_DIR") or Path(__file__).resolve().parents[1] / "data")
        self.root = root
        self.path = root / f"{name}.json"
        self.root.mkdir(parents=True, exist_ok=True)

    def load(self, default: Any) -> Any:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return default

    def save(self, value: Any) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile("w", encoding="utf-8", dir=self.root, delete=False) as tmp:
            json.dump(value, tmp, ensure_ascii=False, indent=2)
            tmp.flush()
            os.fsync(tmp.fileno())
            temp_path = Path(tmp.name)
        os.replace(temp_path, self.path)
