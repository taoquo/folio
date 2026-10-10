#!/usr/bin/env python3
"""folio asset manifest

A document references assets; a diagram is one kind of asset. The reference has
to be checkable, or a figure silently points at a file that was regenerated,
moved, or never existed.

This module records what an asset is, what it was built from, and what came out,
so three questions have answers:

  - Does the referenced artifact still exist, and is it the one the document
    expected?
  - Has the source changed since the artifact was produced?
  - Which diagram produced this figure?

The last question is the connection to the Drawing DSL, and it is deliberately
loose. The document holds an `AssetRef`; the manifest holds the drawing's
identity and its own hashes. Neither IR contains the other, because a document
does not need a diagram's geometry to place it, and a diagram does not need a
document to exist.

Usage:
    python3 scripts/assets.py scan
    python3 scripts/assets.py check
    python3 scripts/assets.py verify --manifest references/manifests/assets-v1.json
    python3 scripts/assets.py stale
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

SCHEMA_VERSION = "1.0"
MANIFEST_PATH = ROOT / "references" / "manifests" / "assets-v1.json"

# Where an asset's source lives and where its outputs land. The diagram pipeline
# owns these directories; the manifest records what is in them rather than
# reaching into the pipeline.
DIAGRAM_SOURCE_DIRS = (
    ROOT / "assets" / "diagrams",
    ROOT / "references" / "fixtures",
)
DIAGRAM_OUTPUT_DIR = ROOT / "assets" / "diagrams" / "generated"

MEDIA_TYPES = {
    "svg": "image/svg+xml",
    "png": "image/png",
    "pdf": "application/pdf",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


@dataclass
class AssetArtifact:
    """One rendered form of an asset."""

    format: str
    path: str
    sha256: str | None = None
    media_type: str | None = None

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"format": self.format, "path": self.path}
        if self.sha256:
            out["sha256"] = self.sha256
        if self.media_type:
            out["media_type"] = self.media_type
        return out


@dataclass
class Asset:
    """A referenced asset, its source, and what was produced from it."""

    asset_id: str
    kind: str
    source_ref: str | None = None
    source_sha256: str | None = None
    artifacts: list[AssetArtifact] = field(default_factory=list)
    alt_text: str | None = None
    intrinsic_size: dict[str, Any] | None = None
    note: str = ""

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "asset_id": self.asset_id,
            "kind": self.kind,
            "artifacts": [a.to_json() for a in self.artifacts],
        }
        if self.source_ref:
            out["source_ref"] = self.source_ref
        if self.source_sha256:
            out["source_sha256"] = self.source_sha256
        if self.alt_text:
            out["alt_text"] = self.alt_text
        if self.intrinsic_size:
            out["intrinsic_size"] = self.intrinsic_size
        if self.note:
            out["note"] = self.note
        return out


@dataclass
class AssetManifest:
    """The assets a build can reference."""

    assets: dict[str, Asset] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "assets": [self.assets[key].to_json() for key in sorted(self.assets)],
        }

    def to_json_text(self) -> str:
        return json.dumps(self.to_json(), indent=2, ensure_ascii=False) + "\n"


def scan_diagrams() -> AssetManifest:
    """Record every generated diagram artifact and its source.

    The source is matched by stem: `assets/diagrams/architecture.html` produces
    `generated/svg/architecture.svg`. A missing source is recorded as such
    rather than omitted, because an artifact with no source cannot be rebuilt.
    """
    manifest = AssetManifest()
    if not DIAGRAM_OUTPUT_DIR.is_dir():
        return manifest

    sources: dict[str, Path] = {}
    for directory in DIAGRAM_SOURCE_DIRS:
        if not directory.is_dir():
            continue
        for path in directory.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".html", ".yaml", ".txt", ".json"}:
                sources.setdefault(path.stem, path)

    for format_dir in sorted(DIAGRAM_OUTPUT_DIR.iterdir()):
        if not format_dir.is_dir():
            continue
        for artifact in sorted(format_dir.iterdir()):
            if not artifact.is_file():
                continue
            suffix = artifact.suffix.lstrip(".").lower()
            asset_id = f"diagram.{artifact.stem}"
            asset = manifest.assets.get(asset_id)
            if asset is None:
                source = sources.get(artifact.stem)
                asset = Asset(
                    asset_id=asset_id,
                    kind="diagram",
                    source_ref=_relative(source) if source else None,
                    source_sha256=sha256_file(source) if source else None,
                    note="" if source else "no source found; this artifact cannot be rebuilt",
                )
                manifest.assets[asset_id] = asset
            asset.artifacts.append(
                AssetArtifact(
                    format=suffix,
                    path=_relative(artifact),
                    sha256=sha256_file(artifact),
                    media_type=MEDIA_TYPES.get(suffix),
                )
            )
    return manifest


def load_manifest(path: Path = MANIFEST_PATH) -> AssetManifest:
    if not path.is_file():
        return AssetManifest()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON: {exc}") from exc

    manifest = AssetManifest(schema_version=str(data.get("schema_version", SCHEMA_VERSION)))
    for entry in data.get("assets") or []:
        artifacts = [
            AssetArtifact(
                format=str(item.get("format", "")),
                path=str(item.get("path", "")),
                sha256=item.get("sha256"),
                media_type=item.get("media_type"),
            )
            for item in entry.get("artifacts") or []
        ]
        manifest.assets[str(entry["asset_id"])] = Asset(
            asset_id=str(entry["asset_id"]),
            kind=str(entry.get("kind", "unknown")),
            source_ref=entry.get("source_ref"),
            source_sha256=entry.get("source_sha256"),
            artifacts=artifacts,
            alt_text=entry.get("alt_text"),
            intrinsic_size=entry.get("intrinsic_size"),
            note=str(entry.get("note", "")),
        )
    return manifest


@dataclass
class AssetIssue:
    """One problem found while checking an asset."""

    asset_id: str
    code: str
    message: str
    severity: str = "error"
    hint: str = ""

    def to_json(self) -> dict[str, Any]:
        out = {"asset_id": self.asset_id, "code": self.code,
               "severity": self.severity, "message": self.message}
        if self.hint:
            out["hint"] = self.hint
        return out


def check(manifest: AssetManifest) -> list[AssetIssue]:
    """Every problem a reader would hit, reported rather than assumed absent."""
    issues: list[AssetIssue] = []

    for asset_id, asset in sorted(manifest.assets.items()):
        if not asset.artifacts:
            issues.append(AssetIssue(
                asset_id, "ASSET-ARTIFACT.EMPTY", "asset has no rendered output",
                hint="Run the diagram build to produce one.",
            ))

        for artifact in asset.artifacts:
            path = ROOT / artifact.path
            if not path.is_file():
                issues.append(AssetIssue(
                    asset_id, "ASSET-ARTIFACT.MISSING", f"{artifact.path} does not exist",
                    hint="Rebuild the diagram, or correct the path.",
                ))
                continue
            actual = sha256_file(path)
            if artifact.sha256 and actual != artifact.sha256:
                issues.append(AssetIssue(
                    asset_id, "ASSET-ARTIFACT.CHANGED",
                    f"{artifact.path} differs from the recorded digest",
                    hint="Rebuild and re-record if the change is intended.",
                ))

        if asset.source_ref:
            source = ROOT / asset.source_ref
            if not source.is_file():
                issues.append(AssetIssue(
                    asset_id, "ASSET-SOURCE.MISSING",
                    f"source {asset.source_ref} does not exist",
                ))
            elif asset.source_sha256:
                if sha256_file(source) != asset.source_sha256:
                    issues.append(AssetIssue(
                        asset_id, "ASSET-SOURCE.CHANGED",
                        f"source {asset.source_ref} changed since the artifact was built",
                        severity="warning",
                        hint="The rendered output may be out of date.",
                    ))

    return issues


def stale_assets(manifest: AssetManifest) -> list[str]:
    """Assets whose source changed after the artifact was recorded."""
    out: list[str] = []
    for asset_id, asset in sorted(manifest.assets.items()):
        if not asset.source_ref or not asset.source_sha256:
            continue
        source = ROOT / asset.source_ref
        if source.is_file() and sha256_file(source) != asset.source_sha256:
            out.append(asset_id)
    return out


def references_in(document_payload: Mapping[str, Any]) -> list[str]:
    """Asset ids a document references.

    The document holds a uri; the manifest holds ids. Matching is by stem so a
    document can reference `generated/svg/architecture.svg` and be checked
    against `diagram.architecture`.
    """
    found: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            uri = value.get("uri")
            if isinstance(uri, str) and uri:
                found.append(f"diagram.{Path(uri).stem}")
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(document_payload)
    return sorted(set(found))


def render_text(manifest: AssetManifest, issues: list[AssetIssue], command: str) -> str:
    if command == "scan":
        lines = ["Asset manifest", ""]
        lines.append(f"  assets recorded   {len(manifest.assets)}")
        lines.append(f"  artifacts         {sum(len(a.artifacts) for a in manifest.assets.values())}")
        without_source = [a.asset_id for a in manifest.assets.values() if not a.source_ref]
        if without_source:
            lines.append("")
            lines.append(f"  {len(without_source)} asset(s) have no source and cannot be rebuilt:")
            for asset_id in without_source[:8]:
                lines.append(f"    {asset_id}")
        lines.append("")
        lines.append("  A document references an asset; the manifest records what it was")
        lines.append("  built from and what came out. Neither contains the other's IR.")
        return "\n".join(lines)

    if command in {"check", "verify"}:
        lines = ["Asset check", ""]
        if not issues:
            lines.append(f"  OK  {len(manifest.assets)} asset(s) resolve, digests match")
        else:
            errors = [i for i in issues if i.severity == "error"]
            warnings = [i for i in issues if i.severity != "error"]
            lines.append(f"  {len(errors)} error(s), {len(warnings)} warning(s)")
            lines.append("")
            for issue in issues[:20]:
                mark = "ERROR" if issue.severity == "error" else "WARN "
                lines.append(f"  {mark} {issue.asset_id}: {issue.message}")
                if issue.hint:
                    lines.append(f"        {issue.hint}")
        return "\n".join(lines)

    if command == "stale":
        stale = stale_assets(manifest)
        lines = ["Stale assets", ""]
        if not stale:
            lines.append("  OK  no asset has a source newer than its artifact")
        else:
            lines.append(f"  {len(stale)} asset(s) need rebuilding:")
            for asset_id in stale:
                lines.append(f"    {asset_id}")
        return "\n".join(lines)

    return json.dumps(manifest.to_json(), indent=2, ensure_ascii=False)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="record the assets present now")
    scan.add_argument("--format", choices=("text", "json"), default="text")
    scan.add_argument("--write", action="store_true", help=f"write {MANIFEST_PATH.name}")

    for name, help_text in (("check", "check the recorded manifest"),
                            ("verify", "check a manifest file"),
                            ("stale", "list assets whose source changed")):
        cmd = sub.add_parser(name, help=help_text)
        cmd.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
        cmd.add_argument("--format", choices=("text", "json"), default="text")

    args = parser.parse_args(argv)

    if args.command == "scan":
        manifest = scan_diagrams()
        if args.write:
            MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
            MANIFEST_PATH.write_text(manifest.to_json_text(), encoding="utf-8")
            print(f"OK: wrote {MANIFEST_PATH.relative_to(ROOT)}")
            return 0
        if args.format == "json":
            print(json.dumps(manifest.to_json(), indent=2, ensure_ascii=False))
        else:
            print(render_text(manifest, [], "scan"))
        return 0

    try:
        manifest = load_manifest(args.manifest)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2

    if args.command == "stale":
        if args.format == "json":
            print(json.dumps({"stale": stale_assets(manifest)}, indent=2))
        else:
            print(render_text(manifest, [], "stale"))
        return 0

    issues = check(manifest)
    if args.format == "json":
        print(json.dumps({"issues": [i.to_json() for i in issues],
                          "assets": len(manifest.assets)}, indent=2, ensure_ascii=False))
    else:
        print(render_text(manifest, issues, args.command))
    return 0 if not any(i.severity == "error" for i in issues) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
