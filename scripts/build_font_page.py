#!/usr/bin/env python3
"""Generate the font choice page.

The demo images render with `Charter, Georgia, serif`, neither of which is in
this repository, so the same build produces different pixels on a machine with a
different Charter. Choosing a font the repository owns fixes that, and choosing
one is a visual decision rather than a technical one -- so the page renders the
same content in each candidate at a size a reader can compare, and states the
measured width difference beside it.

Usage:
    python3 scripts/build_font_page.py
"""

from __future__ import annotations

import base64
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

OUT = ROOT / "docs" / "acceptance" / "font-choice.html"
ASSETS = ROOT / "docs" / "acceptance" / "assets" / "font-choice"

# key, label, note, whether it needs the repository font
CASES = [
    ("charter", "Charter", "系统字体 · 当前使用", "不在仓库中，随 macOS 版本变化"),
    ("charter-105", "Charter 放大 5%", "对照", "系统字体，放大后行宽对比"),
    ("source-serif", "Source Serif 4", "仓库内 · 原尺寸", "1.1 MB，随仓库分发；行宽比 Charter 窄 7%"),
    ("source-serif-108", "Source Serif 4 放大 8%", "仓库内 · 补偿后", "行宽接近 Charter，字号随之变大"),
    ("georgia", "Georgia", "系统字体 · 真正的回退", "行宽比 Charter 宽 1%"),
]

PAPER = "#F6F0EA"
IVORY = "#FDFAF7"
INK = "#24211D"
STONE = "#85776F"
BORDER = "#E5D9CE"
CINNABAR = "#B83D2E"
OLIVE = "#5A4A43"
GREEN = "#4A6B52"
AMBER = "#A8722C"


def embed(path: Path) -> str:
    if not path.is_file():
        return ""
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def measure_width(pdf: Path) -> float | None:
    """The width the text occupies, in points."""
    import os
    import re
    import tempfile

    if not pdf.is_file():
        return None
    env = dict(os.environ)
    env.setdefault("XDG_CACHE_HOME", tempfile.gettempdir())
    result = subprocess.run(
        ["pdftotext", "-bbox", str(pdf), "-"],
        capture_output=True, text=True, check=False, env=env,
    )
    widths = [float(m.group(1)) for m in re.finditer(r'xMax="([0-9.]+)"', result.stdout or "")]
    return max(widths) if widths else None


def build() -> str:
    base = measure_width(ASSETS / "charter.pdf")

    rows = []
    for key, label, kind, note in CASES:
        png = ASSETS / f"{key}-1.png"
        pdf = ASSETS / f"{key}.pdf"
        if not png.is_file():
            continue
        width = measure_width(pdf)
        ratio = (width / base * 100) if (width and base) else None
        rows.append({
            "key": key, "label": label, "kind": kind, "note": note,
            "image": embed(png),
            "width_pt": width, "ratio": ratio,
        })

    def colour(ratio):
        if ratio is None:
            return STONE
        if abs(ratio - 100) <= 1.5:
            return GREEN
        if abs(ratio - 100) <= 5:
            return AMBER
        return CINNABAR

    sections = []
    for r in rows:
        c = colour(r["ratio"])
        ratio_text = f"{r['ratio']:.1f}%" if r["ratio"] else "—"
        width_text = f"{r['width_pt']:.1f}pt" if r["width_pt"] else "—"
        sections.append(f"""
    <section class="case" id="{r['key']}">
      <header>
        <h2>{r['label']}</h2>
        <div class="meta"><span>{r['kind']}</span><span>{r['note']}</span></div>
        <div class="verdict" style="border-color:{c}">
          <span>行宽 <b>{width_text}</b></span>
          <span>相对 Charter <b style="color:{c}">{ratio_text}</b></span>
        </div>
      </header>
      <figure><img src="{r['image']}" alt="{r['label']}"></figure>
    </section>""")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>字体选择对比</title>
<style>
  :root {{ --paper:{PAPER}; --ivory:{IVORY}; --ink:{INK}; --stone:{STONE};
           --border:{BORDER}; --cinnabar:{CINNABAR}; --olive:{OLIVE}; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--paper); color:var(--ink);
          font-family: Charter, "LXGW WenKai", Georgia, serif; line-height:1.6; }}
  .wrap {{ max-width:1200px; margin:0 auto; padding:48px 40px 96px; }}
  h1 {{ font-size:32px; margin:0 0 6px; }}
  .sub {{ color:var(--stone); font-size:15px; }}
  hr {{ border:0; border-top:1px solid var(--border); margin:28px 0; }}

  .note {{ background:var(--ivory); border:1px solid var(--border);
           border-left:3px solid var(--cinnabar); border-radius:6px;
           padding:16px 18px; margin:20px 0; font-size:14px; }}
  .note h3 {{ margin:0 0 8px; font-size:16px; }}
  .note p {{ margin:6px 0; color:var(--olive); }}

  table {{ width:100%; border-collapse:collapse; background:var(--ivory);
           border:1px solid var(--border); border-radius:8px; overflow:hidden; }}
  th,td {{ padding:10px 12px; text-align:left; border-bottom:1px solid var(--border); font-size:14px; }}
  th {{ font-size:11px; letter-spacing:.06em; text-transform:uppercase;
        color:var(--stone); background:#F1EAE2; }}
  tr:last-child td {{ border-bottom:0; }}
  code {{ font-family: ui-monospace, SFMono-Regular, monospace; font-size:12px; }}
  a {{ color:var(--cinnabar); text-decoration:none; }}
  a:hover {{ text-decoration:underline; }}

  .case {{ margin:44px 0; padding-top:6px; }}
  .case header {{ border-left:4px solid var(--cinnabar); padding-left:16px; margin-bottom:16px; }}
  .case h2 {{ font-size:22px; margin:0 0 4px; }}
  .meta {{ display:flex; flex-wrap:wrap; gap:16px; font-size:13px; color:var(--stone); }}
  .verdict {{ display:flex; flex-wrap:wrap; gap:20px; margin-top:10px; padding:8px 12px;
              background:var(--ivory); border:1px solid var(--border);
              border-left-width:3px; border-radius:6px; font-size:14px; }}
  figure {{ margin:0; background:var(--ivory); border:1px solid var(--border);
            border-radius:8px; padding:14px; }}
  img {{ width:100%; height:auto; display:block; border:1px solid var(--border); background:white; }}
  footer {{ margin-top:56px; padding-top:20px; border-top:1px solid var(--border);
            color:var(--stone); font-size:13px; }}
</style>
</head>
<body>
<div class="wrap">

  <h1>字体选择对比</h1>
  <div class="sub">同一段内容，五种设置。用于决定 demo 图改用哪种字体。</div>

  <div class="note">
    <h3>为什么要换字体</h3>
    <p>demo 图当前用 <code>Charter, Georgia, serif</code> —— 两者都是<b>系统字体</b>，不在仓库中。
       系统字体版本变化会改变字形抗锯齿，导致同样的构建在不同机器产生不同像素。</p>
    <p>实测：同环境重建 = 0 像素差异；<code>HEAD~1</code> 版本 vs 当前环境 = 5,024 像素差异，
       但差异全部微弱（无一超过 200 强度），无法从产物解释。</p>
    <p>选一个<b>仓库自带</b>的字体即可根治。仓库内目前只有 <code>Source Serif 4</code>（1.1 MB）。</p>
  </div>

  <h2 style="font-size:20px;margin:32px 0 12px">总览</h2>
  <table>
    <thead><tr><th>方案</th><th>来源</th><th>行宽</th><th>相对 Charter</th><th>说明</th></tr></thead>
    <tbody>
      {''.join(f'''<tr>
        <td><a href="#{r['key']}">{r['label']}</a></td>
        <td>{r['kind']}</td>
        <td class="mono">{f"{r['width_pt']:.1f}pt" if r['width_pt'] else '—'}</td>
        <td class="mono" style="color:{colour(r['ratio'])};font-weight:600">{f"{r['ratio']:.1f}%" if r['ratio'] else '—'}</td>
        <td>{r['note']}</td>
      </tr>''' for r in rows)}
    </tbody>
  </table>

  <hr>
  <h2 style="font-size:20px;margin:0 0 8px">逐个对比</h2>
  <p style="color:var(--stone);font-size:14px;margin:0">
    每张图使用<b>相同的真实内容</b>（architecture-demo 文本），只有字体与字号不同。
  </p>

  {''.join(sections)}

  <div class="note">
    <h3>如何判断</h3>
    <p><b>行宽</b>决定文本占用的横向空间。绿色表示与 Charter 相差 1.5% 以内，黄色 5% 以内，红色更多。</p>
    <p><b>Source Serif 4 原尺寸</b>窄 7%：视觉上字更小、行更短，但与仓库其他文档（用同一字体族）一致。</p>
    <p><b>放大 8% 补偿</b>后行宽接近 Charter，但字号变大，需确认是否符合设计意图。</p>
  </div>

  <footer>
    生成：<code>python3 scripts/build_font_page.py</code> ·
    复现：<code>python3 scripts/build.py artifact-uml-class-demo</code>
  </footer>

</div>
</body>
</html>
"""


if __name__ == "__main__":
    html = build()
    OUT.write_text(html, encoding="utf-8")
    print(f"OK: wrote {OUT} ({OUT.stat().st_size:,} bytes)")
