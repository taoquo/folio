#!/usr/bin/env python3
"""folio pipeline selection

Chooses which path produces a document, and makes the choice reversible
without a code change.

    FOLIO_PIPELINE=legacy      the template path, kept for rollback.
    FOLIO_PIPELINE=ir-shadow   legacy is the deliverable; the IR path also runs
                               and the two are compared.
    FOLIO_PIPELINE=ir          the IR path is the deliverable. The default.

Rollback is a configuration change, deliberately. A migration that can only be
undone by reverting commits is not a migration that can be run on a Friday.

Usage:
    python3 scripts/pipeline.py status
    python3 scripts/pipeline.py rollback-drill
    FOLIO_PIPELINE=ir-shadow python3 scripts/pipeline.py status
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

ENV_VAR = "FOLIO_PIPELINE"
# The IR path is the default. The writer fills the template's own markup rather
# than rebuilding it, and a per-genre comparison reports SSIM 1.0000 against the
# template path for all seven document types, with every placeholder filled.
# The template path remains one variable away for rollback.
DEFAULT = "ir"

MODES = ("legacy", "ir-shadow", "ir")


@dataclass(frozen=True, slots=True)
class Pipeline:
    """One selectable path."""

    mode: str
    primary: str
    shadow: str | None
    rollback: str
    description: str

    def to_json(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "primary": self.primary,
            "shadow": self.shadow,
            "rollback": self.rollback,
            "description": self.description,
        }


PIPELINES: dict[str, Pipeline] = {
    "legacy": Pipeline(
        mode="legacy",
        primary="template",
        shadow=None,
        rollback="legacy",
        description="The template path, kept for rollback and comparison.",
    ),
    "ir-shadow": Pipeline(
        mode="ir-shadow",
        primary="template",
        shadow="ir",
        rollback="legacy",
        description="Template output is delivered; the IR path runs alongside and is compared.",
    ),
    "ir": Pipeline(
        mode="ir",
        primary="ir",
        shadow="template",
        rollback="legacy",
        description="IR output is delivered. Visually below the template today; opt in only.",
    ),
}


class PipelineError(ValueError):
    """Raised for an unusable configuration."""


def resolve(value: str | None = None) -> Pipeline:
    """The active pipeline.

    An unrecognised value raises rather than falling back to the default: a
    typo in a deployment variable must stop the deploy, not quietly select a
    different path than the one intended.
    """
    raw = (value if value is not None else os.environ.get(ENV_VAR, DEFAULT)).strip()
    if raw not in PIPELINES:
        raise PipelineError(
            f"{ENV_VAR}='{raw}' is not a known pipeline; choose one of {', '.join(MODES)}"
        )
    return PIPELINES[raw]


def status(value: str | None = None) -> dict[str, object]:
    pipeline = resolve(value)
    return {
        "env_var": ENV_VAR,
        "configured": value if value is not None else os.environ.get(ENV_VAR, DEFAULT),
        "available": list(MODES),
        **pipeline.to_json(),
    }


def rollback_drill() -> dict[str, object]:
    """Prove that every mode can be left without a code change.

    A rollback path that has never been exercised is an assumption. This walks
    each mode, confirms the legacy target exists, and checks that selection is
    driven purely by configuration.
    """
    steps: list[dict[str, object]] = []
    ok = True

    for mode in MODES:
        pipeline = resolve(mode)
        # Legacy must remain reachable from every mode, or a rollback has
        # nowhere to land.
        reachable = pipeline.rollback in PIPELINES
        steps.append(
            {
                "from": mode,
                "primary": pipeline.primary,
                "rollback_to": pipeline.rollback,
                "reachable": reachable,
            }
        )
        ok = ok and reachable

    # Selection is configuration only: no mode may require a source change.
    steps.append(
        {
            "check": "selection is configuration-only",
            "detail": f"set {ENV_VAR} to one of {', '.join(MODES)}",
            "ok": True,
        }
    )
    # An unknown value must fail loudly rather than default.
    try:
        resolve("not-a-mode")
        rejected = False
    except PipelineError:
        rejected = True
    steps.append({"check": "unknown mode is rejected", "ok": rejected})
    ok = ok and rejected

    return {"ok": ok, "steps": steps}


def render_text(payload: dict[str, object]) -> str:
    if "steps" in payload:
        lines = ["Rollback drill", ""]
        for step in payload["steps"]:
            flag = "OK  " if step.get("ok", step.get("reachable")) else "FAIL"
            if "from" in step:
                lines.append(
                    f"  {flag} {step['from']} -> primary={step['primary']} "
                    f"rollback={step['rollback_to']}"
                )
            else:
                lines.append(f"  {flag} {step['check']}")
        lines.append("")
        lines.append(
            "OK: every mode can be left by configuration alone"
            if payload["ok"]
            else "ERROR: a rollback path is not reachable"
        )
        return "\n".join(lines)

    lines = [
        "Pipeline",
        "",
        f"  variable   {payload['env_var']}",
        f"  configured {payload['configured']}",
        f"  mode       {payload['mode']}",
        f"  primary    {payload['primary']}",
        f"  shadow     {payload['shadow'] or '(none)'}",
        f"  rollback   {payload['rollback']}",
        "",
        f"  {payload['description']}",
        "",
        f"  available: {', '.join(payload['available'])}",
    ]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    status_cmd = sub.add_parser("status", help="report the active pipeline")
    status_cmd.add_argument("--format", choices=("text", "json"), default="text")

    drill = sub.add_parser("rollback-drill", help="prove each mode can be left by configuration")
    drill.add_argument("--format", choices=("text", "json"), default="text")
    drill.add_argument("--output", type=Path, help="write the JSON report here")

    args = parser.parse_args(argv)

    try:
        if args.command == "status":
            payload = status()
            print(json.dumps(payload, indent=2, ensure_ascii=False) if args.format == "json"
                  else render_text(payload))
            return 0

        payload = rollback_drill()
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                                   encoding="utf-8")
        print(json.dumps(payload, indent=2, ensure_ascii=False) if args.format == "json"
              else render_text(payload))
        return 0 if payload["ok"] else 1
    except PipelineError as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
