#!/usr/bin/env python3
"""folio page contracts

The single source of truth for how many pages each registered build target may
produce. `build.py` enforces these contracts as a hard gate; `stabilize.py`
reads the maximum from the same table when solving for overflow. Both used to
carry their own copy, so a contract change could silently apply to one path
only.

Keep this module free of imports from the rest of `scripts/` so either consumer
can load it without pulling in the other.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PageSpec:
    """A page-count contract.

    `min_pages == max_pages` means the document has a strict page count.
    """

    source: str
    min_pages: int
    max_pages: int


# name -> page spec
HTML_TARGETS: dict[str, PageSpec] = {
    # Chinese
    "one-pager":    PageSpec("one-pager.html", 1, 1),
    "letter":       PageSpec("letter.html", 1, 1),
    "long-doc":     PageSpec("long-doc.html", 5, 9),
    "portfolio":    PageSpec("portfolio.html", 4, 8),
    "resume":       PageSpec("resume.html", 2, 2),
    # English
    "one-pager-en": PageSpec("one-pager-en.html", 1, 1),
    "letter-en":    PageSpec("letter-en.html", 1, 1),
    "long-doc-en":  PageSpec("long-doc-en.html", 5, 9),
    "portfolio-en": PageSpec("portfolio-en.html", 4, 8),
    "resume-en":    PageSpec("resume-en.html", 2, 2),
    # Equity Report
    "equity-report":    PageSpec("equity-report.html", 2, 3),
    "equity-report-en": PageSpec("equity-report-en.html", 2, 3),
    # Changelog
    "changelog":    PageSpec("changelog.html", 1, 2),
    "changelog-en": PageSpec("changelog-en.html", 1, 2),
}

PPTX_TARGETS: dict[str, PageSpec] = {
    "slides":    PageSpec("slides.py", 4, 10),
    "slides-en": PageSpec("slides-en.py", 4, 10),
}
