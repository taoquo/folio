#!/usr/bin/env python3
"""Build a local, offline canvas-policy review with real compiler/host results.

Visual thesis: parchment workbench, coral status accents, diagrams as the focal content.
Content: host before/after, full-size artifacts, chart density, executable boundary checks.
Interaction: scenario tabs, native-size/fit toggle, short state transitions with reduced motion.
"""
from __future__ import annotations

import json
from html import escape
from pathlib import Path
from shutil import copy2
from tempfile import TemporaryDirectory

from drawing.compiler import DEFAULT_COMPILER_REGISTRY
from drawing.hosting import embed_html_figure, host_contract, host_fit_report, svg_min_font_size
from drawing.schema_registry import schema_contract
from drawing.validation.models import DrawingCompilationError
from renderers.svg import render_svg

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "build" / "canvas"
ASSETS = OUTPUT / "review"
TEMPLATE = ROOT / "scripts" / "templates" / "canvas-review.html"


def architecture(rows: int, per_row: int, mode: str) -> dict:
    tiers = ["Access", "Gateway", "Identity", "Planning", "Execution", "Tools",
             "Events", "Memory", "Storage", "Search", "Analytics", "Operations"]
    return {
        "schema_version": "3.0", "kind": "architecture", "title": "Agent Platform",
        "layout": "horizontal-layers", "canvas": mode, "focus": "n0",
        "layers": [{"id": f"L{i}", "label": f"L{i + 1:02d}"} for i in range(rows)],
        "nodes": [{"id": f"n{i * per_row + j}", "kind": "service", "label": f"{tiers[i % len(tiers)]} {j + 1}",
                   "layer": f"L{i}"} for i in range(rows) for j in range(per_row)],
        "edges": [{"source": f"n{i * per_row + j}", "target": f"n{(i + 1) * per_row + j}",
                   "kind": "primary"} for i in range(rows - 1) for j in range(per_row)],
    }


def chart(kind: str, count: int, mode: str) -> dict:
    payload = schema_contract(kind).load_canonical_payload()
    field = "tasks" if kind == "gantt" else "rows"
    base = payload[field]
    payload[field] = [{**base[i % len(base)], "id": f"row{i}", "label": f"Workstream {i + 1}", "emphasis": "normal"}
                      for i in range(count)]
    payload.pop("height", None)
    payload.pop("focus", None)
    payload["canvas"] = mode
    return payload


def compile_asset(name: str, payload: dict) -> tuple[object, Path]:
    fixture = ASSETS / f"{name}.json"
    fixture.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
    (ASSETS / f"{name}.svg").write_text(render_svg(result.scene, "artifact", namespace=name), encoding="utf-8")
    return result, fixture


def compile_error(payload: dict) -> str:
    try:
        DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
    except DrawingCompilationError as exc:
        return str(exc)
    raise AssertionError("negative review case unexpectedly compiled")


def build() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    previous = OUTPUT / "index.html"
    backup = OUTPUT / "before-implementation.html"
    if previous.is_file() and not backup.exists():
        copy2(previous, backup)
    overview, overview_path = compile_asset("overview", architecture(2, 3, "figure"))
    poster, poster_path = compile_asset("poster-60", architecture(12, 5, "poster"))
    large, _ = compile_asset("poster-100", architecture(20, 5, "poster"))
    gantt, _ = compile_asset("gantt-20", chart("gantt", 20, "poster"))
    heatmap, _ = compile_asset("heatmap-20", chart("heatmap", 20, "poster"))
    compile_asset("gantt-10", chart("gantt", 10, "figure"))
    checks = []
    for label, payload in [
        ("figure · 10 个节点", architecture(2, 5, "figure")),
        ("poster · 自动高度超限", architecture(60, 5, "poster")),
        ("poster · 40 节点 / 540 高度", {**architecture(8, 5, "poster"), "height": 540}),
        ("gantt · 45 行超限", chart("gantt", 45, "poster")),
    ]:
        checks.append({"case": label, "outcome": "REJECTED", "diagnostic": compile_error(payload)})
    source_text = '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Figure host</title><style>@page{size:A4;margin:20mm 22mm 22mm}body{font:12pt Georgia,serif;background:#F6F0EA;color:#191514}figure{margin:0;break-inside:avoid}figcaption{font-size:10pt;margin-top:8pt}</style></head><body><h1>Agent Platform Overview</h1><p>A bounded overview links to the separate full platform diagram.</p><figure data-folio-diagram-slot="main"></figure></body></html>'
    with TemporaryDirectory(prefix="folio-canvas-host-") as temp:
        source = Path(temp) / "source.html"
        source.write_text(source_text, encoding="utf-8")
        rejection = ""
        for contract in ("a4-portrait", "letter-portrait", "responsive-html"):
            try:
                embed_html_figure(poster, fixture=poster_path, host_file=source,
                    output_host=ASSETS / "rejected.html", artifact_dir=ASSETS / "rejected-assets",
                    contract_key=contract, slot="main",
                    caption="The complete platform needs a separate artifact with full-size access.")
            except ValueError as exc:
                if contract == "a4-portrait":
                    rejection = str(exc)
                checks.append({"case": f"poster → {contract}", "outcome": "REJECTED", "diagnostic": str(exc)})
            else:
                raise AssertionError("poster embedding unexpectedly succeeded")
        manifest = embed_html_figure(overview, fixture=overview_path, host_file=source,
            output_host=ASSETS / "a4-overview.html", artifact_dir=ASSETS / "host-assets",
            contract_key="a4-portrait", slot="main",
            caption="The bounded overview keeps access and gateway responsibilities distinct; the complete system is a separate artifact.")
    minimum = svg_min_font_size(render_svg(large.scene, "artifact"))
    old_scale = min(166 / large.scene.width, 140.25 / large.scene.height)
    old_font = minimum * old_scale * 72 / 25.4
    try:
        host_fit_report(960, 1600, 7, 166, 140.25, host_contract("a4-portrait"))
    except ValueError as exc:
        checks.append({"case": "figure · 高度驱动的过度缩小", "outcome": "REJECTED", "diagnostic": str(exc)})
    report = {
        "comparison": "Existing prototype retained in before-implementation.html; old host panel is a contain-fit illustration, not a historical PDF screenshot.",
        "poster": {"nodes": 60, "height": poster.scene.height, "warnings": [str(d) for d in poster.diagnostics]},
        "gantt_height": gantt.scene.height, "heatmap_height": heatmap.scene.height,
        "host": manifest, "checks": checks,
    }
    (ASSETS / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rows = "\n".join(f'<tr><td>{escape(item["case"])}</td><td>已拒绝</td><td><code>{escape(item["diagnostic"])}</code></td></tr>' for item in checks)
    html = TEMPLATE.read_text(encoding="utf-8")
    values = {"@@CHECK_ROWS@@": rows, "@@OLD_FONT@@": f"{old_font:.2f}",
              "@@FIGURE_FONT@@": str(manifest["placement"]["fit"]["min_font_size"]),
              "@@POSTER_ERROR@@": escape(rejection),
              "@@POSTER_WARNINGS@@": escape("\n".join(str(d) for d in poster.diagnostics)),
              "@@OLD_LINK@@": '<a href="before-implementation.html">保留的旧预览</a>' if backup.exists() else ""}
    for key, value in values.items():
        html = html.replace(key, value)
    if "@@" in html:
        raise ValueError("unfilled canvas review template token")
    previous.write_text(html, encoding="utf-8")
    print(f"OK: wrote {previous}")


if __name__ == "__main__":
    build()
