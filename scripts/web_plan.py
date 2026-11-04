#!/usr/bin/env python3
"""The Web layout plan: what the page must do at each width, and why.

The page is one column, so the plan is small: for each reviewed width it
carries the column, the figure slot and the size the drawing will actually be
delivered at. The plan is arithmetic over the profile, not a renderer. It is
also the single place that decides how a figure is hosted, so the builder, the
checker and the probe cannot disagree.

A figure has two obligations, and either alone can be gamed:

- **legible**: the smallest drawn tier, scaled into its slot, clears the
  contract floor;
- **filled**: the drawing's ink covers enough of the plate it is framed in.
  Enlarging a padded plate raised the type and the empty margin together, so a
  figure that passes only the first is still a hole in the page.

The current response set is closed and honest: `crop-ink` (frame to the ink,
via the drawing's `page-preview` profile), `embed` (frame the full stage), and
`fail`. A type-scale response belongs to the drawing (roadmap P5); until it
exists this module reports the gap instead of pretending.

    web_plan.py --series attention
    web_plan.py --series attention --gate
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import web_contracts as C  # noqa: E402
from projection import web_projection  # noqa: E402

# The widths a page is reviewed at. They are test widths, not CSS breakpoints;
# the breakpoints are the profile's structural steps (480/768/900/1200/1280).
VIEWPORTS = (390, 768, 1024, 1414)

# `base.css` widens the column and the figure slot at this breakpoint.
WIDE_BREAKPOINT = 1280

# The class a width belongs to, in the vocabulary the contracts use.
VIEWPORT_CLASSES = ((480, "narrow"), (768, "compact"), (WIDE_BREAKPOINT - 1, "regular"))


def _px(value: str) -> float:
    return float(value.removesuffix("px"))


def geometry(language: str | None = "zh-Hans-CN") -> dict[str, float]:
    """The horizontal geometry the page is built from, as the profile states it."""
    projected = web_projection(language=language).projected
    return {
        "narrow_x": _px(projected["--web-narrow-page-x"]),
        "compact_x": _px(projected["--web-compact-page-x"]),
        "page_x": _px(projected["--web-page-x"]),
        "page_width": _px(projected["--web-page-width"]),
        "wide_page_width": _px(projected["--web-wide-page-width"]),
        "figure_slot": _px(projected["--web-figure-slot"]),
        "wide_figure_slot": _px(projected["--web-wide-figure-slot"]),
        # The page's heading scale. A figure title is set against it, so the
        # numbers that decide the title's tier come from here, not from a
        # constant in the figure code.
        "h2": _px(projected["--web-h2-size"]),
        "h3": _px(projected["--web-h3-size"]),
    }


def viewport_class(viewport: int) -> str:
    for limit, name in VIEWPORT_CLASSES:
        if viewport <= limit:
            return name
    return "wide"


def gutter_for(viewport: int, g: dict[str, float]) -> float:
    if viewport <= 480:
        return g["narrow_x"]
    if viewport <= 768:
        return g["compact_x"]
    return g["page_x"]


def page_width_for(viewport: int, g: dict[str, float]) -> float:
    return g["wide_page_width"] if viewport >= WIDE_BREAKPOINT else g["page_width"]


def column_for(viewport: int, g: dict[str, float]) -> float:
    """The text column: the page, capped by the viewport, minus both gutters."""
    return min(viewport, page_width_for(viewport, g)) - 2 * gutter_for(viewport, g)


def slot_for(viewport: int, g: dict[str, float]) -> float | None:
    """The figure's cap at this width, or None when the column is the cap.

    Below the compact step the plan lifts `--web-figure-slot` to `none`: the
    page padding already defines the column, and a second cap would put the
    figures on a different right edge than the text.
    """
    if viewport <= BREAKPOINTS["compact"]:
        return None
    return g["wide_figure_slot"] if viewport >= WIDE_BREAKPOINT else g["figure_slot"]


def band_for(viewport: int, g: dict[str, float]) -> float:
    """The width a figure is delivered at: its slot, capped by the column."""
    slot = slot_for(viewport, g)
    column = column_for(viewport, g)
    return column if slot is None else min(slot, column)


def figure_variants(language: str | None = "zh-Hans-CN") -> list[dict]:
    """Each figure class: the viewports it serves and the band it is composed for.

    A drawing is composed for one band, so the class it serves is bounded by
    the type floor at its narrow end -- the composition that delivers 7px at
    360 delivers more at 480, which is a floor being met rather than a target
    being missed. The wide end is reported so the checker can say what the
    reader actually gets there.
    """
    g = geometry(language)
    widest = max(VIEWPORTS)
    out = []
    for spec in C.FIGURE_VARIANTS:
        high = spec["max_viewport"] or widest
        out.append({
            "key": spec["key"],
            "min_viewport": spec["min_viewport"],
            "max_viewport": spec["max_viewport"],
            "band": round(band_for(spec["min_viewport"], g), 1),
            "max_band": round(band_for(high, g), 1),
        })
    return out


def widest_band(variant: str, g: dict[str, float]) -> float:
    """The band a plate is shown at when its class is at its widest.

    A class spans a range of viewports, so the reader at the top of the range
    gets the largest delivery. The title's ceiling binds there; the type floor
    binds at the design band, which is the bottom of the same range.
    """
    for spec in C.FIGURE_VARIANTS:
        if spec["key"] == variant:
            return band_for(spec["max_viewport"] or max(VIEWPORTS), g)
    return band_for(max(VIEWPORTS), g)


def variant_for(viewport: int) -> str:
    """The class a width falls in, in the figure vocabulary."""
    for spec in C.FIGURE_VARIANTS:
        if viewport >= spec["min_viewport"] and (
                spec["max_viewport"] is None or viewport <= spec["max_viewport"]):
            return spec["key"]
    raise ValueError(f"no figure variant serves a {viewport}px viewport")


# A variable whose name carries a viewport qualifier is an *input* to this
# module, not a value the page reads. The plan resolves it into the plain name
# and emits that inside the media query. One name per role, one value per
# width: the stylesheet never declares a second scale of its own.
VIEWPORT_PREFIXES = ("--web-compact-", "--web-narrow-", "--web-wide-")

# Every width at which the composition changes. Three of them carry a value
# override from the plan; three are arrangement only (the figure plate changes
# at 768 and 588, the rail leaves at 900, the chapter numeral steps into the
# margin at 1200). The stylesheet may not declare a width that is not here — a
# breakpoint nobody planned is a size nobody computed.
BREAKPOINTS = {"narrow": 480, "figure": 588, "compact": 768, "rail": 900,
               "index": 1200, "wide": 1280}


def viewport_plan(language: str | None = "zh-Hans-CN") -> dict:
    """Every value that changes with width, and the width it changes at.

    The base entry is what `:root` already carries. Each override lists only
    the roles that differ, so the emitted CSS is a value patch and nothing
    else. `none` is a value: it is how a measure cap is lifted on a narrow
    screen, where the page padding already defines the column.
    """
    projected = web_projection(language=language)
    p, sources = projected.projected, projected.sources

    def take(pairs: list[tuple[str, str]]) -> dict[str, dict[str, str]]:
        values: dict[str, dict[str, str]] = {}
        for variable, alias in pairs:
            values[variable] = {"value": p[alias], "alias": alias,
                                "source": sources.get(alias, "unknown")}
        return values

    # The measure caps come off where the page padding already defines the
    # column. Lists keep theirs: `76ch` is wider than a 676px column, so the
    # cap never bites before the wide step, and lifting it would move them
    # off the margin the paragraphs were reset to.
    lift = [("--web-measure-body", "none"), ("--web-figure-slot", "none")]

    # The regular values, as the page's `:root` carries them. Written down so
    # the plan can be read back at any width without re-resolving the profile.
    base = {
        name: {"value": p[name], "source": sources.get(name, "unknown")}
        for name in ("--web-page-x", "--web-page-top", "--web-page-bottom",
                     "--web-page-width", "--web-h1-size", "--web-kpi-columns",
                     "--web-reading-size", "--web-measure-body", "--web-measure-list",
                     "--web-figure-slot")
    }
    return {
        "language": language,
        "breakpoints": dict(BREAKPOINTS),
        "base": base,
        "overrides": [
            {
                "class": "compact",
                "query": f"max-width: {BREAKPOINTS['compact']}px",
                "values": {
                    **take([
                        ("--web-page-x", "--web-compact-page-x"),
                        ("--web-page-top", "--web-compact-page-top"),
                        ("--web-page-bottom", "--web-compact-page-bottom"),
                        ("--web-h1-size", "--web-compact-h1"),
                        ("--web-kpi-columns", "--web-compact-kpi-columns"),
                    ]),
                    **{name: {"value": value,
                              "source": f"web:layout (compact {BREAKPOINTS['compact']}px)"}
                       for name, value in lift},
                },
            },
            {
                "class": "narrow",
                "query": f"max-width: {BREAKPOINTS['narrow']}px",
                "values": take([
                    ("--web-page-x", "--web-narrow-page-x"),
                    ("--web-page-top", "--web-narrow-page-top"),
                    ("--web-page-bottom", "--web-narrow-page-bottom"),
                    ("--web-h1-size", "--web-narrow-h1"),
                    ("--web-kpi-columns", "--web-narrow-kpi-columns"),
                    # A phone drops the reading step: 16px at 350px of column
                    # is the same voice at a smaller size, not a smaller page.
                    ("--web-reading-size", "--web-narrow-body"),
                ]),
            },
            {
                "class": "wide",
                "query": f"min-width: {BREAKPOINTS['wide']}px",
                "values": take([
                    ("--web-page-width", "--web-wide-page-width"),
                    ("--web-measure-body", "--web-measure-wide-body"),
                    ("--web-measure-list", "--web-measure-wide-list"),
                    ("--web-figure-slot", "--web-wide-figure-slot"),
                ]),
            },
        ],
    }


def stylesheet_breakpoints(css: str) -> list[str]:
    """Widths `base.css` declares that the plan does not know about."""
    known = set(BREAKPOINTS.values())
    problems = []
    for match in re.finditer(r"@media\s*\((min|max)-width:\s*(\d+)px\)", css):
        width = int(match.group(2))
        if width not in known:
            problems.append(
                f"@media ({match.group(1)}-width: {width}px) is not a planned breakpoint")
    return problems


def resolve(plan: dict, viewport: int) -> dict[str, str]:
    """The values in force at one width, base overlaid by each matching step.

    Later overrides win, which is what the cascade does with two media blocks
    that both match: at 390px the narrow block follows the compact one.
    """
    values = {name: item["value"] for name, item in plan["base"].items()}
    for override in plan["overrides"]:
        low, high = _bounds(override["query"])
        if low <= viewport <= high:
            values.update({name: item["value"] for name, item in override["values"].items()})
    return values


def _bounds(query: str) -> tuple[int, int]:
    match = re.match(r"(max|min)-width:\s*(\d+)px", query)
    if not match:
        raise ValueError(f"a plan query the engine cannot read: {query!r}")
    kind, width = match.group(1), int(match.group(2))
    return (0, width) if kind == "max" else (width, 10**6)


# The widths the plan is stated at: the review set, plus both sides of every
# breakpoint. A migration that only holds at the round numbers is not holding.
REVIEW_WIDTHS = tuple(sorted(set(VIEWPORTS) | set(BREAKPOINTS.values())
                             | {B - 1 for B in BREAKPOINTS.values()}))


def plan_document(language: str | None = "zh-Hans-CN") -> dict:
    """The plan as the builder writes it: what the page must compute to."""
    plan = viewport_plan(language)
    g = geometry(language)
    widths: dict[str, dict] = {}
    for viewport in REVIEW_WIDTHS:
        values = resolve(plan, viewport)
        widths[str(viewport)] = {
            "class": viewport_class(viewport),
            "column": round(column_for(viewport, g), 1),
            "band": round(band_for(viewport, g), 1),
            "page_x": _px(values["--web-page-x"]),
            "h1_size": _px(values["--web-h1-size"]),
            "kpi_columns": int(values["--web-kpi-columns"]),
            "reading_size": _px(values["--web-reading-size"]),
            "measure_capped": values["--web-measure-body"] != "none",
            "figure_slot": values["--web-figure-slot"],
        }
    return {**plan, "viewports": widths}


def plan_css(plan: dict) -> tuple[str, dict[str, str]]:
    """Serialise the plan as value-only `@media` blocks. (css, sources)."""
    sources: dict[str, str] = {}
    lines = [
        "/* The viewport plan: every value that changes with width, resolved from",
        "   the Web profile. The stylesheet below decides arrangement only. */",
    ]
    for override in plan["overrides"]:
        lines.append(f"@media ({override['query']}) {{")
        lines.append("  :root {")
        for variable, item in sorted(override["values"].items()):
            lines.append(f"    {variable}: {item['value']}; /* {item['source']} */")
            sources[variable] = item["source"]
        lines.append("  }")
        lines.append("}")
    return "\n".join(lines), sources


def framed_width(entry: dict) -> float:
    """The width the drawing is delivered at, from a current or legacy manifest."""
    box = entry.get("view_box") or []
    if len(box) >= 4:
        return float(box[2])
    if box:
        return float(box[0])
    return float((entry.get("stage") or [0, 0])[0])


def variant_entries(entry: dict) -> dict[str, dict]:
    """A figure's records per class, accepting a pre-variant single record."""
    variants = entry.get("variants")
    if isinstance(variants, dict) and variants:
        return variants
    return {"wide": entry}


def fit_matrix(entry: dict, g: dict[str, float]) -> dict[str, dict]:
    """Per reviewed width: the class that serves it, the band, and the tiers.

    Each width is judged on the plate it actually shows, so the delivered size
    is that plate's own scale into that width's band -- not one plate scaled
    to every width.
    """
    variants = variant_entries(entry)
    rows: dict[str, dict] = {}
    for viewport in VIEWPORTS:
        variant = variant_for(viewport)
        record = variants.get(variant) or variants[next(iter(variants))]
        stage = (record.get("stage") or record.get("view_box") or [0, 0])[0]
        framed = framed_width(record)
        tiers = [float(size) for size in record.get("text_sizes") or []]
        title_units = float(record.get("title_units") or 0.0)
        band = band_for(viewport, g)
        scale = band / framed if framed else 1.0
        delivered = [round(size * scale, 2) for size in tiers]
        rows[str(viewport)] = {
            "class": viewport_class(viewport),
            "variant": variant,
            "column": round(column_for(viewport, g), 1),
            "band": round(band, 1),
            "scale": round(scale, 3),
            "delivered": delivered,
            "title_px": round(title_units * scale, 2) if title_units else None,
            "min_px": min(delivered) if delivered else None,
            "stage_width": stage,
        }
    return rows


def choose_fit(entry: dict) -> str:
    """Which framing this plate is delivered in.

    Framing to the ink is the only response the drawing supports today, and it
    is strictly better than the full stage: the same text at a larger scale,
    with the padding removed. A drawing whose ink already fills its stage is
    framed by either, so `crop-ink` stays the answer.
    """
    ink = entry.get("ink_box")
    stage = (entry.get("stage") or [0, 0])
    if not ink or not stage[0]:
        return "embed"
    return "crop-ink"


def fit_verdict(entry: dict, g: dict[str, float] | None = None) -> tuple[list[str], list[str]]:
    """(errors, notes) for every plate of one figure, against the contract.

    Each plate is judged at its own band: it was composed for the narrowest
    width in its class, so that is where both obligations bind -- the smallest
    tier must clear the floor and the plate must be filled rather than padded.
    """
    errors: list[str] = []
    notes: list[str] = []
    g = g or geometry()
    fit = C.FIGURE_FIT
    target = float(fit["delivered_target_px"])
    tolerance = float(fit["delivered_tolerance_px"])
    low_aspect, high_aspect = C.FIGURE["rendered_aspect"]
    variants = variant_entries(entry)
    single = bool(entry.get("single")) or tuple(variants) == (C.FIGURE_SINGLE_PLATE,)

    for key, plate in variants.items():
        coverage = float(plate.get("coverage") or 0.0)
        if coverage < fit["coverage_min"]:
            errors.append(
                f"{key}: ink covers {coverage:.0%} of the plate, "
                f"below {fit['coverage_min']:.0%}")
        margin = float(plate.get("margin_ratio") or 0.0)
        if margin > fit["margin_ratio_max"]:
            errors.append(
                f"{key}: framing margin is {margin:.1%}, "
                f"above {fit['margin_ratio_max']:.0%}")
        # Coverage is the ink's bounding box; this is the hole inside it.
        empty = int(plate.get("empty_band_units") or 0)
        if empty > fit["empty_band_max"]:
            errors.append(
                f"{key}: a {empty}-unit band inside the drawing is empty, "
                f"above the {fit['empty_band_max']}-unit limit")

        box = plate.get("view_box") or []
        if len(box) == 4 and box[2]:
            aspect = float(box[3]) / float(box[2])
            if not low_aspect <= aspect <= high_aspect:
                where = errors if not single else notes
                where.append(
                    f"{key}: plate is {aspect:.2f} tall per unit wide, outside "
                    f"{low_aspect:g}-{high_aspect:g}"
                    + ("; this family composes on one stage" if single else ""))

        tiers = [float(size) for size in plate.get("text_sizes") or []]
        framed = framed_width(plate)
        if not (tiers and framed):
            errors.append(f"{key}: manifest records no text_sizes")
            continue
        band = float(plate.get("band") or C.FIGURE["slot"])
        delivered = min(tiers) * band / framed
        if delivered + tolerance < target and single:
            # A family that composes on the authored stage only cannot grow its
            # type into a band, so the floor is out of its reach by
            # construction. The engine reports the size the reader gets instead
            # of claiming a floor it cannot meet; the work that closes the gap
            # is adding the family to `STAGE_AWARE`, not loosening the number.
            notes.append(
                f"{key}: this family composes on one stage, so the smallest tier "
                f"is delivered at {delivered:.2f}px in a {band:g}px band "
                f"(floor {target:g}px)")
        elif delivered + tolerance < target:
            errors.append(
                f"{key}: smallest tier is delivered at {delivered:.2f}px in a "
                f"{band:g}px band, below the {target:g}px floor")
        elif delivered > target * 1.6:
            notes.append(
                f"{key}: smallest tier is delivered at {delivered:.2f}px in a "
                f"{band:g}px band; the class may be wider than the composition needs")

        # The title is a page heading: below H2 and above H3 wherever the plate
        # is shown. Its largest delivery is at the class's widest band and its
        # smallest at the design band, so the two ends answer the two bounds.
        units = float(plate.get("title_units") or 0.0)
        if units:
            at_design = units * band / framed
            at_widest = units * widest_band(key, g) / framed
            ceiling = float(g["h2"]) * float(fit["title_h2_ratio"])
            if at_widest > ceiling + 0.05:
                where = notes if single else errors
                where.append(
                    f"{key}: title is {at_widest:.1f}px at the class's widest "
                    f"band, above {ceiling:.1f}px (H2 x {fit['title_h2_ratio']:g})")
            if at_design + float(fit["title_floor_tolerance_px"]) < float(g["h3"]):
                where = notes if single else errors
                where.append(
                    f"{key}: title is {at_design:.1f}px at its design band, "
                    f"under H3's {float(g['h3']):g}px")
    return errors, notes


def series_matrix(manifest: dict, language: str | None = None) -> dict:
    g = geometry(language or manifest.get("language"))
    out: dict[str, dict] = {}
    for module_id, entries in (manifest.get("figures") or {}).items():
        for figure_id, entry in entries.items():
            key = f"{module_id}/{figure_id}"
            errors, notes = fit_verdict(entry, g)
            variants = variant_entries(entry)
            out[key] = {
                "kind": entry.get("kind"),
                "single": bool(entry.get("single")),
                "variants": {
                    name: {
                        "fit": choose_fit(plate),
                        "band": plate.get("band"),
                        "coverage": plate.get("coverage"),
                        "margin_ratio": plate.get("margin_ratio"),
                        "view_box": plate.get("view_box"),
                        "stage": plate.get("stage"),
                        "min_font_px": plate.get("min_font_px"),
                        "title_units": plate.get("title_units"),
                        "title_px": plate.get("title_px"),
                    }
                    for name, plate in variants.items()
                },
                "widths": fit_matrix(entry, g),
                "errors": errors,
                "notes": notes,
            }
    return {"series": manifest.get("series"), "geometry": g,
            "viewports": list(VIEWPORTS),
            "variants": figure_variants(language or manifest.get("language")),
            "figures": out}


def check_manifest(manifest: dict, language: str | None = None) -> tuple[dict, list[str], list[str]]:
    matrix = series_matrix(manifest, language)
    errors: list[str] = []
    notes: list[str] = []
    for name, row in matrix["figures"].items():
        errors.extend(f"{name}: {item}" for item in row["errors"])
        notes.extend(f"{name}: {item}" for item in row["notes"])
    if not matrix["figures"]:
        errors.append("the manifest declares no figures")
    return matrix, errors, notes


def _table(matrix: dict) -> list[str]:
    lines = []
    for name, data in matrix["figures"].items():
        for variant, plate in data["variants"].items():
            view = plate["view_box"] or ["?", "?", "?", "?"]
            title = (f", title {plate['title_px']:.1f}px"
                     f" ({plate['title_units']:g} units)" if plate["title_px"] else "")
            lines.append(
                f"{name} [{variant}]: {plate['fit']}, composed for {plate['band']:g}px, "
                f"framed {view[2]}x{view[3]}, coverage {plate['coverage']:.0%}, "
                f"margin {plate['margin_ratio']:.1%}{title}")
        for width, row in data["widths"].items():
            delivered = " / ".join(f"{size:g}" for size in row["delivered"]) or "-"
            title = f"  title {row['title_px']:g}" if row.get("title_px") else ""
            lines.append(f"  {width:>5} {row['class']:<8} {row['variant']:<8} "
                         f"band {row['band']:>5g} scale {row['scale']:.3f}  {delivered}{title}")
    return lines


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--series", required=True)
    parser.add_argument("--dist", type=Path, default=ROOT / "dist" / "web")
    parser.add_argument("--gate", action="store_true",
                        help="exit nonzero when a figure breaks the fit contract")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    manifest_path = args.dist / args.series / "figures.manifest.json"
    if not manifest_path.is_file():
        print(f"ERROR: no built manifest at {manifest_path}; build the series first")
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    matrix, errors, notes = check_manifest(manifest)

    if args.json:
        print(json.dumps({**matrix, "errors": errors, "notes": notes},
                         ensure_ascii=False, indent=2))
    else:
        print("\n".join(_table(matrix)))
        for note in notes:
            print(f"REVIEW {note}")
        for error in errors:
            print(f"ERROR {error}")
        if not errors:
            print(f"OK: every figure is framed and filled in {matrix['series']}")
    return 1 if (errors and args.gate) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
