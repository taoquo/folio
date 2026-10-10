"""WeasyPrint as one renderer, not as the document implementation.

This adapter is the whole of Folio's coupling to WeasyPrint. Everything above
it speaks the vocabulary in `base.py`; nothing above it imports WeasyPrint.

Capabilities are probed against the installed engine rather than copied from
documentation. WeasyPrint's own version policy warns that a major release can
change rendered output even when the API is unchanged, so a manifest that
describes a version nobody runs is worse than no manifest.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .base import (
    ArtifactSet,
    CapabilityReport,
    RendererError,
    RendererInfo,
    RenderMetrics,
    RenderRequest,
    negotiate,
)

# Features Folio asks about. The vocabulary is Folio's, not WeasyPrint's: each
# name describes what a document needs, and the adapter maps it to whatever the
# engine calls it.
FEATURES = (
    "paged_media",
    "page_counters",
    "running_elements",
    "footnotes",
    "cross_references",
    "bibliography",
    "math",
    "columns",
    "page_floats",
    "tagged_pdf",
    "pdf_ua_1",
    "pdf_a",
    "bookmarks",
    "cjk_line_break",
    "rtl",
    "vertical_writing",
    "forms",
    # Added when the spacing model began expressing them: a document can now ask
    # for elastic spacing and for layout diagnostics, so the renderer has to say
    # whether it can deliver.
    "elastic_spacing",
    "layout_diagnostics",
)


@dataclass(frozen=True, slots=True)
class ProbeEvidence:
    """What a capability claim rests on.

    Recorded so a reviewer can see whether a level came from an actual probe or
    from a fallback assumption.
    """

    feature: str
    level: str
    method: str


def _weasyprint_version() -> str:
    try:
        import weasyprint

        return getattr(weasyprint, "__version__", "unknown")
    except Exception:
        return "absent"


def _option_names() -> set[str]:
    """Option names the installed engine actually accepts."""
    try:
        from weasyprint import DEFAULT_OPTIONS

        return set(DEFAULT_OPTIONS.keys())
    except Exception:
        return set()


class WeasyPrintRenderer:
    """Render HTML to PDF with WeasyPrint."""

    id = "weasy"
    api_version = "1.0"

    def __init__(self, *, name: str | None = None) -> None:
        self._info: RendererInfo | None = None
        self._name = name or self.id

    # -- contract ---------------------------------------------------------

    def probe(self) -> RendererInfo:
        if self._info is not None:
            return self._info
        self._info = RendererInfo(
            name=self._name,
            version=_weasyprint_version(),
            outputs=frozenset({"pdf", "png"}),
            capabilities=self._capabilities(),
        )
        return self._info

    def capability_evidence(self) -> tuple[ProbeEvidence, ...]:
        """How each capability level was determined."""
        evidence = []
        for feature, level in self.probe().capabilities.items():
            if feature in {"tagged_pdf", "pdf_ua_1", "pdf_a"}:
                method = "option probe"
            elif feature in {"cjk_line_break", "rtl", "vertical_writing"}:
                method = "engine default; not yet conformance-tested"
            else:
                method = "CSS Paged Media support in the pinned version"
            evidence.append(ProbeEvidence(feature=feature, level=level, method=method))
        return tuple(evidence)

    def validate_request(self, request: RenderRequest) -> CapabilityReport:
        return negotiate(self.probe(), request.requirements, strict=request.strict)

    def render(self, request: RenderRequest) -> ArtifactSet:
        report = self.validate_request(request)
        if not report.ok:
            missing = ", ".join(m.feature for m in report.missing if m.is_hard)
            raise RendererError(
                f"{self.id}: required capability missing ({missing}); "
                "rendering was refused rather than degraded silently"
            )

        try:
            from weasyprint import HTML
        except Exception as exc:  # pragma: no cover - depends on the host
            raise RendererError(f"{self.id}: engine unavailable: {exc}") from exc

        request.output.parent.mkdir(parents=True, exist_ok=True)
        started = time.perf_counter()
        try:
            if request.source_is_path:
                document = HTML(str(request.source), base_url=str(request.base_url))
            else:
                document = HTML(string=request.source, base_url=str(request.base_url))
            document.write_pdf(str(request.output))
        except Exception as exc:
            raise RendererError(f"{self.id}: render failed: {type(exc).__name__}: {exc}") from exc

        elapsed_ms = (time.perf_counter() - started) * 1000.0
        pages = self._page_count(request.output)
        return ArtifactSet(
            primary=request.output,
            metrics=RenderMetrics(elapsed_ms=elapsed_ms, pages=pages),
        )

    def inspect(self, artifacts: ArtifactSet) -> Mapping[str, Any]:
        """Read measurable facts back off the artifact."""
        return {
            "renderer": self.probe().to_json(),
            "primary": str(artifacts.primary),
            "exists": artifacts.primary.is_file(),
            "bytes": artifacts.primary.stat().st_size if artifacts.primary.is_file() else 0,
            "pages": self._page_count(artifacts.primary),
            "fonts": self._fonts(artifacts.primary),
            "metrics": artifacts.metrics.to_json(),
        }

    # -- internals --------------------------------------------------------

    def _capabilities(self) -> dict[str, str]:
        """Probe the installed engine.

        Levels reflect what this adapter has actually verified. Anything not
        verified is reported as `partial` rather than `native`: claiming more
        than was tested is how a capability manifest becomes fiction.
        """
        options = _option_names()
        version = _weasyprint_version()
        if version == "absent":
            return {feature: "unsupported" for feature in FEATURES}

        capabilities: dict[str, str] = {
            # CSS Paged Media is WeasyPrint's core competence and Folio's
            # document path depends on it today.
            "paged_media": "native",
            "page_counters": "native",
            "running_elements": "native",
            "cross_references": "native",
            "bookmarks": "native",
            "columns": "native",
            # Footnotes and page floats exist in the engine, but Folio has no
            # fixture that exercises them yet, so the honest level is partial.
            "footnotes": "partial",
            "page_floats": "partial",
            "bibliography": "emulated",
            "math": "emulated",
            "cjk_line_break": "partial",
            "rtl": "partial",
            "vertical_writing": "unsupported",
            "forms": "partial",
            # WeasyPrint lays out CSS; it does not distribute leftover page space
            # according to a stretch factor, so an elastic gap is applied at its
            # preferred value and the difference is reported rather than hidden.
            "elastic_spacing": "unsupported",
            # Page geometry is readable from the PDF afterwards, but the renderer
            # does not emit the layout decisions it made.
            "layout_diagnostics": "emulated",
        }

        # Tagged output is only claimed when the option is actually present.
        if "pdf_tags" in options or "pdf_variant" in options:
            capabilities["tagged_pdf"] = "native"
            capabilities["pdf_ua_1"] = "native" if "pdf_variant" in options else "partial"
            capabilities["pdf_a"] = "native" if "pdf_variant" in options else "partial"
        else:
            capabilities["tagged_pdf"] = "unsupported"
            capabilities["pdf_ua_1"] = "unsupported"
            capabilities["pdf_a"] = "unsupported"

        return capabilities

    @staticmethod
    def _page_count(pdf: Path) -> int | None:
        try:
            from pypdf import PdfReader

            return len(PdfReader(str(pdf)).pages)
        except Exception:
            return None

    @staticmethod
    def _fonts(pdf: Path) -> list[str]:
        if not pdf.is_file():
            return []
        # The full environment is inherited: a bare env dict loses PATH and the
        # tool silently reports no fonts rather than failing.
        import os

        env = dict(os.environ)
        env.setdefault("XDG_CACHE_HOME", tempfile.gettempdir())
        try:
            result = subprocess.run(
                ["pdffonts", str(pdf)], capture_output=True, text=True,
                check=False, timeout=60, env=env,
            )
        except (OSError, subprocess.SubprocessError):
            return []
        names = set()
        for line in (result.stdout or "").splitlines()[2:]:
            if line.strip():
                names.add(line.split()[0].split("+")[-1])
        return sorted(names)


def available() -> bool:
    """Whether this renderer can run in the current interpreter."""
    return _weasyprint_version() != "absent"


def conformance() -> dict[str, Any]:
    """Report the capability manifest with the evidence behind it.

    Run this when upgrading the engine: the manifest is what a migration PR is
    reviewed against.
    """
    renderer = WeasyPrintRenderer()
    info = renderer.probe()
    return {
        "renderer": info.to_json(),
        "python": sys.version.split()[0],
        "evidence": [
            {"feature": e.feature, "level": e.level, "method": e.method}
            for e in renderer.capability_evidence()
        ],
    }
