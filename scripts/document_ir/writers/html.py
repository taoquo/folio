"""Write the IR as HTML that the existing template CSS already styles.

This is a compatibility writer, not a new renderer. Its whole job is to emit the
class names the templates use today, so that swapping the content model does
not change a single visible pixel. A new visual treatment is a separate
decision, made later and on purpose.

The writer never invents an id and never renames one. `data-folio-id` carries
the IR id through to the artifact so a quality finding can be traced back to a
node, which is what makes anchor comparison and paragraph metrics possible.
"""

from __future__ import annotations

from collections.abc import Iterable
from html import escape
from typing import Any

from ..model import (
    Block,
    Citation,
    CodeInline,
    CrossRef,
    Document,
    Emphasis,
    FootnoteRef,
    LineBreak,
    Link,
    MathInline,
    Strong,
    Text,
)

# Style hooks the templates define. Kept in one place so a mismatch between
# writer and template is visible rather than scattered.
CLASSES = {
    "page": "page",
    "cover": "cover",
    "toc": "toc",
    "chapter": "chapter",
    "lead": "lead",
    "highlight": "hl",
    "callout": "callout",
    "sidenote": "sidenote",
    "takeaway": "takeaway",
    "tag": "tag",
    "sans": "sans",
}

# Block id prefix -> the template class that draws it. The ids come from the
# bridge's role table, so this is where a semantic slot acquires an appearance.
#
# Only names the templates actually style appear here. Inventing a class would
# produce markup that looks correct and renders unstyled, which is the failure
# this mapping exists to prevent.
BLOCK_CLASSES: dict[str, str] = {
    "p-eyebrow": "eyebrow",
    "h-title": "title-block",
    "p-subtitle": "subtitle",
    "p-lede": "lead",
    "p-metric": "metric",
    "c-metric": "metrics",
    "p-decision-label": "decision-label",
    "p-stage": "tl-year",
    "c-timeline": "timeline",
    "p-owner": "decision-owner",
    "c-footer": "footer",
    "p-callout": "callout",
    "c-callout": "callout",
}

# Container wrappers the templates expect around a run of related blocks. A
# template that lays out metrics in a grid needs the grid element, and a writer
# that emits the metric blocks alone cannot reproduce it.
SECTION_WRAPPERS: dict[str, tuple[str, str]] = {
    "metrics": ("metrics", "metric"),
    "timeline": ("timeline", "tl-year"),
}


def class_for_block(block_id: str) -> str:
    """The template class for a block, or empty when it has none.

    Matched on the longest prefix so `p-metric-2` finds `p-metric`.
    """
    if block_id in BLOCK_CLASSES:
        return BLOCK_CLASSES[block_id]
    best = ""
    for prefix in BLOCK_CLASSES:
        if block_id.startswith(prefix) and len(prefix) > len(best):
            best = prefix
    return BLOCK_CLASSES.get(best, "") if best else ""


class UnsupportedNode(Exception):
    """Raised for a node the compatibility writer cannot express.

    Failing loudly is deliberate: silently dropping content would make the
    migration look successful while losing the reader's material.
    """


def _attr(value: str) -> str:
    return escape(value, quote=True)


def inline_html(node: Any) -> str:
    """Render one inline node."""
    if isinstance(node, Text):
        text = escape(node.value)
        classes = CLASSES["highlight"] if node.highlight else ""
        if classes:
            return f'<span class="{classes}">{text}</span>'
        if node.lang:
            return f'<span lang="{_attr(node.lang)}">{text}</span>'
        return text
    if isinstance(node, Emphasis):
        return f"<em>{inlines_html(node.content)}</em>"
    if isinstance(node, Strong):
        return f"<strong>{inlines_html(node.content)}</strong>"
    if isinstance(node, CodeInline):
        return f"<code>{escape(node.value)}</code>"
    if isinstance(node, Link):
        label = inlines_html(node.label) if node.label else escape(node.target)
        title = f' title="{_attr(node.title)}"' if node.title else ""
        return f'<a href="{_attr(node.target)}"{title}>{label}</a>'
    if isinstance(node, Citation):
        keys = " ".join(escape(k) for k in node.keys)
        return f'<span class="citation" data-keys="{_attr(keys)}">[{escape(node.keys[0]) if node.keys else ""}]</span>'
    if isinstance(node, CrossRef):
        return (
            f'<a class="cross-ref" href="#{_attr(node.target)}" '
            f'data-folio-ref="{_attr(node.target)}">{escape(node.target)}</a>'
        )
    if isinstance(node, FootnoteRef):
        return (
            f'<a class="footnote-ref" href="#{_attr(node.target)}" '
            f'data-folio-ref="{_attr(node.target)}">*</a>'
        )
    if isinstance(node, MathInline):
        described = f' title="{_attr(node.description)}"' if node.description else ""
        return f'<span class="math-inline"{described}>{escape(node.value)}</span>'
    if isinstance(node, LineBreak):
        return "<br>"
    if isinstance(node, str):
        return escape(node)
    raise UnsupportedNode(f"inline node {type(node).__name__} has no HTML form")


def inlines_html(nodes: Iterable[Any]) -> str:
    return "".join(inline_html(node) for node in nodes)


def _id_attrs(node: Block) -> str:
    parts = [f'data-folio-id="{_attr(node.id)}"']
    if node.intent.keep_with_next:
        parts.append('data-folio-keep-with-next="true"')
    if node.intent.keep_together:
        parts.append('data-folio-keep-together="true"')
    if node.intent.break_before != "auto":
        parts.append(f'data-folio-break-before="{_attr(node.intent.break_before)}"')
    return " ".join(parts)


def block_html(node: Block) -> str:
    """Render one block.

    Every element the templates style is reused verbatim; only the content
    model changes.
    """
    attrs = _id_attrs(node)
    payload = node.payload

    if node.type == "section":
        role = payload.get("role") or "body"
        parts = [f'<section class="{CLASSES["chapter"]} {role}" {attrs}>']
        if payload.get("title"):
            parts.append(f'<h2>{inlines_html(payload["title"])}</h2>')
        parts.extend(block_html(child) for child in node.children)
        parts.append("</section>")
        return "".join(parts)

    if node.type == "heading":
        level = payload.get("level", 1)
        level = min(max(int(level), 1), 6)
        # A template may style a heading by class rather than by its level, so
        # the class travels with the block.
        css = class_for_block(node.id)
        cls = f' class="{css}"' if css else ""
        return f'<h{level}{cls} {attrs}>{inlines_html(payload.get("content", ()))}</h{level}>'

    if node.type == "paragraph":
        role = payload.get("role", "body")
        css = class_for_block(node.id)
        if not css and role == "lead":
            css = CLASSES["lead"]
        cls = f' class="{css}"' if css else ""
        return f'<p{cls} {attrs}>{inlines_html(payload.get("content", ()))}</p>'

    if node.type == "list":
        tag = "ol" if payload.get("ordered") else "ul"
        items = []
        for item in payload.get("items", ()):
            detail = ""
            if getattr(item, "detail", ()):
                detail = f'<span class="detail">{inlines_html(item.detail)}</span>'
            items.append(
                f'<li data-folio-id="{_attr(item.id)}">{inlines_html(item.content)}{detail}</li>'
            )
        return f"<{tag} {attrs}>{''.join(items)}</{tag}>"

    if node.type == "definition_list":
        entries = []
        for entry in payload.get("entries", ()):
            entries.append(
                f'<dt data-folio-id="{_attr(entry.id)}">{inlines_html(entry.term)}</dt>'
                f"<dd>{inlines_html(entry.definition)}</dd>"
            )
        return f'<dl {attrs}>{"".join(entries)}</dl>'

    if node.type == "quote":
        attribution = ""
        if payload.get("attribution"):
            attribution = f'<footer>{inlines_html(payload["attribution"])}</footer>'
        return f'<blockquote {attrs}>{inlines_html(payload.get("content", ()))}{attribution}</blockquote>'

    if node.type == "callout":
        kind = payload.get("kind") or "note"
        title = ""
        if payload.get("title"):
            title = f'<div class="callout-title">{inlines_html(payload["title"])}</div>'
        return (
            f'<div class="{CLASSES["callout"]} {escape(str(kind))}" {attrs}>'
            f'{title}<div class="callout-body">{inlines_html(payload.get("content", ()))}</div></div>'
        )

    if node.type == "code_block":
        language = f' data-language="{_attr(str(payload["language"]))}"' if payload.get("language") else ""
        return f'<pre {attrs}{language}><code>{escape(str(payload.get("value", "")))}</code></pre>'

    if node.type == "math_block":
        described = f' data-description="{_attr(str(payload["description"]))}"' if payload.get("description") else ""
        return f'<div class="math-block" {attrs}{described}>{escape(str(payload.get("value", "")))}</div>'

    if node.type == "table":
        columns = payload.get("columns", ())
        header = "".join(
            f'<th data-folio-id="{_attr(col.id)}" scope="col">{inlines_html(col.label)}</th>'
            for col in columns
        )
        body_rows = []
        for row in payload.get("rows", ()):
            cells = "".join(
                f"<td>{inlines_html(cell)}</td>" for cell in getattr(row, "cells", ())
            )
            body_rows.append(f'<tr data-folio-id="{_attr(row.id)}">{cells}</tr>')
        caption = ""
        if payload.get("caption"):
            caption = f"<caption>{inlines_html(payload['caption'])}</caption>"
        return (
            f'<table {attrs}>{caption}<thead><tr>{header}</tr></thead>'
            f'<tbody>{"".join(body_rows)}</tbody></table>'
        )

    if node.type in {"figure", "diagram"}:
        asset = payload.get("asset") or payload.get("drawing")
        uri = getattr(asset, "uri", "")
        alt = escape(str(payload.get("alt", "")), quote=True)
        decimal = "" if payload.get("decorative") else ' data-folio-informative="true"'
        caption = ""
        if payload.get("caption"):
            caption = f'<figcaption>{inlines_html(payload["caption"])}</figcaption>'
        placement = payload.get("placement")
        mode = f' data-folio-placement="{_attr(placement.mode)}"' if placement else ""
        return (
            f'<figure {attrs}{decimal}{mode}><img src="{_attr(uri)}" alt="{alt}">'
            f"{caption}</figure>"
        )

    if node.type == "footnote_definition":
        body = "".join(block_html(child) for child in node.children)
        return f'<div class="{CLASSES["sidenote"]}" {attrs}>{body}</div>'

    if node.type == "thematic_break":
        return f"<hr {attrs}>"

    if node.type == "page_break":
        strength = payload.get("strength", "optional")
        return f'<div class="page-break" data-strength="{_attr(str(strength))}" {attrs}></div>'

    if node.type == "raw_fallback":
        # Passed through unchanged, but marked so the share of fallback content
        # stays measurable in the artifact.
        return f'<div class="raw-fallback" {attrs}>{payload.get("value", "")}</div>'

    raise UnsupportedNode(f"block type '{node.type}' has no HTML form")


def document_body_html(document: Document, *, wrap_containers: bool = True) -> str:
    """The document's blocks as HTML, without a surrounding shell.

    When `wrap_containers` is set, blocks are grouped into the wrappers the
    template lays out with. The grouping is derived from block ids, which come
    from the bridge's role table, so a block acquires its container by the slot
    it fills rather than by a writer-side guess.
    """
    blocks = list(document.blocks)

    if not wrap_containers:
        return "\n".join(block_html(node) for node in blocks)

    from document_ir.containers import build_tree

    by_id = {node.id: node for node in blocks}
    tree = build_tree([node.id for node in blocks])

    # A tree that places nothing is not worth emitting; fall back to the flat
    # form so a document whose ids are unknown still renders.
    if not any(entry["kind"] == "container" for entry in tree):
        return "\n".join(block_html(node) for node in blocks)

    def render_nodes(nodes: list[dict]) -> str:
        parts: list[str] = []
        for entry in nodes:
            if entry["kind"] == "block":
                node = by_id.get(entry["id"])
                if node is not None:
                    parts.append(block_html(node))
                continue

            inner = render_nodes(entry["children"])
            if not inner.strip():
                continue
            element = entry["element"]
            css = entry["css"]
            parts.append(f'<{element} class="{css}">\n{inner}\n</{element}>')
        return "\n".join(parts)

    return render_nodes(tree)


def write_html(document: Document, *, title: str | None = None) -> str:
    """A complete HTML document.

    The shell is intentionally minimal: the templates supply the styling, and
    this writer must not compete with them. `lang` comes from the IR because
    the document declares its language semantically.
    """
    heading = escape(title or document.metadata.title or document.id)
    return (
        "<!DOCTYPE html>\n"
        f'<html lang="{_attr(document.lang)}" dir="{_attr(document.direction)}">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        f"<title>{heading}</title>\n"
        "</head>\n"
        f'<body data-folio-document="{_attr(document.id)}" '
        f'data-folio-schema="{_attr(document.schema_version)}">\n'
        f"{document_body_html(document)}\n"
        "</body>\n"
        "</html>\n"
    )
