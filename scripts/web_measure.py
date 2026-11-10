#!/usr/bin/env python3
"""Measure a built Web page in a real browser.

The page is a browser artifact, so the only honest measurement is the browser's
own. This module serves `dist/web`, opens each page at the widths the contract
names, and records what the renderer decided: computed type, box widths, line
counts, spacing between blocks, and overflow.

It is the oracle `web_verify.py` checks the layout plan against. It never
decides whether a value is right; it reports what happened. The fast gate does
not use it: a browser cannot run on every push, so the plan is verified by
arithmetic there and by this module in the nightly job.

    web_measure.py --series attention
    web_measure.py --series attention --viewports 390,768 --out /tmp/m.json

WeasyPrint is deliberately not used. It is a print formatter: it ignores
`@media (min-width/max-width)` and applies `@media print` instead, so it cannot
see the responsive layer this engine is about.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import socketserver
import sys
import threading
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

# The widths a page is reviewed at. They are test widths, not CSS breakpoints;
# the breakpoints live in the Web profile and are tested at their boundaries by
# `web_verify.py`.
DEFAULT_VIEWPORTS = (390, 768, 1024, 1414)

# What to read, by the role it plays in the engine. A selector that matches
# nothing is reported as absent instead of skipped, so a renamed class cannot
# quietly stop being measured.
TYPE_TARGETS = {
    "h1": "h1",
    "h2": "h2",
    "h3": "h3",
    "body": "body",
    "lead": ".lead",
    "reading": ".chapter p",
    "caption": "figcaption",
    "label": ".src-note",
    "code": ".chapter code",
    "kpi": ".kpi-row .v",
    "table-cell": ".tbl td",
    "rail": ".rail a .label",
}

BOX_TARGETS = {
    "page": ".page",
    "chapter": ".chapter",
    "prose": ".chapter p",
    "list": ".chapter ul",
    "figure": ".figure",
    "figure-svg": ".figure svg",
    "table": ".tbl-wrap",
    "kpi-row": ".kpi-row",
}

# Top-level blocks inside a chapter, measured for vertical rhythm.
BLOCK_SELECTOR = ".chapter > h2, .chapter > h3, .chapter > p, .chapter > ul, " \
                 ".chapter > div, .chapter > table, .chapter > figure"


class _Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args: Any) -> None:  # keep the CLI output clean
        return


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def serve(directory: Path) -> tuple[_Server, str]:
    """Serve `directory` on a loopback port and return the server and its base URL."""
    handler = functools.partial(_Handler, directory=str(directory))
    server = _Server(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


MEASURE_JS = r"""
(args) => {
  const { typeTargets, boxTargets, blockSelector } = args;

  function typeOf(selector) {
    const el = document.querySelector(selector);
    if (!el) return null;
    const s = getComputedStyle(el);
    return {
      size: parseFloat(s.fontSize),
      leading: s.lineHeight === "normal" ? null : parseFloat(s.lineHeight),
      weight: parseInt(s.fontWeight, 10),
      tracking: s.letterSpacing === "normal" ? null : parseFloat(s.letterSpacing),
      family: s.fontFamily,
    };
  }

  // A figure carries one plate per class and CSS hides all but one, so the
  // first match is not always the box the reader sees. A hidden element has no
  // box at all, which is the rule this follows.
  function firstVisible(selector) {
    return [...document.querySelectorAll(selector)]
      .find((el) => getComputedStyle(el).display !== "none") || null;
  }

  function boxOf(selector) {
    const el = firstVisible(selector);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return {
      width: +r.width.toFixed(2),
      height: +r.height.toFixed(2),
      left: +r.left.toFixed(2),
      right: +r.right.toFixed(2),
      contentWidth: +(
        el.clientWidth - parseFloat(getComputedStyle(el).paddingLeft)
        - parseFloat(getComputedStyle(el).paddingRight)
      ).toFixed(2),
      scrollWidth: el.scrollWidth,
      clientWidth: el.clientWidth,
    };
  }

  // A paragraph's lines are its text ranges: one client rect per line.
  function linesOf(el) {
    const ranges = [];
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      if (!node.nodeValue.trim()) continue;
      const range = document.createRange();
      range.selectNodeContents(node);
      for (const rect of range.getClientRects()) {
        if (rect.width > 0.5) ranges.push(rect);
      }
    }
    // One row per line. A line is not one top coordinate: a subscript sits a
    // few pixels low and a superscript a few high, and keying on the rounded
    // top turned every `x_i` into a line of its own. Anything within half a
    // line box of a row belongs to that row.
    const rows = [];
    for (const rect of ranges) {
      let row = rows.find((item) => Math.abs(item.top - rect.top) < 12);
      if (!row) {
        row = { top: rect.top, left: rect.left, right: rect.right };
        rows.push(row);
      }
      row.left = Math.min(row.left, rect.left);
      row.right = Math.max(row.right, rect.right);
    }
    const ordered = rows.sort((a, b) => a.top - b.top);
    const text = el.textContent.replace(/\s+/g, " ").trim();
    const characters = [...text].length;
    // A line holds about half as many Han characters as Latin ones, so a
    // character count means nothing without knowing which script it counted.
    const han = (text.match(/[㐀-䶿一-鿿豈-﫿]/g) || []).length;
    return {
      count: ordered.length,
      widths: ordered.map((r) => +(r.right - r.left).toFixed(2)),
      characters,
      han,
    };
  }

  // A paragraph's role is the block that owns it. A pull quote's sentence is
  // the quote's content, not a paragraph of the running text, and the checker
  // must not ask it to reach the column the way running prose does.
  const ownedRole = (el) => {
    if (el.getAttribute("data-folio-role")) return el.getAttribute("data-folio-role");
    const block = el.closest("[data-folio-role]");
    return block ? block.getAttribute("data-folio-role") : "paragraph";
  };

  const paragraphs = [...document.querySelectorAll(".chapter p")].slice(0, 8).map((el, i) => ({
    index: i,
    role: ownedRole(el),
    lines: linesOf(el),
    width: +el.getBoundingClientRect().width.toFixed(2),
  }));

  // A caption belongs to the plate above it, so its own left edge is measured
  // against that plate's. A note that has wandered into the margin is still
  // the same words; only the left edge says it has left the drawing.
  const captions = [...document.querySelectorAll("figure figcaption, .tbl caption")]
    .map((el, i) => {
      const rect = el.getBoundingClientRect();
      const plate = el.closest("figure") || el.closest("table");
      const plateRect = (plate || el).getBoundingClientRect();
      return {
        index: i,
        tag: el.tagName.toLowerCase(),
        lines: linesOf(el),
        width: +rect.width.toFixed(2),
        left: +rect.left.toFixed(2),
        plate_left: +plateRect.left.toFixed(2),
        plate_width: +plateRect.width.toFixed(2),
      };
    });

  // The colours a reader actually sees, with the background each one sits on.
  // A translucent background is resolved by walking up to the first opaque
  // ancestor, which is the only way a ratio computed here means anything.
  function backgroundOf(el) {
    let node = el;
    while (node && node !== document.documentElement) {
      const colour = getComputedStyle(node).backgroundColor;
      const parts = colour.match(/[\d.]+/g);
      if (parts && (parts.length < 4 || parseFloat(parts[3]) > 0.99)) return colour;
      node = node.parentElement;
    }
    return getComputedStyle(document.body).backgroundColor;
  }

  const colourTargets = {
    "prose": ".chapter p",
    "caption": "figure.figure figcaption",
    "source-note": ".chapter .src-note",
    "chapter-numeral": ".chapter h2 .num",
    "kpi-label": ".kpi .k",
    "table-head": ".tbl th",
  };
  const colours = Object.fromEntries(
    Object.entries(colourTargets).map(([key, selector]) => {
      const el = firstVisible(selector);
      if (!el) return [key, null];
      const s = getComputedStyle(el);
      return [key, {
        colour: s.color,
        background: backgroundOf(el),
        size: parseFloat(s.fontSize),
        weight: parseInt(s.fontWeight, 10),
      }];
    }));

  // Which chapter a block belongs to, so a gap can say whether it sits inside
  // one chapter's flow or crosses the boundary between two. The boundary is a
  // composed rule -- air, padding and a hairline -- not a spacing step.
  const chapters = [...document.querySelectorAll(".chapter")];
  const blocks = [];
  for (const el of document.querySelectorAll(blockSelector)) {
    const r = el.getBoundingClientRect();
    const chapter = el.closest(".chapter");
    blocks.push({
      tag: el.tagName.toLowerCase(),
      role: el.getAttribute("data-folio-role") || el.className || "",
      section: chapter ? chapters.indexOf(chapter) : -1,
      top: +r.top.toFixed(2),
      bottom: +r.bottom.toFixed(2),
      height: +r.height.toFixed(2),
      width: +r.width.toFixed(2),
    });
  }
  const gaps = [];
  for (let i = 1; i < blocks.length; i += 1) {
    gaps.push(+(blocks[i].top - blocks[i - 1].bottom).toFixed(2));
  }

  // Overflow: a table or a formula may scroll on purpose; anything else is a
  // layout defect. The engine decides which, the browser reports which.
  const overflow = [];
  const scrollContainers = [];
  for (const el of document.querySelectorAll("body *")) {
    // Page furniture truncates on purpose (the running label ends in an
    // ellipsis); it is not content the reader has to read in full.
    if (el.closest(".rail, .topbar, .doc-nav")) continue;
    // SVG content is laid out in its own coordinates and scaled by the
    // viewBox: Chromium reports a text run's scrollWidth in one space and its
    // clientWidth in another, which reads as overflow on every upscaled plate.
    // The plate's own box is what can scroll the page, and V-PLAN-03 measures
    // that against the band.
    if (el.ownerSVGElement) continue;
    if (el.scrollWidth <= el.clientWidth + 1 || el.clientWidth <= 0) continue;
    const name = el.tagName.toLowerCase() + (el.className ? "." + String(el.className).split(" ")[0] : "");
    const overflowX = getComputedStyle(el).overflowX;
    const entry = { selector: name, scrollWidth: el.scrollWidth, clientWidth: el.clientWidth, overflowX };
    if (overflowX === "auto" || overflowX === "scroll") scrollContainers.push(entry);
    else overflow.push(entry);
  }

  const fonts = [...document.fonts].map((f) => ({
    family: f.family, status: f.status, weight: f.weight,
  }));

  return {
    viewport: { width: window.innerWidth, height: window.innerHeight },
    document: {
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    },
    types: Object.fromEntries(Object.entries(typeTargets).map(([k, sel]) => [k, typeOf(sel)])),
    boxes: Object.fromEntries(Object.entries(boxTargets).map(([k, sel]) => [k, boxOf(sel)])),
    // A figure carries one plate per class and CSS shows exactly one. The
    // browser is the only place that can say which, and how wide it actually is.
    plates: [...document.querySelectorAll("figure.figure")].map((figure) => {
      const plates = [...figure.querySelectorAll("svg.figure-svg")];
      return {
        id: figure.getAttribute("data-folio-drawing") || "",
        plates: plates.length,
        visible: plates
          .filter((plate) => getComputedStyle(plate).display !== "none")
          .map((plate) => {
            const box = plate.getBoundingClientRect();
            return {
              variant: plate.getAttribute("data-folio-plate") || "",
              width: Math.round(box.width * 100) / 100,
              height: Math.round(box.height * 100) / 100,
            };
          }),
      };
    }),
    paragraphs,
    captions,
    colours,
    blocks,
    gaps,
    overflow,
    scrollContainers,
    fonts,
    counts: {
      chapters: document.querySelectorAll(".chapter").length,
      // Top-level blocks only: a drawing annotates its own internals, and
      // those are the compiler's vocabulary, not the page's.
      blocks: document.querySelectorAll(".chapter > [data-folio-role]").length,
      figures: document.querySelectorAll("figure.figure").length,
      tables: document.querySelectorAll(".tbl-wrap").length,
      lists: document.querySelectorAll(".prose-list").length,
      kpis: document.querySelectorAll(".kpi-row").length,
    },
    title: document.title,
  };
}
"""


def pages_for(dist: Path, series: str) -> list[Path]:
    root = dist / series
    if not root.is_dir():
        raise SystemExit(f"ERROR: no built series at {root}; run build_web.py first")
    return [root / "index.html", *sorted(p for p in root.glob("*/index.html"))]


def launch(playwright: Any) -> Any:
    """A Chromium build: the bundled one when installed, else the user's Chrome."""
    try:
        return playwright.chromium.launch()
    except Exception:
        return playwright.chromium.launch(channel="chrome")


def measure(
    dist: Path,
    series: str,
    viewports: tuple[int, ...] = DEFAULT_VIEWPORTS,
    *,
    settle_ms: int = 120,
) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    dist = Path(dist).resolve()
    server, base = serve(dist)
    result: dict[str, Any] = {
        "series": series,
        "viewports": list(viewports),
        "pages": {},
    }
    try:
        with sync_playwright() as p:
            browser = launch(p)
            result["browser"] = {
                "name": browser.browser_type.name,
                "version": browser.version,
            }
            for page_path in pages_for(dist, series):
                relative = page_path.relative_to(dist).as_posix()
                url = f"{base}/{relative}"
                page_metrics: dict[str, Any] = {}
                for width in viewports:
                    # The page has a scroll-driven entrance: blocks below the
                    # fold sit part-way through a translateY, and their
                    # `getBoundingClientRect()` reports where the animation has
                    # moved them, not where the layout put them. That is a
                    # rendering state, not a measurement, so the measured page
                    # is the one a reader who prefers reduced motion gets --
                    # which is the layout the plan describes.
                    context = browser.new_context(
                        viewport={"width": width, "height": 900},
                        device_scale_factor=1,
                        reduced_motion="reduce",
                    )
                    page = context.new_page()
                    page.goto(url, wait_until="load")
                    page.evaluate("document.fonts.ready.then(() => true)")
                    page.wait_for_timeout(settle_ms)
                    metrics = page.evaluate(
                        MEASURE_JS,
                        {
                            "typeTargets": TYPE_TARGETS,
                            "boxTargets": BOX_TARGETS,
                            "blockSelector": BLOCK_SELECTOR,
                        },
                    )
                    metrics["url"] = url
                    page_metrics[str(width)] = metrics
                    context.close()
                result["pages"][relative] = page_metrics
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
    return result


def summary(result: dict[str, Any]) -> list[str]:
    lines = [
        f"{result['series']}: {result['browser']['name']} {result['browser']['version']}",
    ]
    for page, viewports in result["pages"].items():
        lines.append(f"  {page}")
        for width, m in viewports.items():
            body = (m["types"].get("body") or {}).get("size")
            h1 = (m["types"].get("h1") or {}).get("size")
            prose = (m["boxes"].get("prose") or {}).get("width")
            figure = (m["boxes"].get("figure-svg") or {}).get("width")
            lines.append(
                f"    {width:>5}px  body {body}  h1 {h1}  prose {prose}  figure {figure}"
                f"  overflow {len(m['overflow'])}")
    return lines


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--series", required=True)
    parser.add_argument("--dist", type=Path, default=ROOT / "dist" / "web")
    parser.add_argument("--viewports", default=",".join(str(v) for v in DEFAULT_VIEWPORTS),
                        help="comma-separated widths")
    parser.add_argument("--out", type=Path, default=None,
                        help="write the metrics here (default: dist/web/<series>/metrics.json)")
    parser.add_argument("--json", action="store_true", help="print the metrics instead of a table")
    args = parser.parse_args(argv)

    viewports = tuple(int(v) for v in args.viewports.split(",") if v.strip())
    result = measure(args.dist, args.series, viewports)
    out = args.out or (args.dist / args.series / "metrics.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("\n".join(summary(result)))
        print(f"OK: wrote {out}")

    failures = []
    for page, pages in result["pages"].items():
        for width, m in pages.items():
            if m["document"]["scrollWidth"] > m["document"]["clientWidth"] + 1:
                failures.append(f"{page} @{width}: page scrolls horizontally")
            if m["overflow"]:
                names = ", ".join(o["selector"] for o in m["overflow"][:3])
                failures.append(f"{page} @{width}: {len(m['overflow'])} overflowing element(s): {names}")
            broken = [f for f in m["fonts"] if f["status"] == "error"]
            if broken:
                failures.append(f"{page} @{width}: font failed to load: {broken[0]['family']}")
    for failure in failures:
        print(f"ERROR: {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
