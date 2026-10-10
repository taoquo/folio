"""Bridge existing template content into the IR.

The direction matters. This bridge reads a filled template and produces IR; it
does *not* parse arbitrary HTML back into semantics.

The blueprints are explicit about why: the visual classes in an existing
template cannot reliably recover the author's intent. A `<div class="takeaway">`
is a layout box, and guessing that it means "highlighted conclusion" would be
unverifiable. So the mapping here is a declared table — placeholder to semantic
role — that a reviewer can read and correct.

Nothing is inferred. A placeholder with no declared role becomes a
`raw_fallback` that names itself, so an incomplete bridge is visible instead of
silently lossy.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Literal

from .model import (
    Document,
    Metadata,
    ProfileRefs,
    SourceRef,
    Text,
    block,
)

PLACEHOLDER = re.compile(r"\{\{([^{}]*)\}\}")

Role = Literal["title", "subtitle", "eyebrow", "paragraph", "list_item", "quote",
               "action", "metric", "label", "footer", "ignore", "unmapped"]


@dataclass(frozen=True, slots=True)
class PlaceholderRole:
    """What a placeholder means semantically.

    `role: ignore` exists for placeholders that carry no content, such as a
    date stamp that a profile supplies. Naming them keeps the bridge honest
    without pretending they are body text.
    """

    role: Role
    block_id: str | None = None
    section: str | None = None
    # Heading depth, when the role is a heading. Kept on the role because the
    # same label sits at a different depth in different templates.
    block_id_level: int | None = None
    # For paragraph roles: which paragraph this is. `lead` is styled
    # differently by the templates, so the distinction is content, not taste.
    paragraph_role: str = "body"


@dataclass(frozen=True, slots=True)
class BridgeMap:
    """A declared mapping from placeholder text to semantic role."""

    genre: str
    language: str
    roles: dict[str, PlaceholderRole] = field(default_factory=dict)
    profiles: ProfileRefs = ProfileRefs()

    def role_for(self, placeholder: str) -> PlaceholderRole:
        """The declared role, or `unmapped`.

        The default is deliberately not `paragraph`: treating an undeclared
        placeholder as body text would hide a gap in the bridge behind plausible
        output. `unmapped` becomes a named fallback instead, so an incomplete
        mapping is visible in the artifact and in the fallback ratio.
        """
        if placeholder in self.roles:
            return self.roles[placeholder]

        # `短 bullet 3` is the third occurrence of `短 bullet`; a numbered form
        # takes its base's role so a repeated slot does not become a fallback.
        stripped = re.sub(r"\s*\d+$", "", placeholder).strip()
        if stripped and stripped != placeholder and stripped in self.roles:
            return self.roles[stripped]
        return PlaceholderRole("unmapped")


# A small, closed set of inline tags that a filled template may contain. This is
# not an HTML parser: it recognises the emphasis markers the templates already
# put in their own placeholder text and turns them into semantic inline nodes.
# Anything outside the set stays literal text, so unknown markup cannot silently
# become structure.
INLINE_TAG = re.compile(r"<(strong|em|b|i|span)(?:\s+class=\"([^\"]*)\")?>(.*?)</\1>", re.DOTALL)


def _normalise_id(value: str) -> str:
    """Reduce a proposed id to a valid reference token.

    The IR requires ids matching `^[A-Za-z0-9][A-Za-z0-9._-]*$`. A role table
    written from a template's own wording can carry spaces and slashes, so the
    id is normalised where it is assigned rather than trusted from the table.
    """
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    if not cleaned or not cleaned[0].isalnum():
        cleaned = f"n-{cleaned}" if cleaned else "node"
        cleaned = re.sub(r"[^A-Za-z0-9._-]", "", cleaned)
    return cleaned or "node"


def text_to_inlines(value: str) -> tuple:
    """Turn a value that may contain emphasis markers into inline nodes.

    The templates write `<span class="hl">` and `<strong>` inside their own
    placeholder text, so a filled value can legitimately carry them. Mapping
    them to `Strong` and a highlighted `Text` keeps the emphasis meaningful
    instead of escaping it into visible angle brackets.
    """
    from .model import Strong, Text

    nodes: list = []
    position = 0
    for match in INLINE_TAG.finditer(value):
        if match.start() > position:
            literal = value[position:match.start()]
            if literal:
                nodes.append(Text(value=literal))
        tag, css_class, inner = match.group(1).lower(), match.group(2) or "", match.group(3)
        inner_nodes = text_to_inlines(inner)
        if tag in {"strong", "b"}:
            nodes.append(Strong(content=tuple(inner_nodes)))
        elif tag in {"em", "i"}:
            from .model import Emphasis

            nodes.append(Emphasis(content=tuple(inner_nodes)))
        elif "hl" in css_class.split():
            # The author marked a key claim; how it is emphasised is a theme
            # decision, so the IR records the claim rather than the styling.
            nodes.append(Text(value=_plain(inner), highlight=True))
        else:
            nodes.extend(inner_nodes)
        position = match.end()
    if position < len(value):
        remainder = value[position:]
        if remainder:
            nodes.append(Text(value=remainder))
    return tuple(nodes) if nodes else (Text(value=value),)


def _plain(value: str) -> str:
    """Text with any nested markup removed."""
    return re.sub(r"<[^>]+>", "", value)


def _slug(text: str, *, fallback: str) -> str:
    """A stable, reference-safe id derived from placeholder text.

    Derived from the text rather than from position, so reordering a template
    does not renumber every node. Ids must survive use as a URL fragment and as
    a cross-reference target, so non-ASCII placeholder text -- which most
    Chinese templates use -- is hashed rather than transliterated: a stable
    opaque id beats an unstable readable one.
    """
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    if len(cleaned) >= 3:
        return cleaned[:48]
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
    return f"{fallback}-{digest}"


def placeholders_in(template_text: str) -> list[str]:
    """Placeholder texts in document order, de-duplicated."""
    seen: list[str] = []
    for match in PLACEHOLDER.finditer(template_text):
        name = match.group(1)
        if name not in seen:
            seen.append(name)
    return seen


def bridge_template(
    template_text: str,
    values: dict[str, str],
    *,
    document_id: str,
    lang: str,
    genre: str,
    title: str | None = None,
    bridge_map: BridgeMap | None = None,
    source_id: str = "<template>",
) -> Document:
    """Build IR from a template plus the values filled into it.

    Every placeholder the template declares is accounted for: it either maps to
    a semantic block or becomes a named fallback. Nothing is dropped silently,
    because a lossy bridge that reports success is worse than one that fails.
    """
    mapping = bridge_map or BridgeMap(genre=genre, language=lang)

    # Structural labels default the same way the build defaults them. A fixture
    # describes the document's content; the section headings are the template's
    # structure and should not have to be repeated per fixture.
    from section_defaults import defaults_for

    effective_values = dict(values)
    for placeholder, default in defaults_for(template_text).items():
        if placeholder not in effective_values and placeholder in template_text:
            effective_values[placeholder] = default
    values = effective_values

    blocks = []
    sections: dict[str, list] = {}
    order: list[str] = []

    # The template's own placeholders first, then any value the fixture
    # provides under a key the template does not literally declare, such as the
    # numbered forms that stand for a repeated slot.
    names_to_place = list(placeholders_in(template_text))
    declared = set(names_to_place)
    for extra in values:
        if extra not in declared:
            names_to_place.append(extra)

    # Ids already used in this document. Two placeholders may map to one slot,
    # and an id has to identify exactly one node, so a repeat is given a suffix
    # rather than overwriting or colliding.
    used_ids: set[str] = set()

    for index, name in enumerate(names_to_place):
        value = values.get(name, "").strip()
        if not value:
            continue
        role = mapping.role_for(name)
        if role.role == "ignore":
            continue

        node_id = _normalise_id(role.block_id) if role.block_id else _slug(name, fallback=f"node-{index}")
        # A numbered placeholder shares its base's id, and two nodes cannot share
        # an id: the second section's bullets were collapsed onto the first's.
        number = re.search(r"\s*(\d+)$", name)
        if role.block_id and number and name not in mapping.roles:
            node_id = f"{role.block_id}-{number.group(1)}"

        # A placeholder that maps onto an id another placeholder already used
        # keeps its own node under a distinct id, so the document validates and
        # no content is dropped.
        if node_id in used_ids:
            suffix = 2
            while f"{node_id}-{suffix}" in used_ids:
                suffix += 1
            node_id = f"{node_id}-{suffix}"
        used_ids.add(node_id)
        source = SourceRef(source_id=source_id, locator=name)

        # One branch per role, each ending in `continue`. Falling through would
        # emit the same node twice under two ids, which the validator reports as
        # duplicate content rather than as the control-flow mistake it is.
        if role.role == "title":
            # The title appears twice on purpose: once in metadata, which is what
            # a reader or a screen reader announces, and once as a heading block,
            # because the template renders it visibly. Metadata alone would drop
            # the most prominent text on the page.
            blocks.append(block("heading", node_id, level=1,
                                content=text_to_inlines(value), source=source))
            continue
        if role.role == "heading":
            # A structural label such as `Changelog` or `Features`. The level is
            # a rendering choice, so it is fixed here rather than carried in the
            # role: the IR states what the label is, not how large it prints.
            blocks.append(block("heading", node_id, level=int(role.block_id_level or 2),
                                content=text_to_inlines(value), source=source))
            continue
        if role.role == "subtitle":
            blocks.append(block("paragraph", node_id, role="lead",
                                content=text_to_inlines(value), source=source))
            continue
        if role.role == "eyebrow":
            blocks.append(block("heading", node_id, level=2,
                                content=text_to_inlines(value), source=source))
            continue
        if role.role == "paragraph":
            blocks.append(block("paragraph", node_id, role=role.paragraph_role,
                                content=text_to_inlines(value), source=source))
            continue
        if role.role == "list_item":
            blocks.append(block("list", node_id, ordered=False,
                                items=(_list_item(f"{node_id}-i1", value),), source=source))
            continue
        if role.role == "quote":
            blocks.append(block("quote", node_id, content=text_to_inlines(value), source=source))
            continue
        if role.role == "action":
            blocks.append(block("callout", node_id, kind="action",
                                content=text_to_inlines(value), source=source))
            continue
        if role.role in {"metric", "label"}:
            blocks.append(block("paragraph", node_id, role="annotation",
                                content=text_to_inlines(value), source=source))
            continue
        if role.role == "footer":
            blocks.append(block("paragraph", node_id, role="footer",
                                content=text_to_inlines(value), source=source))
            continue

        blocks.append(
            block(
                "raw_fallback",
                node_id,
                value=value,
                reason=f"bridge has no semantic role for placeholder '{name}'",
                source=source,
            )
        )

        if role.section:
            sections.setdefault(role.section, []).append(blocks.pop())

    # Grouped placeholders become sections, preserving declaration order.
    for section_name in sections:
        order.append(section_name)

    nested = [
        block("section", f"section-{_slug(name, fallback=f's{index}')}",
              role="body", title=(Text(name),), children=tuple(sections[name]))
        for index, name in enumerate(order)
    ]

    return Document(
        id=document_id,
        lang=lang,
        metadata=Metadata(
            title=title or values.get("title") or document_id,
            genre=genre,
        ),
        profiles=mapping.profiles,
        blocks=tuple(nested + blocks),
    )


def _list_item(item_id: str, value: str):
    from .model import ListItem

    return ListItem(id=item_id, content=text_to_inlines(value))


def default_map_for(genre: str, language: str) -> BridgeMap:
    """The declared mapping for the shipped templates.

    Written out rather than inferred. A reviewer can read this table and see
    exactly which placeholder becomes which semantic node.
    """
    zh = language.lower().startswith("zh")
    if genre == "one-pager":
        roles = {
            "section 标题 1": PlaceholderRole("eyebrow", "h-section-1"),
            "section 标题 2": PlaceholderRole("eyebrow", "h-section-2"),
            "DECISION_LABEL": PlaceholderRole("label", "p-decision-label"),
            "ROADMAP_TITLE": PlaceholderRole("heading", "h-roadmap"),
            "ROADMAP_NOTE": PlaceholderRole("label", "p-roadmap-note"),
            "STAGE_1_TITLE": PlaceholderRole("label", "p-stage-1"),
            "STAGE_2_TITLE": PlaceholderRole("label", "p-stage-2"),
            "STAGE_3_TITLE": PlaceholderRole("label", "p-stage-3"),
            "EYEBROW · 如 \"产品方案\" / \"项目提案\" / \"执行摘要\"": PlaceholderRole("eyebrow", "p-eyebrow"),
            "关键词": PlaceholderRole("label", "p-keywords"),
            "标签描述": PlaceholderRole("label", "p-metric-label"),
            "标签": PlaceholderRole("label", "p--"),
            "数字": PlaceholderRole("metric", "p-metric"),
            "日期 YYYY.MM.DD": PlaceholderRole("label", "p-meta-date"),
            "版本号 / 状态": PlaceholderRole("label", "p-meta-version"),
            "机密级别 / 内部 / 公开 等": PlaceholderRole("label", "p-confidentiality"),
            "负责人 / 截止日": PlaceholderRole("label", "p-owner"),
            "阶段标题": PlaceholderRole("label", "p-tl-year"),
            "页码 / 联系方式": PlaceholderRole("footer", "p-footer"),
            "作者": PlaceholderRole("label", "p-meta-author"),
            "作者名": PlaceholderRole("label", "p-meta-author"),
            "文档主标题（serif，2 行内，动词+名词结构最好）": PlaceholderRole("title", "h-title"),
            "文档标题": PlaceholderRole("label", "p--"),
            "一行副标题 / 一句核心论点": PlaceholderRole("subtitle", "p-subtitle"),
            "一段 40-60 字的核心论点导语。用「<span class=\"hl\">关键词</span>」高亮重点。这段定调整个文档。":
                PlaceholderRole("paragraph", "p-lede", paragraph_role="lead"),
            "这里写 1-2 句段落，展开论点。": PlaceholderRole("paragraph", "p-body-1"),
            "1-2 句段落。": PlaceholderRole("paragraph", "p-body-2"),
            "短 bullet：数据/观察/判断": PlaceholderRole("list_item", "l-observations"),
            "短 bullet：带 <span class=\"hl\">关键数字</span> 的论据": PlaceholderRole("list_item", "l-evidence"),
            "短 bullet": PlaceholderRole("list_item", "l-notes"),
            "关键引用 / 重要提示 / 核心 takeaway。比正文更需要引起注意的内容放这里。":
                PlaceholderRole("quote", "q-takeaway"),
            "建议采取的单一动作：批准 / 暂缓 / 追加资源 / 进入下一阶段。":
                PlaceholderRole("action", "c-action"),
            "一句解释": PlaceholderRole("paragraph", "p-explain"),
            "摘要": PlaceholderRole("paragraph", "p-summary"),
        } if zh else {
            "Section one": PlaceholderRole("eyebrow", "h-section-1"),
            "Section two": PlaceholderRole("eyebrow", "h-section-2"),
            "DECISION_LABEL": PlaceholderRole("label", "p-decision-label"),
            "ROADMAP_TITLE": PlaceholderRole("heading", "h-roadmap"),
            "ROADMAP_NOTE": PlaceholderRole("label", "p-roadmap-note"),
            "STAGE_1_TITLE": PlaceholderRole("label", "p-stage-1"),
            "STAGE_2_TITLE": PlaceholderRole("label", "p-stage-2"),
            "STAGE_3_TITLE": PlaceholderRole("label", "p-stage-3"),
            "EYEBROW - e.g. Proposal / Report / Exec Summary": PlaceholderRole("eyebrow", "p-eyebrow"),
            "KEYWORDS": PlaceholderRole("label", "p-keywords"),
            "LABEL": PlaceholderRole("label", "p-label"),
            "NUMBER": PlaceholderRole("metric", "p-metric"),
            "YYYY.MM.DD": PlaceholderRole("label", "p-YYYY.MM.DD"),
            "VERSION / STATUS": PlaceholderRole("label", "p-VERSION / STATUS"),
            "CONFIDENTIALITY - internal / public / draft": PlaceholderRole("label", "p-CONFIDENTIALITY - intern"),
            "Owner / due date": PlaceholderRole("label", "p-owner"),
            "STAGE_TITLE": PlaceholderRole("eyebrow", "p-stage"),
            "PAGE / CONTACT": PlaceholderRole("footer", "p-footer"),
            "AUTHOR": PlaceholderRole("label", "p-meta-author"),
            "Document headline - verb-led, fits in two lines, bookish.":
                PlaceholderRole("title", "h-title"),
            "DOC_TITLE": PlaceholderRole("label", "p-DOC_TITLE"),
            "One-line subtitle or the single sharpest claim.":
                PlaceholderRole("subtitle", "p-subtitle"),
            "~30-40 words. The one paragraph that sets the whole document's tone. Use <span class=\"hl\">brand-color emphasis</span> on the sharpest claim or number. Everything below is in service of this.":
                PlaceholderRole("paragraph", "p-lede", paragraph_role="lead"),
            "One or two sentences expanding the claim.":
                PlaceholderRole("paragraph", "p-body-1"),
            "One or two sentences.": PlaceholderRole("paragraph", "p-body-2"),
            "Short bullet: a data point, observation, or judgment.":
                PlaceholderRole("list_item", "l-observations"),
            "Short bullet with <span class=\"hl\">key figure</span>.":
                PlaceholderRole("list_item", "l-evidence"),
            "Short bullet.": PlaceholderRole("list_item", "l-notes"),
            "Key quote / critical note / the single takeaway that must not be missed.":
                PlaceholderRole("quote", "q-takeaway"),
            "The single recommended action: approve, pause, fund, or move to the next phase.":
                PlaceholderRole("action", "c-action"),
            "One-line explanation.": PlaceholderRole("paragraph", "p-explain"),
            "DESCRIPTION": PlaceholderRole("paragraph", "p-summary"),
        }
        profiles = ProfileRefs(
            typography=f"folio-one-pager-{'zh' if zh else 'en'}-v1",
            page="a4-one-pager-v1",
            language="zh-hans-cn-v1" if zh else "en-us-v1",
            theme="folio-classic-v1",
            taste="one-pager-v1",
        )
        return BridgeMap(genre=genre, language=language, roles=roles, profiles=profiles)

    if genre == "changelog":
        roles = {
            "SECTION_CHANGELOG": PlaceholderRole("heading", "h-changelog"),
            "SECTION_CHANGELOG_ZH": PlaceholderRole("heading", "h-changelog-zh"),
            "SECTION_BREAKING": PlaceholderRole("heading", "h-breaking"),
            "SECTION_BREAKING_ZH": PlaceholderRole("heading", "h-breaking-zh"),
            "SECTION_FEATURES": PlaceholderRole("heading", "h-features"),
            "SECTION_FEATURES_ZH": PlaceholderRole("heading", "h-features-zh"),
            "SECTION_FIXES": PlaceholderRole("heading", "h-fixes"),
            "SECTION_FIXES_ZH": PlaceholderRole("heading", "h-fixes-zh"),
            "SECTION_THANKS": PlaceholderRole("heading", "h-thanks"),
            "版本号": PlaceholderRole("label", "p-version"),
            "版本名称": PlaceholderRole("eyebrow", "h-release"),
            "发布日期": PlaceholderRole("label", "p-release-date"),
            "项目名": PlaceholderRole("label", "p-project-name"),
            "项目 URL": PlaceholderRole("footer", "p-project-url"),
            "项目一句话描述": PlaceholderRole("paragraph", "p-project", ),
            "作者": PlaceholderRole("label", "p-meta-author"),
            "关键词": PlaceholderRole("label", "p-keywords"),
            "一句话版本亮点": PlaceholderRole("paragraph", "p-highlight"),
            "摘要": PlaceholderRole("paragraph", "p-summary"),
            "新功能 1：一句话描述": PlaceholderRole("list_item", "l-added"),
            "新功能 2：一句话描述": PlaceholderRole("list_item", "l-added-2"),
            "新功能 3：一句话描述": PlaceholderRole("list_item", "l-added-3"),
            "修复 1：一句话描述": PlaceholderRole("list_item", "l-fixed"),
            "修复 2：一句话描述": PlaceholderRole("list_item", "l-fixed-2"),
            "修复 3：一句话描述": PlaceholderRole("list_item", "l-fixed-3"),
            "对应中文描述": PlaceholderRole("label", "p-note-1"),
            "同上对应的中文描述": PlaceholderRole("label", "p-note-2"),
            "破坏性变更描述": PlaceholderRole("action", "c-breaking"),
            "感谢贡献者，格式如：\"感谢 @user1、@user2 的贡献。\"": PlaceholderRole("footer", "p-thanks"),
            "VERSION": PlaceholderRole("label", "p-version"),
            "RELEASE_NAME": PlaceholderRole("eyebrow", "h-release"),
            "RELEASE_DATE": PlaceholderRole("label", "p-release-date"),
            "PROJECT_NAME": PlaceholderRole("label", "p-project-name"),
            "PROJECT_URL": PlaceholderRole("footer", "p-project-url"),
            "One-line project description.": PlaceholderRole("paragraph", "p-project"),
            "AUTHOR": PlaceholderRole("label", "p-meta-author"),
            "KEYWORDS": PlaceholderRole("label", "p-keywords"),
            "One-line release highlight.": PlaceholderRole("paragraph", "p-highlight"),
            "DESCRIPTION": PlaceholderRole("paragraph", "p-summary"),
            "New feature 1: one-line description.": PlaceholderRole("list_item", "l-added"),
            "New feature 2: one-line description.": PlaceholderRole("list_item", "l-added-2"),
            "New feature 3: one-line description.": PlaceholderRole("list_item", "l-added-3"),
            "Fix 1: one-line description.": PlaceholderRole("list_item", "l-fixed"),
            "Fix 2: one-line description.": PlaceholderRole("list_item", "l-fixed-2"),
            "Fix 3: one-line description.": PlaceholderRole("list_item", "l-fixed-3"),
            "Breaking change description.": PlaceholderRole("action", "c-breaking"),
            "Thank contributors, e.g. \"Thanks to @user1, @user2 for their contributions.\"": PlaceholderRole("footer", "p-thanks"),
        }
        profiles = ProfileRefs(
            typography=f"folio-changelog-{'zh' if zh else 'en'}-v1",
            page="a4-changelog-v1",
            language="zh-hans-cn-v1" if zh else "en-us-v1",
            theme="folio-classic-v1",
            taste="changelog-v1",
        )
        return BridgeMap(genre=genre, language=language, roles=roles, profiles=profiles)

    if genre == "letter":
        roles = {
            "作者": PlaceholderRole("label", "p-meta-author"),
            "摘要": PlaceholderRole("paragraph", "p-summary"),
            "关键词": PlaceholderRole("label", "p-keywords"),
            "信件主题": PlaceholderRole("eyebrow", "h-subject"),
            "信件主题，一句话说清": PlaceholderRole("paragraph", "p-subject-detail"),
            "收件人姓名 / 称谓": PlaceholderRole("label", "p--"),
            "收件人机构 / 部门": PlaceholderRole("label", "p--"),
            "寄件人姓名": PlaceholderRole("label", "p--"),
            "寄件人地址 / 部门 / 机构": PlaceholderRole("label", "p--"),
            "日期 如 2026 年 4 月 18 日": PlaceholderRole("label", "p--2026 年 4 月 18 日"),
            "敬语。中文常用 \"此致 / 敬礼！\"、\"顺颂商祺\"。英文 \"Best regards,\" / \"Sincerely,\"": PlaceholderRole("footer", "p-closing"),
            "此致": PlaceholderRole("footer", "p-closing"),
            "EMAIL": PlaceholderRole("label", "p-EMAIL"),
            "署名": PlaceholderRole("footer", "p-signature"),
        }
        profiles = ProfileRefs(
            typography=f"folio-letter-{'zh' if zh else 'en'}-v1",
            page="a4-letter-v1",
            language="zh-hans-cn-v1" if zh else "en-us-v1",
            theme="folio-classic-v1",
            taste="letter-v1",
        )
        return BridgeMap(genre=genre, language=language, roles=roles, profiles=profiles)

    if genre == "portfolio":
        roles = {
            "一句自我定位的 headline": PlaceholderRole("title", "h-headline"),
            "一句自我描述 / 作品集主题": PlaceholderRole("subtitle", "p-intro"),
            "一句描述": PlaceholderRole("paragraph", "p-desc"),
            "一句话描述": PlaceholderRole("paragraph", "p-desc-2"),
            "一句话描述这个项目做了什么": PlaceholderRole("list_item", "l-project"),
            "一段关于你当前的关注点 / 方法论。": PlaceholderRole("paragraph", "p-focus"),
            "一段关于你过往经历的概述。": PlaceholderRole("paragraph", "p-history"),
            "作品标题": PlaceholderRole("eyebrow", "h-work"),
            "专业 / 角色": PlaceholderRole("label", "p-role"),
            "EMAIL": PlaceholderRole("label", "p-EMAIL"),
            "URL": PlaceholderRole("label", "p-URL"),
            "ID": PlaceholderRole("label", "p-ID"),
        }
        profiles = ProfileRefs(
            typography=f"folio-portfolio-{'zh' if zh else 'en'}-v1",
            page="a4-portfolio-v1",
            language="zh-hans-cn-v1" if zh else "en-us-v1",
            theme="folio-classic-v1",
            taste="portfolio-v1",
        )
        return BridgeMap(genre=genre, language=language, roles=roles, profiles=profiles)

    if genre == "equity-report":
        roles = {
            "EYEBROW · 如 \"个股研报\" / \"估值分析\" / \"投资备忘\"": PlaceholderRole("eyebrow", "p-eyebrow"),
            "公司名称": PlaceholderRole("title", "h-company"),
            "一句核心判断": PlaceholderRole("subtitle", "p-thesis-short"),
            "2-3 句核心投资论点。用 <span class=\"hl\">关键数据</span> 支撑判断。这段是整份研报的灵魂。":
                PlaceholderRole("paragraph", "p-thesis"),
            "3-5 句总结。包含目标价（如有）、评级建议、核心催化剂、关键假设。":
                PlaceholderRole("callout", "c-summary"),
            "一句话总结：买入/持有/观望的核心理由。": PlaceholderRole("quote", "q-rating"),
            "图表标题": PlaceholderRole("eyebrow", "h-chart"),
            "图表标题，如 \"近 20 个交易日价格走势\"": PlaceholderRole("eyebrow", "h-chart-2"),
            "作者": PlaceholderRole("label", "p-meta-author"),
            "关键词": PlaceholderRole("label", "p-keywords"),
            "交易所": PlaceholderRole("label", "p--"),
            "周期": PlaceholderRole("label", "p--"),
        }
        profiles = ProfileRefs(
            typography=f"folio-equity-report-{'zh' if zh else 'en'}-v1",
            page="a4-equity-report-v1",
            language="zh-hans-cn-v1" if zh else "en-us-v1",
            theme="folio-classic-v1",
            taste="equity-research-v1",
        )
        return BridgeMap(genre=genre, language=language, roles=roles, profiles=profiles)

    if genre == "long-doc":
        roles = {
            "EYEBROW · 如 \"技术报告\" / \"年度总结\" / \"白皮书\"": PlaceholderRole("eyebrow", "p-eyebrow"),
            "Takeaway 1：一句话，可量化的结论": PlaceholderRole("list_item", "l-takeaway"),
            "Takeaway 2：有数据的洞察": PlaceholderRole("list_item", "l-takeaway-2"),
            "Takeaway 3：对未来的判断": PlaceholderRole("list_item", "l-takeaway-3"),
            "一段论述。": PlaceholderRole("paragraph", "p-body"),
            "一段论述。包含数据：<span class=\"hl\">具体数字 / 具体比例</span>。":
                PlaceholderRole("paragraph", "p-body-data"),
            "3-5 行段落，铺陈当前状况。用 <span class=\"hl\">具体数据</span> 而不是形容词。":
                PlaceholderRole("paragraph", "p-situation"),
            "一段重要引用或核心观察。和正文语气略有不同，给读者呼吸节奏。":
                PlaceholderRole("quote", "q-observation"),
            "一段引用，可以是用户访谈、专家观点、文献引用": PlaceholderRole("quote", "q-source"),
            "描述方法论。可以用代码 / 公式示例：": PlaceholderRole("paragraph", "p-method"),
            "基于结论的具体可执行建议。": PlaceholderRole("callout", "c-recommendation"),
            "如果读者要做一件事，是什么？具体到可以周一早上就开始行动。":
                PlaceholderRole("callout", "c-action"),
            "定义": PlaceholderRole("paragraph", "p-definition"),
            "差距": PlaceholderRole("paragraph", "p-gap"),
            "术语": PlaceholderRole("label", "p-term"),
            "标题": PlaceholderRole("eyebrow", "h-section"),
            "作者 / 团队": PlaceholderRole("label", "p--"),
            "作者": PlaceholderRole("label", "p-meta-author"),
            "关键词": PlaceholderRole("label", "p-keywords"),
            "日期": PlaceholderRole("label", "p--"),
            "日期 2026.04": PlaceholderRole("label", "p--2026.04"),
            "发布方 / 机构": PlaceholderRole("label", "p--"),
            "摘要": PlaceholderRole("paragraph", "p-summary"),
            "数据": PlaceholderRole("metric", "p-data"),
            "来源 / 人物": PlaceholderRole("label", "p--"),
            "参考文献 1": PlaceholderRole("footer", "p-ref-1"),
            "参考文献 2": PlaceholderRole("footer", "p-ref-2"),
        }
        profiles = ProfileRefs(
            typography=f"folio-long-doc-{'zh' if zh else 'en'}-v1",
            page="a4-long-doc-v1",
            language="zh-hans-cn-v1" if zh else "en-us-v1",
            theme="folio-classic-v1",
            taste="professional-research-v1",
        )
        return BridgeMap(genre=genre, language=language, roles=roles, profiles=profiles)

    if genre == "resume":
        # A resume's placeholders are dominated by contact fields, which are
        # metadata rather than prose. Only the substantive sections become
        # blocks, so the IR does not fill with fragments of an email address.
        roles = {}
        # Contact fields are content: a resume without its email is not a
        # resume. They carry a label role and the skeleton writer places them in
        # the slots the template declares.
        for key in ("EMAIL", "PHONE", "URL", "HANDLE", "GITHUB_ID", "GITHUB_URL",
                    "X_ID", "STARS", "STARS_TOTAL", "FORKS_TOTAL", "FOLLOWERS_TOTAL"):
            roles[key] = PlaceholderRole("label", f"p-contact-{key.lower().replace('_', '-')}")
        roles.update({
            "80 字以内。建议结构：现任职位 + 级别 + 时长。团队构成（人数、梯队、协作方）。长期演进方向。核心沉淀领域（4-6 个方向）。":
                PlaceholderRole("paragraph", "p-summary"),
            "一段关于你当前工作": PlaceholderRole("paragraph", "p-role"),
            "一句自我定位": PlaceholderRole("subtitle", "p-positioning"),
            "姓名": PlaceholderRole("title", "h-name"),
            "姓名（英文）": PlaceholderRole("label", "p--"),
        })
        profiles = ProfileRefs(
            typography=f"folio-resume-{'zh' if zh else 'en'}-v1",
            page="a4-resume-v1",
            language="zh-hans-cn-v1" if zh else "en-us-v1",
            theme="folio-classic-v1",
            taste="resume-v1",
        )
        return BridgeMap(genre=genre, language=language, roles=roles, profiles=profiles)

    return BridgeMap(genre=genre, language=language)
