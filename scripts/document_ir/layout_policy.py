"""Layout policy: what should happen at a page boundary.

A policy states intent — keep this with the next block, prefer this figure at
the top of a page, reserve space for footnotes. It never states a coordinate or
an engine directive, so the same policy can be handed to a different renderer.

The policy is compiled to CSS separately. That split is the point: the intent
is reviewable on its own, and the CSS it produces is one translation of it
rather than the definition of it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

# Semantic node types are not CSS selectors. The mapping is explicit so a
# policy stays renderer-neutral while still compiling to something a browser or
# a paged-media engine understands.
SELECTOR_FOR = {
    "heading": "h1, h2, h3, h4, h5, h6",
    "figure": "figure",
    "diagram": "figure",
    "table": "table",
    "paragraph": "p",
    "list": "ul, ol",
    "quote": "blockquote",
    "callout": ".callout",
    "code_block": "pre",
}


def selectors_for(kinds: tuple[str, ...]) -> str:
    """Compile node types to a CSS selector list, de-duplicated."""
    selectors: list[str] = []
    for kind in kinds:
        selector = SELECTOR_FOR.get(kind, f".{kind}")
        if selector not in selectors:
            selectors.append(selector)
    return ", ".join(selectors)


# Where a float may be placed. Ordered by preference.
FloatPosition = Literal["top", "bottom", "inline", "next-page-top"]
BreakStrength = Literal["auto", "prefer", "require"]


@dataclass(frozen=True, slots=True)
class KeepRule:
    """A relationship that should survive a page boundary."""

    # Which blocks the rule applies to, by node type or semantic role.
    applies_to: tuple[str, ...]
    with_next: bool = True
    minimum_following_lines: int = 2

    def to_json(self) -> dict[str, Any]:
        return {
            "applies_to": list(self.applies_to),
            "with_next": self.with_next,
            "minimum_following_lines": self.minimum_following_lines,
        }


@dataclass(frozen=True, slots=True)
class FloatRule:
    """Where a float prefers to land, and how long it may wait."""

    applies_to: tuple[str, ...]
    preferred: tuple[FloatPosition, ...] = ("top", "bottom", "inline")
    max_defer_pages: int = 1

    def to_json(self) -> dict[str, Any]:
        return {
            "applies_to": list(self.applies_to),
            "preferred": list(self.preferred),
            "max_defer_pages": self.max_defer_pages,
        }


@dataclass(frozen=True, slots=True)
class FootnotePolicy:
    placement: Literal["same-page-preferred", "end-of-section", "end-of-document"] = "same-page-preferred"
    allow_split: bool = True
    marker_style: Literal["numeric", "symbol"] = "numeric"

    def to_json(self) -> dict[str, Any]:
        return {
            "placement": self.placement,
            "allow_split": self.allow_split,
            "marker_style": self.marker_style,
        }


@dataclass(frozen=True, slots=True)
class PageBreakPolicy:
    """When a break should happen before a block.

    `before_level_1` defaults to `auto`, not to a preferred break. A level-1
    heading is the document title in most of these templates -- the one-pager
    has exactly one -- and forcing a break there splits a single-page document.
    A genre that does open chapters asks for the break explicitly.
    """

    before_level_1: BreakStrength = "auto"
    before_level_2: BreakStrength = "auto"
    # A page-count objective: a preference a policy may trade against other
    # objectives, never a reason to shrink type without a recorded decision.
    page_count_mode: Literal["hard", "soft"] = "soft"
    page_count_target: int | None = None
    page_count_tolerance: int = 1

    def to_json(self) -> dict[str, Any]:
        return {
            "before_level_1": self.before_level_1,
            "before_level_2": self.before_level_2,
            "page_count": {
                "mode": self.page_count_mode,
                "target": self.page_count_target,
                "tolerance": self.page_count_tolerance,
            },
        }


@dataclass(frozen=True, slots=True)
class LayoutPolicy:
    """The whole policy for one document."""

    name: str
    keeps: tuple[KeepRule, ...] = ()
    floats: tuple[FloatRule, ...] = ()
    footnotes: FootnotePolicy = FootnotePolicy()
    breaks: PageBreakPolicy = PageBreakPolicy()
    widow_lines: int = 2
    orphan_lines: int = 2

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "keeps": [k.to_json() for k in self.keeps],
            "floats": [f.to_json() for f in self.floats],
            "footnotes": self.footnotes.to_json(),
            "breaks": self.breaks.to_json(),
            "widow_lines": self.widow_lines,
            "orphan_lines": self.orphan_lines,
        }

    def keep_for(self, kind: str) -> KeepRule | None:
        for rule in self.keeps:
            if kind in rule.applies_to:
                return rule
        return None

    def float_for(self, kind: str) -> FloatRule | None:
        for rule in self.floats:
            if kind in rule.applies_to:
                return rule
        return None


# Defaults that apply to every genre. A genre policy narrows these rather than
# restating them, so an unset value has one meaning in one place.
DEFAULT_KEEPS = (
    KeepRule(applies_to=("heading",), with_next=True, minimum_following_lines=2),
    KeepRule(applies_to=("figure", "diagram"), with_next=False),
    KeepRule(applies_to=("table",), with_next=False),
)

DEFAULT_FLOATS = (
    FloatRule(applies_to=("figure", "diagram"), preferred=("top", "bottom", "inline"), max_defer_pages=1),
)


def policy_for(page_profile: Mapping[str, Any], *, name: str) -> LayoutPolicy:
    """Build a policy from a page profile.

    The profile is the source of truth for page geometry and page-count
    contracts; this function only translates it into layout intent.
    """
    pagination = page_profile.get("pagination") or {}
    contract = page_profile.get("page_count") or {}

    heading_keep = pagination.get("heading_keep") or {}
    keeps = list(DEFAULT_KEEPS)
    if heading_keep.get("enabled"):
        keeps = [
            KeepRule(
                applies_to=("heading",),
                with_next=True,
                minimum_following_lines=int(heading_keep.get("minimum_following_lines", 2)),
            )
        ] + [k for k in keeps if "heading" not in k.applies_to]

    return LayoutPolicy(
        name=name,
        keeps=tuple(keeps),
        floats=DEFAULT_FLOATS,
        footnotes=FootnotePolicy(),
        breaks=PageBreakPolicy(
            page_count_mode=str(contract.get("mode", "soft")),
            page_count_target=contract.get("target") or contract.get("exact"),
            page_count_tolerance=int(contract.get("tolerance_pages", 1)),
        ),
        widow_lines=int(pagination.get("widow_lines", 2)),
        orphan_lines=int(pagination.get("orphan_lines", 2)),
    )


def to_css(policy: LayoutPolicy) -> str:
    """Compile the policy to CSS.

    One translation, kept deliberately thin. Every declaration cites the intent
    it comes from in a comment, so a reviewer can trace a rule back to the
    policy that produced it rather than guessing why it is there.
    """
    lines: list[str] = [f"/* Layout policy: {policy.name} */", ""]

    lines.append(f"/* from widow_lines / orphan_lines: {policy.widow_lines} / {policy.orphan_lines} */")
    lines.append(f"body {{ widows: {policy.widow_lines}; orphans: {policy.orphan_lines}; }}")
    lines.append("")

    for rule in policy.keeps:
        selector = selectors_for(rule.applies_to)
        if rule.with_next:
            lines.append(
                f"/* from keep rule for {selector}: minimum {rule.minimum_following_lines} following lines */"
            )
            lines.append(f"{selector} {{ break-after: avoid; }}")
        else:
            lines.append(f"/* from keep rule for {selector}: keep together */")
            lines.append(f"{selector} {{ break-inside: avoid; }}")
        lines.append("")

    for rule in policy.floats:
        selector = selectors_for(rule.applies_to)
        lines.append(f"/* from float rule for {selector}: prefers {', '.join(rule.preferred)} */")
        if "top" in rule.preferred:
            lines.append(f"{selector} {{ float: top; }}")
        lines.append("")

    breaks = policy.breaks
    if breaks.before_level_1 != "auto":
        lines.append(f"/* from break policy: level 1 headings break {breaks.before_level_1} */")
        lines.append("h1 { break-before: page; }")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
