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
            f'<figure><figcaption>{s["label"]}</figcaption>'
            + next((f'<img src="{i["src"]}" alt="{s["label"]}">' for i in s["images"] if i["doc"] == "one-pager" and i["src"]), "")
            + "</figure>"
            for s in payload
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
  .bad { color: var(--fail); font-weight: 600; }
  .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-top: 18px; }
  .grid figure { padding: 10px; }
  .grid img { border: 0; }
  footer { margin-top: 56px; padding-top: 20px; border-top: 1px solid var(--line); color: var(--muted); font-size: 13px; }
</style>
</head>
<body>
<div class="wrap">

<h1>色系候选对照</h1>
<div class="sub">同一份内容、同一版式、同一字体，只改变颜色</div>

<div class="note">
  <b>这是一次探索，不是已实现的方案。</b>引擎目前还没有把主题色接到页面上 ——
  改主题 profile 不影响任何产物。这个页面用真实的文档构建路径渲染了六个候选色系，
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

<h2>六个方案总览</h2>
<p class="sub" style="margin:0 0 10px">一页纸，六个色系并排。用于快速排除方向不对的方案。</p>
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
}

select.addEventListener('change', render);
render();

const base = DATA[0];
overview.innerHTML = DATA.map(s => {
  const img = s.images.find(i => i.doc === 'one-pager');
  return `<figure><figcaption>${s.label}</figcaption>` +
    (img && img.src ? `<img src="${img.src}" alt="${s.label}">` : '') + `</figure>`;
}).join('');
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
