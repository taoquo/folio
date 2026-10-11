#!/usr/bin/env python3
"""folio link check

Every relative link in a tracked Markdown or HTML file must resolve.

The repository removes things: 257 files in one pass, 23 in another, and each was
verified by hand. Hand verification does not survive the next removal, and a
broken link is the visible form of an accidental deletion -- a reader clicks and
the file is gone, with nothing having said so.

Some targets are deliberately absent, and they are listed rather than special-cased
in the walk:

  * an ignored path (`docs/plans/`, `build/`) is local by policy;
  * an external URL is not this repository's to resolve;
  * an anchor (`#section`) is a link within a page.

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
}


def tracked() -> list[str]:
    result = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    return [line for line in result.stdout.splitlines() if line]


def ignored(paths: set[str]) -> set[str]:
    """Which of these paths git ignores, asked in one call."""
    if not paths:
        return set()
    result = subprocess.run(["git", "check-ignore", "--stdin"], cwd=ROOT,
                            input="\n".join(sorted(paths)), capture_output=True, text=True)
    return {line for line in result.stdout.splitlines() if line}


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


def check() -> list[dict[str, str]]:
    files = tracked()
    # Directories that exist, so a link to one is not a broken link.
    directories = {str(Path(name).parent) for name in files if "/" in name}
    directories |= {str(Path(name).parent.parent) for name in files if name.count("/") > 1}

    raw_targets: list[tuple[str, str, str]] = []
    for name in files:
        if Path(name).suffix.lower() not in SUFFIXES or name in ALLOWED:
            continue
        text = (ROOT / name).read_text(encoding="utf-8", errors="ignore")
        for target in candidates(text, Path(name).suffix.lower()):
            raw_targets.append((name, target, target))

    # Resolve first, then ask git once about the ones that look local and absent.
    resolved: list[tuple[str, str, Path]] = []
    for name, target, _raw in raw_targets:
        parsed = urlparse(target)
        if parsed.scheme or target.startswith(("//", "#", "mailto:", "data:")):
            continue
        clean = unquote(parsed.path)
        if not clean:
            continue
        resolved.append((name, target, (ROOT / Path(name).parent / clean).resolve()))

    absent = {str(path.relative_to(ROOT)) for _n, _t, path in resolved
              if path.is_relative_to(ROOT) and not path.exists()}
    local_by_policy = ignored(absent)

    findings: list[dict[str, str]] = []
    for name, target, path in resolved:
        if path.exists():
            continue
        if not path.is_relative_to(ROOT):
            continue  # outside the repository, not ours to resolve
        relative = str(path.relative_to(ROOT))
        if relative in local_by_policy:
            continue
        if relative in directories:
            continue
        findings.append({
            "document": name,
            "target": target,
            "resolves_to": relative,
            "problem": "the target is not in the repository and is not ignored",
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
