from __future__ import annotations

from pathlib import Path
import re
from typing import Any

MAX_FILE_BYTES = 512 * 1024
MAX_NODES = 12
MAX_EDGES = 24
REMOTE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")

MERMAID_DIALECTS = {"flowchart", "sequence", "state-machine", "er-diagram", "uml-class"}


class ImportError_(ValueError):
    """Raised when an external diagram source cannot be imported deterministically."""


def local_source(path: str | Path, *, base: Path | None = None) -> Path:
    value = str(path)
    if not value.strip():
        raise ImportError_("import path must be a non-empty local path")
    if REMOTE_RE.match(value) or value.startswith("//"):
        raise ImportError_("remote diagram sources are not allowed")
    candidate = Path(value)
    source = candidate if candidate.is_absolute() else (base or Path.cwd()) / candidate
    if not source.is_file():
        raise ImportError_("import source file does not exist")
    if source.stat().st_size > MAX_FILE_BYTES:
        raise ImportError_(f"import source exceeds {MAX_FILE_BYTES} bytes")
    return source


class Ledger:
    """Records what an import preserved, downgraded, or dropped."""

    def __init__(self, source: str, dialect: str, kind: str) -> None:
        self.source = source
        self.dialect = dialect
        self.kind = kind
        self.preserved: list[dict[str, str]] = []
        self.downgraded: list[dict[str, str]] = []
        self.dropped: list[dict[str, str]] = []

    def keep(self, feature: str, detail: str = "") -> None:
        self.preserved.append({"feature": feature, "detail": detail})

    def downgrade(self, feature: str, detail: str) -> None:
        self.downgraded.append({"feature": feature, "detail": detail})

    def drop(self, feature: str, detail: str) -> None:
        self.dropped.append({"feature": feature, "detail": detail})

    def to_dict(self) -> dict[str, Any]:
        total = len(self.preserved) + len(self.downgraded) + len(self.dropped)
        score = round(len(self.preserved) / total, 3) if total else 1.0
        return {
            "schema_version": "1.0",
            "source": self.source,
            "dialect": self.dialect,
            "kind": self.kind,
            "fidelity": score,
            "preserved": self.preserved,
            "downgraded": self.downgraded,
            "dropped": self.dropped,
        }


def _slug(value: str, used: dict[str, str]) -> str:
    if value in used:
        return used[value]
    base = re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip()).strip("-").lower() or "node"
    candidate = base
    index = 2
    while candidate in used.values():
        candidate = f"{base}-{index}"
        index += 1
    used[value] = candidate
    return candidate


def _clean_label(value: str) -> str:
    text = value.strip().strip('"').strip("'")
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    return re.sub(r"\s+", " ", text).strip()
