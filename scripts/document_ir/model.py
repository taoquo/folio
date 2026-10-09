"""Document IR: what a document is, never how it is drawn.

Two rules govern this module.

1. No node carries geometry or style. There is no font size, colour, margin or
   coordinate anywhere below. Those belong to a profile or to a renderer, and
   the boundary is copied from the Drawing DSL, whose semantic layer is
   likewise free of geometry.

2. Every node is immutable and frozen. A transform produces a new document
   rather than mutating one in place, so a pipeline stage cannot quietly
   rewrite an earlier stage's output.

A node's `id` is stable and a renderer must never rename it: cross-references,
anchor diffs, reading order and incremental builds all key on it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Literal

SCHEMA_VERSION = "1.0"


# --------------------------------------------------------------------------
# Source provenance
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SourceRef:
    """Where a node came from.

    Carried so a quality finding can point at an input line instead of at a
    PDF coordinate the author never wrote.
    """

    source_id: str
    locator: str | None = None
    line: int | None = None
    column: int | None = None
    digest: str | None = None

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"source_id": self.source_id}
        for key in ("locator", "line", "column", "digest"):
            value = getattr(self, key)
            if value is not None:
                out[key] = value
        return out


@dataclass(frozen=True, slots=True)
class LayoutIntent:
    """What the author wants to happen, never how to achieve it."""

    keep_with_next: bool = False
    keep_together: bool = False
    break_before: Literal["auto", "page", "column"] = "auto"
    importance: Literal["low", "normal", "high"] = "normal"

    def is_empty(self) -> bool:
        return (
            not self.keep_with_next
            and not self.keep_together
            and self.break_before == "auto"
            and self.importance == "normal"
        )

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.keep_with_next:
            out["keep_with_next"] = True
        if self.keep_together:
            out["keep_together"] = True
        if self.break_before != "auto":
            out["break_before"] = self.break_before
        if self.importance != "normal":
            out["importance"] = self.importance
        return out


# --------------------------------------------------------------------------
# Inline nodes
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Text:
    value: str
    lang: str | None = None
    # The author marked this run as a key claim. How it is emphasised is a
    # theme decision; the IR only records the claim.
    highlight: bool = False

    type: Literal["text"] = "text"

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"type": "text", "value": self.value}
        if self.lang:
            out["lang"] = self.lang
        if self.highlight:
            out["highlight"] = True
        return out


@dataclass(frozen=True, slots=True)
class Emphasis:
    content: tuple[Inline, ...]
    type: Literal["emphasis"] = "emphasis"

    def to_json(self) -> dict[str, Any]:
        return {"type": "emphasis", "content": [i.to_json() for i in self.content]}


@dataclass(frozen=True, slots=True)
class Strong:
    content: tuple[Inline, ...]
    type: Literal["strong"] = "strong"

    def to_json(self) -> dict[str, Any]:
        return {"type": "strong", "content": [i.to_json() for i in self.content]}


@dataclass(frozen=True, slots=True)
class CodeInline:
    value: str
    type: Literal["code"] = "code"

    def to_json(self) -> dict[str, Any]:
        return {"type": "code", "value": self.value}


@dataclass(frozen=True, slots=True)
class Link:
    target: str
    label: tuple[Inline, ...] = ()
    title: str | None = None
    type: Literal["link"] = "link"

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"type": "link", "target": self.target}
        if self.label:
            out["label"] = [i.to_json() for i in self.label]
        if self.title:
            out["title"] = self.title
        return out


@dataclass(frozen=True, slots=True)
class Citation:
    keys: tuple[str, ...]
    type: Literal["citation"] = "citation"

    def to_json(self) -> dict[str, Any]:
        return {"type": "citation", "keys": list(self.keys)}


@dataclass(frozen=True, slots=True)
class CrossRef:
    target: str
    format: Literal["label", "number", "label-and-number"] = "label-and-number"
    type: Literal["cross_ref"] = "cross_ref"

    def to_json(self) -> dict[str, Any]:
        return {"type": "cross_ref", "target": self.target, "format": self.format}


@dataclass(frozen=True, slots=True)
class FootnoteRef:
    target: str
    type: Literal["footnote_ref"] = "footnote_ref"

    def to_json(self) -> dict[str, Any]:
        return {"type": "footnote_ref", "target": self.target}


@dataclass(frozen=True, slots=True)
class MathInline:
    value: str
    description: str | None = None
    type: Literal["math_inline"] = "math_inline"

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"type": "math_inline", "value": self.value}
        if self.description:
            out["description"] = self.description
        return out


@dataclass(frozen=True, slots=True)
class LineBreak:
    type: Literal["line_break"] = "line_break"

    def to_json(self) -> dict[str, Any]:
        return {"type": "line_break"}


Inline = (
    Text | Emphasis | Strong | CodeInline | Link | Citation | CrossRef | FootnoteRef
    | MathInline | LineBreak
)


# --------------------------------------------------------------------------
# Block nodes
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AssetRef:
    uri: str
    sha256: str | None = None
    media_type: str | None = None

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"uri": self.uri}
        if self.sha256:
            out["sha256"] = self.sha256
        if self.media_type:
            out["media_type"] = self.media_type
        return out


@dataclass(frozen=True, slots=True)
class Placement:
    """A preference a renderer may not be able to honour.

    A renderer that cannot must record a downgrade; it must not place the item
    somewhere else and say nothing.
    """

    mode: Literal["inline", "float", "full-width"] = "inline"
    preferred: tuple[str, ...] = ()
    max_defer_pages: int | None = None

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"mode": self.mode}
        if self.preferred:
            out["preferred"] = list(self.preferred)
        if self.max_defer_pages is not None:
            out["max_defer_pages"] = self.max_defer_pages
        return out


@dataclass(frozen=True, slots=True)
class ListItem:
    id: str
    content: tuple[Inline, ...]
    detail: tuple[Inline, ...] = ()

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"id": self.id, "content": [i.to_json() for i in self.content]}
        if self.detail:
            out["detail"] = [i.to_json() for i in self.detail]
        return out


@dataclass(frozen=True, slots=True)
class DefinitionEntry:
    id: str
    term: tuple[Inline, ...]
    definition: tuple[Inline, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "term": [i.to_json() for i in self.term],
            "definition": [i.to_json() for i in self.definition],
        }


@dataclass(frozen=True, slots=True)
class TableColumn:
    id: str
    label: tuple[Inline, ...]
    # Numeric kinds let a profile pick tabular figures without the IR naming a
    # font or a width.
    kind: Literal["text", "number", "date", "currency", "percent"] = "text"
    unit: str | None = None

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"id": self.id, "label": [i.to_json() for i in self.label]}
        if self.kind != "text":
            out["kind"] = self.kind
        if self.unit:
            out["unit"] = self.unit
        return out


@dataclass(frozen=True, slots=True)
class TableRow:
    id: str
    cells: tuple[tuple[Inline, ...], ...]

    def to_json(self) -> dict[str, Any]:
        return {"id": self.id, "cells": [[i.to_json() for i in cell] for cell in self.cells]}


@dataclass(frozen=True, slots=True)
class Block:
    """Base for every block node.

    Held as a plain dataclass rather than a union of separate ones so shared
    traversal can walk `id`, `source` and `intent` uniformly. Concrete types
    narrow the payload.
    """

    id: str
    type: str
    source: SourceRef | None = None
    intent: LayoutIntent = LayoutIntent()
    children: tuple[Block, ...] = ()
    payload: Mapping[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"type": self.type, "id": self.id}
        if self.source is not None:
            out["source"] = self.source.to_json()
        if not self.intent.is_empty():
            out["intent"] = self.intent.to_json()
        for key, value in self.payload.items():
            out[key] = _encode(value)
        if self.children:
            out["blocks"] = [child.to_json() for child in self.children]
        return out

    def walk(self) -> Iterable[Block]:
        yield self
        for child in self.children:
            yield from child.walk()


def _encode(value: Any) -> Any:
    """Serialise a payload value that may hold inline or nested nodes."""
    if isinstance(value, tuple):
        return [_encode(item) for item in value]
    if isinstance(value, list):
        return [_encode(item) for item in value]
    if isinstance(value, dict):
        return {key: _encode(item) for key, item in value.items()}
    if hasattr(value, "to_json"):
        return value.to_json()
    return value


def block(
    block_type: str,
    id: str,
    *,
    source: SourceRef | None = None,
    intent: LayoutIntent | None = None,
    children: Sequence[Block] = (),
    **payload: Any,
) -> Block:
    """Build a block. Validating the payload against the schema is a separate,
    explicit step so construction stays cheap inside a transform."""
    return Block(
        id=id,
        type=block_type,
        source=source,
        intent=intent if intent is not None else LayoutIntent(),
        children=tuple(children),
        payload=dict(payload),
    )


# --------------------------------------------------------------------------
# Document
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Metadata:
    title: str
    subtitle: str | None = None
    author: str | None = None
    publisher: str | None = None
    date: str | None = None
    genre: str | None = None
    keywords: tuple[str, ...] = ()
    confidentiality: str | None = None
    abstract: str | None = None

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"title": self.title}
        for key in ("subtitle", "author", "publisher", "date", "genre", "confidentiality", "abstract"):
            value = getattr(self, key)
            if value:
                out[key] = value
        if self.keywords:
            out["keywords"] = list(self.keywords)
        return out


@dataclass(frozen=True, slots=True)
class ProfileRefs:
    """Names of the profiles that decide presentation.

    The document names them; it never contains their values. This is what keeps
    a theme change from being a content change, and vice versa.
    """

    typography: str | None = None
    page: str | None = None
    language: str | None = None
    theme: str | None = None
    taste: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            key: value
            for key in ("typography", "page", "language", "theme", "taste")
            if (value := getattr(self, key))
        }


@dataclass(frozen=True, slots=True)
class BibliographyEntry:
    id: str
    type: str | None = None
    title: str | None = None
    author: tuple[str, ...] = ()
    year: str | None = None
    url: str | None = None
    publisher: str | None = None
    note: str | None = None

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"id": self.id}
        for key in ("type", "title", "year", "url", "publisher", "note"):
            value = getattr(self, key)
            if value:
                out[key] = value
        if self.author:
            out["author"] = list(self.author)
        return out


@dataclass(frozen=True, slots=True)
class Document:
    id: str
    lang: str
    metadata: Metadata
    blocks: tuple[Block, ...]
    direction: Literal["ltr", "rtl"] = "ltr"
    profiles: ProfileRefs = ProfileRefs()
    bibliography: tuple[BibliographyEntry, ...] = ()
    schema_version: str = SCHEMA_VERSION

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "schema_version": self.schema_version,
            "id": self.id,
            "lang": self.lang,
        }
        if self.direction != "ltr":
            out["direction"] = self.direction
        out["metadata"] = self.metadata.to_json()
        profiles = self.profiles.to_json()
        if profiles:
            out["profiles"] = profiles
        out["blocks"] = [b.to_json() for b in self.blocks]
        if self.bibliography:
            out["bibliography"] = [e.to_json() for e in self.bibliography]
        return out

    def walk(self) -> Iterable[Block]:
        for top in self.blocks:
            yield from top.walk()

    def node_ids(self) -> list[str]:
        return [node.id for node in self.walk()]

    def find(self, node_id: str) -> Block | None:
        for node in self.walk():
            if node.id == node_id:
                return node
        return None

    def with_blocks(self, blocks: Sequence[Block]) -> Document:
        """A new document with different blocks. The original is untouched."""
        return replace(self, blocks=tuple(blocks))
