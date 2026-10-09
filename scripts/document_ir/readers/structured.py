"""Read a serialised document into the IR.

A reader never guesses. Content it cannot express becomes a `raw_fallback`
node that states why, so the pressure on the schema is visible instead of the
content silently disappearing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..model import (
    SCHEMA_VERSION,
    AssetRef,
    BibliographyEntry,
    Block,
    Citation,
    CodeInline,
    CrossRef,
    DefinitionEntry,
    Document,
    Emphasis,
    FootnoteRef,
    LayoutIntent,
    LineBreak,
    Link,
    ListItem,
    MathInline,
    Metadata,
    Placement,
    ProfileRefs,
    SourceRef,
    Strong,
    TableColumn,
    TableRow,
    Text,
    block,
)


class DocumentReadError(ValueError):
    """Raised when input cannot be read at all.

    Structural problems inside an otherwise readable document are reported by
    the validator instead, so a caller can see every issue at once rather than
    fixing them one exception at a time.
    """

    def __init__(self, message: str, *, source: str | None = None) -> None:
        super().__init__(f"{source}: {message}" if source else message)
        self.source = source


def _parse_yaml(text: str) -> dict:
    """Minimal YAML reader for the document subset.

    Supports nested mappings, `- ` lists, inline flow mappings and block
    scalars. PyYAML is not a build dependency, and a construct outside the
    subset raises rather than being skipped.
    """
    lines = text.splitlines()
    root: dict = {}
    stack: list[tuple[int, Any]] = [(-1, root)]
    index = 0

    def scalar(value: str):
        value = value.strip()
        if value.startswith("{") and value.endswith("}"):
            inner = value[1:-1].strip()
            out: dict[str, Any] = {}
            if not inner:
                return out
            depth, current, parts = 0, "", []
            for char in inner:
                if char in "[{":
                    depth += 1
                elif char in "]}":
                    depth -= 1
                if char == "," and depth == 0:
                    parts.append(current)
                    current = ""
                else:
                    current += char
            parts.append(current)
            for part in parts:
                if ":" in part:
                    key, item = part.split(":", 1)
                    out[key.strip()] = scalar(item)
            return out
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            return [scalar(v) for v in inner.split(",")] if inner else []
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            return value[1:-1].replace('\\"', '"').replace("\\n", "\n")
        if value in {"true", "false"}:
            return value == "true"
        if value in {"null", "~"}:
            return None
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            pass
        return value

    while index < len(lines):
        raw = lines[index]
        index += 1
        if raw.lstrip().startswith("#"):
            continue
        stripped = raw.rstrip()
        if not stripped.strip():
            continue
        indent = len(stripped) - len(stripped.lstrip())
        content = stripped.strip()

        while stack and indent <= stack[-1][0]:
            stack.pop()
        container = stack[-1][1]

        if content.startswith("- "):
            item = content[2:].strip()
            if not isinstance(container, list):
                continue
            if ":" in item and not item.startswith(("{", "[")):
                key, value = item.split(":", 1)
                entry = {key.strip(): scalar(value)}
                container.append(entry)
                stack.append((indent, entry))
            else:
                container.append(scalar(item))
            continue

        if ":" not in content:
            continue

        split_at, quote_char = -1, ""
        for position, char in enumerate(content):
            if quote_char:
                if char == quote_char:
                    quote_char = ""
                continue
            if char in "\"'":
                quote_char = char
            elif char == ":":
                split_at = position
                break
        if split_at < 0:
            continue
        key, value = content[:split_at].strip(), content[split_at + 1:].strip()
        if len(key) >= 2 and key[0] == key[-1] and key[0] in "\"'":
            key = key[1:-1]

        if value in {"|", "|-", ">", ">-"}:
            block_lines: list[str] = []
            while index < len(lines):
                nxt = lines[index]
                if not nxt.strip():
                    block_lines.append("")
                    index += 1
                    continue
                nxt_indent = len(nxt) - len(nxt.lstrip())
                if nxt_indent <= indent:
                    break
                block_lines.append(nxt.strip() if value.startswith(">") else nxt[nxt_indent:])
                index += 1
            while block_lines and not block_lines[-1]:
                block_lines.pop()
            joined = " ".join(line for line in block_lines if line) if value.startswith(">") else "\n".join(block_lines)
            if isinstance(container, dict):
                container[key] = joined.strip()
            continue

        if value == "":
            lookahead = None
            for nxt in lines[index:]:
                if not nxt.strip() or nxt.lstrip().startswith("#"):
                    continue
                if len(nxt) - len(nxt.lstrip()) > indent:
                    lookahead = nxt.strip()
                break
            new: Any = [] if (lookahead or "").startswith("- ") else {}
            if isinstance(container, dict):
                container[key] = new
            stack.append((indent, new))
        else:
            if isinstance(container, dict):
                container[key] = scalar(value)
    return root


def _inline(data: Any, *, source_id: str) -> Any:
    """Build one inline node. Unknown types become readable text rather than
    vanishing, so a schema gap shows up as content rather than as silence."""
    if isinstance(data, str):
        return Text(value=data)
    if not isinstance(data, dict):
        return Text(value=str(data))

    kind = data.get("type")
    if kind == "text":
        return Text(
            value=str(data.get("value", "")),
            lang=data.get("lang"),
            highlight=bool(data.get("highlight", False)),
        )
    if kind in {"emphasis", "strong"}:
        content = tuple(_inline(item, source_id=source_id) for item in data.get("content", []))
        return Emphasis(content=content) if kind == "emphasis" else Strong(content=content)
    if kind == "code":
        return CodeInline(value=str(data.get("value", "")))
    if kind == "link":
        label = tuple(_inline(i, source_id=source_id) for i in data.get("label", []))
        return Link(target=str(data.get("target", "")), label=label, title=data.get("title"))
    if kind == "citation":
        return Citation(keys=tuple(str(k) for k in data.get("keys", [])))
    if kind == "cross_ref":
        return CrossRef(target=str(data.get("target", "")),
                        format=str(data.get("format", "label-and-number")))
    if kind == "footnote_ref":
        return FootnoteRef(target=str(data.get("target", "")))
    if kind == "math_inline":
        return MathInline(value=str(data.get("value", "")), description=data.get("description"))
    if kind == "line_break":
        return LineBreak()
    return Text(value=str(data.get("value", "")))


def _inlines(data: Any, *, source_id: str) -> tuple[Any, ...]:
    if data is None:
        return ()
    if isinstance(data, (str, dict)):
        return (_inline(data, source_id=source_id),)
    return tuple(_inline(item, source_id=source_id) for item in data)


def _source(data: Any) -> SourceRef | None:
    if not isinstance(data, dict):
        return None
    return SourceRef(
        source_id=str(data.get("source_id", "")),
        locator=data.get("locator"),
        line=data.get("line"),
        column=data.get("column"),
        digest=data.get("digest"),
    )


def _intent(data: Any) -> LayoutIntent:
    if not isinstance(data, dict):
        return LayoutIntent()
    return LayoutIntent(
        keep_with_next=bool(data.get("keep_with_next", False)),
        keep_together=bool(data.get("keep_together", False)),
        break_before=str(data.get("break_before", "auto")),
        importance=str(data.get("importance", "normal")),
    )


def _placement(data: Any) -> Placement | None:
    if not isinstance(data, dict):
        return None
    return Placement(
        mode=str(data.get("mode", "inline")),
        preferred=tuple(str(p) for p in data.get("preferred", [])),
        max_defer_pages=data.get("max_defer_pages"),
    )


def _block(data: Any, *, source_id: str, fallback_id: str) -> Block:
    if not isinstance(data, dict):
        return block(
            "raw_fallback",
            fallback_id,
            value=json.dumps(data, ensure_ascii=False),
            reason="block was not a mapping",
        )

    kind = str(data.get("type", ""))
    node_id = str(data.get("id") or fallback_id)
    common = {
        "source": _source(data.get("source")),
        "intent": _intent(data.get("intent")),
    }

    def children_of(key: str = "blocks") -> tuple[Block, ...]:
        return tuple(
            _block(item, source_id=source_id, fallback_id=f"{node_id}-{index}")
            for index, item in enumerate(data.get(key, []))
        )

    if kind == "section":
        return block("section", node_id,
                     title=_inlines(data.get("title"), source_id=source_id),
                     role=data.get("role"),
                     children=children_of(), **common)
    if kind == "heading":
        return block("heading", node_id, level=data.get("level", 1),
                     content=_inlines(data.get("content"), source_id=source_id), **common)
    if kind == "paragraph":
        return block("paragraph", node_id,
                     content=_inlines(data.get("content"), source_id=source_id),
                     role=data.get("role", "body"), **common)
    if kind == "list":
        items = tuple(
            ListItem(
                id=str(item.get("id", f"{node_id}-{index}")),
                content=_inlines(item.get("content"), source_id=source_id),
                detail=_inlines(item.get("detail"), source_id=source_id),
            )
            for index, item in enumerate(data.get("items", []))
        )
        return block("list", node_id, ordered=bool(data.get("ordered", False)),
                     items=items, **common)
    if kind == "definition_list":
        entries = tuple(
            DefinitionEntry(
                id=str(item.get("id", f"{node_id}-{index}")),
                term=_inlines(item.get("term"), source_id=source_id),
                definition=_inlines(item.get("definition"), source_id=source_id),
            )
            for index, item in enumerate(data.get("entries", []))
        )
        return block("definition_list", node_id, entries=entries, **common)
    if kind == "quote":
        return block("quote", node_id,
                     content=_inlines(data.get("content"), source_id=source_id),
                     attribution=_inlines(data.get("attribution"), source_id=source_id), **common)
    if kind == "callout":
        return block("callout", node_id, kind=data.get("kind", "note"),
                     title=_inlines(data.get("title"), source_id=source_id),
                     content=_inlines(data.get("content"), source_id=source_id), **common)
    if kind == "code_block":
        return block("code_block", node_id, language=data.get("language"),
                     value=str(data.get("value", "")),
                     caption=_inlines(data.get("caption"), source_id=source_id), **common)
    if kind == "math_block":
        return block("math_block", node_id, value=str(data.get("value", "")),
                     description=data.get("description"), label=data.get("label"), **common)
    if kind == "table":
        columns = tuple(
            TableColumn(
                id=str(col.get("id", f"{node_id}-c{index}")),
                label=_inlines(col.get("label"), source_id=source_id),
                kind=str(col.get("kind", "text")),
                unit=col.get("unit"),
            )
            for index, col in enumerate(data.get("columns", []))
        )
        rows = tuple(
            TableRow(
                id=str(row.get("id", f"{node_id}-r{index}")),
                cells=tuple(_inlines(cell, source_id=source_id) for cell in row.get("cells", [])),
            )
            for index, row in enumerate(data.get("rows", []))
        )
        return block("table", node_id,
                     caption=_inlines(data.get("caption"), source_id=source_id),
                     columns=columns, rows=rows, **common)
    if kind in {"figure", "diagram"}:
        raw_asset = data.get("asset") or data.get("drawing") or {}
        asset = AssetRef(
            uri=str(raw_asset.get("uri", "")),
            sha256=raw_asset.get("sha256"),
            media_type=raw_asset.get("media_type"),
        )
        key = "asset" if kind == "figure" else "drawing"
        return block(kind, node_id, **{key: asset},
                     alt=str(data.get("alt", "")),
                     decorative=bool(data.get("decorative", False)),
                     caption=_inlines(data.get("caption"), source_id=source_id),
                     placement=_placement(data.get("placement")), **common)
    if kind == "footnote_definition":
        return block("footnote_definition", node_id, children=children_of(), **common)
    if kind == "thematic_break":
        return block("thematic_break", node_id, **common)
    if kind == "page_break":
        return block("page_break", node_id, strength=data.get("strength", "optional"), **common)
    if kind == "raw_fallback":
        return block("raw_fallback", node_id, value=str(data.get("value", "")),
                     reason=str(data.get("reason", "")), **common)

    return block(
        "raw_fallback",
        node_id,
        value=json.dumps(data, ensure_ascii=False),
        reason=f"unknown block type '{kind}'",
        **common,
    )


def document_from_data(data: dict, *, source_id: str = "<memory>") -> Document:
    """Build a Document from parsed data. Raises only when the shape is wrong."""
    if not isinstance(data, dict):
        raise DocumentReadError("document must be a mapping", source=source_id)

    schema_version = str(data.get("schema_version", SCHEMA_VERSION))
    if not schema_version.startswith("1."):
        raise DocumentReadError(
            f"unsupported schema_version '{schema_version}'; this reader understands 1.x",
            source=source_id,
        )

    meta = data.get("metadata") or {}
    if not isinstance(meta, dict):
        raise DocumentReadError("metadata must be a mapping", source=source_id)
    metadata = Metadata(
        title=str(meta.get("title", "")),
        subtitle=meta.get("subtitle"),
        author=meta.get("author"),
        publisher=meta.get("publisher"),
        date=meta.get("date"),
        genre=meta.get("genre"),
        keywords=tuple(str(k) for k in meta.get("keywords", [])),
        confidentiality=meta.get("confidentiality"),
        abstract=meta.get("abstract"),
    )

    profiles_data = data.get("profiles") or {}
    profiles = ProfileRefs(
        typography=profiles_data.get("typography"),
        page=profiles_data.get("page"),
        language=profiles_data.get("language"),
        theme=profiles_data.get("theme"),
        taste=profiles_data.get("taste"),
    )

    blocks = tuple(
        _block(item, source_id=source_id, fallback_id=f"block-{index}")
        for index, item in enumerate(data.get("blocks", []) or [])
    )

    bibliography = tuple(
        BibliographyEntry(
            id=str(entry.get("id", "")),
            type=entry.get("type"),
            title=entry.get("title"),
            author=tuple(str(a) for a in entry.get("author", [])),
            year=entry.get("year"),
            url=entry.get("url"),
            publisher=entry.get("publisher"),
            note=entry.get("note"),
        )
        for entry in data.get("bibliography", []) or []
    )

    return Document(
        id=str(data.get("id", "")),
        lang=str(data.get("lang", "")),
        direction=str(data.get("direction", "ltr")),
        metadata=metadata,
        profiles=profiles,
        blocks=blocks,
        bibliography=bibliography,
        schema_version=SCHEMA_VERSION,
    )


def read_json(path: Path) -> Document:
    text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DocumentReadError(f"invalid JSON: {exc}", source=str(path)) from exc
    return document_from_data(data, source_id=str(path))


def read_yaml(path: Path) -> Document:
    text = path.read_text(encoding="utf-8")
    return document_from_data(_parse_yaml(text), source_id=str(path))


def read(path: Path) -> Document:
    """Read a document, choosing the reader by suffix."""
    suffix = path.suffix.lower()
    if suffix == ".json":
        return read_json(path)
    if suffix in {".yaml", ".yml"}:
        return read_yaml(path)
    raise DocumentReadError(f"unsupported input format '{suffix}'", source=str(path))
