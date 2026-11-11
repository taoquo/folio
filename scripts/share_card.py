#!/usr/bin/env python3
"""The card a link unfurls into.

A reading page carries a title, a lead and a plate; a link to it carries a
1200x630 image and two lines of text. This renders that image from the page's
own words, through the same renderer as the page, so the card cannot drift
into a second design system. Nothing here is a social template: there is one
size, one composition, and the colours come from the theme the page was built
in.

    python3 scripts/share_card.py --site                 # render the site's own cards
    python3 scripts/share_card.py --site --check         # re-render, compare bytes
    python3 scripts/share_card.py --site --check-heads   # head vs card on disk, no render

The card is a poster of the page, not a second design: it takes the page's own
grid (a 64px margin inside 1120px becomes 72px inside 1200px), its type steps
up because a card is read at thumbnail size, and every colour is a theme role.

Two facts decide the layout, and both are measured rather than assumed:

* The composition is chosen the way `compose_for_band()` picks a stage: walk
  the type rungs from largest to smallest and keep the first one whose title,
  lead and footer fit above the rule. The title picks the rung, never the lead;
  at the floor the lead is shortened, never the title.
* The lead measure steps down until its last line is not a widow. The renderer
  has no `text-wrap: balance`, so a two-line lead would otherwise end in two
  or three characters.

Fitting reads the renderer's box tree, not a text estimate: line counts come
from the LineBoxes the layout actually produced, so the rung the card chooses
is the rung the reader gets. A card composed for 1.91:1 is what every client
shows; a 1:1 crop trims the right end of the lead, never the title's opening.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

CARD_W, CARD_H = 1200, 630

# The card is a poster of the page, so it takes the page's own grid: the
# homepage sets its content at a 64px margin inside 1120px, with the title at
# 106px and the lead at 21px. On a 1200px canvas that is a 72px margin and a
# 1056px content width, and the type steps up a little because a card is read
# at thumbnail size. The earlier version confined the text to a centred 600px
# column to survive a square crop; the reading proved the cost: the card
# stopped looking like the page it links to, with half the frame empty.
MARGIN_X = 72
CONTENT_W = CARD_W - MARGIN_X * 2
TEXT_TOP = 88
LEAD_W = 900

# Composition A sets the text across the grid; B narrows the text and puts the
# page's first plate on the right. The plate is fitted whole inside its band:
# a diagram cropped through a box is a diagram the reader cannot finish.
COLUMN_B_W = 650
PLATE_L, PLATE_W = 760, 368
PLATE_TOP, PLATE_BOTTOM = 96, 540

RULE_BOTTOM, RULE_H = 84, 5
FOOTER_BOTTOM = 44

MAX_TITLE_LINES = 3
MAX_LEAD_LINES = 2

# The text must stop this far above the rule. Without the gap a two-line title
# chose the largest rung and left the lead sitting on the accent bar, which
# reads as a collision rather than as the bottom of a block.
CONTENT_GAP = 40

# A lead whose last line holds less than this share of the column is a widow:
# on a two-line lead it reads as a stray fragment. The measure steps down by
# LEAD_W_STEP, but never below LEAD_W_MIN, to find a break that fills.
WIDOW_FILL = 0.30
LEAD_W_MIN = 640
LEAD_W_STEP = 40

# Title size, lead size. The first rung that fits wins; the last is the floor.
# A three-line title still has to clear the rule, which is what sets the floor.
RUNGS = ((120, 26), (104, 24), (88, 22), (74, 20))
LEAD_TRIMS = (0, 40, 80, 120, 160)

SITE_FILE = ROOT / "references" / "site" / "share.json"
FONT_FILES = {
    "Source Serif 4": ("SourceSerif4Variable-Roman.ttf", "truetype", "200 900"),
    "LXGW WenKai": ("LXGWWenKai-Regular.ttf", "truetype", None),
    "JetBrains Mono": ("JetBrainsMono.woff2", "woff2", None),
}

_VAR = re.compile(r"--([\w-]+)\s*:\s*([^;]+);")


class ShareCardError(RuntimeError):
    """The card cannot be rendered as asked."""


@dataclass(frozen=True)
class Card:
    """Everything the card prints. Values are plain text, never markup."""

    kicker: str
    title: str
    description: str
    footer: str
    language: str
    surface: str
    ink: str
    muted: str
    secondary: str
    accent: str
    plate: str | None = None
    stack: str = '"Source Serif 4", "LXGW WenKai", Georgia, serif'


# --------------------------------------------------------------- composition


def _face_css() -> str:
    blocks = []
    for family, (filename, fmt, weight) in FONT_FILES.items():
        source = ROOT / "assets" / "fonts" / filename
        if not source.is_file():
            continue
        weight_line = f"  font-weight: {weight};\n" if weight else ""
        blocks.append(
            "@font-face {\n"
            f'  font-family: "{family}";\n'
            f'  src: url("{source.as_uri()}") format("{fmt}");\n'
            f"{weight_line}"
            "  font-display: swap;\n"
            "}"
        )
    return "\n".join(blocks)


def stack_of(css: str, fallback: str, language: str = "en") -> str:
    """The serif stack the page actually resolves for this language.

    The stylesheet re-declares `--serif` under `html[lang="zh-CN"]` so Chinese
    leads with the Kai face. Reading only the first declaration would set the
    Chinese card in the Latin stack, which is a different design for the same
    page.
    """
    blocks = [css]
    if language.lower().startswith("zh"):
        scoped = re.search(r'html\[lang="zh-CN"\]\s*\{([^}]*)\}', css)
        if scoped:
            blocks.insert(0, scoped.group(1))
    for block in blocks:
        match = re.search(r"--serif\s*:\s*([^;]+);", block)
        if match:
            return match.group(1).strip()
    return fallback


def embedded_stack(stack: str) -> str:
    """Put the faces the card ships ahead of the ones it hopes for.

    A page may name a system face first (Charter on macOS). The card embeds
    its faces, so it leads with them: otherwise the same card renders in
    different type on different machines, and a build that promises the same
    bytes would produce two designs.
    """
    parts = [part.strip() for part in stack.split(",") if part.strip()]
    ours = [part for part in parts if part.strip('"\'') in FONT_FILES]
    rest = [part for part in parts if part.strip('"\'') not in FONT_FILES]
    return ", ".join(ours + rest)


def available() -> bool:
    """Whether the rasterizer this module needs is on the machine."""
    return shutil.which("pdftoppm") is not None


def plate_box(svg: str) -> tuple[float, float]:
    """The plate's drawn size, fitted whole inside its band."""
    box = re.search(r'viewBox="[-\d.]+ [-\d.]+ ([\d.]+) ([\d.]+)"', svg)
    if box:
        drawn_w, drawn_h = float(box.group(1)), float(box.group(2))
    else:
        width = re.search(r'\bwidth="([\d.]+)"', svg)
        height = re.search(r'\bheight="([\d.]+)"', svg)
        if not (width and height):
            raise ShareCardError("the plate has neither a viewBox nor a size")
        drawn_w, drawn_h = float(width.group(1)), float(height.group(1))
    scale = min(PLATE_W / drawn_w, (PLATE_BOTTOM - PLATE_TOP) / drawn_h)
    return round(drawn_w * scale, 1), round(drawn_h * scale, 1)


def compose(card: Card, *, rung: int, lead: str, offset: float = 0.0,
            lead_w: int | None = None) -> str:
    """The card as one self-contained page."""
    title_px, lead_px = RUNGS[rung]
    serif = card.stack
    top = TEXT_TOP + offset
    width = COLUMN_B_W if card.plate else CONTENT_W
    lead_w = min(lead_w or LEAD_W, width)
    plate = ""
    if card.plate:
        plate_w, plate_h = plate_box(card.plate)
        plate_top = PLATE_TOP + ((PLATE_BOTTOM - PLATE_TOP) - plate_h) / 2
        plate_left = PLATE_L + (PLATE_W - plate_w)
        plate = (f'<div class="plate" aria-hidden="true" '
                 f'style="left:{plate_left:.1f}px;top:{plate_top:.1f}px;'
                 f'width:{plate_w:.1f}px;height:{plate_h:.1f}px">{card.plate}</div>')
    return f"""<!doctype html>
<html lang="{html.escape(card.language)}">
<head><meta charset="utf-8">
<style>
{_face_css()}
@page {{ size: {CARD_W}px {CARD_H}px; margin: 0; }}
:root {{
  --surface: {card.surface};
  --ink: {card.ink};
  --secondary: {card.secondary};
  --muted: {card.muted};
  --accent: {card.accent};
}}
html, body {{ margin: 0; padding: 0; }}
body {{
  width: {CARD_W}px; height: {CARD_H}px; position: relative;
  background: var(--surface); color: var(--ink);
  font-family: {serif};
}}
.card {{ position: absolute; left: {MARGIN_X}px; top: {top:.1f}px; width: {width}px; }}
.kicker {{
  margin: 0 0 22px; font-size: 14px; line-height: 1.35;
  font-weight: 500; letter-spacing: 0.14em; text-transform: uppercase;
  color: var(--muted);
}}
h1 {{
  margin: 0; font-size: {title_px}px; line-height: 1.05;
  font-weight: 500; letter-spacing: -0.012em;
}}
.lead {{
  margin: 20px 0 0; max-width: {lead_w}px;
  font-size: {lead_px}px; line-height: 1.35; font-weight: 400;
  color: var(--secondary);
}}
.rule {{
  position: absolute; left: {MARGIN_X}px; bottom: {RULE_BOTTOM}px;
  width: 96px; height: {RULE_H}px; background: var(--accent);
}}
.footer {{
  position: absolute; left: {MARGIN_X}px; bottom: {FOOTER_BOTTOM}px;
  margin: 0; font-size: 15px; line-height: 1.4; color: var(--muted);
}}
.plate {{ position: absolute; }}
.plate svg {{ display: block; width: 100%; height: 100%; }}
</style></head>
<body>
<div class="card">
  <p class="kicker">{html.escape(card.kicker)}</p>
  <h1>{html.escape(card.title)}</h1>
  <p class="lead">{html.escape(lead)}</p>
</div>
{plate}
<div class="rule"></div>
<p class="footer">{html.escape(card.footer)}</p>
</body></html>
"""


# ------------------------------------------------------------------ fitting


def _block_boxes(page_box):
    out = []
    stack = [page_box]
    while stack:
        box = stack.pop()
        if type(box).__name__ == "BlockBox":
            lines = sum(1 for child in (getattr(box, "children", None) or [])
                        if type(child).__name__ == "LineBox")
            if lines:
                out.append((box, lines))
        stack.extend(getattr(box, "children", None) or [])
    return out


def _box_class(box) -> str:
    element = getattr(box, "element", None)
    if element is None:
        return ""
    try:
        return element.get("class") or ""
    except AttributeError:
        return ""


def measure(document) -> dict:
    """What the layout produced: line counts and the bottom of the text."""
    page = document.pages[0]
    found = {"title": None, "lead": None, "kicker": None}
    for box, lines in _block_boxes(page._page_box):
        tag = getattr(box, "element_tag", None)
        cls = _box_class(box)
        if tag == "h1":
            found["title"] = (box, lines)
        elif "lead" in cls.split():
            found["lead"] = (box, lines)
        elif "kicker" in cls.split():
            found["kicker"] = (box, lines)
    if found["title"] is None or found["lead"] is None:
        raise ShareCardError("the card layout produced no title or lead box")

    bottom = max(
        found[key][0].position_y + found[key][0].height
        for key in ("title", "lead", "kicker") if found[key] is not None
    )
    right = max(
        found[key][0].position_x + found[key][0].width
        for key in ("title", "lead", "kicker") if found[key] is not None
    )
    left = min(
        found[key][0].position_x
        for key in ("title", "lead", "kicker") if found[key] is not None
    )
    title = found["title"][0]
    lead_box = found["lead"][0]
    last_line = [child for child in (lead_box.children or [])
                 if type(child).__name__ == "LineBox"][-1]
    last_width = max((child.position_x + child.width for child in last_line.children),
                     default=0) - last_line.position_x
    fill = last_width / lead_box.width if lead_box.width else 0
    return {
        "title_lines": found["title"][1],
        "lead_lines": found["lead"][1],
        "lead_fill": round(fill, 3),
        "title_bottom": round(title.position_y + title.height, 2),
        "content_bottom": round(bottom, 2),
        "content_right": round(right, 2),
        "content_left": round(left, 2),
    }


def rule_top() -> float:
    return CARD_H - RULE_BOTTOM - RULE_H


def fits(metrics: dict) -> bool:
    return (
        metrics["title_lines"] <= MAX_TITLE_LINES
        and metrics["lead_lines"] <= MAX_LEAD_LINES
        and metrics["content_bottom"] <= rule_top() - CONTENT_GAP
        and metrics["content_left"] >= MARGIN_X - 0.5
    )


def display_width(text: str) -> int:
    """Preview width in Latin-character units: a CJK glyph counts as two."""
    return sum(2 if ord(char) > 0x2E80 else 1 for char in text)


def describe(text: str, limit: int = 160) -> str:
    """A one-sentence description that fits a preview without cutting a word."""
    text = " ".join(str(text or "").split())
    if display_width(text) <= limit:
        return text
    total = 0
    for index, char in enumerate(text):
        total += 2 if ord(char) > 0x2E80 else 1
        if total > limit - 2:
            return trim(text, index + 1)
    return text


def trim(text: str, limit: int) -> str:
    """Shorten a lead at a word or sentence boundary; never mid-character."""
    if limit <= 0 or len(text) <= limit:
        return text
    cut = text[:limit]
    # Sentence ends first, then clauses, then spaces: the latest boundary of
    # the strongest kind is the one a reader expects the cut at.
    for mark in ("。", "！", "？", ".", "!", "?", "；", ";", "，", ",", "、", " "):
        index = cut.rfind(mark)
        if index >= limit // 2:
            head = cut[:index].rstrip()
            # A sentence that ends where it ends needs no ellipsis; a clause
            # that stops mid-thought does.
            if cut[index] in "。！？.!?":
                return head + cut[index]
            return head + "…"
    return cut.rstrip() + "…"


def _layout(card: Card, rung: int, lead: str, offset: float = 0.0,
            lead_w: int | None = None):
    from weasyprint import HTML

    document = HTML(string=compose(card, rung=rung, lead=lead, offset=offset,
                                   lead_w=lead_w),
                    base_url=str(ROOT)).render()
    return document, measure(document)


def _balanced(card: Card, rung: int, lead: str):
    """Narrow the lead until its last line is not a widow.

    The widest measure that leaves a short last line is what produces
    `…生成的阅 / 读页。` on the Chinese card: two characters alone on a line.
    The renderer cannot rebalance the block (`text-wrap: balance` is not
    implemented), so the measure is stepped down until the last line holds at
    least a quarter of the column. The widest such measure wins, so the lead
    never narrows more than the line break requires.
    """
    width = LEAD_W
    while True:
        document, metrics = _layout(card, rung, lead, lead_w=width)
        settled = (
            metrics["lead_lines"] <= 1
            or metrics["lead_fill"] >= WIDOW_FILL
            or width - LEAD_W_STEP < LEAD_W_MIN
        )
        if settled:
            return width, document, metrics
        width -= LEAD_W_STEP


def _settle(card: Card, rung: int, lead: str, truncated: bool):
    """Apply the lead measure and keep the rung valid."""
    width, document, metrics = _balanced(card, rung, lead)
    if not fits(metrics):
        document, metrics = _layout(card, rung, lead)
        width = LEAD_W
    return document, rung, lead, width, metrics, truncated


def fit(card: Card) -> tuple[object, int, str, int, dict, bool]:
    """The composition, chosen by measurement.

    The title picks the rung, not the lead: the title is the message, so it
    keeps the largest size it can hold in three lines and the lead shortens
    around it. Choosing the rung by whichever text fits first shrank a card
    with a one-word title to the floor because its sentence was long.
    """
    attempts = []
    for rung in range(len(RUNGS)):
        document, metrics = _layout(card, rung, card.description)
        attempts.append((rung, document, metrics))
        if fits(metrics):
            return _settle(card, rung, card.description, False)

    usable = [item for item in attempts
              if item[2]["title_lines"] <= MAX_TITLE_LINES
              and item[2]["title_bottom"] <= rule_top() - CONTENT_GAP]
    if not usable:
        # The title alone is too tall at every rung: shorten the title's
        # composition by dropping to the floor and shortening the lead to
        # nothing, which leaves a single oversized title as the only failure.
        rung = len(RUNGS) - 1
        for limit in LEAD_TRIMS:
            lead = trim(card.description, limit)
            document, metrics = _layout(card, rung, lead)
            if metrics["title_lines"] <= MAX_TITLE_LINES:
                return _settle(card, rung, lead, lead != card.description)
        raise ShareCardError(
            f"the title does not fit at the floor: {card.title!r} "
            f"({metrics['title_lines']} line(s))")

    rung, document, metrics = usable[0]
    for limit in LEAD_TRIMS:
        lead = trim(card.description, limit)
        document, metrics = _layout(card, rung, lead)
        if fits(metrics):
            return _settle(card, rung, lead, lead != card.description)
    lead = trim(card.description, LEAD_TRIMS[-1])
    return _settle(card, rung, lead, True)


# ------------------------------------------------------------------ render


@contextmanager
def reproducible():
    """Pin the PDF's creation date so two builds produce the same bytes."""
    previous = os.environ.get("SOURCE_DATE_EPOCH")
    os.environ["SOURCE_DATE_EPOCH"] = "0"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
        else:
            os.environ["SOURCE_DATE_EPOCH"] = previous


def _rasterize(pdf: Path, png: Path) -> None:
    tool = shutil.which("pdftoppm")
    if tool is None:
        raise ShareCardError("pdftoppm is required to rasterize the share card (poppler)")
    subprocess.run(
        [tool, "-r", "96", "-png", "-singlefile", str(pdf), str(png.with_suffix(""))],
        check=True, capture_output=True,
    )


def render(card: Card, target: Path) -> dict:
    """Compose, fit, render and rasterize one card; return what it recorded."""
    document, rung, lead, lead_w, metrics, truncated = fit(card)
    # Centre the block between the top margin and the rule. The offset is
    # measured, not guessed: the layout already knows how tall the block is.
    available = rule_top() - CONTENT_GAP - TEXT_TOP
    height = metrics["content_bottom"] - TEXT_TOP
    offset = max(0.0, (available - height) / 2)
    if offset > 0.5:
        document, metrics = _layout(card, rung, lead, offset, lead_w)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent, prefix=".card-") as raw:
        work = Path(raw)
        pdf, png = work / "card.pdf", work / "card.png"
        with reproducible():
            document.write_pdf(str(pdf))
        _rasterize(pdf, png)
        staged = work / "staged.png"
        shutil.copy2(png, staged)
        staged.replace(target)
    return {
        "image": target.name,
        "width": CARD_W,
        "height": CARD_H,
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "title_px": RUNGS[rung][0],
        "lead_px": RUNGS[rung][1],
        "title_lines": metrics["title_lines"],
        "lead_lines": metrics["lead_lines"],
        "lead_fill": metrics["lead_fill"],
        "lead_w": lead_w,
        "content_bottom": metrics["content_bottom"],
        "truncated": truncated,
        "description": lead,
    }


def ink_box(png: Path) -> tuple[int, int, int, int]:
    """The bounding box of everything drawn on the card, in pixels."""
    from PIL import Image, ImageChops

    image = Image.open(png).convert("RGB")
    background = Image.new("RGB", image.size, image.getpixel((4, 4)))
    diff = ImageChops.difference(image, background).convert("L")
    box = diff.point(lambda value: 255 if value > 8 else 0).getbbox()
    if box is None:
        raise ShareCardError(f"{png.name} is blank")
    return box


# ------------------------------------------------------------------- inputs


def card_from_page(page: dict, *, surface: str, ink: str, secondary: str,
                   muted: str, accent: str, plate: str | None = None,
                   stack: str | None = None) -> Card:
    """A module or series page as a card. Missing values degrade, never guess."""
    return Card(
        kicker=str(page.get("kicker") or ""),
        title=str(page.get("title") or ""),
        description=str(page.get("description") or ""),
        footer=str(page.get("footer") or ""),
        language=str(page.get("language") or "en"),
        surface=surface, ink=ink, secondary=secondary, muted=muted, accent=accent,
        plate=plate, **({"stack": stack} if stack else {}),
    )


def colours(root_css: str) -> dict[str, str]:
    """The roles every card needs, read from the theme the page uses."""
    values = {name: value.strip() for name, value in _VAR.findall(root_css)}
    wanted = {
        "surface": "color-surface-page",
        "ink": "color-text-primary",
        "secondary": "color-text-secondary",
        "muted": "color-text-muted",
        "accent": "color-accent-brand",
    }
    missing = [css for css in wanted.values() if css not in values]
    if missing:
        raise ShareCardError(f"the theme is missing {', '.join('--' + name for name in missing)}")
    return {key: values[css] for key, css in wanted.items()}


def share_meta(*, title: str, description: str, url: str | None, image: str | None,
               image_alt: str, site: str, locale: str, kind: str,
               canonical: str | None = None, theme_color: str | None = None,
               with_description: bool = True,
               image_base: str | None = None,
               version: str | None = None) -> list[str]:
    """The head block a link preview reads.

    `image` is relative to `url`, which is what makes one card work for a page
    and the file that sits next to it. Absolute addresses are only emitted when
    the origin is known: a relative `og:url` is worse than none, because a
    crawler resolves it against its own path.

    `version` is the image's content digest. Platforms cache by URL, so a card
    that changes while its URL does not is a card they keep showing the old
    version of; the digest is the only thing that makes the change visible.
    """
    hero = bool(url and image)
    lines = []
    if with_description:
        lines.append(f'<meta name="description" content="{html.escape(description, quote=True)}">')
    lines += [
        f'<meta property="og:type" content="{kind}">',
        f'<meta property="og:site_name" content="{html.escape(site, quote=True)}">',
        f'<meta property="og:title" content="{html.escape(title, quote=True)}">',
        f'<meta property="og:description" content="{html.escape(description, quote=True)}">',
        f'<meta property="og:locale" content="{locale}">',
        f'<meta name="twitter:card" content="{"summary_large_image" if hero else "summary"}">',
        f'<meta name="twitter:title" content="{html.escape(title, quote=True)}">',
        f'<meta name="twitter:description" content="{html.escape(description, quote=True)}">',
    ]
    if url:
        lines.append(f'<meta property="og:url" content="{html.escape(url, quote=True)}">')
        lines.append(f'<link rel="canonical" href="{html.escape(canonical or url, quote=True)}">')
    if url and image:
        base = (image_base or url).rstrip("/")
        absolute = image if image.startswith(("http://", "https://")) else f"{base}/{image.lstrip('/')}"
        if version and "?" not in absolute:
            absolute = f"{absolute}?v={version}"
        lines += [
            f'<meta property="og:image" content="{html.escape(absolute, quote=True)}">',
            f'<meta property="og:image:width" content="{CARD_W}">',
            f'<meta property="og:image:height" content="{CARD_H}">',
            '<meta property="og:image:type" content="image/png">',
            f'<meta property="og:image:alt" content="{html.escape(image_alt, quote=True)}">',
            f'<meta name="twitter:image" content="{html.escape(absolute, quote=True)}">',
        ]
    if theme_color:
        lines.append(f'<meta name="theme-color" content="{theme_color}">')
    return lines


def locale_for(language: str) -> str:
    return "zh_CN" if language.lower().startswith("zh") else "en_US"


# ------------------------------------------------------------------- head

META_START = "<!-- folio-meta:start -->"
META_END = "<!-- folio-meta:end -->"
CANONICAL = re.compile(r'<link rel="canonical" href="[^"]*">')


def page_url(origin: str, path: str | None) -> str:
    """The page's own address; a directory index keeps the clean URL."""
    path = (path or "").lstrip("/")
    return f"{origin}/" if path in ("", "index.html") else f"{origin}/{path}"


def page_head(source: Path) -> tuple[str, str]:
    """The title and description a page already carries, unescaped."""
    text = source.read_text(encoding="utf-8")
    title = re.search(r"<title>(.*?)</title>", text, re.S)
    description = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', text)
    return (
        html.unescape(title.group(1).strip()) if title else "",
        html.unescape(description.group(1)) if description else "",
    )


def meta_block(lines: list[str], indent: str = "  ") -> str:
    """The block, delimited so a later build owns it and a check can read it."""
    body = "\n".join(indent + line for line in lines)
    return f"{indent}{META_START}\n{body}\n{indent}{META_END}"


def apply_meta(source: Path, block: str, *, check: bool) -> tuple[bool, str]:
    """Write the block into a page's head, or report drift. Returns (ok, what)."""
    text = source.read_text(encoding="utf-8")
    start, end = text.find(META_START), text.find(META_END)
    if 0 <= start < end:
        head = text.rfind("\n", 0, start) + 1
        tail = text.find("\n", end)
        updated = text[:head] + block + text[tail if tail >= 0 else len(text):]
        action = "matches"
    else:
        anchor = re.search(r"<title>.*?</title>[ \t]*\n", text, re.S)
        if anchor is None:
            raise ShareCardError(f"{source.name}: no <title> to anchor the head block")
        updated = text[:anchor.end()] + block + "\n" + text[anchor.end():]
        action = "added"
    if updated == text:
        return True, "matches"
    if check:
        return False, "differs"
    source.write_text(updated, encoding="utf-8")
    return True, "written" if action == "matches" else "added"


def apply_canonical(source: Path, url: str, *, check: bool) -> tuple[bool, str]:
    """Point a redirect stub's canonical at its target, absolutely."""
    text = source.read_text(encoding="utf-8")
    if not CANONICAL.search(text):
        raise ShareCardError(f"{source.name}: no canonical link to rewrite")
    updated = CANONICAL.sub(
        f'<link rel="canonical" href="{html.escape(url, quote=True)}">', text, count=1)
    if updated == text:
        return True, "matches"
    if check:
        return False, "differs"
    source.write_text(updated, encoding="utf-8")
    return True, "written"


# --------------------------------------------------------------------- site


def png_size(path: Path) -> tuple[int, int]:
    """Width and height from the PNG header, so the check needs no decoder."""
    with path.open("rb") as handle:
        head = handle.read(24)
    if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        raise ShareCardError(f"{path.name}: not a PNG")
    return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")


def site_meta(page: dict, *, site: str, origin: str, palette: dict[str, str],
              version: str) -> list[str]:
    """One homepage's head block, from the page's own title and description."""
    title, description = page_head(ROOT / page["file"])
    return share_meta(
        title=title or page["title"],
        description=description or page["description"],
        url=page_url(origin, page.get("path")),
        image=page["out"],
        image_alt=page.get("image_alt") or page["title"],
        site=site,
        locale=locale_for(page["language"]),
        kind="website",
        theme_color=palette["surface"],
        # The homepage keeps its own description tag; the block must not grow
        # a second one.
        with_description=False,
        image_base=f"{origin}/",
        version=version,
    )


def site_record(page: dict, record: dict) -> dict:
    """What the card was made of.

    The manifest records the card's own inputs, not just its digest: a digest
    alone says the file is intact, not that it still says what the page says.
    """
    return {
        "page": page["file"],
        "image": page["out"],
        "title": page["title"],
        "source_description": page["description"],
        "description": record["description"],
        "width": record["width"],
        "height": record["height"],
        "sha256": record["sha256"],
        "title_px": record["title_px"],
        "lead_px": record["lead_px"],
        "lines": {"title": record["title_lines"], "lead": record["lead_lines"]},
        "lead_w": record["lead_w"],
        "truncated": record["truncated"],
    }


def manifest_text(cards: list[dict]) -> str:
    return json.dumps({"cards": cards}, ensure_ascii=False, indent=2) + "\n"


def stale_reasons(entry: dict | None, page: dict, digest: str) -> list[str]:
    """Why a card on disk is not the card this page's words would draw."""
    if entry is None:
        return ["no manifest entry for it"]
    reasons = []
    if entry.get("sha256") != digest:
        reasons.append("the image changed since the manifest was written")
    if (entry.get("width"), entry.get("height")) != (CARD_W, CARD_H):
        reasons.append(f"the manifest records {entry.get('width')}x{entry.get('height')}")
    if entry.get("title") != page["title"]:
        reasons.append("the title changed since the card was drawn")
    if entry.get("source_description") != page["description"]:
        reasons.append("the description changed since the card was drawn")
    return reasons


def site_cards(config: Path = SITE_FILE, *, check: bool = False,
               heads: bool = False) -> int:
    """Render the pages a reader opens directly (the two homepages).

    `check` re-renders and compares bytes; `heads` trusts the file on disk and
    checks that the head and the manifest still describe it. The second is what
    a portable gate can run: text layout is deterministic, but the rasterizer
    that turns the PDF into a PNG is not guaranteed to agree across platforms,
    so bytes are compared where the card was authored and the recorded inputs
    everywhere.
    """
    data = json.loads(config.read_text(encoding="utf-8"))
    origin = data["origin"].rstrip("/")
    # The homepages carry their colours in `styles.css`, already baked from the
    # theme. Reading the stylesheet is what keeps the card and the page one
    # system; a colour written into this config would be a second source.
    site_css = (ROOT / data["stylesheet"]).read_text(encoding="utf-8")
    palette = colours(site_css)
    manifest_path = ROOT / data["manifest"] if data.get("manifest") else None
    recorded: dict[str, dict] | None = None
    if heads and manifest_path is not None:
        if manifest_path.is_file():
            recorded = {card["image"]: card for card in
                        json.loads(manifest_path.read_text(encoding="utf-8"))["cards"]}
        else:
            recorded = {}
    cards: list[dict] = []
    failures = 0
    for page in data["pages"]:
        target = ROOT / page["out"]
        source = ROOT / page["file"]
        if heads:
            if not target.is_file():
                print(f"ERROR: {page['out']} is missing; run without --check-heads")
                failures += 1
                continue
            try:
                width, height = png_size(target)
            except ShareCardError as exc:
                print(f"ERROR: {exc}")
                failures += 1
                continue
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            version = digest[:8]
            if (width, height) != (CARD_W, CARD_H):
                print(f"ERROR: {page['out']} is {width}x{height}, "
                      f"expected {CARD_W}x{CARD_H}")
                failures += 1
            reasons = stale_reasons(recorded.get(page["out"]), page, digest) \
                if recorded is not None else []
            if reasons:
                print(f"ERROR: {page['out']} is stale: {'; '.join(reasons)}")
                failures += 1
            elif (width, height) == (CARD_W, CARD_H):
                print(f"OK: {page['out']} {width}x{height} sha {version}")
        else:
            card = Card(
                kicker=page["kicker"], title=page["title"], description=page["description"],
                footer=page["footer"], language=page["language"],
                stack=embedded_stack(stack_of(site_css, Card.stack, page["language"])),
                **palette,
            )
            if check:
                with tempfile.TemporaryDirectory(prefix="share-") as raw:
                    staged = Path(raw) / page["out"].split("/")[-1]
                    record = render(card, staged)
                    current = (hashlib.sha256(target.read_bytes()).hexdigest()
                               if target.is_file() else "")
                same = current == record["sha256"]
                print(f"{'OK' if same else 'ERROR'}: {page['out']} "
                      f"{'matches' if same else 'differs'} (sha {record['sha256'][:12]})")
                failures += 0 if same else 1
            else:
                record = render(card, target)
                print(f"OK: wrote {page['out']} ({record['width']}x{record['height']}, "
                      f"title {record['title_px']}px, sha {record['sha256'][:12]})")
            version = record["sha256"][:8]
            cards.append(site_record(page, record))

        lines = site_meta(page, site=data["site_name"], origin=origin,
                          palette=palette, version=version)
        ok, action = apply_meta(source, meta_block(lines), check=check or heads)
        print(f"{'OK' if ok else 'ERROR'}: {page['file']} head {action}")
        failures += 0 if ok else 1

    if manifest_path is not None and not heads:
        text = manifest_text(cards)
        if check:
            current = manifest_path.read_text(encoding="utf-8") if manifest_path.is_file() else ""
            same = current == text
            print(f"{'OK' if same else 'ERROR'}: {data['manifest']} "
                  f"{'matches' if same else 'differs'}")
            failures += 0 if same else 1
        else:
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(text, encoding="utf-8")
            print(f"OK: wrote {data['manifest']}")

    for redirect in data.get("redirects", []):
        source = ROOT / redirect["file"]
        target_url = page_url(origin, redirect["to"])
        ok, action = apply_canonical(source, target_url, check=check or heads)
        print(f"{'OK' if ok else 'ERROR'}: {redirect['file']} canonical {action} -> {target_url}")
        failures += 0 if ok else 1

    if not (check or heads):
        print(f"OK: {len(data['pages'])} site card(s) at {origin}")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--site", action="store_true", help="render the site's own share cards")
    parser.add_argument("--check", action="store_true", help="compare bytes, write nothing")
    parser.add_argument("--check-heads", action="store_true",
                        help="check the head against the card on disk; render nothing")
    parser.add_argument("--config", type=Path, default=SITE_FILE)
    args = parser.parse_args(argv)
    if not args.site:
        parser.print_help()
        return 2
    if args.check and args.check_heads:
        parser.error("--check and --check-heads are alternatives")
    try:
        return site_cards(args.config, check=args.check, heads=args.check_heads)
    except ShareCardError as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
