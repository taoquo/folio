"""Deterministic importers that turn external diagram sources into Folio payloads."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .drawio import load_drawio_diagram
from .ledger import ImportError_, Ledger, local_source
from .mermaid import load_mermaid_diagram

DIALECTS = ("mermaid", "drawio")
_SUFFIX_DIALECTS = {".mmd": "mermaid", ".mermaid": "mermaid", ".drawio": "drawio", ".xml": "drawio"}


def detect_dialect(path: str | Path) -> str:
    """Resolve one dialect from the file suffix; never guess from file contents."""

    suffix = Path(str(path)).suffix.lower()
    dialect = _SUFFIX_DIALECTS.get(suffix)
    if dialect is None:
        raise ImportError_(
            "cannot detect an import dialect from the file suffix; pass --dialect mermaid or --dialect drawio"
        )
    return dialect


def load_diagram_source(
    path: str | Path, *, dialect: str = "auto", base: Path | None = None
) -> tuple[dict[str, Any], Ledger]:
    """Import one local diagram source into a typed Folio payload plus its fidelity ledger."""

    resolved = detect_dialect(path) if dialect in ("auto", "", None) else dialect
    if resolved not in DIALECTS:
        raise ImportError_(f"unsupported import dialect: {resolved}")
    if resolved == "mermaid":
        return load_mermaid_diagram(path, base=base)
    return load_drawio_diagram(path, base=base)


__all__ = [
    "DIALECTS",
    "ImportError_",
    "Ledger",
    "detect_dialect",
    "load_diagram_source",
    "load_drawio_diagram",
    "load_mermaid_diagram",
    "local_source",
]
