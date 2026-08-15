from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class DrawingDiagnostic:
    level: str
    code: str
    message: str
    object_id: str | None = None
    path: str | None = None
    hint: str | None = None
    related_ids: tuple[str, ...] = ()

    def __str__(self) -> str:
        target = f" [{self.object_id}]" if self.object_id else ""
        return f"{self.level} {self.code}{target}: {self.message}"

    def to_envelope(self, *, stage: str, kind: str | None) -> dict[str, object]:
        related = sorted({*(self.related_ids or ()), *([self.object_id] if self.object_id else [])})
        return {
            "code": self.code,
            "severity": self.level,
            "stage": stage,
            "kind": kind,
            "path": self.path or "",
            "message": self.message,
            "hint": self.hint or "",
            "related_ids": related,
        }


def diagnostic_envelopes(
    diagnostics: Iterable[DrawingDiagnostic],
    *,
    stage: str,
    kind: str | None,
) -> list[dict[str, object]]:
    envelopes = [item.to_envelope(stage=stage, kind=kind) for item in diagnostics]
    return sorted(
        envelopes,
        key=lambda item: (
            str(item["stage"]), str(item["code"]), str(item["path"]),
            ",".join(str(value) for value in item["related_ids"]),
        ),
    )


class DrawingCompilationError(ValueError):
    """A deterministic compiler failure with machine-readable diagnostics."""

    def __init__(self, stage: str, diagnostics: Iterable[DrawingDiagnostic]):
        self.stage = stage
        self.diagnostics = tuple(diagnostics)
        detail = "; ".join(str(item) for item in self.diagnostics) or "unknown drawing compiler error"
        super().__init__(f"drawing compilation failed at {stage}: {detail}")


def raise_for_errors(stage: str, diagnostics: Iterable[DrawingDiagnostic]) -> tuple[DrawingDiagnostic, ...]:
    resolved = tuple(diagnostics)
    errors = tuple(item for item in resolved if item.level == "ERROR")
    if errors:
        raise DrawingCompilationError(stage, errors)
    return resolved
