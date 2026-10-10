#!/usr/bin/env python3
"""folio build manifest

Records everything that decides what a build produces, so two builds can be
told apart when they differ and trusted when they do not.

`render_env.py` already records the machine: interpreter, libraries, tools and
the fonts the renderer can see. This adds the parts that belong to the build
itself -- which commit, which dependency lock, which renderer, which locale,
which options -- and folds both into one fingerprint.

Usage:
    python3 scripts/build_manifest.py show
    python3 scripts/build_manifest.py show --format json
    python3 scripts/build_manifest.py compare <manifest.json>
    python3 scripts/build_manifest.py write dist/reports/build-manifest.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import locale
import os
import platform
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

SCHEMA_VERSION = "1.0"

# Environment variables that can change what a build produces. Anything not on
# this list is deliberately excluded: recording the whole environment would make
# two manifests differ for reasons that cannot affect a page.
TRACKED_ENV = (
    "FOLIO_PIPELINE",
    "FOLIO_AUTHOR",
    "SOURCE_DATE_EPOCH",
    "TZ",
    "LANG",
    "LC_ALL",
)


def _git(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = (result.stdout or "").strip()
    return value or None


def commit() -> str | None:
    return _git("rev-parse", "HEAD")


def commit_is_dirty() -> bool:
    """Whether tracked files differ from the recorded commit.

    A build from a dirty tree cannot be reproduced from the commit alone, so the
    fact is recorded rather than hidden.
    """
    status = _git("status", "--porcelain", "--untracked-files=no")
    return bool(status)


def dependency_lock_hash() -> str | None:
    """A digest over the files that pin dependencies.

    Absent lock files are reported as None rather than hashed as empty, so a
    project that has none says so instead of pretending to be locked.
    """
    candidates = [
        "pyproject.toml",
        "requirements.txt",
        "requirements-ci.txt",
        "poetry.lock",
        "uv.lock",
        "pnpm-lock.yaml",
        "package-lock.json",
    ]
    present = [ROOT / name for name in candidates if (ROOT / name).is_file()]
    if not present:
        return None

    digest = hashlib.sha256()
    for path in sorted(present):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def font_manifest_hash() -> str | None:
    """A digest over the font manifest and the bundled font files.

    The manifest alone is not enough: replacing a font file without editing the
    manifest would otherwise leave the fingerprint unchanged.
    """
    manifest = ROOT / "references" / "manifests" / "fonts-v1.yaml"
    font_dir = ROOT / "assets" / "fonts"
    if not manifest.is_file() and not font_dir.is_dir():
        return None

    digest = hashlib.sha256()
    if manifest.is_file():
        digest.update(manifest.read_bytes())
    if font_dir.is_dir():
        for path in sorted(font_dir.rglob("*")):
            if path.is_file():
                digest.update(path.name.encode("utf-8"))
                digest.update(path.read_bytes())
    return digest.hexdigest()


@dataclass(frozen=True)
class BuildManifest:
    """What produced an artifact, and under which conditions."""

    folio_commit: str | None
    commit_is_dirty: bool
    python_version: str
    dependency_lock_hash: str | None
    renderer_name: str
    renderer_version: str
    font_manifest_hash: str | None
    locale: str
    platform: str
    machine: str
    build_options: dict[str, str] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "folio_commit": self.folio_commit,
            "commit_is_dirty": self.commit_is_dirty,
            "python_version": self.python_version,
            "dependency_lock_hash": self.dependency_lock_hash,
            "renderer": {"name": self.renderer_name, "version": self.renderer_version},
            "font_manifest_hash": self.font_manifest_hash,
            "locale": self.locale,
            "platform": self.platform,
            "machine": self.machine,
            "build_options": dict(sorted(self.build_options.items())),
        }

    @property
    def fingerprint(self) -> str:
        """A digest over everything that can change rendered output.

        `build_options` is included, the commit's dirty flag is not: an
        uncommitted edit is a fact about provenance, and the file contents are
        already captured by the commit plus the recorded options.
        """
        payload = self.to_json()
        payload.pop("commit_is_dirty", None)
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def differences(self, other: BuildManifest) -> list[str]:
        """Which fields differ, for a report that names the cause."""
        mine, theirs = self.to_json(), other.to_json()
        out: list[str] = []
        for key in sorted(set(mine) | set(theirs)):
            if key == "schema_version":
                continue
            if mine.get(key) != theirs.get(key):
                out.append(key)
        return out


def _renderer_identity() -> tuple[str, str]:
    """The renderer a build would use, and its version."""
    try:
        from renderers.weasy import WeasyPrintRenderer, available

        if available():
            info = WeasyPrintRenderer().probe()
            return info.name, info.version
    except Exception:
        pass
    return "unavailable", "unavailable"


def _current_locale() -> str:
    try:
        value = locale.setlocale(locale.LC_ALL, None)
        return value or "C"
    except Exception:
        return os.environ.get("LC_ALL") or os.environ.get("LANG") or "C"


def capture(build_options: dict[str, str] | None = None) -> BuildManifest:
    """Read the current build conditions."""
    options = {key: os.environ[key] for key in TRACKED_ENV if key in os.environ}
    if build_options:
        options.update(build_options)

    name, version = _renderer_identity()
    return BuildManifest(
        folio_commit=commit(),
        commit_is_dirty=commit_is_dirty(),
        python_version=platform.python_version(),
        dependency_lock_hash=dependency_lock_hash(),
        renderer_name=name,
        renderer_version=version,
        font_manifest_hash=font_manifest_hash(),
        locale=_current_locale(),
        platform=f"{platform.system()} {platform.release()}",
        machine=platform.machine(),
        build_options=options,
    )


def compare_files(baseline_path: Path, current: BuildManifest) -> dict[str, Any]:
    """Compare a recorded manifest against the current conditions."""
    try:
        recorded = json.loads(baseline_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": f"cannot read {baseline_path}: {exc}"}

    renderer = recorded.get("renderer") or {}
    other = BuildManifest(
        folio_commit=recorded.get("folio_commit"),
        commit_is_dirty=bool(recorded.get("commit_is_dirty")),
        python_version=str(recorded.get("python_version", "")),
        dependency_lock_hash=recorded.get("dependency_lock_hash"),
        renderer_name=str(renderer.get("name", "")),
        renderer_version=str(renderer.get("version", "")),
        font_manifest_hash=recorded.get("font_manifest_hash"),
        locale=str(recorded.get("locale", "")),
        platform=str(recorded.get("platform", "")),
        machine=str(recorded.get("machine", "")),
        build_options=dict(recorded.get("build_options") or {}),
    )
    differing = current.differences(other)
    return {
        "ok": not differing,
        "differences": differing,
        "fingerprint_match": current.fingerprint == _fingerprint_of(recorded),
    }


def _fingerprint_of(payload: dict[str, Any]) -> str:
    copy = dict(payload)
    copy.pop("commit_is_dirty", None)
    encoded = json.dumps(copy, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def render_text(manifest: BuildManifest) -> str:
    payload = manifest.to_json()
    lines = ["Build manifest", ""]
    lines.append(f"  commit          {payload['folio_commit'] or '(not a git checkout)'}")
    if payload["commit_is_dirty"]:
        lines.append("  worktree        tracked files differ from the commit")
    lines.append(f"  python          {payload['python_version']}")
    lines.append(f"  renderer        {payload['renderer']['name']} {payload['renderer']['version']}")
    lines.append(f"  locale          {payload['locale']}")
    lines.append(f"  platform        {payload['platform']} / {payload['machine']}")
    lock = payload["dependency_lock_hash"]
    lines.append(f"  lock file       {lock[:16] + '...' if lock else '(none found)'}")
    fonts = payload["font_manifest_hash"]
    lines.append(f"  fonts           {fonts[:16] + '...' if fonts else '(none found)'}")
    if payload["build_options"]:
        lines.append("  build options")
        for key, value in payload["build_options"].items():
            lines.append(f"    {key}={value}")
    lines.append("")
    lines.append(f"  fingerprint     {manifest.fingerprint[:32]}")
    lines.append("")
    lines.append("  The fingerprint covers everything that can change rendered output.")
    lines.append("  Two builds with the same fingerprint should produce the same pages;")
    lines.append("  a difference points at the field that moved.")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    show = sub.add_parser("show", help="print the current build manifest")
    show.add_argument("--format", choices=("text", "json"), default="text")

    write = sub.add_parser("write", help="record the current manifest to a file")
    write.add_argument("path", type=Path)

    compare = sub.add_parser("compare", help="compare a recorded manifest with now")
    compare.add_argument("path", type=Path)
    compare.add_argument("--format", choices=("text", "json"), default="text")

    args = parser.parse_args(argv)

    if args.command == "show":
        manifest = capture()
        if args.format == "json":
            print(json.dumps(manifest.to_json(), indent=2, ensure_ascii=False))
        else:
            print(render_text(manifest))
        return 0

    if args.command == "write":
        manifest = capture()
        args.path.parent.mkdir(parents=True, exist_ok=True)
        args.path.write_text(
            json.dumps(manifest.to_json(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"OK: wrote {args.path}")
        return 0

    manifest = capture()
    result = compare_files(args.path, manifest)
    if args.format == "json":
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        if result.get("error"):
            print(f"ERROR: {result['error']}")
            return 2
        if result["ok"]:
            print("OK: the build conditions match the recorded manifest")
        else:
            print("ERROR: the build conditions differ")
            for name in result["differences"]:
                print(f"  {name}")
            print("")
            print("  A difference here explains a difference in output. Re-record with")
            print("  `build_manifest.py write` once the change is intended.")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
