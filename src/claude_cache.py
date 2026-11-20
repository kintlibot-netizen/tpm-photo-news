"""Remembers Claude's answers for one carousel, so a rebuild never asks the same question twice.

The key is a SHA-256 of the model, the full prompt and (for the image check) the image bytes. The prompt holds the
official text, so when the official page changes, the question changes and Claude is asked again. A reply is only
stored after it was read successfully (a parse error or an unreadable image check is never remembered).

The cache lives in data/carousel-cache/<carousel folder>.json. data/ is never committed or published, and nothing
secret is in it (only the prompts' official text and Claude's verdicts). Deleting the file forces fresh answers.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "carousel-cache"
MAX_ENTRIES = 500


def key_for(model: str, prompt: str, extra: bytes = b"") -> str:
    digest = hashlib.sha256()
    digest.update(model.encode("utf-8") + b"\0" + prompt.encode("utf-8") + b"\0")
    digest.update(extra)
    return digest.hexdigest()


class ReplyCache:
    """A small JSON file of {key: reply}. Safe to use from several threads (the image checks run in parallel)."""

    def __init__(self, path: Path | None):
        self.path = Path(path) if path is not None else None
        self._lock = threading.Lock()
        self._data: dict[str, str] = {}
        self.hits = 0
        if self.path is not None:
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self._data = {k: v for k, v in loaded.items() if isinstance(k, str) and isinstance(v, str)}
            except (OSError, ValueError):
                self._data = {}

    def get(self, key: str) -> str | None:
        with self._lock:
            value = self._data.get(key)
            if value is not None:
                self.hits += 1
            return value

    def put(self, key: str, reply: str) -> None:
        with self._lock:
            self._data[key] = reply
            while len(self._data) > MAX_ENTRIES:
                self._data.pop(next(iter(self._data)))
            if self.path is None:
                return
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                temp = self.path.with_name(self.path.name + ".tmp")
                temp.write_text(json.dumps(self._data, ensure_ascii=False), encoding="utf-8")
                os.replace(temp, self.path)
            except OSError:
                pass  # a cache that can't be written only means Claude is asked again next time


def for_folder(folder_name: str, cache_dir: Path | None = None) -> ReplyCache:
    return ReplyCache((cache_dir or CACHE_DIR) / f"{folder_name}.json")
