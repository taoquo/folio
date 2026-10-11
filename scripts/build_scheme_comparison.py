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
def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default="docs/acceptance/theme-schemes.html")
    args = parser.parse_args(argv)

    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(f"OK: wrote {args.out}  ({out.stat().st_size // 1024} KB)")
    print(f"  {len(results)} scheme(s): {', '.join(name for name, _, _, _ in results)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
