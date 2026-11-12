#!/usr/bin/env python3
"""folio site build

Assembles the static site Cloudflare serves at the declared origin.

The homepages are authored and themed in the repository, not generated at
request time. The deploy directory is therefore a copy of tracked sources: the
three pages, the stylesheet, the fonts and the assets they name, plus the
AdSense record and the response headers. Copying rather than uploading the
repository root keeps local work, planning notes and the ZIP out of the site.

Every local reference in a copied page or stylesheet is resolved against the
deploy directory before the command reports success, so a missing image fails
here instead of 404ing in production. The Cloudflare asset limits are checked
too: 20,000 files and 25 MiB per file.

Usage:
    python3 scripts/build_site.py
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dist" / "site"

PAGES = ("index.html", "index-zh.html", "index-en.html", "styles.css")
DIRECTORIES = (
    "assets/fonts",
    "assets/images",
    "assets/illustrations",
    "assets/diagrams/generated/png",
)
# The demos are showcase captures: the homepages link their PDF and PNG, never
# the HTML source, and the sources carry references to repository-only images.
DEMOS = "assets/demos"
EXTRAS = {
    "references/site/_headers": "_headers",
    "references/site/_redirects": "_redirects",
    "references/site/ads.txt": "ads.txt",
}

MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_FILES = 20_000

ATTRIBUTE = re.compile(r'(?:href|src)="([^"]+)"')
SRCSET = re.compile(r'srcset="([^"]+)"')
CSS_URL = re.compile(r'url\(\s*["\']?([^"\')]+)')


def references(text: str):
    """Every local resource a page or stylesheet names."""
    yield from ATTRIBUTE.findall(text)
    for value in SRCSET.findall(text):
        for part in value.split(","):
            target = part.strip().split(" ")[0]
            if target:
                yield target
    yield from CSS_URL.findall(text)


def resolve_reference(source: Path, raw: str) -> Path | None:
    raw = raw.strip()
    if not raw or raw.startswith(("http://", "https://", "data:", "mailto:", "#", "//")):
        return None
    path = unquote(urlsplit(raw).path)
    if not path:
        return None
    if path.startswith("/"):
        return (OUT / path.lstrip("/")).resolve()
    return (source.parent / path).resolve()


def check_copied_files() -> list[str]:
    errors: list[str] = []
    root = OUT.resolve()
    for name in PAGES:
        source = OUT / name
        for raw in references(source.read_text(encoding="utf-8", errors="replace")):
            target = resolve_reference(source, raw)
            if target is None:
                continue
            if root not in target.parents and target != root:
                errors.append(f"{source.relative_to(OUT)}: reference escapes the site: {raw}")
            elif not target.exists():
                errors.append(f"{source.relative_to(OUT)}: missing {raw}")
    return errors


def check_limits() -> list[str]:
    errors: list[str] = []
    files = [path for path in OUT.rglob("*") if path.is_file()]
    if len(files) > MAX_FILES:
        errors.append(f"{len(files)} files exceeds the {MAX_FILES} Cloudflare limit")
    for path in files:
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            errors.append(
                f"{path.relative_to(OUT)} is {size / 1024 / 1024:.1f} MiB, "
                f"above the 25 MiB Cloudflare limit"
            )
    return errors


def copy_demos() -> None:
    target = OUT / DEMOS
    target.mkdir(parents=True)
    for source in sorted((ROOT / DEMOS).iterdir()):
        if source.is_file() and source.suffix != ".html":
            shutil.copy2(source, target / source.name)


def build() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    for name in PAGES:
        shutil.copy2(ROOT / name, OUT / name)
    for name in DIRECTORIES:
        shutil.copytree(ROOT / name, OUT / name)
    copy_demos()
    for source, name in EXTRAS.items():
        shutil.copy2(ROOT / source, OUT / name)

    errors = check_copied_files() + check_limits()
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    files = [path for path in OUT.rglob("*") if path.is_file()]
    total = sum(path.stat().st_size for path in files)
    print(f"OK: {len(files)} file(s), {total / 1024 / 1024:.1f} MiB in {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(build())
