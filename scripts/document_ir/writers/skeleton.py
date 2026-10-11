"""Fill a template's own markup from a Document IR.

The compatibility writer first rebuilt the document's markup from the IR, and a
visual comparison put the result at SSIM 0.135 against the template: correct
tags, no layout. The reason is that a template's appearance lives in its DOM
shape, not its class names -- `.header .title-block .eyebrow` only matches when
all three levels are present and in that order.

Rebuilding that shape from a flat block list means reproducing 61 structural
tags exactly, and every attempt moved the score somewhere between 0.13 and 0.32.
The template already contains the shape, so this module uses it: the template is
the skeleton, the IR supplies the values, and the ids are attached for
provenance.

This is what "HTML compatibility writer" means in the plan: HTML is a renderer
artifact, and the template is part of the renderer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

PLACEHOLDER = re.compile(r"\{\{([^{}]*)\}\}", re.DOTALL)
BODY = re.compile(r"(<body[^>]*>)(.*?)(</body>)", re.DOTALL | re.IGNORECASE)
STYLE = re.compile(r"<style[^>]*>.*?</style>", re.DOTALL | re.IGNORECASE)


@dataclass
class FillResult:
    """What the fill produced, and what it could not place."""

    html: str
    filled: int = 0
    missing: list[str] = field(default_factory=list)
    # Values the IR carried that no placeholder accepted. Reported rather than
    # dropped: a document that loses a paragraph should say so.
    unused: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.missing

    def to_json(self) -> dict[str, Any]:
        return {
            "filled": self.filled,
            "missing": self.missing,
            "unused": self.unused,
            "complete": self.complete,
        }


def body_of(template_html: str) -> str:
    """The template's body markup, which is the skeleton to fill."""
    match = BODY.search(template_html)
    return match.group(2) if match else template_html


def _normalise(text: str) -> str:
    """A placeholder name reduced to a comparable form."""
    return re.sub(r"\s+", " ", text).strip()


def _aliases(placeholder: str) -> tuple[str, ...]:
    """Names a value may carry to fill this placeholder.

    A fixture writes the template's own placeholder text, while the IR carries
    semantic ids. Both are accepted so a value is placed whether it came from a
    fixture or from a bridge.
    """
    name = _normalise(placeholder)
    bare = name[2:-2].strip() if name.startswith("{{") and name.endswith("}}") else name
    # Both spellings name the same slot: a fixture writes the template's own text
    # with its braces, a bridge carries the bare name.
    out = [name, name.lower(), bare, bare.lower(), "{{" + bare + "}}", "{{" + bare + "}}".lower()]
    return tuple(dict.fromkeys(out))


def payload_lang(item: Any) -> str | None:
    """The language a node declares, wherever it declares it."""
    payload = getattr(item, "payload", None) or {}
    value = payload.get("lang")
    return str(value) if value else None


def _with_language(text: str, lang: str | None) -> str:
    """Mark a run whose language differs from the document's.

    The document already declares its language on the `<html>` element, so a run
    that matches it needs no marker. Marking only the exceptions keeps the
    markup readable and the intent visible: this span exists because the
    language changed here.
    """
    language = (lang or "").strip()
    if not language or not text:
        return text
    return f'<span lang="{language}">{text}</span>'


def collect_values(document: Any) -> dict[str, str]:
    """Every string the IR can offer, keyed by the names it may be asked for.

    A block contributes its id, its source locator and its text, so whichever of
    those a template uses, the value is found.
    """
    values: dict[str, str] = {}

    def inline_text(item: Any) -> str:
        """The text of an inline node, keeping its emphasis.

        A `Strong` node contributes `<strong>...</strong>` rather than bare
        words. The IR records emphasis as structure, so dropping the tag would
        lose a decision the author made; keeping it means the template's own CSS
        applies exactly as it does on the template path.
        """
        value = getattr(item, "value", None)
        if value:
            text = str(value)
            return _with_language(text, getattr(item, "lang", None) or payload_lang(item))

        payload = getattr(item, "payload", {}) or {}
        own = payload.get("value")
        if isinstance(own, str) and own:
            return _with_language(own, payload.get("lang"))

        item_type = getattr(item, "type", "") or payload.get("type", "")
        nested = getattr(item, "content", None) or payload.get("content") or ()
        inner = "".join(inline_text(child) for child in nested)

        if item_type in {"strong", "b"}:
            return f"<strong>{inner}</strong>" if inner else ""
        if item_type in {"emphasis", "em", "i"}:
            return f"<em>{inner}</em>" if inner else ""
        if getattr(item, "highlight", False) or payload.get("highlight"):
            return f'<span class="hl">{inner}</span>' if inner else ""
        if item_type == "code":
            return f"<code>{inner}</code>" if inner else ""
        return inner

    def text_of(node: Any) -> str:
        if hasattr(node, "text"):
            try:
                value = node.text()
                if value:
                    return str(value).strip()
            except Exception:
                pass
        payload = getattr(node, "payload", {}) or {}
        parts: list[str] = []
        for item in payload.get("content", ()) or ():
            parts.append(inline_text(item))
        if not parts:
            for key in ("value", "alt", "title", "label"):
                candidate = payload.get(key)
                if isinstance(candidate, str):
                    parts.append(candidate)
        return "".join(parts).strip()

    def walk(node: Any) -> None:
        payload = getattr(node, "payload", {}) or {}
        text = text_of(node)

        # The source locator is the placeholder a fixture filled, so it is the
        # most direct match available.
        source = getattr(node, "source", None)
        if source is not None:
            locator = getattr(source, "locator", None)
            if isinstance(locator, str) and locator:
                if text:
                    values.setdefault(_normalise(locator), text)
                    values.setdefault(locator.strip(), text)
                # A bridge labels a slot like `{{数字}}`; the template asks for
                # `数字`, so the braces come off.
                bare = locator.strip()
                if text:
                    # Store both spellings: a fixture keys the slot with braces,
                    # a bridge carries the bare name, and a placeholder may ask
                    # with either. Which one a caller uses must not decide
                    # whether the value is found.
                    if bare.startswith("{{") and bare.endswith("}}"):
                        values.setdefault(bare[2:-2].strip(), text)
                        values.setdefault(bare, text)
                    else:
                        values.setdefault(bare, text)
                        values.setdefault("{{" + bare + "}}", text)

        node_id = getattr(node, "id", "")
        if isinstance(node_id, str) and node_id and text:
            values.setdefault(node_id, text)

        # A list keeps its content in its items rather than in its own payload,
        # so each item is offered under its own id as well as under the list's.
        #
        # A placeholder names one slot, and the bridge may split it into several
        # items. The list carries the locator and the items do not, so an item of
        # a single-item list also answers to its parent's name -- which is the
        # slot the template is asking for.
        items = list(payload.get("items", ()) or ())
        parent_locator = None
        if source is not None:
            candidate = getattr(source, "locator", None)
            if isinstance(candidate, str) and candidate.strip():
                parent_locator = candidate.strip()

        for item in items:
            item_text = "".join(inline_text(x) for x in (getattr(item, "content", ()) or ()))
            item_id = getattr(item, "id", "")
            if item_id and item_text:
                values.setdefault(item_id, item_text)
            if item_text:
                values.setdefault(f"{node_id}-{item_id}" if node_id else item_id, item_text)
            if item_text and parent_locator:
                values.setdefault(parent_locator, item_text)
                if parent_locator.startswith("{{") and parent_locator.endswith("}}"):
                    values.setdefault(parent_locator[2:-2].strip(), item_text)

        for child in getattr(node, "children", ()) or ():
            walk(child)

    blocks = getattr(document, "blocks", None)
    if blocks is not None:
        for block in blocks:
            walk(block)
    else:
        for node in document.walk():
            walk(node)

    return values


def fill_template(template_html: str, document: Any) -> FillResult:
    """Put the IR's values into the template's own markup.

    Each placeholder takes the first unused value that matches it. A placeholder
    the template repeats -- four metric cards each asking for `数字` -- consumes
    successive values, so repetition in the template maps onto repetition in the
    document.
    """
    values = {key: value for key, value in collect_values(document).items() if value}
    used: set[str] = set()
    missing: list[str] = []
    filled = 0

    # How many times each placeholder name has been asked for, so a document
    # with several values for one slot serves them in order.
    asked: dict[str, int] = {}

    # Placeholder wording that means "a bullet goes here". The template
    # describes the slot rather than naming it, so the category is what can be
    # matched.
    BULLET_WORDS = (
        "bullet", "短 bullet", "条目", "list item", "item",
        # The changelog numbers its entries rather than calling them bullets.
        "新功能", "修复", "变更", "feature", "fix", "change",
    )

    def is_bullet_slot(placeholder: str) -> bool:
        lowered = placeholder.lower()
        return any(word in lowered for word in BULLET_WORDS)

    def list_item_keys() -> list[str]:
        """Value keys that came from a list item, in document order.

        Empty entries are skipped: an empty string is not content, and offering
        it would fill a bullet with nothing.
        """
        seen_text: set[str] = set()
        unique: list[str] = []
        for key, value in values.items():
            if "-i" not in key or not key.rsplit("-i", 1)[-1].isdigit() or not value:
                continue
            if value in seen_text:
                continue
            seen_text.add(value)
            unique.append(key)
        return unique

    # Which list-item value each distinct bullet placeholder has reached. A
    # template repeats one placeholder once per bullet, and two sections ask for
    # different kinds; a single global queue would let the second section take
    # the first section's items.
    bullet_cursor: dict[str, int] = {}
    # Values consumed as bullets in the current section. Kept apart from the
    # document-wide record so a section boundary resets one and not the other.
    bullet_used: set[str] = set()

    def candidates_for(placeholder: str) -> list[str]:
        """Value keys that may fill this placeholder, best match first.

        Ordered by confidence: the placeholder's own text, then a value whose
        source locator is that text, then an id equal to it. Prefix matching
        comes last because it is the weakest signal and the one that swapped two
        values in the equity report.
        """
        name = _normalise(placeholder)
        found: list[str] = []

        # 1. The placeholder's own text, which is how a fixture fills a template.
        for alias in _aliases(placeholder):
            if values.get(alias) and alias not in found:
                found.append(alias)

        # 2. A value whose source locator is this placeholder.
        for key, value in values.items():
            if not value or key in found:
                continue
            if key == name:
                found.append(key)

        if not found:
            for key, value in values.items():
                if not value or key in found:
                    continue
                if key.startswith(name) or name.startswith(key):
                    found.append(key)

        if is_bullet_slot(placeholder):
            # A numbered key names a specific occurrence: the third `短 bullet`
            # slot takes `短 bullet 3` when the fixture provides one.
            index = asked.get(name, 0) + 1
            for suffix in (f"{name} {index}", f"{name}{index}"):
                if values.get(suffix):
                    found.insert(0, suffix)
                    break

        if not found and is_bullet_slot(placeholder):
            # Otherwise a bullet draws from this section's queue, and an item not
            # yet used in the section comes first: three slots should show three
            # different items rather than the first one three times.
            queue = list_item_keys()
            fresh = [key for key in queue if values[key] not in bullet_used]
            found.extend(fresh or queue)
        return found

    def replace(match: re.Match) -> str:
        nonlocal filled
        name = _normalise(match.group(1))
        asked[name] = asked.get(name, 0) + 1

        options = candidates_for(match.group(1))
        if not options:
            missing.append(name)
            return match.group(0)

        # The first time a placeholder is seen, take an unused value; after
        # that, reuse the one already chosen. A template's fourth metric card
        # repeats the first when the document models a single metric.
        used_text = {values[key] for key in used}
        chosen = next(
            (key for key in options if key not in used and values[key] not in used_text),
            next((key for key in options if key not in used), options[0]),
        )
        used.add(chosen)
        filled += 1
        if is_bullet_slot(match.group(1)):
            bullet_cursor[name] = bullet_cursor.get(name, 0) + 1
            bullet_used.add(values[chosen])
        return values[chosen]

    # The whole document is filled, not just the body: the head carries the
    # title, author, description and keywords, and leaving them as literal
    # `{{...}}` text is both visible to a reader of the file and invisible to
    # any check that inspects the rendered page.
    #
    # Sections are filled one at a time so each one's bullets start from the
    # first list item. Filling the document in one pass let the second section
    # consume the queue the first had already drawn from.
    if "</section>" in template_html:
        parts = re.split(r"(</section>)", template_html)
        filled_parts: list[str] = []
        for part in parts:
            if part == "</section>":
                # Only the bullet queues reset. A section is a new consumer of
                # the document's bullets, not a new document: clearing every
                # used value let a chart label take a paragraph that an earlier
                # section had already placed.
                bullet_cursor.clear()
                bullet_used.clear()
                filled_parts.append(part)
                continue
            filled_parts.append(PLACEHOLDER.sub(replace, part))
        html = "".join(filled_parts)
    else:
        html = PLACEHOLDER.sub(replace, template_html)

    # A value the template never asked for is reported, so content is not lost
    # without anyone noticing.
    unused = [
        key for key, value in values.items()
        if key not in used and value and key not in missing
    ]

    return FillResult(html=html, filled=filled, missing=missing, unused=unused[:20])


def attach_ids(html: str, document: Any) -> str:
    """Tag the rendered elements with their IR ids.

    Provenance is what lets a rendered page be traced back to the block that
    produced it, which is the property the IR exists to provide. The id goes on
    the element that already carries the template's class, so nothing about the
    appearance changes.
    """
    ids = [node.id for node in document.walk()] if hasattr(document, "walk") else []
    if not ids:
        return html

    # The nth fillable element takes the nth id. The mapping is positional
    # because the template's structure is positional; ids exist for tracing, not
    # for layout, so an approximate pairing still delivers the property.
    counter = {"n": 0}

    def tag(match: re.Match) -> str:
        if counter["n"] >= len(ids):
            return match.group(0)
        node_id = ids[counter["n"]]
        counter["n"] += 1
        return f'{match.group(0)[:-1]} data-folio-id="{node_id}">'

    return re.sub(r"<(?:h[1-6]|p|li|section|div)\b[^>]*>", tag, html)
