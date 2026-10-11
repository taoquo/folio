#!/usr/bin/env python3
"""folio colour reference

Writes the colour system's reference page from the live profiles.

Hand-written colour documentation drifts: this repository had four values in a
token table that no renderer read, and a theme profile whose colours resolved to
empty strings. The page is generated so it says what the code says.

    python3 scripts/build_color_reference.py
    python3 scripts/build_color_reference.py --out docs/acceptance/colour.html
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import projection  # noqa: E402
import style_resolver  # noqa: E402

from drawing.theme.contrast import contrast_ratio  # noqa: E402

GROUPS = ("surface", "text", "border", "accent", "status", "data")

GROUP_LABEL = {
    "surface": ("画布与容器", "页面、卡片；一个文档的底色层次"),
    "text": ("文字层级", "正文、次级、弱化；层级靠明度而不是字号"),
    "border": ("分隔与描边", "卡片边框、表格线、题头下的细线"),
    "accent": ("品牌强调", "唯一的彩色。设计系统只允许一个"),
    "status": ("状态语义", "值意味着什么；必须与文字同时出现"),
    "data": ("图表编码", "一条数据系列是什么；不表达好坏"),
}

# Pairs that decide whether a page is readable. (foreground, background, minimum, purpose)
PAIRS = (
    ("color.text.primary", "color.surface.page", 4.5, "正文 / 画布"),
    ("color.text.primary", "color.surface.card", 4.5, "正文 / 卡片"),
    ("color.text.secondary", "color.surface.page", 4.5, "次级文字 / 画布"),
    ("color.text.muted", "color.surface.page", 4.5, "弱化文字 / 画布"),
    ("color.text.warm", "color.surface.page", 4.5, "暖文字 / 画布"),
    ("color.accent.brand", "color.surface.page", 4.5, "强调 / 画布"),
    ("color.accent.brand", "color.accent.tint", 3.0, "强调 / 强调底"),
    ("color.surface.page", "color.accent.brand", 3.0, "反白 / 强调块"),
    ("color.status.caution", "color.surface.page", 4.5, "警告 / 画布"),
    ("color.status.negative", "color.surface.page", 4.5, "负向 / 画布"),
    ("color.border.default", "color.surface.page", 1.2, "细线 / 画布"),
)


def _style(theme: str | None = None):
    return style_resolver.resolve(names={"theme": theme} if theme else None)


def usage() -> dict[str, set[str]]:
    """Which templates reference each custom property."""
    out: dict[str, set[str]] = defaultdict(set)
    for directory in ("assets/templates", "assets/diagrams"):
        for path in sorted((ROOT / directory).glob("*.html")):
            text = path.read_text(encoding="utf-8", errors="ignore")
            for var in set(re.findall(r"var\(\s*(--[a-z0-9-]+)", text)):
                out[var].add(path.name)
    return out


def collect(style) -> dict:
    palette: dict[str, str] = {}
    roles: dict[str, dict[str, str]] = {}
    for path, value in style.values.items():
        text = str(value.value).strip()
        if not text.startswith("#"):
            continue
        if path.startswith("palette."):
            palette[path.split(".", 1)[1]] = text
        elif path.startswith("color."):
            origin = ""
            if "palette." in value.chain[-1]:
                origin = value.chain[-1].split("palette.")[-1]
            roles[path] = {"value": text, "origin": origin}

    used = usage()
    alias_for = {v: k for k, v in projection.LEGACY_ALIASES.items()}

    role_rows = {}
    for path, body in roles.items():
        variable = projection.colour_variable(path)
        legacy = alias_for.get(path)
        names = set(used.get(variable, ()))
        if legacy:
            names |= set(used.get(legacy, ()))
        role_rows[path] = {**body, "variable": variable, "legacy": legacy,
                           "templates": sorted(names), "count": len(names)}

    palette_rows = {}
    for name, value in palette.items():
        users = [p for p, b in roles.items() if b["value"].upper() == value.upper()]
        palette_rows[name] = {"value": value, "roles": users}

    contrasts = []
    for fg, bg, minimum, purpose in PAIRS:
        a = role_rows.get(fg, {}).get("value", "")
        b = role_rows.get(bg, {}).get("value", "")
        if not a or not b:
            continue
        ratio = contrast_ratio(a, b)
        contrasts.append({"purpose": purpose, "foreground": a, "background": b,
                          "ratio": round(ratio, 2), "minimum": minimum,
                          "pass": ratio + 1e-9 >= minimum})

    return {"palette": palette_rows, "roles": role_rows, "contrasts": contrasts,
            "theme": style.domains.get("theme")}


def render(data: dict) -> str:
    roles = data["roles"]
    groups: dict[str, list[str]] = defaultdict(list)
    for path in roles:
        groups[path.split(".")[1]].append(path)

    unused = [p for p, b in roles.items() if not b["count"]]

    palette_cards = "".join(
        f'<figure class="sw"><div class="chip" style="background:{html.escape(b["value"])}"></div>'
        f'<figcaption><code>{html.escape(name)}</code>'
        f'<span class="hex">{html.escape(b["value"])}</span>'
        f'<span class="uses">{len(b["roles"])} 个角色</span></figcaption></figure>'
        for name, b in sorted(data["palette"].items())
    )

    def role_table(paths: list[str]) -> str:
        rows = []
        for path in sorted(paths):
            body = roles[path]
            mark = "" if body["count"] else '<span class="bad">未被引用</span>'
            legacy = f'<code>{html.escape(body["legacy"])}</code>' if body["legacy"] else "—"
            rows.append(
                f'<tr><td><span class="dot" style="background:{html.escape(body["value"])}"></span>'
                f'<code>{html.escape(path)}</code></td>'
                f'<td><code>{html.escape(body["variable"])}</code></td>'
                f'<td><code>{html.escape(body["value"])}</code></td>'
                f'<td>{html.escape(body["origin"]) or "—"}</td>'
                f'<td>{legacy}</td>'
                f'<td class="num">{body["count"] or mark}</td></tr>'
            )
        return (
            '<table><thead><tr><th>角色</th><th>CSS 变量</th><th>值</th>'
            '<th>色板来源</th><th>旧名（迁移期）</th><th>模板</th></tr></thead><tbody>'
            + "".join(rows) + "</tbody></table>"
        )

    group_sections = ""
    for group in GROUPS:
        if group not in groups:
            continue
        label, note = GROUP_LABEL[group]
        group_sections += (
            f'<h3>{label} <code>color.{group}.*</code> '
            f'<span class="count">{len(groups[group])} 个</span></h3>'
            f'<p class="note">{note}</p>' + role_table(groups[group])
        )

    contrast_rows = "".join(
        f'<tr><td>{html.escape(c["purpose"])}</td>'
        f'<td><code>{c["foreground"]}</code></td><td><code>{c["background"]}</code></td>'
        f'<td class="num">{c["ratio"]:.2f}:1</td><td class="num">{c["minimum"]}:1</td>'
        f'<td class="{"ok" if c["pass"] else "bad"}">{"通过" if c["pass"] else "不通过"}</td></tr>'
        for c in data["contrasts"]
    )

    alias_rows = "".join(
        f'<tr><td><code>{html.escape(legacy)}</code></td>'
        f'<td><code>{html.escape(role)}</code></td>'
        f'<td>{len(roles.get(role, {}).get("templates", []))}</td></tr>'
        for legacy, role in sorted(projection.LEGACY_ALIASES.items())
    )

    unused_list = "".join(f'<li><code>{html.escape(p)}</code></li>' for p in sorted(unused)) or "<li>无</li>"

    families: dict[str, list[str]] = defaultdict(list)
    for name in data["palette"]:
        match = re.match(r"^([a-z]+)-(\d+)$", name)
        families[match.group(1) if match else "（无数字后缀）"].append(name)

    return _PAGE.format(
        theme=html.escape(data["theme"] or ""),
        palette_count=len(data["palette"]),
        role_count=len(roles),
        unused_count=len(unused),
        groups=group_sections,
        palette=palette_cards,
        contrasts=contrast_rows,
        aliases=alias_rows,
        alias_count=len(projection.LEGACY_ALIASES),
        unused=unused_list,
        families=", ".join(f"{k} ×{len(v)}" for k, v in sorted(families.items())),
    )


_PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>色彩系统参考 · Folio</title>
<style>
  :root {{
    --paper: #F6F0EA; --ivory: #FBF7F3; --ink: #191514; --muted: #85776F;
    --line: #E5D9CE; --accent: #B83D2E; --ok: #2F6B4F;
    --serif: "Source Serif 4", Charter, Georgia, serif;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--paper); color: var(--ink);
         font-family: var(--serif); line-height: 1.65; }}
  .wrap {{ max-width: 1280px; margin: 0 auto; padding: 44px 40px 96px; }}
  h1 {{ font-size: 31px; margin: 0 0 6px; }}
  .sub {{ color: var(--muted); font-size: 15px; margin-bottom: 26px; }}
  h2 {{ font-size: 20px; margin: 44px 0 10px; }}
  h3 {{ font-size: 16px; margin: 28px 0 4px; }}
  h3 .count {{ color: var(--muted); font-size: 12px; font-weight: 400; margin-left: 6px; }}
  p.note {{ color: var(--muted); font-size: 13.5px; margin: 0 0 12px; }}
  .cards {{ display: grid; grid-template-columns: repeat(auto-fill,minmax(148px,1fr)); gap: 14px; margin: 18px 0 6px; }}
  .sw {{ margin: 0; background: var(--ivory); border: 1px solid var(--line); border-radius: 7px; padding: 9px; }}
  .sw .chip {{ height: 52px; border-radius: 5px; border: 1px solid var(--line); }}
  .sw figcaption {{ font-size: 11px; margin-top: 7px; display: flex; flex-direction: column; gap: 2px; }}
  .sw .hex {{ font-family: ui-monospace, monospace; color: #3A312D; }}
  .sw .uses {{ color: var(--muted); }}
  table {{ width: 100%; border-collapse: collapse; background: var(--ivory); border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }}
  th, td {{ padding: 8px 11px; text-align: left; border-bottom: 1px solid var(--line); font-size: 13px; vertical-align: middle; }}
  th {{ font-size: 11px; letter-spacing: .05em; text-transform: uppercase; color: var(--muted); background: #F1EAE2; }}
  tr:last-child td {{ border-bottom: 0; }}
  code {{ font-family: ui-monospace, monospace; font-size: 12px; }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .dot {{ display: inline-block; width: 11px; height: 11px; border-radius: 50%; border: 1px solid var(--line); margin-right: 7px; vertical-align: -1px; }}
  .ok {{ color: var(--ok); font-weight: 600; }}
  .bad {{ color: var(--accent); font-weight: 600; }}
  .stats {{ display: flex; flex-wrap: wrap; gap: 26px; margin: 20px 0 4px; }}
  .stat b {{ display: block; font-size: 24px; }}
  .stat span {{ color: var(--muted); font-size: 12px; }}
  footer {{ margin-top: 56px; padding-top: 20px; border-top: 1px solid var(--line); color: var(--muted); font-size: 13px; }}
</style>
</head>
<body>
<div class="wrap">

<h1>色彩系统参考</h1>
<div class="sub">当前主题 <code>{theme}</code> · 由 profile 实时生成，不是手写的</div>

<div class="stats">
  <div class="stat"><b>{palette_count}</b><span>色板原始色</span></div>
  <div class="stat"><b>{role_count}</b><span>语义角色</span></div>
  <div class="stat"><b>{unused_count}</b><span>未被模板引用</span></div>
  <div class="stat"><b>{alias_count}</b><span>迁移别名</span></div>
</div>

<h2>怎么读这套颜色</h2>
<p class="note">
两层。色板是原始颜料，每个色值只写一次；角色是用途，指向色板。
模板只读角色，不读色板。改色板一项，所有引用它的角色一起变 ——
品牌红被五个角色共用，以前是靠把这个值写五遍。
</p>
<p class="note">
命名由路径派生：<code>color.text.primary</code> 就是
<code>--color-text-primary</code>。一条规则，加角色只需想一个名字。
</p>

<h2>色板 · {palette_count} 项</h2>
<p class="note">原始色值，只被角色引用。命名家族：{families}</p>
<div class="cards">{palette}</div>

<h2>语义角色 · {role_count} 个</h2>
{groups}

<h2>对比度</h2>
<p class="note">决定一页是否可读的色对。不达标照实标红。</p>
<table><thead><tr><th>用途</th><th>前景</th><th>背景</th><th>实测</th><th>最低</th><th>结果</th></tr></thead>
<tbody>{contrasts}</tbody></table>

<h2>未被引用的角色 · {unused_count} 个</h2>
<p class="note">
一个角色若没有任何模板读它，要么是漏了接线，要么是词汇预留。
消费门禁要求它们显式登记理由。
</p>
<ul>{unused}</ul>

<h2>迁移别名 · {alias_count} 条</h2>
<p class="note">
模板目前读的是旧变量名，投影把旧名指向新角色。模板逐个迁移后，别名逐条删除；
一条检查会在别名无人读取时报错，防止它变成第二套命名。
</p>
<table><thead><tr><th>旧变量</th><th>现在指向的角色</th><th>使用模板数</th></tr></thead>
<tbody>{aliases}</tbody></table>

<footer>
生成：<code>python3 scripts/build_color_reference.py</code> ·
定义：<code>references/profiles/theme/&lt;name&gt;.yaml</code>
</footer>
</div>
</body>
</html>
"""


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--theme", default=None, help="a theme profile name")
    parser.add_argument("--out", default="docs/acceptance/color-system.html")
    args = parser.parse_args(argv)

    style = _style(args.theme)
    data = collect(style)
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(data), encoding="utf-8")
    print(f"OK: wrote {args.out}")
    print(f"  theme {data['theme']}, {len(data['palette'])} palette, {len(data['roles'])} roles")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
