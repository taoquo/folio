#!/usr/bin/env python3
"""Folio Web reading-page check.

The verifier half of the scenario: every rule in `references/web/` carries a
`W-*` id, and this script reports the same ids. A rule that no check covers is
listed in the acceptance table as `semi` or `manual`, never silently.

    python3 scripts/check_web.py dist/web/attention/attention/index.html --level 3
    python3 scripts/check_web.py dist/web/attention/index.html --series-dir dist/web/attention
    python3 scripts/check_web.py page.html --source /tmp/ain.txt --level 3

Levels follow C4: L1 (structure, text, delivery) runs anywhere; L2 adds declared
density and colour; L3 adds figure geometry.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import web_contracts as C  # noqa: E402
import web_geometry  # noqa: E402
import web_page as WP  # noqa: E402
import web_plan  # noqa: E402

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


@dataclass
class Node:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list[Node | str] = field(default_factory=list)
    parent: Node | None = None

    def classes(self) -> set[str]:
        return set((self.attrs.get("class") or "").split())

    def text(self) -> str:
        parts: list[str] = []
        for child in self.children:
            parts.append(child if isinstance(child, str) else child.text())
        return " ".join(parts)

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk()


class Tree(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("document")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, {key: value or "" for key, value in attrs}, parent=self.stack[-1])
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Node(tag, {key: value or "" for key, value in attrs}, parent=self.stack[-1]))

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def parse(path: Path) -> tuple[Node, str]:
    text = path.read_text(encoding="utf-8")
    tree = Tree()
    tree.feed(text)
    return tree.root, text


def find_all(node: Node, tag: str | None = None, cls: str | None = None) -> list[Node]:
    out = []
    for item in node.walk():
        if tag and item.tag != tag:
            continue
        if cls and cls not in item.classes():
            continue
        out.append(item)
    return out


def find_one(node: Node, tag: str | None = None, cls: str | None = None) -> Node | None:
    found = find_all(node, tag, cls)
    return found[0] if found else None


def _strip_at_blocks(css: str) -> str:
    """Drop @media / @supports blocks: their declarations are conditional."""
    out: list[str] = []
    index = 0
    while index < len(css):
        match = re.search(r"@(media|supports|font-face)\b", css[index:])
        if not match:
            out.append(css[index:])
            break
        start = index + match.start()
        out.append(css[index:start])
        brace = css.find("{", start)
        if brace < 0:
            break
        depth, cursor = 0, brace
        while cursor < len(css):
            if css[cursor] == "{":
                depth += 1
            elif css[cursor] == "}":
                depth -= 1
                if depth == 0:
                    break
            cursor += 1
        index = cursor + 1
    return "".join(out)


def css_declarations(text: str) -> dict[str, dict[str, str]]:
    """Selector -> declarations, from the first <style> block."""
    match = re.search(r"<style[^>]*>([\s\S]*?)</style>", text)
    if not match:
        return {}
    css = re.sub(r"/\*[\s\S]*?\*/", "", match.group(1))
    css = _strip_at_blocks(css)
    out: dict[str, dict[str, str]] = {}
    for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        selector = selector.strip()
        props = {}
        for declaration in body.split(";"):
            if ":" in declaration:
                key, value = declaration.split(":", 1)
                props[key.strip()] = value.strip()
        if props:
            out.setdefault(selector, {}).update(props)
    return out


_VAR_REF = re.compile(r"var\(\s*(--[a-z0-9-]+)\s*(?:,\s*([^()]*))?\)")


def resolve_value(value: str, variables: dict[str, str], depth: int = 8) -> str:
    """Substitute `var(--x)` from the page's own `:root`, including fallbacks.

    The Web sheet declares relationships, not values, so a density check that
    read the raw declaration would measure `var(--web-body-size)` as zero.
    """
    text = value
    for _ in range(depth):
        updated = _VAR_REF.sub(
            lambda match: variables.get(match.group(1), match.group(2) or ""),
            text,
        )
        if updated == text:
            break
        text = updated
    return text.strip()


def resolved_declarations(css: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    """Declarations with every custom property substituted."""
    variables: dict[str, str] = {}
    for selector, props in css.items():
        if selector == ":root":
            variables.update({key: value for key, value in props.items()
                              if key.startswith("--")})
    return {
        selector: {key: resolve_value(value, variables) for key, value in props.items()}
        for selector, props in css.items()
    }


def px(value: str | None, base: float = 16.0) -> float | None:
    if not value:
        return None
    match = re.search(r"(-?\d+(?:\.\d+)?)(px|rem|em|ch|pt)?", value)
    if not match:
        return None
    number = float(match.group(1))
    unit = match.group(2) or "px"
    return {"px": number, "rem": number * base, "em": number * base, "ch": number * 0.5 * base,
            "pt": number * 1.3333}.get(unit)


def padding(value: str | None, base: float = 16.0) -> tuple[float, float]:
    parts = (value or "").split()
    values = [px(part, base) or 0.0 for part in parts] or [0.0]
    if len(values) == 1:
        return values[0], values[0]
    if len(values) == 2:
        return values[1], values[1]
    return values[1] if len(values) > 1 else values[0], values[3] if len(values) > 3 else values[1]


class Report:
    def __init__(self) -> None:
        self.items: list[tuple[str, str, str]] = []  # (id, status, detail)

    def add(self, rule: str, ok: bool, detail: str) -> None:
        self.items.append((rule, "PASS" if ok else "FAIL", detail))

    def note(self, rule: str, status: str, detail: str) -> None:
        self.items.append((rule, status, detail))

    def failed(self) -> list[tuple[str, str, str]]:
        return [item for item in self.items if item[1] == "FAIL"]


def check_delivery(root: Node, text: str, report: Report, path: Path, series: str | None, page_type: str) -> None:
    links = find_all(root, "link")
    styles = [link for link in links if "stylesheet" in (link.attrs.get("rel") or "")]
    report.add("W-DLV-01", not styles, f"{len(styles)} external stylesheet link(s)")
    scripts = [node for node in find_all(root, "script") if node.attrs.get("src")]
    report.add("W-DLV-01b", not scripts, f"{len(scripts)} external script(s)")
    if page_type == "module-archive":
        topbar = find_one(root, cls="topbar")
        back = find_all(topbar, "a") if topbar else []
        report.add("W-DLV-04", len(back) == C.TOPBAR_LINKS, f"topbar links = {len(back)}")
    else:
        report.note("W-DLV-04", "SKIP", "series index has no topbar")
    downloads = [node for node in root.walk() if node.tag == "a" and node.attrs.get("download")]
    report.add("W-DLV-05", not downloads, f"{len(downloads)} download attribute(s)")
    report.add("W-DLV-05b", "file://" not in text and "data:application" not in text, "no embedded working files")
    html = find_one(root, "html")
    lang = (html.attrs.get("lang") if html else "") or ""
    if lang.lower().startswith("zh"):
        report.add("W-DLV-09", "@font-face" in text,
                   "Chinese page embeds the engine's CJK face")
    else:
        report.note("W-DLV-09", "SKIP", f"page language is {lang or 'unset'}")
    if series and page_type == "module-archive":
        shape = path.parent.parent.name == series and path.name == "index.html" and len(path.parts) >= 3
        report.add("W-DLV-03", shape, f"module url shape: {path.parent.parent.name}/{path.parent.name}/{path.name}")
    else:
        report.note("W-DLV-03", "SKIP", "not a module page")


def check_structure(root: Node, report: Report, series_dir: Path | None = None) -> str:
    body = find_one(root, "body")
    page_type = "module-archive" if body and "module-archive" in body.classes() else (
        "series-index" if body and "series-index" in body.classes() else "unknown")
    report.add("W-STR-01", page_type in C.PAGE_TYPES, f"page type = {page_type}")
    missing = [region for region in C.PAGE_TYPES.get(page_type, {}).get("required", ())
               if find_one(root, cls=region) is None]
    report.add("W-STR-01b", not missing, f"missing regions: {missing or 'none'}")

    head = find_one(root, cls="doc-head")
    after = []
    if head is not None:
        siblings: list[Node] = []
        parent = head.parent
        if parent is not None:
            seen = False
            for child in parent.children:
                if child is head:
                    seen = True
                    continue
                if seen and isinstance(child, Node):
                    siblings.extend(child.walk())
        for node in siblings:
            if node.classes() & set(C.FORBIDDEN_AFTER_HEAD):
                after.append(node.classes())
    report.add("W-STR-02", not after, f"header trio after doc-head: {after or 'none'}")

    statuses = [node.attrs.get("data-status", "") for node in root.walk()
                if node.tag in {"span", "li"} and node.attrs.get("data-status")]
    bad = [value for value in statuses if not C.is_allowed_status(value)]
    report.add("W-STR-04", not bad, f"status outside the closed vocabulary: {bad or 'none'}")

    if series_dir is not None and page_type == "series-index":
        blocks = find_all(root, cls="module-block")
        modules = [path for path in series_dir.glob("*/index.html")]
        report.add("W-STR-03", len(blocks) == len(modules),
                   f"{len(blocks)} index block(s) for {len(modules)} module page(s)")
    return page_type


def check_page_model(root: Node, report: Report, page_type: str,
                     manifest: dict | None, module_id: str) -> None:
    """W-STR-05 / W-STR-06: the page is what the model said it was.

    The model reads the fragment's top-level blocks and gives each a role from a
    closed vocabulary. The build annotates them; this rule reads the rendered
    DOM back and compares. A block that lost its role between the model and the
    page is a builder defect, and the count comparison catches the subtler case
    where a block was dropped or duplicated on the way.
    """
    if page_type != "module-archive":
        report.note("W-STR-05", "SKIP", f"not a module page ({page_type})")
        report.note("W-STR-06", "SKIP", f"not a module page ({page_type})")
        return

    known = set(WP.BLOCK_ROLES.values()) | {"figure"}
    unlabelled: list[str] = []
    ids: list[str] = []
    counts: dict[str, int] = {}
    for chapter in find_all(root, cls="chapter"):
        for child in chapter.children:
            if not isinstance(child, Node):
                continue
            role = child.attrs.get("data-folio-role", "")
            block_id = child.attrs.get("data-folio-id", "")
            if role not in known or not block_id:
                unlabelled.append(f"{chapter.attrs.get('id', '?')}>{child.tag}"
                                  f".{' '.join(sorted(child.classes())) or '-'}"
                                  f" role={role or 'missing'}")
                continue
            counts[role] = counts.get(role, 0) + 1
            ids.append(block_id)
    duplicates = sorted({value for value in ids if ids.count(value) > 1})
    report.add("W-STR-05", not unlabelled and not duplicates,
               f"blocks without a known role or id: {unlabelled or 'none'}; "
               f"duplicate ids: {duplicates or 'none'}")

    model = ((manifest or {}).get("pages") or {}).get(module_id)
    if model is None:
        report.note("W-STR-06", "SKIP",
                    "the manifest records no page model (built with FOLIO_WEB_MODEL=off)")
        return
    expected = model.get("counts") or {}
    disagree = sorted(
        f"{role} {expected.get(role, 0)}→{counts.get(role, 0)}"
        for role in set(expected) | set(counts)
        if expected.get(role, 0) != counts.get(role, 0))
    report.add("W-STR-06", not disagree,
               f"{sum(counts.values())} block(s) in the page, "
               f"{sum(expected.values())} in the model; {disagree or 'counts agree'}")


def check_rail(root: Node, text: str, report: Report, page_type: str) -> None:
    """The right-side scale: one tick per region, active on scroll."""
    if page_type == "module-archive":
        targets = [f'#{node.attrs.get("id", "")}' for node in find_all(root, cls="chapter")]
        unit = "chapter"
    elif page_type == "series-index":
        targets = [f'#{node.attrs.get("id", "")}' for node in find_all(root, cls="module-block")]
        unit = "module"
    else:
        targets, unit = [], "region"

    rail = find_one(root, cls="rail")
    links = find_all(rail, "a") if rail else []
    hrefs = [link.attrs.get("href", "") for link in links]
    report.add("W-DLV-06", rail is not None and bool(targets) and hrefs == targets,
               f"rail ticks {len(hrefs)} for {len(targets)} {unit}(s)")

    labels = [find_one(link, cls="label") for link in links]
    labelled = all(label is not None and label.text().strip() for label in labels)
    current = [link.attrs.get("aria-current") for link in links]
    report.add("W-DLV-07",
               labelled and bool(rail and rail.attrs.get("aria-label")) and current.count("true") == 1,
               f"rail labels = {labelled}, aria-label = {bool(rail and rail.attrs.get('aria-label'))}, "
               f"active = {current.count('true')}")

    scripts = [node.text() for node in find_all(root, "script") if not node.attrs.get("src")]
    inline = any("addEventListener('scroll'" in script or 'addEventListener("scroll"' in script for script in scripts)
    report.add("W-DLV-08", inline, "inline scroll-spy present (no external script)")


def check_text(root: Node, report: Report) -> None:
    banned_hits = []
    for tag in ("h1", "h2", "h3", "h4"):
        for node in find_all(root, tag):
            value = node.text()
            if any(token in value for token in C.TITLE_BANNED):
                banned_hits.append((tag, value[:40]))
    report.add("W-TXT-01", not banned_hits, f"titles with banned symbols: {banned_hits or 'none'}")

    numbers = []
    for node in find_all(root, "h2"):
        num = find_one(node, cls="num")
        if num and num.text().strip().isdigit():
            numbers.append(int(num.text().strip()))
    expected = list(range(1, len(numbers) + 1))
    report.add("W-TXT-02", numbers == expected, f"chapter numbers {numbers}")

    captions = [node.text().strip() for node in find_all(root, "figcaption")]
    report.add("W-TXT-03", all(C.FIGCAPTION.match(value) for value in captions),
               f"{sum(1 for v in captions if not C.FIGCAPTION.match(v))} figcaption(s) off grammar")

    figure_nums = []
    for value in captions:
        match = C.FIGURE_NUM.match(value)
        if match:
            figure_nums.append(match.group(1))
    report.add("W-TXT-02b", len(figure_nums) == len(set(figure_nums)),
               f"figure numbers {figure_nums}")


def check_components(root: Node, report: Report, source_text: str | None) -> None:
    if not source_text:
        report.note("W-CNT-02", "SKIP", "no --source given")
        return
    hits = []
    for name, pattern, component in C.COMPONENT_PATTERNS:
        if re.search(pattern, source_text):
            present = find_one(root, cls=component) is not None
            hits.append((name, component, present))
    report.add("W-CNT-02", all(present for _n, _c, present in hits), f"componentization: {hits}")


def check_content(root: Node, report: Report, source_text: str | None) -> None:
    if not source_text:
        report.note("W-CNT-01", "SKIP", "no --source given")
        return
    page_text = " ".join(node.text() for node in [root]).lower()
    source_words = [word for word in re.findall(r"[a-z][a-z-]{2,}", source_text.lower())]
    unique = sorted(set(source_words))
    missing = [word for word in unique if word not in page_text]
    coverage = 1 - len(missing) / max(1, len(unique))
    report.add("W-CNT-01", coverage >= 0.95, f"source word coverage {coverage:.3f} ({len(missing)} missing)")


def check_clauses(root: Node, report: Report) -> None:
    offenders = []
    for cls in ("insight", "card", "lead"):
        for node in find_all(root, cls=cls):
            target = find_one(node, "p") or node
            value = target.text()
            if len(re.findall(r"[。；;]", value)) >= 2:
                offenders.append((cls, value[:30]))
    report.add("W-CNT-03", not offenders, f"multi-clause blocks: {offenders or 'none'}")

    malformed = []
    for node in find_all(root, cls="insight"):
        paragraphs = find_all(node, "p")
        lists = find_all(node, "ul") + find_all(node, "ol")
        if lists or len(paragraphs) != 1:
            malformed.append(node.text()[:30])
    report.add("W-CNT-04", not malformed, f"insight blocks that are lists or multi-paragraph: {malformed or 'none'}")


def check_density(root: Node, css: dict[str, dict[str, str]], report: Report) -> None:
    css = resolved_declarations(css)
    body = css.get("body", {})
    body_size = px(body.get("font-size")) or 0
    low, high = C.DENSITY["body_size"]
    report.add("W-DEN-01", low <= body_size <= high, f"body font-size {body_size}px")

    h2 = px(css.get(".chapter h2", {}).get("font-size")) or 0
    low, high = C.DENSITY["h2_size"]
    report.add("W-DEN-02", low <= h2 <= high, f"h2 font-size {h2}px")

    page_left, page_right = padding(css.get(".page", {}).get("padding"))
    low, high = C.DENSITY["page_padding_x"]
    report.add("W-DEN-03", low <= page_left <= high and low <= page_right <= high,
               f"page padding {page_left}/{page_right}px")

    card = padding(css.get(".kpi", {}).get("padding"))
    low, high = C.DENSITY["card_padding"]
    report.add("W-DEN-04", low <= card[0] <= high, f"card padding {card[0]}px")

    cell = css.get(".tbl td", {})
    cell_font = px(cell.get("font-size")) or body_size or 13
    cell_height = px(cell.get("height")) or 0
    row = cell_height if cell_height else round(cell_font * 1.45 + 2 * 5, 1)
    low, high = C.DENSITY["table_row_height"]
    report.add("W-DEN-05", low <= row <= high, f"table row height {row}px")

    measure = css.get(".chapter p", {}).get("max-width", "")
    chars = re.match(r"(\d+(?:\.\d+)?)ch", measure)
    low, high = C.MEASURE_CHARS
    report.add("W-DEN-06", bool(chars) and low <= float(chars.group(1)) <= high,
               f"measure = {measure or 'unbounded'}")

    arrows = [cell.text()[:24] for cell in find_all(root, "td") if "→" in cell.text()]
    report.add("W-DEN-07", not arrows, f"table cells with arrow flows: {arrows[:3] or 'none'}")


def check_styles(text: str, css: dict[str, dict[str, str]], report: Report) -> None:
    """Every variable the page reads is defined, and the template decides no value.

    This is the rule that keeps the Web scenario from drifting back into a
    second design system: a size, family, spacing or radius outside `:root` is
    a value the engine cannot change.
    """
    variables = {
        key: value
        for selector, props in css.items()
        if selector == ":root"
        for key, value in props.items()
        if key.startswith("--")
    }
    used = set(re.findall(r"var\(\s*(--[a-z0-9-]+)", text))
    missing = sorted(name for name in used if name not in variables)
    report.add("W-COL-06", not missing, f"undefined custom properties: {missing or 'none'}")

    literal_properties = ("font-size", "font-family", "line-height", "padding",
                          "margin", "gap", "border-radius")
    literals: list[str] = []
    for selector, props in css.items():
        if selector == ":root":
            continue
        for prop in literal_properties:
            value = props.get(prop)
            if not value:
                continue
            if re.search(r"\b\d*\.?\d+(px|pt|em|rem)\b", value):
                literals.append(f"{selector} {prop}: {value}")
    report.add("W-DEN-08", not literals,
               f"template-decided type/spacing values: {literals[:4] or 'none'}")

    # The screen scale must be present and engine-sourced, not merely defined.
    required = ("--serif", "--mono", "--web-body-size", "--web-space-6")
    absent = [name for name in required if name not in variables]
    report.add("W-DEN-09", not absent, f"missing Web profile variables: {absent or 'none'}")


def check_semantics(root: Node, report: Report) -> None:
    """Every semantic mark names one of the ten meanings."""
    phases = find_all(root, cls="phase")
    unlabelled = [node.text()[:24] for node in phases
                  if node.attrs.get("data-role") not in C.SEMANTIC_ROLES]
    report.add("W-COL-07", not unlabelled,
               f"semantic marks without a known data-role: {unlabelled or 'none'}")


def check_colour(root: Node, text: str, css: dict[str, dict[str, str]], report: Report) -> None:
    style = re.search(r"<style[^>]*>([\s\S]*?)</style>", text)
    body = style.group(1) if style else ""
    depth = 0
    outside = []
    for line in body.splitlines():
        if ":root" in line:
            depth = 1
        elif depth and "}" in line:
            depth = 0
            continue
        if depth:
            continue
        if re.search(r"#[0-9a-fA-F]{3,6}\b", line) and "FOLIO" not in line:
            outside.append(line.strip()[:60])
    report.add("W-COL-01", not outside, f"hex outside :root: {outside[:3] or 'none'}")

    required = ("--color-surface-page", "--color-text-primary", "--color-accent-brand",
                "--color-semantic-delivered", "--serif", "--mono", "--web-body-size")
    missing = [name for name in required if f"{name}:" not in body]
    report.add("W-COL-02", not missing, f"missing theme vars: {missing or 'none'}")

    redefinitions = len(re.findall(r"--color-accent-brand:\s*[^;]+;", body))
    report.add("W-COL-03", redefinitions <= 1, f"accent redefinitions: {redefinitions}")
    report.note("W-COL-04", "REVIEW", "semantic colour in page chrome is a review item")
    report.note("W-COL-05", "REVIEW", "per-figure colour count is recorded in the figure manifest")


def check_figures(
    root: Node,
    text: str,
    report: Report,
    level: int,
    page_type: str,
    manifest: dict | None,
    module_id: str,
) -> None:
    rules = ("W-FIG-01", "W-FIG-03", "W-FIG-05", "W-FIG-06", "W-FIG-07", "W-FIG-08",
             "W-FIG-09", "W-FIG-10", "W-FIG-11", "W-FIG-12", "W-GEO-01")
    if page_type == "series-index":
        for rule in rules:
            report.note(rule, "SKIP", "series index carries no figures")
        return

    figures = find_all(root, "figure")
    report.add("W-FIG-05", len(figures) >= 3, f"{len(figures)} figure(s), need >= 3")

    module_figures = (manifest or {}).get("figures", {}).get(module_id, {})
    problems: list[str] = []
    for figure in figures:
        figure_id = figure.attrs.get("data-folio-drawing", "")
        kind = figure.attrs.get("data-kind", "")
        composition = figure.attrs.get("data-composition", "")
        axis = figure.attrs.get("data-axis", "")
        caption = find_one(figure, "figcaption")
        if not figure_id:
            problems.append("missing data-folio-drawing")
            continue
        if kind not in C.FIGURE_KINDS:
            problems.append(f"{figure_id}: kind {kind!r} not in the DSL")
        if composition and composition not in C.COMPOSITIONS:
            problems.append(f"{figure_id}: composition {composition!r} invalid")
        if axis not in C.AXES:
            problems.append(f"{figure_id}: axis {axis!r} invalid")
        entry = module_figures.get(figure_id)
        if entry is None:
            problems.append(f"{figure_id}: not in figures.manifest.json")
            continue
        if entry.get("kind") != kind or entry.get("composition", "") != composition:
            problems.append(f"{figure_id}: data attributes disagree with the manifest")
        # A figure has one reading direction unless a band composed on the
        # other axis, in which case each plate states its own. Compare the
        # plate where it speaks and fall back to the figure's one axis.
        plates = web_plan.variant_entries(entry)
        for plate in find_all(figure, "svg", "figure-svg"):
            name = plate.attrs.get("data-folio-plate", "")
            stated = plate.attrs.get("data-axis") or entry.get("axis", "")
            recorded = plates.get(name, {}).get("axis") or entry.get("axis", "")
            if stated != recorded:
                problems.append(
                    f"{figure_id}[{name}]: axis {stated!r} disagrees with the manifest {recorded!r}")
        if caption is None:
            problems.append(f"{figure_id}: no figcaption")
        elif not C.FIGCAPTION.match(caption.text().strip()):
            # The axis is not in the caption any more; `data-axis` above and the
            # manifest entry carry it, so the two can still be compared.
            problems.append(f"{figure_id}: caption off grammar")
    report.add("W-FIG-01", not problems, f"figure contract: {problems or 'none'}")

    report.add("W-FIG-03", all(find_one(f, "title") and find_one(f, "desc") for f in figures),
               "figure title/desc present")

    # A composed plate's node boxes are its authored tiers scaled by the stage
    # and held at the type's floor, so the guard is the band they live in, not
    # the three 960-unit sizes: a box narrower than 96 units cannot hold its
    # eyebrow, and one past 224 is a tier nobody declared.
    off_tier = [
        f"{figure_id}[{variant}]:{size}"
        for figure_id, entry in module_figures.items()
        if entry.get("kind") == "architecture"
        for variant, plate in web_plan.variant_entries(entry).items()
        for size in plate.get("node_sizes", [])
        if not (96 <= size[0] <= 224 and 64 <= size[1] <= 80)
    ]
    report.add("W-FIG-09", not off_tier, f"architecture node sizes off the tier band: {off_tier or 'none'}")

    chapters = find_all(root, cls="chapter")
    empty = []
    for chapter in chapters:
        if not any(find_one(chapter, cls=cls) for cls in
                   ("figure", "tbl-wrap", "kpi-row", "phase-seg", "multi-card", "insight", "prose-list")):
            empty.append(chapter.attrs.get("id", "?"))
    # W-FIG-10: the manifest records every tier each composed plate draws, and
    # the rule converts them to the size that plate delivers at its own band.
    # It fails on missing data; the sizes themselves are the review's evidence.
    plates = [
        (f"{figure_id}[{variant}]", plate)
        for figure_id, entry in module_figures.items()
        for variant, plate in web_plan.variant_entries(entry).items()
    ]
    missing_tiers = [name for name, plate in plates if not plate.get("text_sizes")]
    delivered = []
    for name, plate in plates:
        tiers = sorted(plate.get("text_sizes") or [])
        width = web_plan.framed_width(plate)
        band = float(plate.get("band") or C.FIGURE["slot"])
        if not tiers or not width:
            continue
        scaled = " / ".join(f"{size * band / width:.1f}" for size in tiers)
        units = float(plate.get("title_units") or 0.0)
        title = f" title {units * band / width:.1f}px" if units else ""
        delivered.append(f"{name}@{band:g} {scaled}{title}")
    report.add("W-FIG-10", not missing_tiers,
               f"manifest tiers present; delivered: {'; '.join(delivered) or 'none'}")

    # W-FIG-11 and W-FIG-12 are the two obligations of a plate, judged once per
    # composed band: the ink must fill the plate, the plate must be filled
    # (not padded), its shape must stay inside the aspect band, and its
    # smallest tier must clear the floor at the band it was composed for.
    # `web_plan.fit_verdict` is the one place those are stated, so the checker
    # cannot drift from the builder.
    errors: list[str] = []
    notes: list[str] = []
    for figure_id, entry in module_figures.items():
        figure_errors, figure_notes = web_plan.fit_verdict(entry)
        errors.extend(f"{figure_id}: {item}" for item in figure_errors)
        notes.extend(f"{figure_id}: {item}" for item in figure_notes)
    unfilled = [item for item in errors if "delivered at" not in item]
    report.add("W-FIG-11", not unfilled, f"figure plates: {unfilled or 'filled'}")
    # W-FIG-12 keeps its own rule id for the legibility half of the verdict,
    # because that is the number the review reads. Both halves are errors now:
    # the composition meets the floor, so a plate that misses it is a defect.
    short = [item for item in errors if "delivered at" in item]
    report.add("W-FIG-12", not short,
               f"smallest tier below {C.FIGURE_FIT['delivered_target_px']:g}px: "
               f"{short or 'none'}"
               + (f"; one-stage families: {notes}" if notes else ""))

    report.add("W-FIG-06", not empty, f"chapters without a block component: {empty or 'none'}")

    examples = [f for f in figures if f.attrs.get("data-example") == "true"]
    report.add("W-FIG-08", bool(examples), f"{len(examples)} worked-example figure(s)")

    # Every plate carries the hash of the drawing it was rendered from, and
    # every one of them is compared: a stale narrow plate beside a fresh wide
    # one is exactly the failure a single figure-level hash would miss.
    provenance: list[str] = []
    for figure_id, _attrs, plates in web_geometry.figures_in(text):
        entry = module_figures.get(figure_id)
        if entry is None:
            provenance.append(f"{figure_id}: no manifest entry")
            continue
        records = web_plan.variant_entries(entry)
        for variant, svg_text, _stage in plates:
            record = records.get(variant)
            if record is None:
                provenance.append(f"{figure_id}[{variant or '?'}]: no manifest record")
                continue
            # The hash covers the plate markup without its own hash attribute,
            # which is the only way the attribute can record it.
            bare = re.sub(r'\sdata-folio-sha="[^"]*"', "", svg_text, count=1)
            if hashlib.sha256(bare.encode("utf-8")).hexdigest()[:16] != record.get("svg_sha"):
                provenance.append(f"{figure_id}[{variant}]: svg hash does not match the manifest")
    report.add("W-FIG-07", not provenance, f"provenance: {provenance or 'none'}")

    if level >= 3:
        host = web_geometry.audit_host(text) if figures else []
        dsl_errors = [
            f"{figure_id}:{item['code']}"
            for figure_id, entry in module_figures.items()
            for item in entry.get("diagnostics", [])
            if item.get("level") == "ERROR"
        ]
        findings = [f"{item.code} {item.figure}" for item in host
                    if item.level == "ERROR"] + dsl_errors
        report.add("W-GEO-01", not findings, f"graphics: {findings[:4] or 'none'}")
        # A plate whose shape the page did not choose: the family composes on
        # one stage, so the shape is the drawing's own. Reported with the
        # measurement so the reader knows what arrived, and not counted as a
        # page defect.
        reviews = [f"{item.code} {item.figure}: {item.detail}"
                   for item in host if item.level != "ERROR"]
        if reviews:
            report.note("W-GEO-02", "REVIEW",
                        f"plate shapes the page did not choose: {reviews[:2]}")


def check_links(root: Node, report: Report) -> None:
    ids = {node.attrs.get("id") for node in root.walk() if node.attrs.get("id")}
    broken = []
    for anchor in find_all(root, "a"):
        href = anchor.attrs.get("href") or ""
        if href.startswith("#") and href[1:] and href[1:] not in ids:
            broken.append(href)
    report.add("W-ACC-10", not broken, f"broken anchors: {broken or 'none'}")


def check_evidence(root: Node, text: str, report: Report, page_type: str) -> None:
    if page_type == "series-index":
        report.note("W-CNT-05", "SKIP", "index is a listing, not a module")
        return
    cites = re.findall(r"[A-Za-z0-9_./-]+\.(?:py|md|yaml|yml|json):\d+", text)
    has_chapter = any(
        token in node.text()
        for node in find_all(root, "h2")
        for token in ("引擎对照", "Engine comparison")
    )
    report.add("W-CNT-05", len(cites) >= 2 and has_chapter,
               f"{len(cites)} file:line cite(s), engine-comparison chapter = {has_chapter}")


def acceptance(report: Report) -> list[tuple[str, str, str]]:
    status = {rule: state for rule, state, _detail in report.items}
    rows = []
    mapping = {
        "zero-deletion": ["W-CNT-01"],
        # A block only counts as componentized if the page model knows it: the
        # role vocabulary is what makes the component a contract.
        "componentized": ["W-CNT-02", "W-STR-05", "W-STR-06"],
        "no-purple": ["W-CNT-03"],
        "no-header-trio": ["W-STR-02"],
        "reading-rail": ["W-DLV-06", "W-DLV-07", "W-DLV-08"],
        "table-shape": ["W-DEN-05"],
        "figures": ["W-FIG-01", "W-FIG-03", "W-FIG-05", "W-FIG-06", "W-FIG-09",
                    "W-FIG-10", "W-FIG-11", "W-FIG-12"],
        "figure-provenance": ["W-FIG-07"],
        "figure-dsl": ["W-GEO-01"],
        "geometry": ["W-GEO-01"],
        "numbering": ["W-TXT-02", "W-TXT-02b"],
        "title-symbols": ["W-TXT-01"],
        "links": ["W-ACC-10", "W-DLV-01b"],
        "colour": ["W-COL-01", "W-COL-02", "W-COL-06", "W-COL-07", "W-DEN-08", "W-DEN-09"],
        "evidence": ["W-CNT-05"],
    }
    for item in C.ACCEPTANCE:
        rules = mapping.get(item.key, [])
        if item.kind == "manual":
            rows.append((item.key, "MANUAL", item.title))
            continue
        states = [status.get(rule, "SKIP") for rule in rules]
        if any(state == "FAIL" for state in states):
            rows.append((item.key, "FAIL", item.title))
        elif all(state in {"PASS"} for state in states):
            rows.append((item.key, "PASS", item.title))
        else:
            rows.append((item.key, "SKIP", item.title))
    return rows


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", type=Path)
    parser.add_argument("--level", type=int, default=1, choices=(1, 2, 3))
    parser.add_argument("--source", type=Path, default=None)
    parser.add_argument("--series-dir", type=Path, default=None)
    parser.add_argument("--figures-manifest", type=Path, default=None)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    root, text = parse(args.path)
    source_text = args.source.read_text(encoding="utf-8", errors="ignore") if args.source else None
    series = args.series_dir.name if args.series_dir else None
    css = css_declarations(text)

    report = Report()
    page_type = check_structure(root, report, args.series_dir)
    check_delivery(root, text, report, args.path, series, page_type)
    check_text(root, report)
    check_links(root, report)
    check_evidence(root, text, report, page_type)
    check_rail(root, text, report, page_type)
    manifest = json.loads(args.figures_manifest.read_text(encoding="utf-8")) if args.figures_manifest else None
    module_id = args.path.parent.name
    check_figures(root, text, report, args.level, page_type, manifest, module_id)
    check_page_model(root, report, page_type, manifest, module_id)
    if args.level >= 2:
        check_styles(text, css, report)
        check_density(root, css, report)
        check_semantics(root, report)
        check_colour(root, text, css, report)
        check_clauses(root, report)
        check_content(root, report, source_text)
        check_components(root, report, source_text)

    rows = acceptance(report)
    if args.format == "json":
        print(json.dumps({
            "path": str(args.path),
            "checks": [{"rule": rule, "status": state, "detail": detail}
                       for rule, state, detail in report.items],
            "acceptance": [{"item": item, "status": state, "title": title}
                           for item, state, title in rows],
        }, ensure_ascii=False, indent=2))
    else:
        print(f"Folio Web check · {args.path}  (level {args.level})")
        for rule, state, detail in report.items:
            print(f"  {state:<6} {rule:<10} {detail}")
        print("\nAcceptance")
        for item, state, title in rows:
            print(f"  {state:<6} {item:<16} {title}")
        failed = report.failed()
        print(f"\n{'OK' if not failed else 'FAILED'}: {len(failed)} failing check(s)")
    return 0 if not report.failed() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
