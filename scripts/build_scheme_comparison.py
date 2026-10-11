#!/usr/bin/env python3
"""folio scheme comparison

Puts every colour scheme side by side, so choosing one is a comparison rather
than a guess. The reference page answers what a scheme contains; this answers
which of them to use, which needs them measured the same way in one view.

    python3 scripts/build_scheme_comparison.py

A scheme is one YAML file in `references/profiles/theme/`. This finds them all,
so a new one appears here as soon as it is written.
"""

from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_theme_schemes as schemes  # noqa: E402

from drawing.theme.contrast import contrast_ratio  # noqa: E402

# The roles worth comparing: what a page is made of.
SHOWN = (
    ("画布", "color.surface.page"),
    ("卡片", "color.surface.card"),
    ("正文", "color.text.primary"),
    ("次级", "color.text.secondary"),
    ("弱化", "color.text.muted"),
    ("标题", "color.text.warm"),
    ("品牌", "color.accent.brand"),
    ("浅底", "color.accent.brand-tint"),
    ("正/负向", "color.status.negative"),
    ("警告", "color.status.caution"),
    ("细线", "color.border.default"),
)

results = []
for name in sorted(schemes.profiles()):
    result = schemes.check_scheme(name)
    values = result["values"]
    findings = result["findings"]
    contrast = []
    for foreground, background, minimum, purpose in schemes.CONTRAST_PAIRS:
        front, back = values.get(foreground, ""), values.get(background, "")
        if not front.startswith("#") or not back.startswith("#"):
            continue
        ratio = contrast_ratio(front, back)
        contrast.append((purpose, ratio, minimum, ratio + 1e-9 >= minimum))
    results.append((name, values, findings, contrast))

columns = "".join(f"<th>{html.escape(n)}</th>" for n, _, _, _ in results)
rows = ""
for label, role in SHOWN:
    cells = ""
    for _name, values, _f, _c in results:
        colour = values.get(role, "")
        cells += (f'<td><span class="chip" style="background:{html.escape(colour)}"></span>'
                  f'<code>{html.escape(colour)}</code></td>')
    rows += f'<tr><th class="row">{label}<br><code>{role}</code></th>{cells}</tr>'

contrast_rows = ""
seen = []
for purpose, *_ in results[0][3]:
    seen.append(purpose)
for purpose in seen:
    cells = ""
    for _name, _v, _f, contrast in results:
        match = next((c for c in contrast if c[0] == purpose), None)
        if match is None:
            cells += "<td>—</td>"
            continue
        _, ratio, minimum, ok = match
        cells += (f'<td class="{"ok" if ok else "bad"}">{ratio:.2f}:1'
                  f'<span class="min"> / {minimum}</span></td>')
    contrast_rows += f'<tr><th class="row">{html.escape(purpose)}</th>{cells}</tr>'

summary = "".join(
    f'<tr><td><code>{html.escape(n)}</code></td><td class="num">{len(v)}</td>'
    f'<td class="num">{len([k for k in v if k.startswith("palette.")])}</td>'
    f'<td class="{"ok" if not f else "bad"}">{"通过" if not f else f"{len(f)} 项不通过"}</td></tr>'
    for n, v, f, _c in results
)

page = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>色系对照 · Folio</title>
<style>
  :root {{ --paper:#F6F0EA; --ivory:#FBF7F3; --ink:#191514; --muted:#756A63;
           --line:#E6DACD; --accent:#B83D2E; --ok:#2F6B4F; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--paper); color:var(--ink);
         font-family:"Source Serif 4",Charter,Georgia,serif; line-height:1.6; }}
  .wrap {{ max-width:1180px; margin:0 auto; padding:44px 40px 96px; }}
  h1 {{ font-size:30px; margin:0 0 6px; }}
  .sub {{ color:var(--muted); font-size:14.5px; margin-bottom:26px; }}
  h2 {{ font-size:19px; margin:38px 0 8px; }}
  table {{ width:100%; border-collapse:collapse; background:var(--ivory);
           border:1px solid var(--line); border-radius:8px; overflow:hidden; margin-bottom:8px; }}
  th, td {{ padding:8px 10px; border-bottom:1px solid var(--line); font-size:13px;
            text-align:left; vertical-align:middle; }}
  thead th {{ background:#F1EAE2; font-size:12px; }}
  th.row {{ text-align:right; color:var(--muted); font-weight:400; font-size:12px;
            white-space:nowrap; width:150px; }}
  tr:last-child td, tr:last-child th {{ border-bottom:0; }}
  code {{ font-family:ui-monospace,monospace; font-size:11.5px; }}
  .chip {{ display:inline-block; width:22px; height:22px; border-radius:4px;
           border:1px solid var(--line); vertical-align:-5px; margin-right:7px; }}
  .ok {{ color:var(--ok); font-weight:600; }}
  .bad {{ color:var(--accent); font-weight:600; }}
  .min {{ color:var(--muted); font-weight:400; font-size:11px; }}
  .num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  .note {{ color:var(--muted); font-size:13.5px; }}
  footer {{ margin-top:48px; padding-top:18px; border-top:1px solid var(--line);
            color:var(--muted); font-size:13px; }}
</style>
</head>
<body>
<div class="wrap">

<h1>色系对照</h1>
<div class="sub">每个方案用同一套标准测量。选一个，然后 <code>FOLIO_THEME=&lt;名字&gt;</code> 就是它。</div>

<h2>标准</h2>
<table><thead><tr><th class="row">方案</th><th>角色</th><th>色板</th><th>检查</th></tr></thead>
<tbody>{summary}</tbody></table>

<h2>关键角色并排</h2>
<p class="note">颜色本身不是信号：状态色永远与文字同时出现，灰阶打印或色觉差异下仍然可读。</p>
<table><thead><tr><th class="row">用途</th>{columns}</tr></thead><tbody>{rows}</tbody></table>

<h2>对比度</h2>
<p class="note">文字需 4.5:1，细线需 1.2:1。每个文字色都在画布与卡片两个底面上测。</p>
<table><thead><tr><th class="row">用途</th>{columns}</tr></thead><tbody>{contrast_rows}</tbody></table>

<h2>怎么用</h2>
<p class="note">
<code>FOLIO_THEME=folio-slate-v1 python3 scripts/build.py</code><br>
<code>FOLIO_THEME=folio-slate-v1 python3 scripts/build.py</code> ·
<code>FOLIO_THEME=folio-slate-v1 python3 scripts/build_static_theme.py</code><br>
未设 <code>FOLIO_THEME</code> 时用标记 <code>default</code> 的那个方案。
</p>

<footer>
生成：<code>python3 scripts/build_scheme_comparison.py</code> ·
定义：<code>references/profiles/theme/*.yaml</code>
</footer>
</div>
</body>
</html>
"""

# What each scheme is called on a page, and why a reader would pick it. The
# profile knows the colours; the copy is the one thing it cannot carry.
COPY = {
    "folio-classic-v1": {
        "en": ("Folio Classic", "Warm parchment canvas, cinnabar accent. The system's own voice."),
        "zh": ("典籍", "暖羊皮纸画布，朱砂强调。系统自己的声音。"),
    },
    "folio-slate-v1": {
        "en": ("Folio Slate", "Cool neutral canvas, deep azure accent. Institutional research."),
        "zh": ("石板", "冷中性画布，深天青强调。适合机构研究。"),
    },
    "folio-forest-v1": {
        "en": ("Folio Forest", "Warm bone canvas, deep forest accent. Editorial and long-form."),
        "zh": ("林间", "暖骨白画布，深林绿强调。适合编辑与长文。"),
    },
}

# The five that say what a scheme looks like at a glance.
CHIPS = ("color.surface.page", "color.surface.card", "color.text.primary",
         "color.accent.brand", "color.accent.brand-tint")

LEAD = {
    "en": ("Three schemes ship, one file each in <code>references/profiles/theme/</code>. "
           "<code>FOLIO_THEME</code> selects one, and it reaches documents, diagrams, "
           "slide decks and these pages. Every scheme is held to the same bar: text at "
           "4.5:1 on both surfaces, a hairline that stays visible, and ramp numbers that "
           "follow lightness."),
    "zh": ("内置三套色系，每套一个文件，放在 <code>references/profiles/theme/</code>。"
           "<code>FOLIO_THEME</code> 指定其中一套，作用于文档、图表、幻灯片和这些页面。"
           "每套色系都过同一套标准：文字在两个底面上都达到 4.5:1，细线保持可见，"
           "同族编号跟随明度。"),
}

HEADING = {"en": "Choosing a Scheme", "zh": "切换色系"}
FOOT = {
    "en": ("<code>FOLIO_THEME=folio-slate-v1 python3 scripts/build.py</code> renders in a "
           "scheme; <code>python3 scripts/check_theme_schemes.py</code> holds every scheme "
           "to the bar. Unset, the profile marked <code>default</code> is used."),
    "zh": ("<code>FOLIO_THEME=folio-slate-v1 python3 scripts/build.py</code> 用指定色系渲染；"
           "<code>python3 scripts/check_theme_schemes.py</code> 校验每套色系是否达标。"
           "不设置时使用标记 <code>default</code> 的那一套。"),
}

DEFAULT_LABEL = {"en": "Default", "zh": "默认"}
USAGE_LABEL = {"en": "Use", "zh": "用法"}

TARGETS = ("index.html", "index-zh.html")
START, END = "<!-- folio-schemes:start -->", "<!-- folio-schemes:end -->"


def render_gallery(language: str) -> str:
    """The block that goes between the markers on the homepages."""
    import yaml

    cards = []
    for name in sorted(schemes.profiles()):
        body = schemes.profiles()[name]
        profile = (yaml.safe_load(
            (ROOT / "references" / "profiles" / "theme" / f"{name}.yaml").read_text(encoding="utf-8")
        ).get("profiles") or {}).get(name) or {}
        palette = profile.get("palette") or {}
        result = schemes.check_scheme(name)
        values = result["values"]
        title, note = COPY.get(name, {}).get(language, (name, ""))

        lines = [
            '      <article class="scheme">',
            '        <div class="scheme-head">',
            f'          <p class="scheme-name">{title}</p>',
            f'          <code class="scheme-id">{name}</code>',
        ]
        if body.get("default"):
            lines.append(f'          <span class="scheme-flag">{DEFAULT_LABEL[language]}</span>')
        lines += [
            "        </div>",
            f'        <p class="scheme-note">{note}</p>',
            '        <div class="scheme-chips">'
            + "".join(f'<span class="scheme-chip" style="background:'
                      f'{values.get(role, "#000000")}"></span>' for role in CHIPS)
            + "</div>",
            f'        <p class="scheme-count">{len(palette)} palette entries · '
            f'{result["metrics"]["roles"]} roles</p>',
            "      </article>",
        ]
        cards.append("\n".join(lines))

    return "\n".join([
        START,
        f'      <h3 class="subhead">{HEADING[language]}</h3>',
        '      <p style="font-size:14px;color:var(--color-text-secondary);margin:0 0 18px;'
        f'line-height:1.6;">{LEAD[language]}</p>',
        '      <div class="schemes">',
        "\n".join(cards),
        "      </div>",
        f'      <p class="scheme-foot">{FOOT[language]}</p>',
        f'      {END}',
    ])


def inject(check: bool = False) -> int:
    """Write the gallery into both homepages, replacing what is between the markers."""
    import re

    failures = 0
    for relative in TARGETS:
        path = ROOT / relative
        text = path.read_text(encoding="utf-8")
        language = "zh" if "zh" in relative else "en"
        block = render_gallery(language)
        pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.DOTALL)
        found = pattern.search(text)
        if not found:
            print(f"ERROR: {relative}: the markers {START} / {END} are not in the file")
            failures += 1
            continue
        updated = text[:found.start()] + block + text[found.end():]
        if check:
            if updated != text:
                print(f"  {relative}: the gallery is behind the profiles")
                failures += 1
            continue
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            print(f"  {relative}: gallery written")
    return failures


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default="docs/acceptance/theme-schemes.html")
    parser.add_argument("--inject", action="store_true",
                        help="write the gallery into index.html and index-zh.html")
    parser.add_argument("--check", action="store_true",
                        help="report whether the gallery is behind the profiles")
    args = parser.parse_args(argv)

    if args.inject or args.check:
        failures = inject(check=args.check)
        if args.check:
            if failures:
                print(f"ERROR: {failures} homepage(s) behind the profiles")
            else:
                print(f"OK: {len(TARGETS)} gallery(ies) match the profiles")
        return 1 if failures else 0

    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(f"OK: wrote {args.out}  ({out.stat().st_size // 1024} KB)")
    print(f"  {len(results)} scheme(s): {', '.join(name for name, _, _, _ in results)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
