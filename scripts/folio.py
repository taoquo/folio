#!/usr/bin/env python3
"""Product CLI for Folio."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from build import DIAGRAM_ARTIFACT_TARGETS, DIAGRAM_TARGETS, HTML_TARGETS, PPTX_TARGETS


ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = ROOT / "scripts" / "build.py"
PACKAGE_SCRIPT = ROOT / "scripts" / "package-skill.sh"


def _run_build(args: list[str]) -> int:
    result = subprocess.run([sys.executable, str(BUILD_SCRIPT), *args], cwd=ROOT)
    return result.returncode


def _run_package() -> int:
    result = subprocess.run(["bash", str(PACKAGE_SCRIPT)], cwd=ROOT)
    return result.returncode


def _print_group(label: str, names: list[str]) -> None:
    print(f"{label}:")
    for name in names:
        print(f"  {name}")


def list_targets() -> int:
    _print_group("HTML targets", sorted(HTML_TARGETS))
    _print_group("Diagram targets", sorted(DIAGRAM_TARGETS))
    _print_group("Artifact targets", sorted(DIAGRAM_ARTIFACT_TARGETS))
    _print_group("Slide targets", sorted(PPTX_TARGETS))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build, verify, package, and diagnose Folio.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_cmd = subparsers.add_parser("build", help="Build all targets or one named target.")
    build_cmd.add_argument("target", nargs="?", help="Optional build target.")

    verify_cmd = subparsers.add_parser("verify", help="Verify all targets or one named target.")
    verify_cmd.add_argument("target", nargs="?", help="Optional verify target.")

    subparsers.add_parser("check", help="Run CSS and token checks.")
    subparsers.add_parser("doctor", help="Check local PDF/PPTX/diagram dependencies.")
    subparsers.add_parser("package", help="Build dist/folio.zip.")
    subparsers.add_parser("list-targets", help="List known build targets.")

    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv[1:])

    if args.command == "build":
        return _run_build([args.target] if args.target else [])
    if args.command == "verify":
        command = ["--verify"]
        if args.target:
            command.append(args.target)
        return _run_build(command)
    if args.command == "check":
        return _run_build(["--check"])
    if args.command == "doctor":
        return _run_build(["--doctor"])
    if args.command == "package":
        return _run_package()
    if args.command == "list-targets":
        return list_targets()

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
