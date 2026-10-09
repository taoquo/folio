# Known defects in the current document rendering path

Recorded during the M0 baseline freeze. These are **defects, not accepted
behaviour**: listing them here keeps the baseline from silently declaring
today's bugs as correct. A baseline update must never be the way one of these
disappears.

Each entry states what is wrong, the evidence, and what "fixed" would mean.

---

## D1 · English body font is not bundled and resolves from the host

**Status**: RESOLVED — Source Serif 4 (variable, OFL-1.1) is now bundled at
`assets/fonts/SourceSerif4Variable-Roman.ttf` and declared as the first entry of
every English `--serif` stack via `@font-face`. Charter remains in the stack as
an accepted fallback for decorative glyphs past Source Serif's 919-codepoint
coverage, but no longer carries body text, so English pagination no longer
depends on the host.

**Severity when open**: high — it changed pagination, so it could break the
strict page contracts without any source change.

**Evidence of the original problem**:

- `fc-match Charter` → `/System/Library/Fonts/Supplemental/Charter.ttc` (macOS only)
- `find . -iname "*harter*"` outside `.git` → nothing
- `.github/workflows/drawing-dsl.yml` installed no font packages at all
- `--verify` asserted English documents must embed Charter, so the same gate
  that should protect this depended on it

**Verification after the fix**: all seven English targets embed `Source-Serif-4`
subsets; page counts are unchanged at every target including the exact
contracts (resume 2, one-pager 1).

---

## D2 · Committed Chinese demo PDFs embed fonts no stack declares

**Status**: RESOLVED by decision — the four host fallbacks (`Times-Roman`,
`STSongti-SC-Regular`, `Hiragino-Mincho-ProN-Light`, plus the diagram-only
`Verdana`) are now named in `acceptable_substitutes`. Fresh renders of all
seven Chinese targets embed only LXGW WenKai and JetBrains Mono; the
substitutions survive in the older committed demo PDFs, which predate the font
work.

**Severity when open**: medium — the documents rendered correctly, but the font
was unchosen rather than chosen.

**Evidence**:

```
pdffonts assets/demos/demo-agent-ops-longdoc-zh.pdf
  GAAAAA+Times-Roman            ...
  HAAAAA+STSongti-SC-Regular    ...
```

The font gate reports these as sanctioned rather than silent, and still fails on
a font that is not claimed.

**Claimed in**: `references/manifests/fonts-v1.yaml` (`acceptable_substitutes`,
`known_unsanctioned`).

---

## D3 · PDF byte digests are not a determinism signal

**Severity**: medium — it invalidates a check that looks obvious.

**What happens**: rendering the same template in separate processes produces
different PDF bytes every time, while the rendered page is identical. The
difference is inside the zlib-compressed content streams.

**Evidence**:

```
5 fresh renders of long-doc-en:
  4af2ef045af6c945  af8ecbcda4679ca4  30e05a9ed7506397
  669b06c440692929  7be34af426e945d8      (5 distinct digests)

Same two PDFs compared on content:
  raster page sha256  identical
  extracted text sha256  identical
```

**Consequence**: any gate based on PDF bytes would report a regression on every
rebuild and would be ignored within a week. Determinism is therefore judged on
page count, fonts, rasterised page, and extracted text.

**Fixed means**: nothing to fix in the renderer. The defect was in the checking
approach; both `determinism.py` and `document_baseline.py` now compare content
and treat byte digests as forensics only.

---

## D4 · Local interpreter is outside the declared CI matrix

**Status**: RESOLVED — the CI matrix now covers 3.10, 3.12, and 3.14, and the
release gate runs on 3.14. The interpreter producing local baselines is
therefore exercised by CI.

**Severity when open**: low at the time, high had it diverged further.

**Evidence**: `references/manifests/render-env-v1.json` records
`python.version = 3.14.5` against `ci_matrix = ["3.10", "3.12", "3.14"]`.

---

## D5 · The stabilizer is not part of the build path

**Severity**: medium — two sources of truth for page fitting.

**What happens**: `stabilize.py` tightens section gap, line height, font size,
and page margins to satisfy a page budget, writing to `dist/stabilized/`.
`build.py` never reads `references/stabilizer_profiles.json` and never runs the
solver. The two are documented as "intentionally independent".

**Evidence**: `references/stabilizer_profiles.json` has exactly one consumer,
`scripts/stabilize.py`. `build.py` does not reference it.

**Consequence**: a document can pass `--verify` while the stabilizer would have
changed it, and the solver's decisions never appear in a build artifact.

**Fixed means**: solver decisions become observable `LayoutDecision` records on
the build path, or the stabilizer's output becomes an explicit build input.

**Scheduled**: M5-6 in `docs/plans/document-engine-implementation-plan.md`.

---

## D6 · Diagram templates resolve a Latin-only stack on every host

**Severity**: low — noticed while testing the font gate, not a correctness
problem for the diagrams themselves.

**What happens**: diagram templates declare `Charter, Georgia, Palatino, serif`
and embed `Verdana` on this machine. The diagrams are embedded into documents,
so the substitution propagates into any document that hosts them.

**Evidence**: `pdffonts` on any `diagram-*.pdf` reports `Verdana` / `Verdana-Bold`.

**Fixed means**: same resolution as D1 — a declared, present font, or an
explicitly widened and recorded stack. Currently sanctioned for diagrams only,
so the gate does not fail on it.

**Tracked in**: `references/manifests/fonts-v1.yaml`
(`fallback_chains.diagram_serif`, `acceptable_substitutes.diagram`).
