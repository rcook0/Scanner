import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


@dataclass
class FileResponseCache:
    """Very simple file-based response cache.

    Used by HTTP vendors to avoid hitting the same endpoint with the same
    parameters too frequently.

    It stores arbitrary JSON-serialisable payloads under a SHA-256 key.
    Expiry is based on file modification time.
    """

    root: Path
    ttl_seconds: int = 43200  # 12 hours by default

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for_key(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.root / f"{digest}.json"

    def get(self, key: str) -> Optional[Any]:
        path = self._path_for_key(key)
        if not path.exists():
            return None

        # TTL check based on mtime
        if self.ttl_seconds > 0:
            age = time.time() - path.stat().st_mtime
            if age > self.ttl_seconds:
                return None

        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("payload")
        except Exception:
            return None

    def set(self, key: str, payload: Any) -> None:
        path = self._path_for_key(key)
        body = {
            "created_ts": time.time(),
            "payload": payload,
        }
        tmp_path = path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(body, f)
        tmp_path.replace(path)
