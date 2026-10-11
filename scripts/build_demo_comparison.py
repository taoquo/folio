#!/usr/bin/env python3
"""Generate the demo comparison page.

The demo images changed when `build.py` ran, and the question is whether they
changed in a way that matters. A byte difference says nothing about that; two
renderings of the same diagram differ in bytes whenever anything about the
encoder or a glyph position moves.

So the page shows what a reader needs to decide: the two renderings side by
side, the difference amplified, and the region where they disagree. The numbers
are measured at build time and printed beside the images.
"""
from __future__ import annotations

import base64
import sys
from pathlib import Path

ROOT = Path("/Users/shuke/WorkSpace/01Code/04Git2/folio")
sys.path.insert(0, str(ROOT / "scripts"))

OUT = ROOT / "docs" / "acceptance" / "demo-comparison.html"
ASSETS = ROOT / "docs" / "acceptance" / "assets" / "demo-diff"

CASES = [
    ("architecture", "demo-architecture", "架构图", "diagram-architecture"),
    ("data-platform", "demo-data-platform", "数据平台图", "diagram-architecture"),
    ("flowchart-v2", "demo-flowchart-v2", "流程图 v2", "diagram-flowchart"),
    ("uml-class", "demo-uml-class", "UML 类图", "diagram-uml-class"),
    ("workflow-engine", "demo-workflow-engine", "工作流引擎图", "diagram-workflow-engine"),
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


def measure(before: Path, after: Path) -> dict:
    """How different the two renderings are, and where."""
    try:
        from PIL import Image, ImageChops
    except ImportError:
        return {"error": "Pillow unavailable"}

    if not (before.is_file() and after.is_file()):
        return {"error": "missing image"}

    a = Image.open(before).convert("RGB")
    b = Image.open(after).convert("RGB")
    if a.size != b.size:
        return {"error": f"size differs: {a.size} vs {b.size}"}

    diff = ImageChops.difference(a, b)
    bbox = diff.getbbox()
    changed = sum(1 for px in diff.get_flattened_data() if px != (0, 0, 0)) \
        if hasattr(diff, "get_flattened_data") else \
        sum(1 for px in list(diff.getdata()) if px != (0, 0, 0))
    total = a.size[0] * a.size[1]

    return {
        "size": f"{a.size[0]}x{a.size[1]}",
        "changed_px": changed,
        "changed_pct": changed / total * 100 if total else 0,
        "bbox": bbox,
        "region": f"{bbox[2] - bbox[0]}x{bbox[3] - bbox[1]} px @ ({bbox[0]}, {bbox[1]})" if bbox else "—",
    }


def verdict(pct: float) -> tuple[str, str]:
    if pct <= 0:
        return "完全相同", GREEN
    if pct < 1.0:
        return "轻微差异", AMBER
    if pct < 5.0:
        return "有差异", CINNABAR
    return "明显差异", CINNABAR


def build() -> str:
    rows = []
    for key, demo_name, label, target in CASES:
        before = ASSETS / f"{key}-before.png"
        after = ASSETS / f"{key}-after.png"
        diff = ASSETS / f"{key}-diff.png"
        crop_b = ASSETS / f"{key}-crop-before.png"
        crop_a = ASSETS / f"{key}-crop-after.png"

        m = measure(before, after)
        if "error" in m:
            rows.append((key, demo_name, label, target, m, None))
            continue
        rows.append((key, demo_name, label, target, m, {
            "before": embed(before), "after": embed(after), "diff": embed(diff),
            "crop_before": embed(crop_b), "crop_a": embed(crop_a),
        }))

    sections = []
    for key, demo_name, label, target, m, images in rows:
        if images is None:
            sections.append(f"""
    <section class="case">
      <h2>{label}</h2>
      <p class="err">无法测量：{m.get('error')}</p>
    </section>""")
            continue

        v, colour = verdict(m["changed_pct"])
        sections.append(f"""
    <section class="case" id="{key}">
      <header>
        <h2>{label}</h2>
        <div class="meta">
          <span><code>assets/demos/{demo_name}.png</code></span>
          <span>目标 <code>{target}</code></span>
          <span>尺寸 {m['size']}</span>
        </div>
        <div class="verdict" style="border-color:{colour}">
          <b style="color:{colour}">{v}</b>
          <span>差异像素 <b>{m['changed_px']:,}</b>（{m['changed_pct']:.3f}%）</span>
          <span>区域 <code>{m['region']}</code></span>
        </div>
      </header>

      <div class="pair">
        <figure>
          <figcaption>改前</figcaption>
          <img src="{images['before']}" alt="{label} 改前">
        </figure>
        <figure>
          <figcaption>改后</figcaption>
          <img src="{images['after']}" alt="{label} 改后">
        </figure>
      </div>

      <div class="detail">
        <figure class="zoom">
          <figcaption>差异区域 · 改前</figcaption>
          <img src="{images['crop_before']}" alt="差异区域改前">
        </figure>
        <figure class="zoom">
          <figcaption>差异区域 · 改后</figcaption>
          <img src="{images['crop_a']}" alt="差异区域改后">
        </figure>
        <figure class="zoom">
          <figcaption>差异放大 6 倍</figcaption>
          <img src="{images['diff']}" alt="差异放大">
        </figure>
      </div>
    </section>""")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Demo 图像对比</title>
<style>
  :root {{ --paper:{PAPER}; --ivory:{IVORY}; --ink:{INK}; --stone:{STONE};
           --border:{BORDER}; --cinnabar:{CINNABAR}; --olive:{OLIVE}; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:var(--paper); color:var(--ink);
          font-family: Charter, "LXGW WenKai", Georgia, serif; line-height:1.6; }}
  .wrap {{ max-width:1400px; margin:0 auto; padding:48px 40px 96px; }}
  h1 {{ font-size:32px; margin:0 0 6px; }}
  .sub {{ color:var(--stone); font-size:15px; }}
  hr {{ border:0; border-top:1px solid var(--border); margin:28px 0; }}

  .note {{ background:var(--ivory); border:1px solid var(--border);
           border-left:3px solid var(--cinnabar); border-radius:6px;
           padding:16px 18px; margin:20px 0; font-size:14px; }}
  .note h3 {{ margin:0 0 8px; font-size:16px; }}
  .note p {{ margin:6px 0; color:var(--olive); }}

  .cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr));
            gap:14px; margin:24px 0; }}
  .card {{ background:var(--ivory); border:1px solid var(--border);
           border-radius:8px; padding:16px 18px; }}
  .card .k {{ font-size:11px; letter-spacing:.08em; text-transform:uppercase; color:var(--stone); }}
  .card .v {{ font-size:28px; font-weight:700; color:var(--cinnabar); margin:4px 0 2px; }}
  .card .n {{ font-size:12px; color:var(--olive); }}

  table {{ width:100%; border-collapse:collapse; background:var(--ivory);
           border:1px solid var(--border); border-radius:8px; overflow:hidden; }}
  th,td {{ padding:10px 12px; text-align:left; border-bottom:1px solid var(--border); font-size:14px; }}
  th {{ font-size:11px; letter-spacing:.06em; text-transform:uppercase;
        color:var(--stone); background:#F1EAE2; }}
  tr:last-child td {{ border-bottom:0; }}
  code {{ font-family: ui-monospace, SFMono-Regular, monospace; font-size:12px; }}
  a {{ color:var(--cinnabar); text-decoration:none; }}
  a:hover {{ text-decoration:underline; }}

  .case {{ margin:56px 0; padding-top:8px; }}
  .case header {{ border-left:4px solid var(--cinnabar); padding-left:16px; margin-bottom:18px; }}
  .case h2 {{ font-size:24px; margin:0 0 6px; }}
  .meta {{ display:flex; flex-wrap:wrap; gap:18px; font-size:13px; color:var(--stone); }}
  .verdict {{ display:flex; flex-wrap:wrap; gap:20px; align-items:baseline;
              margin-top:12px; padding:10px 14px; background:var(--ivory);
              border:1px solid var(--border); border-left-width:3px;
              border-radius:6px; font-size:14px; }}
  .pair,.detail {{ display:grid; gap:1px; background:var(--border);
                   border:1px solid var(--border); border-radius:8px; overflow:hidden; }}
  .pair {{ grid-template-columns:1fr 1fr; }}
  .detail {{ grid-template-columns:repeat(3,1fr); margin-top:14px; }}
  figure {{ margin:0; background:var(--ivory); padding:14px; }}
  figcaption {{ font-size:12px; color:var(--stone); margin-bottom:10px; letter-spacing:.04em; }}
  img {{ width:100%; height:auto; display:block; border:1px solid var(--border); background:white; }}
  .err {{ color:var(--cinnabar); }}
  footer {{ margin-top:56px; padding-top:20px; border-top:1px solid var(--border);
            color:var(--stone); font-size:13px; }}
</style>
</head>
<body>
<div class="wrap">

  <h1>Demo 图像对比</h1>
  <div class="sub">改前（<code>HEAD~1</code>）与改后（当前工作区）的逐像素比较</div>

  <div class="note">
    <h3>这些图为什么会变</h3>
    <p>运行全量 <code>python3 scripts/build.py</code> 会重建图表示例的 PNG。这一步与文档引擎的改动
       无关，是构建脚本的既有行为。</p>
    <p><b>但它们确实变了</b> —— 差异 0.07% 到 0.43%，不是编码噪声。下方每一组都给出改前、改后、
       差异放大图和差异所在区域，供你判断这是否可以接受。</p>
    <p><code>index.html</code> 与 <code>index-zh.html</code> <b>未变</b>。</p>
  </div>

  <div class="cards">
    <div class="card"><div class="k">受影响的 demo</div><div class="v">{len([r for r in rows if 'error' not in r[4]])}</div><div class="n">共 5 个</div></div>
    <div class="card"><div class="k">最大差异</div><div class="v">{max((r[4].get('changed_pct',0) for r in rows if 'error' not in r[4]), default=0):.3f}%</div><div class="n">像素占比</div></div>
    <div class="card"><div class="k">index.html</div><div class="v">未变</div><div class="n">无差异</div></div>
    <div class="card"><div class="k">文档示例</div><div class="v">已重做</div><div class="n">走 IR 生成</div></div>
  </div>

  <h2 style="font-size:20px;margin:32px 0 12px">总览</h2>
  <table>
    <thead>
      <tr><th>Demo</th><th>尺寸</th><th>差异像素</th><th>占比</th><th>区域</th><th>判定</th></tr>
    </thead>
    <tbody>
      {''.join(f'''<tr>
        <td><a href="#{r[0]}">{r[2]}</a></td>
        <td class="mono">{r[4].get('size','—')}</td>
        <td class="mono">{r[4].get('changed_px',0):,}</td>
        <td class="mono">{r[4].get('changed_pct',0):.3f}%</td>
        <td class="mono">{r[4].get('region','—')}</td>
        <td style="color:{verdict(r[4].get('changed_pct',0))[1]};font-weight:600">{verdict(r[4].get('changed_pct',0))[0]}</td>
      </tr>''' for r in rows if 'error' not in r[4])}
    </tbody>
  </table>

  <hr>
  <h2 style="font-size:20px;margin:0 0 8px">逐个对比</h2>
  <p style="color:var(--stone);font-size:14px;margin:0">
    每组给出整图对照、差异区域放大，以及放大 6 倍的差异掩码。
  </p>

  {''.join(sections)}

  <div class="note">
    <h3>如何判断</h3>
    <p>若差异区域<b>只落在文字</b>，通常是字形位置或字体度量的微小变化，视觉上不可见。</p>
    <p>若差异<b>改变了图形结构</b>（线条、框、箭头），则需要人工判断。</p>
    <p>每一组的差异放大图会把 6 倍以内的差异高亮，空白表示该处完全相同。</p>
  </div>

  <footer>
    生成：<code>python3 scripts/build_demo_comparison.py</code> ·
    复核：<code>python3 scripts/visual_diff.py &lt;before.pdf&gt; &lt;after.pdf&gt;</code>
  </footer>

</div>
</body>
</html>
"""


if __name__ == "__main__":
    html = build()
    OUT.write_text(html, encoding="utf-8")
    print(f"OK: wrote {OUT} ({OUT.stat().st_size:,} bytes)")
