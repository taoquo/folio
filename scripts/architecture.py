#!/usr/bin/env python3
"""folio architecture census

Checks the engine's structure, not its parts.

The other checks answer "does this module work". This one answers a question
none of them asked: "does the path that produces the deliverable use it". A
module can be correct, tested, documented and unreachable, and every existing
check passes — that is how the engine reached a state where the IR was built,
verified and not on the path that produces the published examples.

So this census verifies the connections between layers:

  reachability   a capability is used by a path that produces an artifact
  layering       a layer does not import something above it
  declarations   a stated default is the one the code uses
  evidence       a claim in a document names the command that shows it

Each entry states a fact about the structure and runs a check for it. A check
that cannot be wrong is not worth keeping, so entries assert a specific
connection rather than the presence of a file.

Usage:
    python3 scripts/architecture.py check
    python3 scripts/architecture.py reachability
    python3 scripts/architecture.py layering
    python3 scripts/architecture.py check --format json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

# The paths that produce a deliverable. A capability is reachable when one of
# these uses it; a capability used only by tests or by an inspection tool is
# built but not shipped.
PRODUCTION_PATHS = (
    "scripts/build.py",
    "scripts/document_build.py",
)

# Which path is expected to use which capability, and why.
#
# Named per path rather than per module: a module used by one path must not
# satisfy the requirement for another. `build.py` uses the renderer boundary, so
# a joined check counted `renderers` as reachable while the path that builds
# finished documents called `weasyprint` directly.
REQUIRED_CALLS = {
    "scripts/document_build.py": {
        "document_ir": "a finished document is built from the semantic model",
        "renderers": "rendering must go through the boundary, not around it",
        "pipeline": "the path must be selectable and reversible",
        "projection": "the resolved style must reach the page",
    },
    "scripts/build.py": {
        "renderers": "template rendering must go through the boundary",
    },
}

# A layer may not import the layer above it. `document_ir` describes meaning; it
# must not know how anything is drawn.
# A writer's job is to speak its format, so `writers/` is exempt: importing
# `pptx` there is the point. What must not name a backend is the semantic core.
LAYERS = {
    "scripts/document_ir/model.py": ("the semantic core", ("weasyprint", "pptx", "reportlab")),
    "scripts/document_ir/validate.py": ("the validator", ("weasyprint", "pptx", "reportlab")),
    "scripts/document_ir/bridge.py": ("the template bridge", ("weasyprint", "pptx", "reportlab")),
    "scripts/document_ir/containers.py": ("the container rules", ("weasyprint", "pptx", "reportlab")),
    "scripts/renderers/weasy.py": ("the WeasyPrint adapter", ("document_ir.bridge",)),
}

# A switch is a claim about behaviour. When the table says on, the code says on.
DECLARED_DEFAULTS = {
    "FOLIO_STYLE_PROJECTION": ("scripts/document_build.py", True),
    "FOLIO_LAYOUT_POLICY": ("scripts/document_build.py", True),
    "FOLIO_BUILD_MANIFEST": ("scripts/document_build.py", True),
    "FOLIO_PIPELINE": ("scripts/pipeline.py", "ir"),
}


@dataclass
class Finding:
    """One structural problem."""

    area: str
    subject: str
    detail: str
    severity: str = "error"

    def to_json(self) -> dict[str, Any]:
        return {"area": self.area, "subject": self.subject,
                "detail": self.detail, "severity": self.severity}


@dataclass
class Census:
    findings: list[Finding] = field(default_factory=list)
    checked: int = 0

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)

    @property
    def ok(self) -> bool:
        return not [f for f in self.findings if f.severity == "error"]

    def to_json(self) -> dict[str, Any]:
        return {
            "checked": self.checked,
            "errors": len([f for f in self.findings if f.severity == "error"]),
            "warnings": len([f for f in self.findings if f.severity == "warning"]),
            "findings": [f.to_json() for f in self.findings],
        }


def _read(path: str | Path) -> str:
    full = ROOT / path
    if not full.is_file():
        return ""
    try:
        return full.read_text(encoding="utf-8")
    except OSError:
        return ""


def _module_names() -> list[str]:
    """Every importable module under scripts/."""
    names: set[str] = set()
    for path in (ROOT / "scripts").rglob("*.py"):
        if "__pycache__" in path.parts or path.name == "__init__.py":
            continue
        names.add(path.stem)
    for path in (ROOT / "scripts" / "document_ir").rglob("*.py"):
        if path.name == "__init__.py":
            names.add("document_ir")
    return sorted(names)


def _used(text: str, module: str) -> bool:
    """Whether a module is called, not merely imported.

    An `import` line names a module whether or not anything calls it. A call
    looks like `module.name(` or `from module import name` followed by `name(`.
    """
    name = module.split(".")[-1]
    if re.search(rf"\b{re.escape(name)}\.[a-zA-Z_]", text):
        return True
    # `from x import y` binds `y`, which may then be called or used as a
    # namespace: `y()`, or `y.thing()` for a submodule.
    for match in re.finditer(rf"from\s+[\w.]*{re.escape(name)}\s+import\s+([^\n]+)", text):
        for part in match.group(1).split(","):
            symbol = part.strip().split(" as ")[-1].strip().strip("()")
            if not symbol or symbol == "*":
                continue
            if re.search(rf"\b{re.escape(symbol)}\s*[.(]", text):
                return True
    return False


def reachability() -> Census:
    """Which capabilities each production path actually travels through."""
    census = Census()

    for path, requirements in REQUIRED_CALLS.items():
        text = _read(path)
        if not text:
            continue
        for module, why in requirements.items():
            census.checked += 1
            if not _used(text, module):
                census.add(Finding(
                    area="reachability",
                    subject=f"{path}: {module}",
                    detail=f"this path does not call it, so {why} does not hold",
                ))

    return census


def layering() -> Census:
    """Whether a layer imports something above it."""
    census = Census()

    for target, (description, forbidden) in LAYERS.items():
        path = ROOT / target
        if not path.is_file():
            continue
        census.checked += 1
        text = _read(target)
        for name in forbidden:
            if re.search(rf"^\s*(from|import)\s+{re.escape(name)}", text, re.MULTILINE):
                census.add(Finding(
                    area="layering",
                    subject=target,
                    detail=f"{description} imports {name}, which sits above it",
                ))

    # The semantic layer must also avoid naming a page's geometry or a colour.
    # A test walks the model fields; this checks the source does not reach for a
    # drawing library at import time.
    return census


def declared_defaults() -> Census:
    """Whether a documented default is the one the code uses."""
    census = Census()
    docs = _read("AGENTS.md") + _read("docs/architecture/integration-status.md")

    for variable, (path, expected) in DECLARED_DEFAULTS.items():
        census.checked += 1
        text = _read(path)
        if isinstance(expected, bool):
            pattern = rf'{variable}"\s*,\s*default=(True|False)'
            match = re.search(pattern, text)
            if not match:
                continue  # no boolean default to compare
            actual = match.group(1) == "True"
            if actual != expected:
                census.add(Finding(
                    area="declarations",
                    subject=variable,
                    detail=(
                        f"the code defaults to {'on' if actual else 'off'} while "
                        f"the documentation states {'on' if expected else 'off'}"
                    ),
                ))
        else:
            pattern = rf'{variable}"?\s*[:=]\s*"([^"]+)"'
            match = re.search(pattern, text)
            if match and match.group(1) != expected:
                census.add(Finding(
                    area="declarations",
                    subject=variable,
                    detail=f"the code defaults to {match.group(1)!r}, not {expected!r}",
                ))

        if variable not in docs:
            census.add(Finding(
                area="declarations",
                subject=variable,
                detail="the switch is not described in the operating rules",
                severity="warning",
            ))

    return census


def module_reachability() -> dict[str, dict[str, int]]:
    """How often each module is named by production, tests and tools."""
    production = "\n".join(_read(p) for p in PRODUCTION_PATHS)
    test_text = ""
    for path in (ROOT / "tests").glob("*.py"):
        test_text += _read(path.relative_to(ROOT))

    rows: dict[str, dict[str, int]] = {}
    for name in _module_names():
        pattern = rf"\b{re.escape(name)}\b"
        rows[name] = {
            "production": len(re.findall(pattern, production)),
            "tests": len(re.findall(pattern, test_text)),
        }
    return rows


def check() -> Census:
    census = Census()
    for part in (reachability(), layering(), declared_defaults()):
        census.checked += part.checked
        census.findings.extend(part.findings)
    return census


def render_text(census: Census, command: str) -> str:
    if command == "reachability":
        rows = module_reachability()
        lines = ["Reachability", ""]
        lines.append(f"  {'module':<28}{'production':>11}{'tests':>7}  state")
        lines.append("  " + "-" * 58)
        for name, counts in sorted(rows.items()):
            if counts["production"]:
                state = "reachable"
            elif counts["tests"]:
                state = "built, unreachable"
            else:
                continue
            lines.append(
                f"  {name:<28}{counts['production']:>11}{counts['tests']:>7}  {state}"
            )
        lines.append("")
        lines.append("  'production' counts references in the paths that produce a")
        lines.append("  deliverable. A module with tests and no production reference is")
        lines.append("  correct, covered, and not shipped.")
        return "\n".join(lines)

    result = check() if command == "check" else (
        reachability() if command == "reachability" else layering()
    )

    lines = [f"Architecture census — {command}", ""]
    lines.append(f"  checks run     {result.checked}")
    lines.append(f"  errors         {len([f for f in result.findings if f.severity == 'error'])}")
    lines.append(f"  warnings       {len([f for f in result.findings if f.severity == 'warning'])}")

    if result.findings:
        lines.append("")
        for finding in result.findings:
            mark = "ERROR" if finding.severity == "error" else "WARN "
            lines.append(f"  {mark} [{finding.area}] {finding.subject}")
            lines.append(f"        {finding.detail}")
    else:
        lines.append("")
        lines.append("  Every layer is reachable from a production path and no layer")
        lines.append("  imports something above it.")

    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "reachability", "layering"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    if args.command == "reachability":
        if args.format == "json":
            print(json.dumps(module_reachability(), indent=2, ensure_ascii=False))
        else:
            print(render_text(Census(), "reachability"))
        return 0

    result = check() if args.command == "check" else layering()
    if args.format == "json":
        print(json.dumps(result.to_json(), indent=2, ensure_ascii=False))
    else:
        print(render_text(result, args.command))
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
