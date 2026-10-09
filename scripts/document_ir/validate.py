"""Semantic validation for the Document IR.

Validation is fail-closed: a document with an ERROR does not render. Tolerating
a structural mistake here means discovering it later as a mis-set page, and by
then the cause is several stages away from the symptom.

ID rules are enforced from the start because everything downstream depends on
them. Cross-references, anchor diffs, reading order and incremental builds all
key on node identity; a renderer that renames a node breaks all four silently.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Literal

from .model import Block, Document, Inline, Text

Severity = Literal["INFO", "WARNING", "ERROR"]

# Ids are referenced from prose, so they must survive a round trip through
# JSON, an anchor and a URL fragment.
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

# Cross-reference targets must already exist when the document renders, or the
# reader sees a broken pointer.
REFERENCE_TARGETS = {
    "cross_ref": "target",
    "footnote_ref": "target",
}


@dataclass(frozen=True, slots=True)
class Diagnostic:
    severity: Severity
    code: str
    subject: str
    message: str
    hint: str | None = None

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "severity": self.severity,
            "code": self.code,
            "subject": self.subject,
            "message": self.message,
        }
        if self.hint:
            out["hint"] = self.hint
        return out


@dataclass
class ValidationReport:
    diagnostics: list[Diagnostic] = field(default_factory=list)

    def add(self, severity: Severity, code: str, subject: str, message: str,
            hint: str | None = None) -> None:
        self.diagnostics.append(Diagnostic(severity, code, subject, message, hint))

    def error(self, code: str, subject: str, message: str, hint: str | None = None) -> None:
        self.add("ERROR", code, subject, message, hint)

    def warning(self, code: str, subject: str, message: str, hint: str | None = None) -> None:
        self.add("WARNING", code, subject, message, hint)

    @property
    def errors(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == "ERROR"]

    @property
    def warnings(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == "WARNING"]

    @property
    def ok(self) -> bool:
        """Fail-closed: any ERROR blocks rendering."""
        return not self.errors

    def to_json(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": len(self.errors),
            "warnings": len(self.warnings),
            "diagnostics": [d.to_json() for d in self.diagnostics],
        }


def _inline_text(nodes: Iterable[Inline]) -> str:
    """Plain text of an inline run, for checks that need to read it."""
    out: list[str] = []
    for node in nodes:
        value = getattr(node, "value", None)
        if isinstance(value, str):
            out.append(value)
        content = getattr(node, "content", None)
        if content:
            out.append(_inline_text(content))
        label = getattr(node, "label", None)
        if label:
            out.append(_inline_text(label))
    return "".join(out)


def validate(document: Document) -> ValidationReport:
    report = ValidationReport()

    _check_identity(document, report)
    _check_language_and_metadata(document, report)
    _check_references(document, report)
    _check_figures(document, report)
    _check_headings(document, report)
    _check_tables(document, report)
    _check_raw_fallback(document, report)

    return report


def _check_identity(document: Document, report: ValidationReport) -> None:
    seen: dict[str, int] = {}
    for node in document.walk():
        if not node.id:
            report.error("DOC.IR.ID.MISSING", node.type, "node has no id",
                         hint="Give every node an id; references and anchors key on it.")
            continue
        if not ID_PATTERN.match(node.id):
            report.error(
                "DOC.IR.ID.INVALID",
                node.id,
                f"id '{node.id}' is not a valid reference token",
                hint="Use letters, digits, dot, dash or underscore, starting with a letter or digit.",
            )
        seen[node.id] = seen.get(node.id, 0) + 1

    for node_id, count in sorted(seen.items()):
        if count > 1:
            report.error(
                "DOC.IR.ID.DUPLICATE",
                node_id,
                f"id '{node_id}' is used by {count} nodes",
                hint="Ids must be unique: a duplicate makes a cross-reference ambiguous.",
            )

    # A renderer must never rename a node, so the document id may not collide
    # with a node id either.
    if document.id in seen:
        report.warning("DOC.IR.ID.COLLISION", document.id,
                       "document id is also used by a node")


def _check_language_and_metadata(document: Document, report: ValidationReport) -> None:
    if not document.lang or len(document.lang) < 2:
        report.error("DOC.IR.LANG.MISSING", document.id,
                     "document language is required",
                     hint="Set lang to a BCP 47 tag; it drives hyphenation and font fallback.")
    if not document.metadata.title:
        report.error("DOC.IR.TITLE.MISSING", document.id, "document title is required")
    if not document.blocks:
        report.error("DOC.IR.CONTENT.EMPTY", document.id, "document has no blocks")

    # Empty text nodes are almost always a transform that dropped content.
    for node in document.walk():
        payload = node.payload
        content = payload.get("content")
        if isinstance(content, tuple) and content:
            text = _inline_text(content)
            if not text.strip():
                report.warning("DOC.IR.TEXT.EMPTY", node.id,
                               f"{node.type} has content but no readable text")


def _check_references(document: Document, report: ValidationReport) -> None:
    ids = set(document.node_ids())
    bibliography = {entry.id for entry in document.bibliography}

    for node in document.walk():
        for inline in _iter_inlines(node.payload):
            node_type = getattr(inline, "type", "")
            if node_type in REFERENCE_TARGETS:
                target = getattr(inline, REFERENCE_TARGETS[node_type], None)
                if not target:
                    report.error("DOC.IR.REF.EMPTY", node.id,
                                 f"{node_type} has no target")
                elif target not in ids:
                    report.error(
                        "DOC.IR.REF.BROKEN",
                        node.id,
                        f"{node_type} points at '{target}', which does not exist",
                        hint="Add the target node or fix the id; a broken pointer reaches the reader.",
                    )
            elif node_type == "citation":
                for citation_key in getattr(inline, "keys", ()):
                    if bibliography and citation_key not in bibliography:
                        report.error(
                            "DOC.IR.CITE.UNKNOWN",
                            node.id,
                            f"citation '{citation_key}' is not in the bibliography",
                        )

    # Footnote definitions must be reachable from the text, or they are dead
    # content that still occupies a page.
    referenced = set()
    for node in document.walk():
        for inline in _iter_inlines(node.payload):
            if getattr(inline, "type", "") == "footnote_ref":
                referenced.add(getattr(inline, "target", ""))
    defined = {
        node.id for node in document.walk() if node.type == "footnote_definition"
    }
    for node_id in sorted(defined - referenced):
        report.warning("DOC.IR.FOOTNOTE.ORPHAN", node_id,
                       "footnote definition is never referenced")
    for node_id in sorted(referenced - defined):
        report.error("DOC.IR.FOOTNOTE.MISSING", node_id,
                     "footnote reference has no definition",
                     hint="Every call needs a matching definition.")


def _check_figures(document: Document, report: ValidationReport) -> None:
    for node in document.walk():
        if node.type not in {"figure", "diagram"}:
            continue
        alt = str(node.payload.get("alt", "")).strip()
        decorative = bool(node.payload.get("decorative", False))
        # Alt text is a correctness requirement, not a style preference: a
        # reader using a screen reader gets nothing without it.
        if not alt and not decorative:
            report.error(
                "DOC.A11Y.MISSING_ALT",
                node.id,
                f"{node.type} has no alt text and is not marked decorative",
                hint="Describe the figure, or set decorative when it carries no information.",
            )
        asset = node.payload.get("asset") or node.payload.get("drawing")
        uri = asset.get("uri") if isinstance(asset, dict) else getattr(asset, "uri", None)
        if not uri:
            report.error("DOC.IR.ASSET.MISSING", node.id,
                         f"{node.type} has no asset uri")


def _check_headings(document: Document, report: ValidationReport) -> None:
    """Heading levels must not skip, or the outline lies to the reader."""
    previous = 0
    first_heading_seen = False
    for node in document.walk():
        if node.type != "heading":
            continue
        level = node.payload.get("level")
        if not isinstance(level, int) or not 1 <= level <= 6:
            report.error("DOC.IR.HEADING.LEVEL", node.id,
                         f"heading level {level!r} is outside 1-6")
            continue
        if not first_heading_seen:
            first_heading_seen = True
            previous = level
            continue
        if level > previous + 1:
            report.error(
                "DOC.A11Y.HEADING_SKIP",
                node.id,
                f"heading jumps from level {previous} to {level}",
                hint="A skipped level breaks the document outline for assistive technology.",
            )
        previous = level


def _check_tables(document: Document, report: ValidationReport) -> None:
    for node in document.walk():
        if node.type != "table":
            continue
        columns = node.payload.get("columns") or ()
        rows = node.payload.get("rows") or ()
        if not columns:
            report.error("DOC.IR.TABLE.NO_COLUMNS", node.id, "table has no columns")
            continue
        for row in rows:
            cells = getattr(row, "cells", ())
            if len(cells) != len(columns):
                row_id = getattr(row, "id", "?")
                report.error(
                    "DOC.IR.TABLE.RAGGED",
                    node.id,
                    f"row '{row_id}' has {len(cells)} cells for {len(columns)} columns",
                    hint="Ragged rows make the table unreadable to a screen reader.",
                )


def _check_raw_fallback(document: Document, report: ValidationReport) -> None:
    """Raw fallback is an escape hatch, and its growth means the IR is too
    narrow. Counted rather than banned, so the pressure is visible."""
    nodes = list(document.walk())
    fallbacks = [n for n in nodes if n.type == "raw_fallback"]
    for node in fallbacks:
        if not str(node.payload.get("reason", "")).strip():
            report.error("DOC.IR.RAWFALLBACK.REASON", node.id,
                         "raw_fallback must state why it could not be expressed")
    if nodes and len(fallbacks) / len(nodes) > 0.10:
        report.warning(
            "DOC.IR.RAWFALLBACK.EXCESSIVE",
            document.id,
            f"{len(fallbacks)} of {len(nodes)} nodes are raw fallback",
            hint="A high share means the IR cannot express this content; widen the schema.",
        )


def _iter_inlines(value: Any) -> Iterable[Any]:
    """Walk any nested structure looking for inline nodes."""
    if isinstance(value, (tuple, list)):
        for item in value:
            yield from _iter_inlines(item)
        return
    if isinstance(value, dict):
        for item in value.values():
            yield from _iter_inlines(item)
        return
    if hasattr(value, "to_json") and not isinstance(value, Block):
        yield value
        return
    # Text is legitimate inline content that carries no nested nodes.
    if isinstance(value, Text):
        yield value
