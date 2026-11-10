"""Content-addressed storage for raw source responses.

Real data is not reproducible: a page changes, an RDAP record is updated, a
certificate expires. Storing the exact bytes we saw is what makes a report
defensible six months later.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from .config import settings


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class EvidenceStore:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or settings.evidence_dir
        self.directory.mkdir(parents=True, exist_ok=True)

    def store(self, payload: bytes) -> tuple[str, str]:
        """Persist ``payload`` and return ``(sha256, absolute_path)``."""
        sha = digest(payload)
        path = self.directory / f"{sha}.bin"
        if not path.exists():
            path.write_bytes(payload)
        return sha, str(path)

    def load(self, sha: str) -> bytes:
        return (self.directory / f"{sha}.bin").read_bytes()
