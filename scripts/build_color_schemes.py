#!/usr/bin/env python3
"""folio colour scheme explorer

Renders the same documents under several candidate colour schemes and writes a
page where they can be compared and chosen between.

This is an exploration tool, not a production path. Nothing here is wired into
the engine: the schemes live in `references/exploration/color-schemes.yaml`, the
rendering reuses the real document path so what the page shows is what the
engine produces, and the output is a review artifact.

Why render rather than simulate. A swatch grid can show six palettes, but it
cannot show what a palette does to a page: how a heading reads against the
canvas, whether a table header still separates, whether the accent is doing too
much. Those are the questions the choice depends on, so each scheme is applied
to real content and rendered.

The one substitution the templates force. Fourteen page backgrounds are written
`background: #F6F0EA` inside `@page`, where a custom property cannot reach in
this renderer. A colour scheme that changed only the variables would leave every
page on the shipped parchment, so the literal is substituted too -- and the page
says so, because it is a real limitation of the current wiring rather than a
detail of this tool.

Usage:
    python3 scripts/build_color_schemes.py                # write the comparison page
    python3 scripts/build_color_schemes.py --list          # list the schemes
    python3 scripts/build_color_schemes.py --only ink-teal # render one scheme
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import yaml  # noqa: E402

SCHEMES_FILE = ROOT / "references" / "exploration" / "color-schemes.yaml"
OUT_PAGE = ROOT / "docs" / "acceptance" / "color-schemes.html"
SCRATCH = ROOT / "dist" / "color-schemes"

# One document per personality: a sparse one, a data-dense one, a list one.
DOCUMENTS = ("one-pager", "equity-report", "changelog")

# The values the shipped theme uses, so a literal left in a template can be
# traced back to the variable it means.
SHIPPED_VALUES = {
    "#F6F0EA": "parchment",
    "#FBF7F3": "ivory",
    "#E9DED4": "border",
    "#191514": "near-black",
    "#3A312D": "dark-warm",
    "#5A4A43": "olive",
    "#85776F": "stone",
    "#B83D2E": "brand",
    "#F7E6E1": "brand-tint",
    "#F1D2CC": "tag-bg",
    "#E8DED6": "border-soft",
    "#e3baa9": "rule-warm",
}


def load_schemes() -> dict[str, Any]:
    return yaml.safe_load(SCHEMES_FILE.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def document_html(name: str) -> str:
    """The filled, projected HTML the production path would deliver.

    Reusing the real path matters: a scheme comparison built from hand-made
    markup would show this tool's idea of a document rather than the engine's.
    """
    import corpus as _corpus  # noqa: PLC0415
    from document_build import _content_of, _inject, _project, _template_for  # noqa: PLC0415
    from document_ir.bridge import bridge_template, default_map_for  # noqa: PLC0415
    from document_ir.writers.skeleton import attach_ids, fill_template  # noqa: PLC0415

    fixture_path = ROOT / "references" / "fixtures" / "document" / "showcase" / f"showcase-{name}.yaml"
    fixture = _corpus.load_fixture(fixture_path)
    template_text = _template_for(fixture).read_text(encoding="utf-8")
    genre = str(fixture.get("genre", ""))
    language = str(fixture.get("language", "en-US"))

    document = bridge_template(
        template_text,
        _content_of(fixture),
        document_id=name,
        lang=language,
        genre=genre,
        bridge_map=default_map_for(genre, language),
    )
    filled = fill_template(template_text, document)
    html = attach_ids(filled.html, document)
    projected = _project(genre, language, fixture)
    return _inject(html, projected) if projected else html


def apply_scheme(html: str, tokens: dict[str, str]) -> str:
    """Rewrite a document's colours to a scheme.

    Declared variables are replaced in place. Variables the template does not
    declare are appended, so a scheme is complete regardless of which template
    it lands on. Literals that mean a variable are replaced by value.
    """
    # 1. Declared variables, inside their own declarations.
    def replace_declaration(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in tokens:
            return match.group(0)
        return f"--{name}:{match.group(2)}{tokens[name]};"

    html = re.sub(r"--([a-z0-9-]+):(\s*)#[0-9A-Fa-f]{6};", replace_declaration, html)

    # 2. Literals left in the stylesheet, traced by value.
    for value, variable in SHIPPED_VALUES.items():
        if variable in tokens:
            html = re.sub(re.escape(value), tokens[variable], html, flags=re.IGNORECASE)

    # 3. Anything the template never declared.
    declared = set(re.findall(r"--([a-z0-9-]+)\s*:", html))
    extra = {f"--{k}": v for k, v in tokens.items() if k not in declared}
    if extra:
        block = ":root {\n" + "".join(f"  {k}: {v};\n" for k, v in sorted(extra.items())) + "}\n"
        html = html.replace("</style>", block + "</style>", 1)

    return html


def render_png(html: str, base_url: Path, target: Path) -> None:
    from document_build import _render_html  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    target.parent.mkdir(parents=True, exist_ok=True)
    pdf = target.with_suffix(".pdf")
    _render_html(html, base_url, pdf)

    import os
    import subprocess  # noqa: PLC0415

    env = dict(os.environ)
    env.setdefault("XDG_CACHE_HOME", "/tmp/fc-cache")
    stem = target.with_suffix("")
    subprocess.run(
        ["pdftoppm", "-r", "90", "-png", "-f", "1", "-l", "1", str(pdf), str(stem)],
        check=True, env=env, capture_output=True,
    )
    produced = stem.with_name(stem.name + "-1.png")
    image = Image.open(produced).convert("RGB")
    # A page is mostly flat colour and text; a small palette keeps the page
    # light enough to hold six schemes without visible loss.
    image = image.quantize(colors=128, method=Image.Quantize.MEDIANCUT).convert("P")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    target.write_bytes(buffer.getvalue())
    produced.unlink(missing_ok=True)
    pdf.unlink(missing_ok=True)


# --------------------------------------------------------------------------
# Measurement
# --------------------------------------------------------------------------


def _srgb(channel: int) -> float:
    value = channel / 255
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def contrast(foreground: str, background: str) -> float:
    def luminance(colour: str) -> float:
        text = colour.lstrip("#")
        r, g, b = (int(text[i:i + 2], 16) for i in (0, 2, 4))
        return 0.2126 * _srgb(r) + 0.7152 * _srgb(g) + 0.0722 * _srgb(b)

    a, b = luminance(foreground), luminance(background)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


def contrast_rows(scheme: dict[str, Any], pairs: list[list[Any]]) -> list[dict[str, Any]]:
    rows = []
    for foreground, background, minimum, role in pairs:
        values = scheme["tokens"]
        if foreground not in values or background not in values:
            continue
        ratio = contrast(values[foreground], values[background])
        rows.append({
            "role": role,
            "foreground": values[foreground],
            "background": values[background],
            "ratio": round(ratio, 2),
            "minimum": minimum,
            "pass": ratio + 1e-9 >= minimum,
        })
    return rows


# Colour weakness, as matrices on linear RGB. Viénot's approximation of
# protanopia and deuteranopia: the two most common, and the two the EU data
# visualisation guide says a red-and-brown palette fails.
_CVD_MATRICES: dict[str, tuple[tuple[float, float, float], ...]] = {
    "protanopia": (
        (0.11238, 0.88762, 0.0),
        (0.11238, 0.88762, 0.0),
        (0.00401, -0.00401, 1.0),
    ),
    "deuteranopia": (
        (0.29275, 0.70725, 0.0),
        (0.29275, 0.70725, 0.0),
        (-0.02234, 0.02234, 1.0),
    ),
}

# Status colours must stay apart from each other, and a reader who cannot see the
# difference has lost the meaning. The threshold is a heuristic: the distance is
# plain sRGB Euclidean, the full range is 441, and 25 is a screening value chosen
# to separate the schemes that collapse from the ones that do not. It is not a
# standard, and a scheme that fails it is not thereby unusable -- it is a scheme
# whose status colours depend on the word beside them.
CVD_MINIMUM_DISTANCE = 25.0


def _rgb(colour: str) -> tuple[int, int, int]:
    text = colour.lstrip("#")
    return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _linear(channel: int) -> float:
    value = channel / 255
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def _encode(value: float) -> int:
    value = min(max(value, 0.0), 1.0)
    encoded = 12.92 * value if value <= 0.0031308 else 1.055 * value ** (1 / 2.4) - 0.055
    return round(encoded * 255)


def simulate(colour: str, kind: str) -> str:
    """The colour as a reader with that colour weakness would see it."""
    matrix = _CVD_MATRICES[kind]
    linear = [_linear(c) for c in _rgb(colour)]
    out = [sum(matrix[i][j] * linear[j] for j in range(3)) for i in range(3)]
    return "#" + "".join(f"{_encode(v):02X}" for v in out)


def distance(a: str, b: str) -> float:
    return sum((x - y) ** 2 for x, y in zip(_rgb(a), _rgb(b))) ** 0.5


def luminance(colour: str) -> float:
    r, g, b = _rgb(colour)
    return round(0.2126 * _linear(r) + 0.7152 * _linear(g) + 0.0722 * _linear(b), 4)


def greyscale_rows(scheme: dict[str, Any]) -> list[dict[str, Any]]:
    """The luminance of each level, which is what survives a mono print."""
    tokens = scheme["tokens"]
    levels = ("near-black", "olive", "stone", "sand", "border", "parchment")
    return [
        {"name": name, "value": tokens[name], "luminance": luminance(tokens[name])}
        for name in levels if name in tokens
    ]


def greyscale_separation(scheme: dict[str, Any]) -> list[dict[str, Any]]:
    """How far apart the three text levels are, in luminance."""
    tokens = scheme["tokens"]
    rows = []
    for a, b, role, minimum in (("near-black", "olive", "正文 → 次级文字", 0.03),
                                ("olive", "stone", "次级 → 弱化文字", 0.06),
                                ("near-black", "stone", "正文 → 弱化文字", None)):
        if a in tokens and b in tokens:
            delta = abs(luminance(tokens[a]) - luminance(tokens[b]))
            rows.append({"role": role, "delta": round(delta, 3), "minimum": minimum,
                         # The two muted levels are the pair that merges; the other
                         # steps are reported because the number is useful, not
                         # because a threshold applies to them.
                         "pass": None if minimum is None else delta >= minimum})
    return rows


def cvd_rows(scheme: dict[str, Any]) -> list[dict[str, Any]]:
    """Whether the status colours stay apart for a colour-weak reader."""
    tokens = scheme["tokens"]
    # `brand` is deliberately the same colour as `status-positive` in every
    # scheme, so comparing them would always report a distance of zero. What
    # matters is whether the four status colours stay apart from each other.
    statuses = [n for n in ("status-positive", "status-caution",
                            "status-negative", "status-informative") if n in tokens]
    rows = []
    for kind in ("protanopia", "deuteranopia"):
        shown = statuses + (["brand"] if "brand" in tokens else [])
        seen = {name: simulate(tokens[name], kind) for name in shown}
        pairs = []
        for i, first in enumerate(statuses):
            for second in statuses[i + 1:]:
                pairs.append((first, second, round(distance(seen[first], seen[second]), 1)))
        worst = min(pairs, key=lambda p: p[2]) if pairs else None
        rows.append({
            "kind": kind,
            "samples": [{"name": name, "original": tokens[name], "value": seen[name]}
                        for name in statuses + ["brand"] if name in tokens],
            "pairs": [{"a": a, "b": b, "distance": d} for a, b, d in pairs],
            "worst": {"a": worst[0], "b": worst[1], "distance": worst[2]} if worst else None,
            "pass": bool(worst and worst[2] >= CVD_MINIMUM_DISTANCE),
        })
    return rows


def scheme_group(scheme: dict[str, Any]) -> str:
    """A family label, measured rather than declared."""
    tokens = scheme["tokens"]
    paper = tokens["parchment"]
    r, _, b = _rgb(paper)
    if luminance(paper) < 0.3:
        return "深色"
    brand_r, brand_g, brand_b = _rgb(tokens["brand"])
    chroma = max(brand_r, brand_g, brand_b) - min(brand_r, brand_g, brand_b)
    if chroma < 40:
        return "无色"
    if r - b > 8:
        return "暖"
    if b - r > 4:
        return "冷"
    return "中性"


# --------------------------------------------------------------------------
# Page
# --------------------------------------------------------------------------

SWATCH_ORDER = ("parchment", "ivory", "sand", "border", "olive", "stone",
                "near-black", "brand", "brand-tint", "tag-bg")


def build_page(data: dict[str, Any], images: dict[str, dict[str, str]]) -> str:
    schemes = data["schemes"]
    pairs = data["contrast_pairs"]

    payload = []
    for scheme in schemes:
        sid = scheme["id"]
        payload.append({
            "id": sid,
            "label": scheme["label"],
            "rationale": scheme["rationale"],
            "shipped": bool(scheme.get("shipped")),
            "swatches": [
                {"name": name, "value": scheme["tokens"][name]}
                for name in SWATCH_ORDER if name in scheme["tokens"]
            ],
            "contrast": contrast_rows(scheme, pairs),
            "greyscale": greyscale_rows(scheme),
            "greyscaleSeparation": greyscale_separation(scheme),
            "cvd": cvd_rows(scheme),
            "group": scheme_group(scheme),
            "images": [{"doc": doc, "src": images.get(sid, {}).get(doc, "")} for doc in DOCUMENTS],
        })

    first = payload[0]
    initial = {
        "rationale": first["rationale"] + ('<span class="tag">现状</span>' if first["shipped"] else ""),
        "swatches": "".join(
            f'<div class="swatch"><div class="chip" style="background:{s["value"]}"></div>'
            f'<div class="name">{s["name"]}</div><div class="hex">{s["value"]}</div></div>'
            for s in first["swatches"]
        ),
        "docs": "".join(
            f'<figure><figcaption>{i["doc"]}</figcaption>'
            + (f'<img src="{i["src"]}" alt="{first["label"]} · {i["doc"]}">' if i["src"] else "<p>未渲染</p>")
            + "</figure>"
            for i in first["images"]
        ),
        "contrast": "".join(
            f'<tr><td>{r["role"]}</td><td><code>{r["foreground"]}</code></td>'
            f'<td><code>{r["background"]}</code></td><td>{r["ratio"]:.2f}:1</td>'
            f'<td>{r["minimum"]}:1</td>'
            f'<td class="{"ok" if r["pass"] else "bad"}">{"通过" if r["pass"] else "不通过"}</td></tr>'
            for r in first["contrast"]
        ),
        "overview": "".join(
            f'<figure data-group="{s["group"]}"><figcaption>{s["label"]}'
            f'<span class="chip-tag">{s["group"]}</span></figcaption>'
            + next((f'<img src="{i["src"]}" alt="{s["label"]}">' for i in s["images"] if i["doc"] == "one-pager" and i["src"]), "")
            + "</figure>"
            for s in payload
        ),
        "greyscale": "".join(
            f'<tr><td>{r["name"]}</td><td><code>{r["value"]}</code></td>'
            f'<td>{r["luminance"]:.3f}</td>'
            f'<td><span class="bar" style="width:{r["luminance"] * 100:.0f}%"></span></td></tr>'
            for r in first["greyscale"]
        ),
        "separation": "".join(
            f'<tr><td>{r["role"]}</td><td>{r["delta"]:.3f}</td>'
            f'<td>{r["minimum"] if r["minimum"] is not None else "—"}</td>'
            f'<td class="{"muted" if r["pass"] is None else ("ok" if r["pass"] else "bad")}">'
            f'{"参考" if r["pass"] is None else ("通过" if r["pass"] else "偏近")}</td></tr>'
            for r in first["greyscaleSeparation"]
        ),
        "cvd": "".join(
            f'<tr><td>{r["kind"]}</td>'
            f'<td>{r["worst"]["a"]} / {r["worst"]["b"]}</td>'
            f'<td>{r["worst"]["distance"]:.1f}</td>'
            f'<td>{CVD_MINIMUM_DISTANCE:.0f}</td>'
            f'<td class="{"ok" if r["pass"] else "bad"}">{"可辨" if r["pass"] else "易混"}</td></tr>'
            for r in first["cvd"]
        ),
        "cvdsamples": "".join(
            f'<div class="cvd-row"><span class="cvd-label">{row["kind"]}</span>'
            + "".join(
                f'<span class="cvd-chip" title="{s["name"]} {s["original"]} → {s["value"]}" '
                f'style="background:{s["value"]}"></span>'
                for s in row["samples"]
            )
            + "</div>"
            for row in first["cvd"]
        ),
    }

    page = _PAGE.replace("__PAYLOAD__", json.dumps(payload, ensure_ascii=False))
    for key, value in initial.items():
        page = page.replace(f"__INITIAL_{key.upper()}__", value)
    return page


_PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>色系候选对照 · Folio</title>
<style>
  :root {
    --paper: #F6F0EA; --ivory: #FBF7F3; --ink: #191514; --muted: #85776F;
    --line: #E5D9CE; --accent: #B83D2E; --pass: #2F6B4F; --fail: #B83D2E;
    --serif: "Source Serif 4", Charter, Georgia, serif;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--paper); color: var(--ink);
    font-family: var(--serif); line-height: 1.65;
  }
  .wrap { max-width: 1400px; margin: 0 auto; padding: 44px 40px 96px; }
  h1 { font-size: 31px; margin: 0 0 6px; letter-spacing: -0.01em; }
  .sub { color: var(--muted); font-size: 15px; margin-bottom: 26px; }
  h2 { font-size: 19px; margin: 40px 0 12px; }
  .note {
    background: var(--ivory); border: 1px solid var(--line);
    border-left: 3px solid var(--accent); border-radius: 6px;
    padding: 15px 18px; margin: 18px 0; font-size: 14px; color: #3A312D;
  }
  .note b { color: var(--ink); }
  .picker {
    display: flex; flex-wrap: wrap; gap: 10px; align-items: center;
    background: var(--ivory); border: 1px solid var(--line);
    border-radius: 8px; padding: 16px 18px; margin: 22px 0;
  }
  label { font-size: 13px; color: var(--muted); letter-spacing: .04em; text-transform: uppercase; }
  select {
    font: inherit; font-size: 15px; padding: 8px 12px; border-radius: 6px;
    border: 1px solid var(--line); background: #fff; color: var(--ink);
    min-width: 290px;
  }
  .rationale { flex: 1 1 380px; font-size: 14px; color: #3A312D; }
  .tag {
    font-size: 11px; letter-spacing: .05em; text-transform: uppercase;
    background: var(--accent); color: var(--paper); border-radius: 3px;
    padding: 2px 7px; margin-left: 8px;
  }
  .swatches { display: flex; flex-wrap: wrap; gap: 8px; margin: 18px 0 6px; }
  .swatch { width: 92px; }
  .chip { height: 46px; border-radius: 5px; border: 1px solid var(--line); }
  .swatch .name { font-size: 10.5px; color: var(--muted); margin-top: 5px; }
  .swatch .hex { font-size: 10.5px; font-family: ui-monospace, monospace; color: #3A312D; }
  .docs { display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px; margin-top: 22px; }
  figure { margin: 0; background: var(--ivory); border: 1px solid var(--line); border-radius: 8px; padding: 12px; }
  figcaption { font-size: 12px; color: var(--muted); margin-bottom: 9px; }
  img { width: 100%; display: block; border: 1px solid var(--line); border-radius: 3px; background: #fff; }
  table { width: 100%; border-collapse: collapse; background: var(--ivory); border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }
  th, td { padding: 9px 12px; text-align: left; border-bottom: 1px solid var(--line); font-size: 13px; }
  th { font-size: 11px; letter-spacing: .05em; text-transform: uppercase; color: var(--muted); background: #F1EAE2; }
  tr:last-child td { border-bottom: 0; }
  code { font-family: ui-monospace, monospace; font-size: 12px; }
  .ok { color: var(--pass); font-weight: 600; }
  .muted { color: var(--muted); }
  .bad { color: var(--fail); font-weight: 600; }
  .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-top: 18px; }
  .grid figure { padding: 10px; }
  .grid img { border: 0; }
  .chip-tag {
    font-size: 10px; letter-spacing: .05em; text-transform: uppercase;
    background: #EDE4DA; color: #5A4A43; border-radius: 3px;
    padding: 1px 6px; margin-left: 7px;
  }
  .bar { display: inline-block; height: 9px; background: #B9ACA3; border-radius: 2px; min-width: 2px; }
  .cvd-row { display: flex; align-items: center; gap: 7px; margin: 8px 0; }
  .cvd-label {
    font-size: 11px; letter-spacing: .05em; text-transform: uppercase;
    color: var(--muted); width: 116px; flex: none;
  }
  .cvd-chip { width: 46px; height: 30px; border-radius: 4px; border: 1px solid var(--line); }
  .filters { display: flex; flex-wrap: wrap; gap: 7px; margin: 10px 0 2px; }
  .filter {
    font: inherit; font-size: 13px; padding: 5px 13px; border-radius: 999px;
    border: 1px solid var(--line); background: var(--ivory); color: #3A312D; cursor: pointer;
  }
  .filter.on { background: var(--accent); border-color: var(--accent); color: var(--paper); }
  footer { margin-top: 56px; padding-top: 20px; border-top: 1px solid var(--line); color: var(--muted); font-size: 13px; }
</style>
</head>
<body>
<div class="wrap">

<h1>色系候选对照</h1>
<div class="sub">同一份内容、同一版式、同一字体，只改变颜色</div>

<div class="note">
  <b>这是一次探索，不是已实现的方案。</b>引擎目前还没有把主题色接到页面上 ——
  改主题 profile 不影响任何产物。这个页面用真实的文档构建路径渲染了十二个候选色系，
  供你判断方向，而不是让你从色卡上想象。
</div>

<div class="picker">
  <label for="scheme">色系</label>
  <select id="scheme"></select>
  <div class="rationale" id="rationale">__INITIAL_RATIONALE__</div>
</div>

<div class="swatches" id="swatches">__INITIAL_SWATCHES__</div>

<div class="docs" id="docs">__INITIAL_DOCS__</div>

<h2>对比度</h2>
<p class="sub" style="margin:0 0 10px">按当前色系实测，WCAG 阈值；不达标照实标红。</p>
<table>
  <thead><tr><th>用途</th><th>前景</th><th>背景</th><th>实测</th><th>最低</th><th>结果</th></tr></thead>
  <tbody id="contrast">__INITIAL_CONTRAST__</tbody>
</table>

<h2>灰阶层级</h2>
<p class="sub" style="margin:0 0 10px">
  黑白打印时唯一还在的信息。亮度（0–1）与三个文字层级的间距。
</p>
<table>
  <thead><tr><th>令牌</th><th>值</th><th>亮度</th><th></th></tr></thead>
  <tbody id="greyscale">__INITIAL_GREYSCALE__</tbody>
</table>
<table style="margin-top:14px">
  <thead><tr><th>层级间距</th><th>实测</th><th>建议下限</th><th>结果</th></tr></thead>
  <tbody id="separation">__INITIAL_SEPARATION__</tbody>
</table>

<h2>色觉差异</h2>
<p class="sub" style="margin:0 0 10px">
  红绿色弱约每十二名男性有一名。状态色之间若在这个模拟下靠得太近，
  颜色就不再承载含义。距离为 sRGB 欧氏距离，满量程 441。
</p>
<div id="cvdsamples">__INITIAL_CVDSAMPLES__</div>
<table style="margin-top:14px">
  <thead><tr><th>模拟</th><th>最近的一对</th><th>距离</th><th>下限</th><th>结果</th></tr></thead>
  <tbody id="cvd">__INITIAL_CVD__</tbody>
</table>

<h2>十二个方案总览</h2>
<p class="sub" style="margin:0 0 10px">一页纸并排。用于快速排除方向不对的方案。</p>
<div class="filters" id="filters"></div>
<div class="grid" id="overview">__INITIAL_OVERVIEW__</div>

<div class="note">
  <b>一个已知限制，照实说明。</b>14 个页面背景写在 <code>@page</code> 的
  <code>background: #F6F0EA</code> 里，而这个渲染器的 <code>@page</code> 规则读不到自定义属性。
  所以本页除了替换变量，还按值替换了这个字面量 —— 否则每个方案的页面底色都会是同一个羊皮纸。
  这是当前接线的真实限制，修复计划里已列为待办。
</div>

<footer>
  渲染：真实的文档构建路径 · 方案定义：<code>references/exploration/color-schemes.yaml</code> ·
  生成：<code>python3 scripts/build_color_schemes.py</code>
</footer>
</div>

<script>
const DATA = __PAYLOAD__;
const select = document.getElementById('scheme');
const rationale = document.getElementById('rationale');
const swatches = document.getElementById('swatches');
const docs = document.getElementById('docs');
const contrastBody = document.getElementById('contrast');
const overview = document.getElementById('overview');

for (const scheme of DATA) {
  const option = document.createElement('option');
  option.value = scheme.id;
  option.textContent = scheme.label + (scheme.shipped ? '（现状）' : '');
  select.appendChild(option);
}

function current() {
  return DATA.find(s => s.id === select.value) || DATA[0];
}

function render() {
  const scheme = current();
  rationale.innerHTML = scheme.rationale + (scheme.shipped ? '<span class="tag">现状</span>' : '');

  swatches.innerHTML = scheme.swatches.map(s =>
    `<div class="swatch"><div class="chip" style="background:${s.value}"></div>` +
    `<div class="name">${s.name}</div><div class="hex">${s.value}</div></div>`).join('');

  docs.innerHTML = scheme.images.map(i =>
    `<figure><figcaption>${i.doc}</figcaption>` +
    (i.src ? `<img src="${i.src}" alt="${scheme.label} · ${i.doc}">` : '<p>未渲染</p>') +
    `</figure>`).join('');

  contrastBody.innerHTML = scheme.contrast.map(r =>
    `<tr><td>${r.role}</td><td><code>${r.foreground}</code></td><td><code>${r.background}</code></td>` +
    `<td>${r.ratio.toFixed(2)}:1</td><td>${r.minimum}:1</td>` +
    `<td class="${r.pass ? 'ok' : 'bad'}">${r.pass ? '通过' : '不通过'}</td></tr>`).join('');

  document.getElementById('greyscale').innerHTML = scheme.greyscale.map(r =>
    `<tr><td>${r.name}</td><td><code>${r.value}</code></td><td>${r.luminance.toFixed(3)}</td>` +
    `<td><span class="bar" style="width:${Math.round(r.luminance * 100)}%"></span></td></tr>`).join('');

  document.getElementById('separation').innerHTML = scheme.greyscaleSeparation.map(r =>
    `<tr><td>${r.role}</td><td>${r.delta.toFixed(3)}</td>` +
    `<td>${r.minimum === null ? '—' : r.minimum}</td>` +
    `<td class="${r.pass === null ? 'muted' : (r.pass ? 'ok' : 'bad')}">` +
    `${r.pass === null ? '参考' : (r.pass ? '通过' : '偏近')}</td></tr>`).join('');

  document.getElementById('cvd').innerHTML = scheme.cvd.map(r =>
    `<tr><td>${r.kind}</td><td>${r.worst.a} / ${r.worst.b}</td>` +
    `<td>${r.worst.distance.toFixed(1)}</td><td>60</td>` +
    `<td class="${r.pass ? 'ok' : 'bad'}">${r.pass ? '可辨' : '易混'}</td></tr>`).join('');

  document.getElementById('cvdsamples').innerHTML = scheme.cvd.map(r =>
    `<div class="cvd-row"><span class="cvd-label">${r.kind}</span>` +
    r.samples.map(s =>
      `<span class="cvd-chip" title="${s.name} ${s.original} → ${s.value}" ` +
      `style="background:${s.value}"></span>`).join('') +
    `</div>`).join('');
}

select.addEventListener('change', render);
render();

// The overview shows every scheme at once; the chips narrow it to a family.
const groups = [...new Set(DATA.map(s => s.group))];
const filters = document.getElementById('filters');
let activeGroup = '全部';
filters.innerHTML = ['全部', ...groups].map(g =>
  `<button class="filter${g === '全部' ? ' on' : ''}" data-group="${g}">${g}</button>`).join('');
function paintOverview() {
  overview.innerHTML = DATA.filter(s => activeGroup === '全部' || s.group === activeGroup).map(s => {
    const img = s.images.find(i => i.doc === 'one-pager');
    return `<figure data-group="${s.group}"><figcaption>${s.label}` +
      `<span class="chip-tag">${s.group}</span></figcaption>` +
      (img && img.src ? `<img src="${img.src}" alt="${s.label}">` : '') + `</figure>`;
  }).join('');
}
filters.addEventListener('click', event => {
  const button = event.target.closest('.filter');
  if (!button) return;
  activeGroup = button.dataset.group;
  for (const other of filters.querySelectorAll('.filter')) other.classList.toggle('on', other === button);
  paintOverview();
});
paintOverview();
</script>
</body>
</html>
"""


# --------------------------------------------------------------------------
# Entry
# --------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list", action="store_true", help="list the schemes and stop")
    parser.add_argument("--only", action="append", default=None, help="render one scheme")
    args = parser.parse_args(argv)

    data = load_schemes()
    schemes = data["schemes"]
    if args.list:
        for scheme in schemes:
            print(f"  {scheme['id']:<18} {scheme['label']}")
        return 0

    if args.only:
        wanted = set(args.only)
        schemes = [s for s in schemes if s["id"] in wanted]

    # Build each document once; only the colours change between schemes.
    html_by_doc: dict[str, str] = {}
    base_url = ROOT / "assets" / "templates"
    for doc in DOCUMENTS:
        html_by_doc[doc] = document_html(doc)
        print(f"  built {doc}")

    images: dict[str, dict[str, str]] = {}
    for scheme in schemes:
        sid = scheme["id"]
        images[sid] = {}
        for doc in DOCUMENTS:
            target = SCRATCH / f"{sid}-{doc}.png"
            render_png(apply_scheme(html_by_doc[doc], scheme["tokens"]), base_url, target)
            encoded = base64.b64encode(target.read_bytes()).decode()
            images[sid][doc] = f"data:image/png;base64,{encoded}"
            print(f"  rendered {sid} / {doc}  ({target.stat().st_size // 1024} KB)")

    if args.only:
        print("\n  partial run: page not written")
        return 0

    OUT_PAGE.parent.mkdir(parents=True, exist_ok=True)
    OUT_PAGE.write_text(build_page(data, images), encoding="utf-8")
    print(f"\nOK: wrote {OUT_PAGE} ({OUT_PAGE.stat().st_size // 1024} KB)")

    for scheme in data["schemes"]:
        rows = contrast_rows(scheme, data["contrast_pairs"])
        failed = [r for r in rows if not r["pass"]]
        state = "OK  " if not failed else "FAIL"
        detail = "" if not failed else f"  {', '.join(r['role'] for r in failed)}"
        print(f"  {state} {scheme['id']:<18} {len(rows) - len(failed)}/{len(rows)} 对比度通过{detail}")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
