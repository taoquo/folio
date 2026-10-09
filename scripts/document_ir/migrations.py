"""Schema evolution for the Document IR.

Two rules, both aimed at keeping old documents readable forever:

1. A reader accepts every version it has ever accepted. Reading never requires
   an upgrade first.
2. A migrator moves `old -> current` and nothing else. There is no path back:
   rewriting a v1 document into v0 would destroy the record of what was
   actually written.

The schema version is independent of the Folio release version. Folio 9.0 does
not imply IR 2.0; only a breaking semantic change raises the IR major.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CURRENT_VERSION = "1.0"

# Versions this reader understands. Adding one is a one-line change here plus a
# migration function; removing one is a breaking change that needs a decision.
READABLE_VERSIONS: tuple[str, ...] = ("1.0",)


class MigrationError(ValueError):
    """Raised when a document cannot be brought to the current version."""


@dataclass(frozen=True, slots=True)
class Migration:
    """One step in the upgrade chain."""

    from_version: str
    to_version: str
    apply: Callable[[dict], dict]
    note: str

    def to_json(self) -> dict[str, str]:
        return {
            "from": self.from_version,
            "to": self.to_version,
            "note": self.note,
        }


def _version_tuple(version: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in str(version).split("."))
    except ValueError as exc:
        raise MigrationError(f"'{version}' is not a dotted version") from exc


def version_of(data: Mapping[str, Any]) -> str:
    """The schema version of a document, or a clear failure."""
    if not isinstance(data, Mapping):
        raise MigrationError("document must be a mapping")
    raw = data.get("schema_version")
    if raw is None:
        raise MigrationError(
            "document has no schema_version; every document must declare one so "
            "a future reader can tell what it is looking at"
        )
    return str(raw)


def is_readable(version: str) -> bool:
    return version in READABLE_VERSIONS


def is_current(version: str) -> bool:
    return _version_tuple(version) == _version_tuple(CURRENT_VERSION)


# --------------------------------------------------------------------------
# Migration steps
#
# Empty today, and that is the honest state: the IR has only ever had one
# version. The machinery exists now so that the first migration is a small,
# reviewable addition rather than an archaeology exercise.
# --------------------------------------------------------------------------

MIGRATIONS: tuple[Migration, ...] = ()


def _chain(from_version: str, to_version: str) -> list[Migration]:
    """Ordered steps from one version to another."""
    if _version_tuple(from_version) > _version_tuple(to_version):
        raise MigrationError(
            f"cannot migrate backwards from {from_version} to {to_version}: "
            "keep the original document and read it with its own version's reader"
        )

    remaining = list(MIGRATIONS)
    ordered: list[Migration] = []
    current = from_version
    guard = 0
    while current != to_version:
        guard += 1
        if guard > 64:
            raise MigrationError(f"migration chain from {from_version} did not converge")
        step = next((m for m in remaining if m.from_version == current), None)
        if step is None:
            raise MigrationError(f"no migration step from {current}")
        ordered.append(step)
        remaining.remove(step)
        current = step.to_version
    return ordered


def migrate(data: Mapping[str, Any], *, to_version: str = CURRENT_VERSION) -> dict[str, Any]:
    """Bring a document to a version, applying each step in order.

    The input is never modified: a migration returns a new document, so the
    original stays available as evidence of what was written.
    """
    version = version_of(data)
    if version == to_version:
        return dict(data)

    if not is_readable(version):
        raise MigrationError(
            f"schema version '{version}' is not readable; readable versions are "
            f"{', '.join(READABLE_VERSIONS)}"
        )

    result = dict(data)
    for step in _chain(version, to_version):
        result = step.apply(result)
        result["schema_version"] = step.to_version
    return result


def migrate_file(path: Path, *, to_version: str = CURRENT_VERSION) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MigrationError(f"{path}: invalid JSON: {exc}") from exc
    return migrate(data, to_version=to_version)


def supported_versions() -> dict[str, Any]:
    """What this reader accepts, for a CLI or a report."""
    return {
        "current": CURRENT_VERSION,
        "readable": list(READABLE_VERSIONS),
        "migrations": [m.to_json() for m in MIGRATIONS],
    }


def compatibility_report(documents: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Which of a set of documents a reader can open, and which need migrating.

    Used to answer "can the current reader open the archive" before changing
    anything, which is the question that matters when a schema moves.
    """
    readable, needs_migration, unreadable = [], [], []
    for name, data in documents.items():
        try:
            version = version_of(data)
        except MigrationError:
            unreadable.append({"document": name, "reason": "no schema_version"})
            continue
        if not is_readable(version):
            unreadable.append({"document": name, "reason": f"unknown version {version}"})
        elif is_current(version):
            readable.append({"document": name, "version": version})
        else:
            needs_migration.append({"document": name, "version": version})

    return {
        "current": CURRENT_VERSION,
        "readable": readable,
        "needs_migration": needs_migration,
        "unreadable": unreadable,
        "ok": not unreadable,
    }
