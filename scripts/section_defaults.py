#!/usr/bin/env python3
"""Defaults for structural labels that a template promotes to placeholders.

A section label is content: `Changelog`, `Features` and `Fixes` are the
document's structure, not its decoration. When a label moves into a
placeholder so the IR can express it, the template still has to render on
its own -- the build fills placeholders from the author, and an author who
says nothing should get the wording the template used to carry.

The two template families share placeholder names but not wording, so the
default is selected by the document's language.
"""

from __future__ import annotations

# Shared labels: identical in both languages.
SHARED_DEFAULTS: dict[str, str] = {
    "SECTION_CHANGELOG": "Changelog",
    "SECTION_BREAKING": "Breaking Changes",
    "SECTION_FEATURES": "Features",
    "SECTION_FIXES": "Fixes",
    "DECISION_LABEL": "Decision",
}

ZH_DEFAULTS: dict[str, str] = {
    "SECTION_CHANGELOG_ZH": "更新日志",
    "SECTION_BREAKING_ZH": "破坏性变更",
    "SECTION_FEATURES_ZH": "新功能",
    "SECTION_FIXES_ZH": "修复",
    "SECTION_THANKS": "致谢",
    "ROADMAP_TITLE": "时间线 / 路线图",
    "ROADMAP_NOTE": "（适用于方案类文档）",
    "STAGE_1_TITLE": "阶段 1",
    "STAGE_2_TITLE": "阶段 2",
    "STAGE_3_TITLE": "阶段 3",
}

EN_DEFAULTS: dict[str, str] = {
    "SECTION_THANKS": "Acknowledgements",
    "ROADMAP_TITLE": "Roadmap",
    "ROADMAP_NOTE": "three-step arc for proposals",
    "STAGE_1_TITLE": "Phase 1",
    "STAGE_2_TITLE": "Phase 2",
    "STAGE_3_TITLE": "Phase 3",
}


def defaults_for(html: str) -> dict[str, str]:
    """The default set for a template, chosen by its language."""
    is_english = 'lang="en' in html or "en-US" in html[:600]
    merged = dict(SHARED_DEFAULTS)
    merged.update(EN_DEFAULTS if is_english else ZH_DEFAULTS)
    return merged


def apply_section_defaults(html: str) -> str:
    """Replace any unfilled structural label with its default wording."""
    import re

    table = defaults_for(html)

    def replace(match: re.Match) -> str:
        name = match.group(1).strip()
        return table.get(name, match.group(0))

    return re.sub(r"\{\{([^{}]*)\}\}", replace, html)

# The flat table is kept for callers that only need the Chinese set, which is
# the default language of the templates.
SECTION_LABEL_DEFAULTS: dict[str, str] = {**SHARED_DEFAULTS, **ZH_DEFAULTS}
