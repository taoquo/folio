#!/usr/bin/env python3
"""folio link check

Every relative link in a tracked Markdown or HTML file must resolve.

The repository removes things: 257 files in one pass, 23 in another, and each was
verified by hand. Hand verification does not survive the next removal, and a
broken link is the visible form of an accidental deletion -- a reader clicks and
the file is gone, with nothing having said so.

A link must point at a file a clone receives. A file that exists only on the
author's machine is not a published target: it resolves in `ls` and 404s for
every reader, which is the failure a disk-only check cannot see.

Some targets are deliberately absent, and they are listed rather than special-cased
in the walk:

  * an external URL is not this repository's to resolve;
  * an anchor (`#section`) is a link within a page;
  * a document rendered elsewhere resolves beside its rendered copy (`ALLOWED`).

    python3 scripts/check_links.py
    python3 scripts/check_links.py --format json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]

# `[text](target)` and `![alt](target)`.
MARKDOWN = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)")
# HTML `src` / `href`.
HTML_ATTR = re.compile(r'(?:src|href)\s*=\s*"([^"]+)"')
# CSS `url(...)`, quoted or bare.
CSS_URL = re.compile(r"url\(\s*['\"]?([^'\")\s]+)")

# Which patterns apply to which file. A `.html` page's links are attributes --
# applying the Markdown pattern to one reads code samples as links.
PATTERNS = {
    ".md": (MARKDOWN, HTML_ATTR),
    ".html": (HTML_ATTR,),
    ".css": (CSS_URL,),
}

SUFFIXES = {".md", ".html", ".css"}

# Documents whose links resolve in a rendered location rather than in place.
# Each entry states why, because an unexplained exception is one nobody dares
# remove and nobody can check.
ALLOWED = {
    "scripts/templates/canvas-review.html":
        "a template build_canvas_review.py renders into build/canvas/, where review/ is "
        "created beside it",
    "assets/templates/web/module.html":
        "build_web.py renders it to dist/web/<series>/<module>/index.html, where "
        "../index.html is the series index it links back to",
}


def tracked() -> list[str]:
    result = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    return [line for line in result.stdout.splitlines() if line]


def published_directories(files: list[str]) -> set[str]:
    """Every directory a clone receives, derived from the files it receives."""
    directories: set[str] = set()
    for name in files:
        parts = Path(name).parts
        for depth in range(1, len(parts)):
            directories.add(str(Path(*parts[:depth])))
    return directories


# Regions that cannot hold a live link: a fenced block, an inline code span, an
# HTML comment, and a script or style element.
DEAD_SPANS = (
    re.compile(r"```.*?```", re.DOTALL),
    re.compile(r"`[^`\n]+`"),
    re.compile(r"<!--.*?-->", re.DOTALL),
    re.compile(r"<script\b.*?</script>", re.DOTALL | re.IGNORECASE),
    re.compile(r"<style\b.*?</style>", re.DOTALL | re.IGNORECASE),
)

# An unfilled placeholder is not a target yet: `href="{{URL}}"` resolves once a
# document fills it in, and reporting it would report the template's design.
PLACEHOLDER = re.compile(r"\{\{|\}\}|\$\{")


def candidates(text: str, suffix: str = ".md") -> list[str]:
    """Link targets in a document, in the order they appear."""
    spans = [(m.start(), m.end()) for pattern in DEAD_SPANS for m in pattern.finditer(text)]
    found: list[str] = []
    for pattern in PATTERNS.get(suffix, (MARKDOWN, HTML_ATTR)):
        for match in pattern.finditer(text):
            if any(start <= match.start() < end for start, end in spans):
                continue
            target = match.group(1)
            if PLACEHOLDER.search(target):
                continue
            found.append(target)
    return found


def check(root: Path = ROOT, files: list[str] | None = None) -> list[dict[str, str]]:
    """Broken links in tracked documents.

    `files` is the set of paths a clone receives; the default asks git. The
    parameter exists so a test can describe a small tree without inventing a
    repository.
    """
    root = root.resolve()
    files = tracked() if files is None else files
    published = set(files)
    directories = published_directories(files)

    raw_targets: list[tuple[str, str, str]] = []
    for name in files:
        if Path(name).suffix.lower() not in SUFFIXES or name in ALLOWED:
            continue
        text = (root / name).read_text(encoding="utf-8", errors="ignore")
        for target in candidates(text, Path(name).suffix.lower()):
            raw_targets.append((name, target, target))

    resolved: list[tuple[str, str, Path]] = []
    for name, target, _raw in raw_targets:
        parsed = urlparse(target)
        if parsed.scheme or target.startswith(("//", "#", "mailto:", "data:")):
            continue
        clean = unquote(parsed.path)
        if not clean:
            continue
        resolved.append((name, target, (root / Path(name).parent / clean).resolve()))

    findings: list[dict[str, str]] = []
    for name, target, path in resolved:
        if not path.is_relative_to(root):
            continue  # outside the repository, not ours to resolve
        relative = str(path.relative_to(root))
        present = path.exists() and (relative in published or relative in directories)
        if present:
            continue
        findings.append({
            "document": name,
            "target": target,
            "resolves_to": relative,
            "problem": ("the target is not tracked, so a clone would not have it"
                        if path.exists()
                        else "the target is not in the repository"),
        })
    return findings


def render(findings: list[dict[str, str]]) -> str:
    lines = ["Link check", ""]
    if not findings:
        lines.append("  Every relative link in a tracked document resolves.")
    for finding in findings:
        lines.append(f"  ERROR {finding['document']}: {finding['target']}")
        lines.append(f"        -> {finding['resolves_to']}: {finding['problem']}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    findings = check()
    if args.format == "json":
        print(json.dumps({"findings": findings, "ok": not findings}, indent=2, ensure_ascii=False))
    else:
        print(render(findings))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
