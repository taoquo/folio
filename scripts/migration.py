#!/usr/bin/env python3
"""folio migration status

Reports how far each document type has come toward being produced by the IR,
and what is still missing before it could be.

The migration itself is deliberately not automated here. What this reports is
the evidence a decision needs: whether the type can be rendered from the IR at
all, how much of its content survives the bridge, and whether the two paths
agree.

Usage:
    python3 scripts/migration.py status
    python3 scripts/migration.py status --format json
    python3 scripts/migration.py plan resume
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


GENRES = (
    "one-pager", "letter", "long-doc", "portfolio", "resume", "equity-report",
    "changelog", "slides",
)

# The order matters. Hard-page contracts migrate last because they are the
# least forgiving: a resume that gains a page has failed, not drifted.
MIGRATION_ORDER = (
    "changelog", "long-doc", "portfolio", "letter", "equity-report",
    "one-pager", "resume", "slides",
)

HARD_PAGE_GENRES = {"resume", "one-pager", "letter"}


@dataclass
class GenreStatus:
    genre: str
    ir_capable: bool = False
    bridge_mapped: int = 0
    fixtures: int = 0
    profiles: bool = False
    hard_page_contract: bool = False
    blockers: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        """Whether this type could be produced from the IR today.

        Ready means: the bridge maps it, and a fixture exists to prove it. A
        type with a mapping but no fixture has never actually been rendered
        through the IR path, so calling it ready would be a guess.
        """
        return self.ir_capable and self.bridge_mapped > 0 and self.fixtures > 0

    def to_json(self) -> dict[str, object]:
        return {
            "genre": self.genre,
            "ready": self.ready,
            "ir_capable": self.ir_capable,
            "bridge_mappings": self.bridge_mapped,
            "fixtures": self.fixtures,
            "profiles": self.profiles,
            "hard_page_contract": self.hard_page_contract,
            "blockers": self.blockers,
        }


def _bridge_mappings(genre: str, language: str = "zh-Hans-CN") -> int:
    try:
        from document_ir.bridge import default_map_for

        return len(default_map_for(genre, language).roles)
    except Exception:
        return 0


def _fixture_count(genre: str) -> int:
    directory = ROOT / "references" / "fixtures" / "document"
    if not directory.is_dir():
        return 0
    count = 0
    for path in directory.rglob("*.yaml"):
        try:
            import corpus

            if corpus.load_fixture(path).get("genre") == genre:
                count += 1
        except Exception:
            continue
    return count


def _profiles_for(genre: str) -> bool:
    try:
        import profile_check

        profiles = profile_check.load_profiles()
        typography = {
            body.get("genre") for body in profiles.get("typography", {}).values()
        }
        page = {body.get("genre") for body in profiles.get("page", {}).values()}
        return genre in typography and genre in page
    except Exception:
        return False


def survey() -> list[GenreStatus]:
    statuses: list[GenreStatus] = []
    for genre in GENRES:
        status = GenreStatus(
            genre=genre,
            bridge_mapped=_bridge_mappings(genre),
            fixtures=_fixture_count(genre),
            profiles=_profiles_for(genre),
            hard_page_contract=genre in HARD_PAGE_GENRES,
        )
        status.ir_capable = status.bridge_mapped > 0

        if status.bridge_mapped == 0:
            status.blockers.append("no bridge mapping")
        if status.fixtures == 0:
            status.blockers.append("no fixture exercising this genre")
        if not status.profiles:
            status.blockers.append("no typography or page profile")
        if genre == "slides":
            status.blockers.append("PPTX output has no IR writer yet")
        statuses.append(status)
    return statuses


def plan(genre: str) -> dict[str, object]:
    """What migrating one genre would involve, in order."""
    statuses = {s.genre: s for s in survey()}
    status = statuses.get(genre)
    if status is None:
        return {"genre": genre, "error": "unknown genre"}

    steps = [
        "Confirm the bridge maps every placeholder the template declares",
        "Render the fixture through both paths and compare pages, fonts and text",
        "Record the differences; a fixed template wording difference is expected "
        "until that wording moves into the IR",
        "Enable the IR path for this genre behind the pipeline variable",
        "Keep the template path reachable for rollback",
    ]
    if status.hard_page_contract:
        steps.insert(0, "Migrate last: this genre has a hard page contract")

    return {
        "genre": genre,
        "ready": status.ready,
        "blockers": status.blockers,
        "steps": steps,
        "position": MIGRATION_ORDER.index(genre) + 1 if genre in MIGRATION_ORDER else None,
    }


def render_text(statuses: list[GenreStatus]) -> str:
    lines = ["Migration status — IR readiness per document type", ""]
    lines.append(f"  {'genre':<15} {'ready':>6} {'bridge':>7} {'fixtures':>9} {'profiles':>9}  blockers")
    lines.append("  " + "-" * 88)
    for status in statuses:
        lines.append(
            f"  {status.genre:<15} {'yes' if status.ready else 'no':>6} "
            f"{status.bridge_mapped:>7} {status.fixtures:>9} "
            f"{'yes' if status.profiles else 'no':>9}  "
            f"{'; '.join(status.blockers) if status.blockers else ''}"
        )

    ready = sum(1 for s in statuses if s.ready)
    lines.append("")
    lines.append(f"  {ready}/{len(statuses)} type(s) can be produced from the IR today")
    lines.append("")
    lines.append("  Migration order (hard page contracts last):")
    for index, genre in enumerate(MIGRATION_ORDER, start=1):
        status = next((s for s in statuses if s.genre == genre), None)
        flag = "ready" if status and status.ready else "not ready"
        lines.append(f"    {index}. {genre:<15} {flag}")
    lines.append("")
    lines.append("  Legacy remains the deliverable until every type in scope is ready and")
    lines.append("  the two paths agree on a corpus run.")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    status_cmd = sub.add_parser("status", help="report IR readiness per document type")
    status_cmd.add_argument("--format", choices=("text", "json"), default="text")
    status_cmd.add_argument("--output", type=Path, help="write the JSON report here")

    plan_cmd = sub.add_parser("plan", help="what migrating one genre involves")
    plan_cmd.add_argument("genre")
    plan_cmd.add_argument("--format", choices=("text", "json"), default="text")

    args = parser.parse_args(argv)

    if args.command == "status":
        statuses = survey()
        payload = {
            "types": [s.to_json() for s in statuses],
            "ready": sum(1 for s in statuses if s.ready),
            "total": len(statuses),
            "migration_order": list(MIGRATION_ORDER),
        }
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                                   encoding="utf-8")
        if args.format == "json":
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(render_text(statuses))
        return 0

    payload = plan(args.genre)
    if args.format == "json":
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        if "error" in payload:
            print(f"ERROR: {payload['error']}")
            return 2
        print(f"Migrating {payload['genre']}")
        print(f"  ready: {'yes' if payload['ready'] else 'no'}")
        if payload["blockers"]:
            print("  blockers:")
            for blocker in payload["blockers"]:
                print(f"    - {blocker}")
        print("  steps:")
        for index, step in enumerate(payload["steps"], start=1):
            print(f"    {index}. {step}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
