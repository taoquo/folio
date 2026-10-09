#!/usr/bin/env python3
"""folio fixture content mapping

Lets a fixture describe its content with stable semantic keys and have those
mapped onto whatever placeholders a given template actually declares.

The templates name their slots in four different styles: Chinese instructions,
English sentences, bare uppercase words and UPPER_SNAKE names. Renaming 437 of
them would break every existing document, so the mapping lives here instead.
An author writes one set of keys; the layer finds the matching slot per
template.

Usage:
    python3 scripts/fixture_map.py resolve <fixture.yaml>
    python3 scripts/fixture_map.py check
    python3 scripts/fixture_map.py aliases
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

PLACEHOLDER = re.compile(r"\{\{([^{}]*)\}\}", re.DOTALL)

# Semantic key -> the placeholder names that mean it, per template family.
# The left side is what a fixture writes; the right side is what the templates
# say. Adding a template means adding its names here, not editing the template.
ALIASES: dict[str, tuple[str, ...]] = {
    "title": (
        "文档标题", "文档主标题（serif，2 行内，动词+名词结构最好）", "TITLE", "ARTICLE_TITLE",
        "作品标题", "公司名称", "COMPANY_NAME", "项目名", "PROJECT_NAME", "姓名", "NAME",
    ),
    "subtitle": (
        "一行副标题 / 一句核心论点", "一句自我定位的 headline", "SUBTITLE", "一句核心判断",
        "一句自我描述 / 作品集主题",
    ),
    "eyebrow": (
        "标签描述", "作品标题", "EYEBROW", "标签",
    ),
    "summary": (
        "摘要", "SUMMARY", "一句话版本亮点", "一句话总结：买入/持有/观望的核心理由。",
        "项目一句话描述", "PROJECT_DESCRIPTION", "一句描述",
    ),
    "body": (
        "这里写 1-2 句段落，展开论点。", "1-2 句段落。", "一段论述。", "A paragraph.",
        "本段", "正文", "BODY",
    ),
    "author": (
        "作者", "作者名", "作者 / 团队", "AUTHOR", "AUTHOR / TEAM", "寄件人姓名", "收件人姓名 / 称谓",
    ),
    "date": (
        "日期 YYYY.MM.DD", "发布日期", "DATE", "日期", "周期", "PERIOD",
    ),
    "version": (
        "版本号", "版本号 / 状态", "VERSION", "版本名称", "RELEASE_NAME",
    ),
    "keywords": (
        "关键词", "KEYWORDS", "标签",
    ),
    "url": (
        "项目 URL", "URL", "PROJECT_URL", "WEBSITE", "网址",
    ),
    "email": ("EMAIL", "邮箱"),
    "confidentiality": ("机密级别 / 内部 / 公开 等", "CONFIDENTIALITY", "密级"),
    "footer": ("页码 / 联系方式", "FOOTER", "页脚"),
    "bullet": ("短 bullet", "BULLET", "bullet"),
    "metric": ("数字", "METRIC", "指标", "数据"),
    "quote": ("关键引用 / 重要提示 / 核心 takeaway。比正文更需要引起注意的内容放这里。", "QUOTE", "引用"),
    "action": ("建议采取的单一动作：批准 / 暂缓 / 追加资源 / 进入下一阶段。", "ACTION", "建议"),
    "owner": ("负责人 / 截止日", "OWNER", "负责人"),
    "stage": ("阶段标题", "STAGE"),
    # The equity report's own slots, which are named as full instructions.
    "thesis": (
        "2-3 句核心投资论点。用 <span class=\"hl\">关键数据</span> 支撑判断。这段是整份研报的灵魂。",
        "2-3 sentence investment thesis.",
    ),
    "verdict": (
        "3-5 句总结。包含目标价（如有）、评级建议、核心催化剂、关键假设。",
        "3-5 sentence summary.",
    ),
    "call": ("一句核心判断", "一句话总结：买入/持有/观望的核心理由。", "single-sentence call"),
    "chart_title": ("图表标题", "图表标题，如 \"近 20 个交易日价格走势\"", "CHART_TITLE"),
    "price": ("当前价格", "目标价", "PRICE", "CURRENT_PRICE"),
    "exchange": ("交易所", "EXCHANGE", "TICKER"),
    "disclaimer": ("机构名 / 免责声明", "DISCLAIMER"),
    "thanks": (
        "感谢贡献者，格式如：\"感谢 @user1、@user2 的贡献。\"",
        "感谢贡献者",
        "THANKS",
        "Acknowledgements",
    ),
    "description": ("项目一句话描述", "一句描述", "一句话描述", "DESCRIPTION", "PROJECT_DESCRIPTION"),
    "positioning": ("一句自我定位的 headline", "一句自我定位", "HEADLINE"),
    "portfolio_theme": ("一句自我描述 / 作品集主题", "PORTFOLIO_THEME"),
    "identity": ("ID", "编号", "IDENTIFIER"),
    "feature_note": ("对应中文描述", "同上对应的中文描述", "FEATURE_NOTE"),
}


def placeholders_in(template_text: str) -> list[str]:
    names, seen = [], set()
    for match in PLACEHOLDER.finditer(template_text):
        name = re.sub(r"\s+", " ", match.group(1)).strip()
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


# Category keywords, checked in order. A key containing one of these words is
# treated as describing that kind of slot.
MEANING_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("thanks", ("感谢", "致谢", "thanks", "acknowledg")),
    # The changelog pairs each entry with a note; the English template has one
    # note slot per entry, which is what these keys describe.
    ("feature_note", ("对应中文描述", "同上对应", "对应的", "note for", "chinese description")),
    ("keywords", ("关键词", "keyword", "tag")),
    ("summary", ("摘要", "总结", "summary", "亮点", "highlight")),
    ("date", ("日期", "date", "发布日期", "周期", "period")),
    ("version", ("版本", "version")),
    ("author", ("作者", "author", "寄件人", "sender")),
    ("title", ("标题", "title", "主题", "subject", "公司", "名称", "作品")),
    ("url", ("url", "网址", "链接")),
    ("email", ("email", "邮箱")),
    ("metric", ("数字", "number", "指标", "数据", "data", "价格", "price")),
    ("chart_title", ("图表", "chart")),
    ("exchange", ("交易所", "exchange", "ticker")),
    ("confidentiality", ("密级", "机密", "confidential")),
    ("footer", ("页脚", "footer", "页码")),
)


def _match_by_meaning(key: str, names: list[str], taken: dict[str, str]) -> str | None:
    """The first unused slot whose name shares a category with the key."""
    lowered = key.lower()
    for category, words in MEANING_RULES:
        if not any(word in lowered for word in words):
            continue
        aliases = ALIASES.get(category, ())
        for name in names:
            if name in taken:
                continue
            if name in aliases or any(word in name.lower() for word in words):
                return name
    return None


def template_for(genre: str, language: str) -> Path | None:
    """The template a fixture's genre and language resolve to."""
    from shadow import _template_for

    try:
        return _template_for({"genre": genre, "language": language})
    except Exception:
        return None


def resolve(content: dict[str, Any], template_text: str) -> tuple[dict[str, str], list[str]]:
    """Map semantic keys onto the template's own placeholder names.

    Returns the resolved mapping and the keys that found no slot, so a fixture
    written against the wrong template is reported rather than silently empty.
    """
    names = placeholders_in(template_text)
    resolved: dict[str, str] = {}
    unresolved: list[str] = []

    for raw_key, value in content.items():
        # A fixture normally writes the template's own placeholder, braces and
        # all. The braces are syntax, not part of the name, so they come off
        # before anything is matched.
        key = raw_key.strip()
        if key.startswith("{{") and key.endswith("}}"):
            key = key[2:-2].strip()

        if key in names:
            resolved[key] = str(value)
            continue

        candidates = ALIASES.get(key, ())
        match = next((name for name in names if name in candidates), None)
        if match is None:
            # Fall back to a case-insensitive comparison, which catches the
            # uppercase family without listing every name twice.
            lowered = key.lower()
            match = next((name for name in names if name.lower() == lowered), None)
        if match is None:
            # Last resort: what kind of slot does this key describe? A fixture
            # written in Chinese rendered through an English template has no
            # literal match, and the author's intent is the category.
            match = _match_by_meaning(key, names, resolved)
        if match is None:
            unresolved.append(key)
        else:
            resolved.setdefault(match, str(value))

    return resolved, unresolved


def resolve_fixture(path: Path) -> dict[str, Any]:
    """Resolve one fixture's content against its template."""
    import corpus

    data = corpus.load_fixture(path)
    template = template_for(data.get("genre", ""), data.get("language", ""))
    if template is None or not template.is_file():
        return {
            "fixture": path.stem,
            "template": None,
            "resolved": {},
            "unresolved": sorted((data.get("content") or {}).keys()),
            "error": "no template resolved",
        }

    resolved, unresolved = resolve(data.get("content") or {}, template.read_text(encoding="utf-8"))
    return {
        "fixture": path.stem,
        "genre": data.get("genre"),
        "language": data.get("language"),
        "template": template.name,
        "semantic_keys": len(resolved),
        "unresolved": sorted(unresolved),
    }


def check_all() -> dict[str, Any]:
    """Report resolution across the whole corpus."""
    import corpus

    results = [resolve_fixture(p) for p in corpus.discover_fixtures()]
    with_unresolved = [r for r in results if r["unresolved"]]
    without_template = [r for r in results if r.get("error")]
    return {
        "fixtures": len(results),
        "fully_resolved": len(results) - len(with_unresolved),
        "with_unresolved": len(with_unresolved),
        "without_template": len(without_template),
        "details": with_unresolved[:10],
    }


def render_text(payload: dict[str, Any]) -> str:
    lines = ["Fixture content mapping", ""]
    lines.append(f"  fixtures            {payload['fixtures']}")
    lines.append(f"  fully resolved      {payload['fully_resolved']}")
    lines.append(f"  with unresolved     {payload['with_unresolved']}")
    lines.append(f"  without a template  {payload['without_template']}")
    if payload["details"]:
        lines.append("")
        lines.append("  Keys that found no slot (first 10 fixtures):")
        for item in payload["details"]:
            keys = ", ".join(item["unresolved"][:4])
            lines.append(f"    {item['fixture']}: {keys}")
    lines.append("")
    lines.append("  Unresolved keys are reported, not dropped: a fixture written against")
    lines.append("  the wrong template should fail loudly rather than render empty.")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="report resolution across the corpus").add_argument(
        "--format", choices=("text", "json"), default="text")
    resolve_cmd = sub.add_parser("resolve", help="resolve one fixture")
    resolve_cmd.add_argument("fixture")
    resolve_cmd.add_argument("--format", choices=("text", "json"), default="json")
    sub.add_parser("aliases", help="list the semantic key vocabulary")

    args = parser.parse_args(argv)

    if args.command == "check":
        payload = check_all()
        print(json.dumps(payload, indent=2, ensure_ascii=False)
              if args.format == "json" else render_text(payload))
        return 0

    if args.command == "resolve":
        payload = resolve_fixture(Path(args.fixture))
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    print("Semantic keys and the placeholder names they map to:")
    for key, names in sorted(ALIASES.items()):
        print(f"  {key:<18} {len(names)} alias(es)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
