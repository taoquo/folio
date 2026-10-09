#!/usr/bin/env python3
"""folio render environment

Records everything that can change rendered output but is not part of the
repository: interpreter, PDF/rendering libraries, Poppler, Node, and the font
files actually visible to the renderer.

Two builds of the same source are only comparable when this fingerprint
matches. Without it a visual difference cannot be attributed to a code change
rather than to the machine.

Usage:
    python3 scripts/render_env.py                     # print JSON
    python3 scripts/render_env.py --output env.json   # write JSON
    python3 scripts/render_env.py --diff env.json     # compare with a record
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "references" / "manifests" / "render-env-v1.json"


def _run(argv: list[str]) -> str | None:
    """First line of a command's output, or None when unavailable.

    Both streams are considered: Poppler tools print their version banner to
    stderr while Node prints it to stdout. stderr is still captured rather than
    inherited, and fontconfig is pointed at a writable cache directory, so host
    warnings cannot pollute the manifest.
    """
    import os
    import tempfile

    env = dict(os.environ)
    env.setdefault("XDG_CACHE_HOME", tempfile.gettempdir())
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True, check=False, timeout=20, env=env
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    text = (result.stdout or "").strip() or (result.stderr or "").strip()
    return text.splitlines()[0] if text else None


def _version_line(argv: list[str]) -> str | None:
    out = _run(argv)
    if not out:
        return None
    match = re.search(r"(\d+(?:\.\d+)+)", out)
    return match.group(1) if match else out


def _python_packages() -> dict[str, str | None]:
    from importlib.metadata import PackageNotFoundError, version

    packages = {
        "weasyprint": "weasyprint",
        "pypdf": "pypdf",
        "pillow": "Pillow",
        "jsonschema": "jsonschema",
        "python-pptx": "python-pptx",
    }
    found: dict[str, str | None] = {}
    for label, distribution in packages.items():
        try:
            found[label] = version(distribution)
        except PackageNotFoundError:
            found[label] = None
        except Exception:
            found[label] = "unknown"
    return found


def _font_fingerprint() -> dict[str, object]:
    """Hash the font files a renderer can actually resolve."""
    entries = []
    fonts_dir = ROOT / "assets" / "fonts"
    if fonts_dir.is_dir():
        for path in sorted(fonts_dir.iterdir()):
            if path.is_file():
                entries.append(
                    {
                        "name": path.name,
                        "source": "bundled",
                        "bytes": path.stat().st_size,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                )

    # System fonts the templates name but do not bundle. Presence is recorded,
    # not contents: these are host-provided and cannot be hashed portably.
    resolved = {}
    for family in ("Charter", "Georgia", "Palatino", "LXGW WenKai", "JetBrains Mono"):
        match = _run(["fc-match", "-f", "%{file}", family])
        resolved[family] = match or None

    digest = hashlib.sha256(
        json.dumps(
            [{"name": e["name"], "sha256": e["sha256"]} for e in entries],
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()

    return {"bundled": entries, "resolved": resolved, "bundled_digest": digest}


def collect() -> dict[str, object]:
    return {
        "schema_version": 1,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            # pyproject declares >=3.10. CI covers the floor, an intermediate,
            # and the newest supported interpreter; a local interpreter outside
            # this set is a drift signal, not an error.
            "declared_floor": "3.10",
            "ci_matrix": ["3.10", "3.12", "3.14"],
        },
        "packages": _python_packages(),
        "tools": {
            "pdftoppm": _version_line(["pdftoppm", "-v"]),
            "pdffonts": _version_line(["pdffonts", "-v"]),
            "pdftotext": _version_line(["pdftotext", "-v"]),
            "node": _version_line(["node", "--version"]),
            "rsvg-convert": _version_line(["rsvg-convert", "--version"]),
        },
        "fonts": _font_fingerprint(),
        "tool_paths": {
            name: (shutil.which(name) or None)
            for name in ("pdftoppm", "pdffonts", "pdftotext", "node", "rsvg-convert")
        },
    }


def compare(recorded: dict, current: dict) -> list[str]:
    """Differences that would make two renders non-comparable."""
    differences: list[str] = []

    for section in ("platform", "python", "packages", "tools"):
        old = recorded.get(section, {})
        new = current.get(section, {})
        for key in sorted(set(old) | set(new)):
            if old.get(key) != new.get(key):
                differences.append(f"{section}.{key}: {old.get(key)!r} -> {new.get(key)!r}")

    old_fonts = recorded.get("fonts", {})
    new_fonts = current.get("fonts", {})
    if old_fonts.get("bundled_digest") != new_fonts.get("bundled_digest"):
        differences.append("fonts.bundled_digest changed")
    for family in sorted(set(old_fonts.get("resolved", {})) | set(new_fonts.get("resolved", {}))):
        old_path = old_fonts.get("resolved", {}).get(family)
        new_path = new_fonts.get("resolved", {}).get(family)
        if old_path != new_path:
            differences.append(f"fonts.resolved.{family}: {old_path!r} -> {new_path!r}")

    return differences


def render_text(env: dict) -> str:
    lines = [
        "Render environment",
        f"  platform   {env['platform']['system']} {env['platform']['release']} ({env['platform']['machine']})",
        f"  python     {env['python']['version']} (floor {env['python']['declared_floor']}, ci {','.join(env['python']['ci_matrix'])})",
        "",
        "Packages",
    ]
    for name, version in env["packages"].items():
        lines.append(f"  {name:<14} {version or 'missing'}")
    lines.append("")
    lines.append("Tools")
    for name, version in env["tools"].items():
        lines.append(f"  {name:<14} {version or 'missing'}")
    lines.append("")
    lines.append("Fonts")
    for entry in env["fonts"]["bundled"]:
        lines.append(f"  bundled      {entry['name']} ({entry['bytes']} bytes)")
    for family, path in env["fonts"]["resolved"].items():
        lines.append(f"  resolved     {family:<14} {path or 'NOT FOUND'}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, help=f"write JSON here (default: {DEFAULT_OUTPUT})")
    parser.add_argument("--diff", type=Path, help="compare against a recorded environment")
    parser.add_argument("--format", choices=("json", "text"), default="text")
    parser.add_argument("--write", action="store_true", help="write the default record")
    args = parser.parse_args(argv)

    current = collect()

    if args.diff:
        if not args.diff.is_file():
            print(f"ERROR: no recorded environment at {args.diff}")
            return 2
        recorded = json.loads(args.diff.read_text(encoding="utf-8"))
        differences = compare(recorded, current)
        if not differences:
            print(f"OK: environment matches {args.diff}")
            return 0
        print(f"ERROR: environment differs from {args.diff}")
        for item in differences:
            print(f"  {item}")
        return 1

    target = args.output or (DEFAULT_OUTPUT if args.write else None)
    if target:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(current, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"OK: wrote render environment to {target}")

    if args.format == "json":
        print(json.dumps(current, indent=2, ensure_ascii=False))
    elif not target:
        print(render_text(current))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
