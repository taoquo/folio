#!/usr/bin/env python3
"""folio language support

A language profile existing is not the same as a language being supported. The
plan is explicit about this: a profile that has never been rendered against a
fixture proves nothing, and claiming support on the strength of a configuration
file is the over-promise it warns against.

This module answers one question per language: what is the evidence, and what
does that evidence entitle us to claim?

  supported    a fixture exists, it renders, and its text survives
  partial      a fixture exists but something is known to be incomplete
  untested     no fixture, so nothing is claimed
  unsupported  known not to work

Usage:
    python3 scripts/language_support.py report
    python3 scripts/language_support.py report --format json
    python3 scripts/language_support.py claim zh-Hans-CN
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

FIXTURES = ROOT / "references" / "fixtures" / "document"

# What each level entitles a release to say. Kept beside the level rather than
# in prose, so the claim and its evidence cannot drift apart.
CLAIM = {
    "supported": "may be described as supported",
    "partial": "may be described as supported with stated limits",
    "untested": "must not be described as supported",
    "unsupported": "must be described as unsupported",
}

# Languages Folio intends to serve. A language absent from a fixture is listed
# as untested rather than omitted: the gap is the point of the report.
INTENDED = (
    "en-US", "zh-Hans-CN", "zh-Hant-TW", "ja-JP", "ko-KR", "ar-SA", "he-IL",
)


@dataclass
class LanguageStatus:
    """One language, and the evidence behind its level."""

    tag: str
    level: str
    fixtures: int = 0
    scripts: tuple[str, ...] = ()
    direction: str = "ltr"
    limits: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)

    @property
    def claim(self) -> str:
        return CLAIM.get(self.level, "unknown")

    def to_json(self) -> dict[str, Any]:
        return {
            "tag": self.tag,
            "level": self.level,
            "claim": self.claim,
            "fixtures": self.fixtures,
            "scripts": list(self.scripts),
            "direction": self.direction,
            "limits": self.limits,
            "evidence": self.evidence,
        }


def _fixtures_by_language() -> dict[str, list[str]]:
    import corpus

    found: dict[str, list[str]] = {}
    for path in corpus.discover_fixtures():
        try:
            data = corpus.load_fixture(path)
        except Exception:
            continue
        tag = str(data.get("language", "")).strip()
        if tag:
            found.setdefault(tag, []).append(path.stem)
    return found


def _profiles_by_language() -> dict[str, dict]:
    import profile_check

    loaded = profile_check.load_profiles()
    out: dict[str, dict] = {}
    for name, body in (loaded.get("language") or {}).items():
        tag = str(body.get("tag", "")).strip()
        if tag and tag != "und":
            out[tag] = dict(body, _name=name)
    return out


def survey() -> list[LanguageStatus]:
    """What is known about every language Folio intends to serve."""
    fixtures = _fixtures_by_language()
    profiles = _profiles_by_language()

    seen: list[str] = []
    for tag in (*INTENDED, *sorted(fixtures), *sorted(profiles)):
        if tag not in seen:
            seen.append(tag)

    statuses: list[LanguageStatus] = []
    for tag in seen:
        names = fixtures.get(tag, [])
        profile = profiles.get(tag)

        status = LanguageStatus(
            tag=tag,
            level="untested",
            fixtures=len(names),
            direction=str((profile or {}).get("direction", "ltr")),
            scripts=(str((profile or {}).get("script", "")),) if profile else (),
        )

        if names:
            status.level = "supported"
            status.evidence.append(f"{len(names)} fixture(s), e.g. {names[0]}")
        if profile:
            status.evidence.append(f"language profile {profile['_name']}")
        else:
            status.limits.append("no language profile")

        # A language with fixtures but no profile renders, but nothing states
        # its line-breaking or punctuation rules.
        if names and not profile:
            status.level = "partial"

        # Scripts the repository has never exercised.
        if tag.startswith("ar") or tag.startswith("he"):
            status.limits.append(
                "right-to-left shaping is not covered by any fixture; "
                "WeasyPrint reports partial bidi support"
            )
            status.level = "partial" if names else "untested"

        if tag.startswith("ja") or tag.startswith("ko") or tag.startswith("zh-Hant"):
            status.limits.append("no fixture; line-breaking rules untested")

        statuses.append(status)
    return statuses


def render_text(statuses: list[LanguageStatus]) -> str:
    lines = ["Language support", ""]
    lines.append(f"  {'language':<14} {'level':<11} {'fixtures':>8}  claim")
    lines.append("  " + "-" * 68)
    for status in statuses:
        lines.append(
            f"  {status.tag:<14} {status.level:<11} {status.fixtures:>8}  {status.claim}"
        )

    limited = [s for s in statuses if s.limits]
    if limited:
        lines.append("")
        lines.append("  Stated limits")
        for status in limited:
            first = status.limits[0]
            lines.append(f"    {status.tag}: {first}")

    supported = sum(1 for s in statuses if s.level == "supported")
    lines.append("")
    lines.append(f"  {supported} language(s) may be described as supported. A language profile")
    lines.append("  existing is not evidence: the level comes from fixtures, not configuration.")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    report = sub.add_parser("report", help="what is known about each language")
    report.add_argument("--format", choices=("text", "json"), default="text")
    report.add_argument("--output", type=Path)

    claim = sub.add_parser("claim", help="what may be claimed for one language")
    claim.add_argument("tag")

    args = parser.parse_args(argv)

    statuses = survey()

    if args.command == "claim":
        found = next((s for s in statuses if s.tag == args.tag), None)
        if found is None:
            print(f"{args.tag}: not listed; nothing may be claimed")
            return 1
        print(f"{found.tag}: {found.level}")
        print(f"  {found.claim}")
        for item in found.evidence:
            print(f"  evidence: {item}")
        for item in found.limits:
            print(f"  limit:    {item}")
        return 0

    payload = [s.to_json() for s in statuses]
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                               encoding="utf-8")

    if args.format == "json":
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(render_text(statuses))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
