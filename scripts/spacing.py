#!/usr/bin/env python3
"""folio spacing model

The space between two blocks is currently whatever the template's CSS happens
to produce. One rule says `margin-bottom: 6pt`, another says `margin-top: 18pt`,
and the browser decides which wins by collapsing them. The result is a number
nobody can explain: ask why a heading sits 24pt above its paragraph and the
answer is a computation, not a decision.

This module makes the space a decision. An adjacent pair of blocks resolves to
one gap, with a stated origin, before anything is rendered.

The distinction the plan draws is kept:

  intrinsic   the object's own metrics -- a line box, a glyph's height
  semantic    decided by the relationship: heading to body, figure to caption
  contextual  adjusted by environment: section opening, dense table, two columns
  optical     a small correction for visual balance, opt-in and bounded

Values carry `min`, `preferred` and `max` rather than one number, so a backend
that can distribute space has something to work with and one that cannot still
has a defined fallback. Elastic behaviour is *declared*, never assumed: a
resolver reports when a backend cannot honour it instead of pretending the
spacing was applied.

Usage:
    python3 scripts/spacing.py pairs
    python3 scripts/spacing.py resolve --pairs heading,paragraph paragraph,paragraph
    python3 scripts/spacing.py audit assets/templates/one-pager.html
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

Unit = Literal["pt", "px", "em", "rem", "mm"]
Kind = Literal["intrinsic", "semantic", "contextual", "optical"]
Constraint = Literal["hard", "soft"]

# Named strengths, so a priority is readable rather than an opaque integer.
# `required` outranks everything; `weak` yields to any other rule.
STRENGTHS: dict[str, int] = {
    "required": 100,
    "strong": 75,
    "normal": 50,
    "weak": 25,
}


class SpacingError(ValueError):
    """Raised for a spacing declaration that cannot be used."""


@dataclass(frozen=True)
class Length:
    """A measurement with an explicit unit.

    The unit is required. A bare number in a stylesheet is a guess about what
    the author meant, and a spacing system built on guesses cannot be audited.
    """

    value: float
    unit: Unit

    def __post_init__(self) -> None:
        if self.unit not in ("pt", "px", "em", "rem", "mm"):
            raise SpacingError(f"unknown unit {self.unit!r}")
        if self.value < 0:
            raise SpacingError(f"a length cannot be negative: {self.value}")

    def to_json(self) -> dict[str, Any]:
        return {"value": self.value, "unit": self.unit}

    def __str__(self) -> str:
        return f"{self.value:g}{self.unit}"

    def as_pt(self, *, base_pt: float = 10.0, root_pt: float = 10.0) -> float:
        """Convert to points for comparison, using this document's type size.

        `em` is relative to the body size and `rem` to the root size, which is
        why the conversion needs the document rather than assuming 16px.
        """
        if self.unit == "pt":
            return self.value
        if self.unit == "px":
            return self.value * 0.75
        if self.unit == "em":
            return self.value * base_pt
        if self.unit == "rem":
            return self.value * root_pt
        if self.unit == "mm":
            return self.value * 72.0 / 25.4
        raise SpacingError(f"cannot convert {self.unit!r}")


@dataclass(frozen=True)
class SpaceSpec:
    """The space between two adjacent blocks.

    `min` and `max` bound what a backend may produce; `preferred` is what the
    design asks for. `stretch` and `shrink` describe how far the value may move
    under page pressure -- a backend that cannot do this must say so, and the
    resolver records that rather than reporting success.
    """

    preferred: Length
    min: Length | None = None
    max: Length | None = None
    stretch: float = 0.0
    shrink: float = 0.0
    strength: str = "normal"
    kind: Kind = "semantic"
    constraint: Constraint = "soft"
    collapse_group: str | None = None
    note: str = ""

    def __post_init__(self) -> None:
        if self.strength not in STRENGTHS:
            raise SpacingError(
                f"unknown strength {self.strength!r}; use one of {', '.join(STRENGTHS)}"
            )
        if self.stretch < 0 or self.shrink < 0:
            raise SpacingError("stretch and shrink cannot be negative")
        for bound, name in ((self.min, "min"), (self.max, "max")):
            if bound is not None and bound.unit != self.preferred.unit:
                raise SpacingError(
                    f"{name} uses {bound.unit} while preferred uses {self.preferred.unit}; "
                    "comparing them would need a conversion the model cannot assume"
                )
        if self.min is not None and self.min.value > self.preferred.value:
            raise SpacingError(f"min {self.min} exceeds preferred {self.preferred}")
        if self.max is not None and self.max.value < self.preferred.value:
            raise SpacingError(f"max {self.max} is below preferred {self.preferred}")

    @property
    def priority(self) -> int:
        return STRENGTHS[self.strength]

    @property
    def elastic(self) -> bool:
        """Whether this gap may move under page pressure."""
        return self.stretch > 0 or self.shrink > 0

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "preferred": self.preferred.to_json(),
            "stretch": self.stretch,
            "shrink": self.shrink,
            "strength": self.strength,
            "priority": self.priority,
            "kind": self.kind,
            "constraint": self.constraint,
        }
        if self.min is not None:
            out["min"] = self.min.to_json()
        if self.max is not None:
            out["max"] = self.max.to_json()
        if self.collapse_group:
            out["collapse_group"] = self.collapse_group
        if self.note:
            out["note"] = self.note
        return out


# The base rules. Each names the relationship it governs, because a spacing
# table whose entries are just numbers cannot be reviewed.
BASE_RULES: dict[tuple[str, str], SpaceSpec] = {
    ("heading", "paragraph"): SpaceSpec(
        preferred=Length(6, "pt"), min=Length(4, "pt"), max=Length(10, "pt"),
        kind="semantic", constraint="soft",
        note="A heading belongs to the text it introduces.",
    ),
    ("paragraph", "paragraph"): SpaceSpec(
        preferred=Length(6, "pt"), min=Length(4, "pt"), max=Length(8, "pt"),
        stretch=0.2, shrink=0.3, kind="semantic",
        note="Body rhythm; may absorb small page pressure.",
    ),
    ("paragraph", "heading"): SpaceSpec(
        preferred=Length(18, "pt"), min=Length(12, "pt"), max=Length(24, "pt"),
        stretch=0.5, kind="semantic",
        note="More room before a heading than after it, so sections read as sections.",
    ),
    ("figure", "caption"): SpaceSpec(
        preferred=Length(4, "pt"), min=Length(2, "pt"), max=Length(6, "pt"),
        kind="semantic", constraint="hard",
        note="A caption that drifts from its figure stops being a caption.",
    ),
    ("caption", "paragraph"): SpaceSpec(
        preferred=Length(10, "pt"), min=Length(8, "pt"), kind="semantic",
        note="Body resumes after a caption; the figure owns the space above it.",
    ),
    ("figure", "paragraph"): SpaceSpec(
        preferred=Length(12, "pt"), min=Length(8, "pt"), max=Length(18, "pt"),
        stretch=0.4, kind="semantic",
        note="A figure and its caption read as one object, so the break comes after both.",
    ),
    ("list_item", "list_item"): SpaceSpec(
        preferred=Length(3, "pt"), min=Length(2, "pt"), max=Length(6, "pt"),
        kind="semantic",
        note="Tighter than prose, so a list reads as one object.",
    ),
    ("paragraph", "list"): SpaceSpec(
        preferred=Length(6, "pt"), min=Length(4, "pt"), kind="semantic",
        note="A list introduced by a sentence stays with it.",
    ),
    ("list", "paragraph"): SpaceSpec(
        preferred=Length(10, "pt"), min=Length(6, "pt"), kind="semantic",
        note="Leaving a list needs more room than entering one, so the list ends visibly.",
    ),
    ("code_block", "paragraph"): SpaceSpec(
        preferred=Length(10, "pt"), min=Length(8, "pt"), kind="semantic",
        note="Prose resumes after code with enough room to leave the block behind.",
    ),
    ("paragraph", "code_block"): SpaceSpec(
        preferred=Length(10, "pt"), min=Length(8, "pt"), kind="semantic",
        note="Code arrives as a unit; the gap separates it from the sentence above.",
    ),
    ("table", "paragraph"): SpaceSpec(
        preferred=Length(12, "pt"), min=Length(8, "pt"), kind="semantic",
        note="A table is wide and dense; prose after it needs a clear break.",
    ),
    ("quote", "paragraph"): SpaceSpec(
        preferred=Length(12, "pt"), min=Length(8, "pt"), kind="semantic",
        note="A quotation returns to the main voice after a clear pause.",
    ),
    ("paragraph", "quote"): SpaceSpec(
        preferred=Length(12, "pt"), min=Length(8, "pt"), kind="semantic",
        note="A quotation is set apart from the argument it supports.",
    ),
}

# The fallback when a pair has no rule. Deliberately generous rather than tight:
# an unlisted pair is a gap in this table, and a spacing system should make that
# visible rather than silently inventing a comfortable number.
DEFAULT_SPEC = SpaceSpec(
    preferred=Length(8, "pt"), min=Length(4, "pt"), max=Length(16, "pt"),
    kind="semantic", strength="weak",
    note="No rule for this pair; add one rather than relying on the fallback.",
)


@dataclass
class ResolvedGap:
    """One pair's gap, with the rule that produced it."""

    before: str
    after: str
    spec: SpaceSpec
    rule: str
    context: tuple[str, ...] = ()

    @property
    def is_fallback(self) -> bool:
        return self.rule == "fallback"

    def to_json(self) -> dict[str, Any]:
        out = {"before": self.before, "after": self.after, "rule": self.rule,
               "spec": self.spec.to_json()}
        if self.context:
            out["context"] = list(self.context)
        return out

    def explain(self, *, body_size_pt: float = 10.0, root_size_pt: float = 10.0) -> str:
        spec = self.spec
        lines = [
            f"{self.before} -> {self.after}",
            f"  preferred   {spec.preferred}  ({spec.preferred.as_pt(base_pt=body_size_pt, root_pt=root_size_pt):.2f}pt)",
        ]
        if spec.min is not None and spec.max is not None:
            lines.append(f"  range       {spec.min} .. {spec.max}")
        lines.append(f"  kind        {spec.kind}  ({spec.constraint}, {spec.strength})")
        lines.append(f"  rule        {self.rule}")
        if spec.elastic:
            lines.append(
                f"  elastic     stretch {spec.stretch}, shrink {spec.shrink} "
                "-- a backend that cannot distribute space must report it"
            )
        if spec.note:
            lines.append(f"  note        {spec.note}")
        return "\n".join(lines)


def normalise(kind: str) -> str:
    """Reduce a node type to the vocabulary the rules use."""
    lowered = kind.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "p": "paragraph", "text": "paragraph", "body": "paragraph",
        "h1": "heading", "h2": "heading", "h3": "heading",
        "h4": "heading", "h5": "heading", "h6": "heading", "title": "heading",
        "li": "list_item", "listitem": "list_item", "item": "list_item",
        "ul": "list", "ol": "list", "listblock": "list",
        "img": "figure", "image": "figure", "diagram": "figure",
        "codeblock": "code_block", "code": "code_block", "pre": "code_block",
        "blockquote": "quote", "callout": "quote",
    }
    return aliases.get(lowered, lowered)


def resolve_gap(before: str, after: str, *, context: tuple[str, ...] = ()) -> ResolvedGap:
    """The gap between two adjacent block types.

    Context adjusts the semantic value rather than replacing it, so a section
    opening gets more room without losing the relationship the pair declares.
    """
    left, right = normalise(before), normalise(after)
    spec = BASE_RULES.get((left, right))
    rule = f"{left}->{right}"

    if spec is None:
        spec = DEFAULT_SPEC
        rule = "fallback"

    applied_context: list[str] = []
    if spec is not DEFAULT_SPEC:
        for item in context:
            adjusted = _apply_context(item, spec, left, right)
            if adjusted is not None:
                spec = adjusted
                applied_context.append(item)

    return ResolvedGap(before=left, after=right, spec=spec, rule=rule,
                       context=tuple(applied_context))


def _apply_context(context: str, spec: SpaceSpec, left: str, right: str) -> SpaceSpec | None:
    """Adjust a gap for its environment, or leave it alone.

    Context is additive on the preferred value and keeps the original bounds
    where they still make sense, so a contextual rule cannot silently turn a
    hard constraint into a soft one.
    """
    context = context.strip().lower()

    if context in {"section-opening", "chapter"} and right == "heading":
        return SpaceSpec(
            preferred=Length(spec.preferred.value + 6, spec.preferred.unit),
            min=spec.min, max=None,
            kind="contextual", constraint=spec.constraint, strength=spec.strength,
            note="A section opens with more room than a heading inside one.",
        )
    if context == "dense" and left == right == "list_item":
        return SpaceSpec(
            preferred=Length(max(spec.preferred.value - 1, 1), spec.preferred.unit),
            min=spec.min, max=spec.max,
            kind="contextual", constraint=spec.constraint, strength=spec.strength,
            note="A long list tightens rather than drifting into prose rhythm.",
        )
    if context == "two-column" and left == "paragraph" and right == "paragraph":
        return SpaceSpec(
            preferred=Length(spec.preferred.value + 2, spec.preferred.unit),
            min=spec.min, max=spec.max, stretch=spec.stretch, shrink=spec.shrink,
            kind="contextual", constraint=spec.constraint, strength=spec.strength,
            note="Narrower measures need a clearer break between paragraphs.",
        )
    return None


def audit_template(path: Path) -> dict[str, Any]:
    """Report the spacing a template declares in CSS.

    This is the starting point of the migration: it shows what the templates
    currently decide, so a rule can be moved into the model deliberately rather
    than all at once.
    """
    if not path.is_file():
        return {"error": f"not found: {path}"}

    text = path.read_text(encoding="utf-8")
    declarations: list[dict[str, Any]] = []
    for match in re.finditer(
        r"([a-z-]+)\s*:\s*([0-9.]+)(pt|px|em|rem|mm)\b", text, re.IGNORECASE
    ):
        property_name, value, unit = match.group(1), match.group(2), match.group(3)
        if not any(word in property_name for word in ("margin", "padding", "gap")):
            continue
        declarations.append({
            "property": property_name,
            "value": float(value),
            "unit": unit.lower(),
        })

    grouped: dict[str, int] = {}
    for item in declarations:
        key = f"{item['property']}:{item['value']:g}{item['unit']}"
        grouped[key] = grouped.get(key, 0) + 1

    return {
        "template": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
        "declarations": len(declarations),
        "distinct": len(grouped),
        "values": dict(sorted(grouped.items(), key=lambda pair: -pair[1])),
        "note": (
            "These numbers are the template's decisions today. Each one that "
            "matters becomes a rule in this module, so the gap is explainable "
            "after the migration."
        ),
    }


def render_text(payload: Any, command: str, target: str | None = None) -> str:
    if command == "pairs":
        lines = ["Spacing rules", ""]
        lines.append(f"  {'pair':<32} {'preferred':>10} {'kind':<11} strength")
        lines.append("  " + "-" * 66)
        for (left, right), spec in sorted(BASE_RULES.items()):
            lines.append(
                f"  {left + ' -> ' + right:<32} {str(spec.preferred):>10} "
                f"{spec.kind:<11} {spec.strength}"
            )
        lines.append("")
        lines.append(f"  {len(BASE_RULES)} rule(s). A pair without a rule falls back to "
                     f"{DEFAULT_SPEC.preferred}, which is reported rather than hidden.")
        return "\n".join(lines)

    if command == "resolve":
        lines = [f"Resolved gap — {target}", "", target and ""]
        gap: ResolvedGap = payload["gap"]
        lines.append(gap.explain(body_size_pt=payload["body_size_pt"]))
        return "\n".join(line for line in lines if line is not None)

    if command == "audit":
        if payload.get("error"):
            return f"ERROR: {payload['error']}"
        lines = [f"Template spacing — {payload['template']}", ""]
        lines.append(f"  {payload['declarations']} declaration(s), {payload['distinct']} distinct")
        lines.append("")
        for key, count in list(payload["values"].items())[:14]:
            lines.append(f"    {key:<28} x{count}")
        lines.append("")
        lines.append("  " + payload["note"].replace(". ", ".\n  "))
        return "\n".join(lines)

    return json.dumps(payload, indent=2, ensure_ascii=False)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    pairs = sub.add_parser("pairs", help="list the base spacing rules")
    pairs.add_argument("--format", choices=("text", "json"), default="text")

    resolve_cmd = sub.add_parser("resolve", help="resolve the gap for a pair")
    resolve_cmd.add_argument("--pair", required=True,
                             help="two block types, e.g. heading,paragraph")
    resolve_cmd.add_argument("--context", action="append", default=[])
    resolve_cmd.add_argument("--body-size-pt", type=float, default=10.0)
    resolve_cmd.add_argument("--format", choices=("text", "json"), default="text")

    audit = sub.add_parser("audit", help="report the spacing a template declares")
    audit.add_argument("template", nargs="?", default="assets/templates/one-pager.html")
    audit.add_argument("--format", choices=("text", "json"), default="text")

    args = parser.parse_args(argv)

    if args.command == "pairs":
        if args.format == "json":
            print(json.dumps(
                {f"{a}->{b}": spec.to_json() for (a, b), spec in BASE_RULES.items()},
                indent=2, ensure_ascii=False))
        else:
            print(render_text(None, "pairs"))
        return 0

    if args.command == "resolve":
        parts = [p.strip() for p in args.pair.split(",")]
        if len(parts) != 2:
            print("ERROR: --pair needs two block types, e.g. heading,paragraph")
            return 2
        gap = resolve_gap(parts[0], parts[1], context=tuple(args.context))
        payload = {"gap": gap, "body_size_pt": args.body_size_pt}
        if args.format == "json":
            print(json.dumps(gap.to_json(), indent=2, ensure_ascii=False))
        else:
            print(render_text(payload, "resolve", f"{parts[0]} -> {parts[1]}"))
        return 0

    path = Path(args.template)
    if not path.is_absolute():
        path = ROOT / path
    payload = audit_template(path)
    if args.format == "json":
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(render_text(payload, "audit"))
    return 0 if not payload.get("error") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
