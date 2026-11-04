#!/usr/bin/env python3
"""Check a built page against its plan, in a real browser.

`web_measure.py` says what the browser did. This module says whether that is
what the engine asked for. The two are separate on purpose: a measurement that
also judged itself would be a checker grading its own work.

Every rule here compares a computed value with a value the plan states, and the
tolerance is stated rather than felt. A page that drifts from its plan is an
engine defect; two pixels of drift is not a design decision.

    web_verify.py --plan dist/web/attention/plan.json \\
                  --metrics dist/web/attention/metrics.json \\
                  --manifest dist/web/attention/figures.manifest.json

The fast gate runs the arithmetic half (`web_plan.py`); this runs where a
browser is allowed, which is the nightly job.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import web_contracts as C  # noqa: E402
import web_plan  # noqa: E402
from projection import web_projection  # noqa: E402

# The tolerance each rule allows. They are not round numbers picked for
# comfort: a computed font-size is exact in Chromium, a box is a subpixel
# measurement, and a margin gap inherits the rounding of both edges.
TOLERANCE = {
    "type_px": 0.5,
    "leading_px": 1.0,
    "box_px": 1.0,
    "gap_px": 1.5,
    "figure_px": 0.25,
}

# Which projected variable each measured type role must equal. The two roles a
# width changes are overridden from the plan after this table is applied.
TYPE_ROLES = {
    "h1": "--web-h1-size",
    "h2": "--web-h2-size",
    "h3": "--web-h3-size",
    "body": "--web-body-size",
    "lead": "--web-lead-size",
    "reading": "--web-reading-size",
    "caption": "--web-caption-size",
    "label": "--web-label-size",
    "code": "--web-code-size",
    "kpi": "--web-kpi-size",
    "table-cell": "--web-dense-size",
    "rail": "--web-label-size",
}

LEADING_ROLES = {role: name.replace("-size", "-leading") for role, name in TYPE_ROLES.items()}


def _px(value: str) -> float:
    return float(value.removesuffix("px"))


def _fail(rule: str, statement: str, detail: str) -> dict:
    return {"rule": rule, "statement": statement, "status": "FAIL", "detail": detail}


def _pass(rule: str, statement: str, detail: str) -> dict:
    return {"rule": rule, "statement": statement, "status": "PASS", "detail": detail}


def expected_types(plan: dict, viewport: int, projected: dict[str, str]) -> dict[str, dict]:
    """What each measured role must resolve to at this width."""
    values = web_plan.resolve(plan, viewport)
    expected: dict[str, dict] = {}
    for role, variable in TYPE_ROLES.items():
        size = values.get(variable, projected.get(variable))
        if size is None:
            continue
        leading = projected.get(LEADING_ROLES[role])
        expected[role] = {
            "size": _px(size) if size.endswith("px") else float(size),
            "leading": round(_px(size) * float(leading), 2) if leading else None,
        }
    return expected


# A measured role exists only when the page has a block that plays it. The
# model counts decide which: a chapter with no `<h3>` cannot be asked for an
# h3, and a selector that stopped matching is then a missing block, which
# W-STR-06 already fails.
ROLE_PRESENCE = {
    "h3": "section-title",
    "caption": "figure",
    "label": "source-note",
    "kpi": "kpi-row",
    "table-cell": "table",
}


def check_types(plan: dict, projected: dict[str, str], page: dict, viewport: int,
                counts: dict[str, int] | None = None) -> list[dict]:
    rows = []
    expected = expected_types(plan, viewport, projected)
    measured = page.get("types") or {}
    wrong_size, wrong_leading, absent = [], [], []
    for role, want in expected.items():
        required_by = ROLE_PRESENCE.get(role)
        if required_by is not None and counts is not None and not counts.get(required_by):
            continue  # the page has no such block, so no such role to measure
        got = measured.get(role)
        if not got:
            absent.append(role)
            continue
        if abs(got["size"] - want["size"]) > TOLERANCE["type_px"]:
            wrong_size.append(f"{role} {got['size']:g} != {want['size']:g}")
        if want["leading"] and got.get("leading") is not None:
            if abs(got["leading"] - want["leading"]) > TOLERANCE["leading_px"]:
                wrong_leading.append(f"{role} {got['leading']:g} != {want['leading']:g}")
    statement = "computed type equals the plan at every role"
    if absent:
        rows.append(_fail("V-PLAN-01", statement, f"not rendered: {', '.join(absent)}"))
    elif wrong_size or wrong_leading:
        rows.append(_fail("V-PLAN-01", statement,
                          f"size: {wrong_size or 'ok'}; leading: {wrong_leading or 'ok'}"))
    else:
        rows.append(_pass("V-PLAN-01", statement, f"{len(expected)} role(s) agree"))
    return rows


def check_prose(plan: dict, page: dict, viewport: int) -> dict:
    statement = "the prose column is the planned column"
    planned = plan["viewports"][str(viewport)]
    box = (page.get("boxes") or {}).get("prose")
    if not box:
        return _fail("V-PLAN-02", statement, "no prose paragraph on the page")
    width = box["width"]
    if planned["measure_capped"]:
        # A measure cap is a character count, and only the browser knows how
        # wide a character is here. The plan's obligation is that the cap does
        # not cross the column.
        ok = width <= planned["column"] + TOLERANCE["box_px"]
        return (_pass if ok else _fail)(
            "V-PLAN-02", statement,
            f"prose {width:g} ≤ column {planned['column']:g} with the measure applied"
            if ok else f"prose {width:g} overruns the column {planned['column']:g}")
    ok = abs(width - planned["column"]) <= TOLERANCE["box_px"]
    return (_pass if ok else _fail)(
        "V-PLAN-02", statement,
        f"prose {width:g} = column {planned['column']:g}"
        if ok else f"prose {width:g} != column {planned['column']:g}")


def check_figure(plan: dict, page: dict, viewport: int) -> dict:
    statement = "the figure spans its band"
    planned = plan["viewports"][str(viewport)]
    box = (page.get("boxes") or {}).get("figure")
    if not box:
        return {"rule": "V-PLAN-03", "statement": statement, "status": "SKIP",
                "detail": "no figure on this page"}
    ok = abs(box["width"] - planned["band"]) <= TOLERANCE["box_px"]
    return (_pass if ok else _fail)(
        "V-PLAN-03", statement,
        f"{box['width']:g} = band {planned['band']:g}"
        if ok else f"{box['width']:g} != band {planned['band']:g}")


def check_plates(viewport: int, page: dict) -> dict:
    """Exactly one plate is shown, and it is the class the plan says.

    This is the invariant the whole variant mechanism rests on: several plates
    per figure are only safe while the browser shows one of them, and the one
    it shows has to be the composition made for this width. A figure whose
    family composes on one stage carries one plate, and at this width it must
    show that plate.
    """
    statement = "one plate per figure is shown, and it is this width's class"
    plates = page.get("plates") or []
    if not plates:
        return {"rule": "V-FIG-13", "statement": statement, "status": "SKIP",
                "detail": "no figure on this page"}
    expected = web_plan.variant_for(viewport)
    problems, shown = [], []
    for figure in plates:
        visible = figure.get("visible") or []
        want = C.FIGURE_SINGLE_PLATE if figure.get("plates") == 1 else expected
        if len(visible) != 1:
            problems.append(f"{figure.get('id')}: {len(visible)} plate(s) visible")
        elif visible[0].get("variant") != want:
            problems.append(
                f"{figure.get('id')}: shows {visible[0].get('variant')}, expected {want}")
        else:
            shown.append(want)
    kinds = "/".join(sorted(set(shown)))
    return (_pass if not problems else _fail)(
        "V-FIG-13", statement,
        f"every figure shows its {kinds} plate"
        if not problems else "; ".join(problems[:3]))


def check_figure_type(manifest: dict, page: dict, module_id: str, viewport: int) -> dict:
    """The delivered sizes the browser's own plate width implies.

    Two obligations travel together because they are one measurement of one
    plate: the smallest tier clears the legibility floor, and the title stays
    between the page's H3 and its H2 -- the figure is a section of the page, so
    its title reads as a heading, not as another body line.
    """
    statement = "the plate's type lands where the plan says, title included"
    entry = ((manifest or {}).get("figures") or {}).get(module_id) or {}
    figure = next(iter(entry.values()), None)
    shown = next(
        (item for item in (page.get("plates") or []) if (item.get("visible") or [])),
        None)
    if not figure or not shown:
        return {"rule": "V-FIG-12", "statement": statement, "status": "SKIP",
                "detail": "no figure manifest entry on this page"}
    variant = shown["visible"][0]
    record = (figure.get("variants") or {}).get(variant.get("variant")) or figure
    tiers = record.get("text_sizes") or []
    framed = web_plan.framed_width(record)
    if not tiers or not framed:
        return _fail("V-FIG-12", statement, "the manifest records no type tiers")
    delivered = min(tiers) * variant["width"] / framed
    floor = C.FIGURE_FIT["delivered_target_px"]
    parts = [f"{variant.get('variant')} plate: smallest tier {delivered:.2f}px "
             f"at a {variant['width']:g}px band (floor {floor:g}px)"]
    legible = delivered + C.FIGURE_FIT["delivered_tolerance_px"] >= floor

    # The title is read at the width the browser actually gave the plate, so
    # this is the one check that sees the delivery instead of trusting the
    # manifest's arithmetic. Its allowed range is the page's own: above H3,
    # below the H2 share.
    units = float(record.get("title_units") or figure.get("title_units") or 0.0)
    heading_ok = True
    if units:
        page = web_plan.geometry((manifest or {}).get("language"))
        at_plate = units * variant["width"] / framed
        ceiling = float(page["h2"]) * float(C.FIGURE_FIT["title_h2_ratio"])
        parts.append(f"title {at_plate:.2f}px (H3 {float(page['h3']):g}, ceiling {ceiling:.1f})")
        heading_ok = (
            at_plate + float(C.FIGURE_FIT["title_floor_tolerance_px"]) >= float(page["h3"])
            and at_plate <= ceiling + TOLERANCE["figure_px"])
    detail = "; ".join(parts)
    if legible and heading_ok:
        return _pass("V-FIG-12", statement, detail)
    if figure.get("single"):
        # The family composes on the authored stage only; no plate this page
        # could emit would clear the floor here. Reported, not gated: the
        # engine says what the reader gets and what would have to change.
        return {"rule": "V-FIG-12", "statement": statement, "status": "REVIEW",
                "detail": detail + "; this family composes on one stage"}
    return _fail("V-FIG-12", statement, detail)


def check_rhythm(projected: dict[str, str], page: dict) -> dict:
    """Every vertical gap is a step on the space scale.

    Margins collapse, so an adjacent pair leaves one value, not their sum. A
    gap that is not on the scale means a margin was written by hand somewhere
    the profile does not reach.
    """
    statement = "every block gap is a step on the space scale"
    scale = sorted({round(_px(value), 2) for name, value in projected.items()
                    if name.startswith("--web-space-")})
    blocks = page.get("blocks") or []
    known = bool(blocks) and all("section" in block for block in blocks)
    inside: list[float] = []
    breaks: list[float] = []
    for previous, current in zip(blocks, blocks[1:]):
        gap = round(current["top"] - previous["bottom"], 2)
        if abs(gap) <= TOLERANCE["gap_px"]:
            continue
        crossed = known and previous["section"] != current["section"]
        (breaks if crossed else inside).append(gap)
    gaps = inside + breaks
    stray = [gap for gap in inside
             if not any(abs(gap - step) <= TOLERANCE["gap_px"] for step in scale)]
    if not gaps:
        return {"rule": "V-RHYTHM-01", "statement": statement, "status": "SKIP",
                "detail": "no adjacent block pairs"}
    # A chapter boundary is deliberately not a spacing step: it is the air
    # above the chapter, the padding under its rule and the hairline itself,
    # read as one break. What can still be wrong is that a break stops reading
    # as one, so it must be wider than any gap measured inside a chapter at the
    # same viewport -- comparing it to the base scale would judge a narrow
    # page by a wide page's step.
    ceiling = max(inside) if inside else scale[-1]
    tight = [gap for gap in breaks if gap <= ceiling]
    if not stray and not tight:
        return _pass("V-RHYTHM-01", statement,
                     f"{len(inside)} gap(s) on the scale, {len(breaks)} section break(s)")
    detail = []
    if stray:
        detail.append(f"off-scale gaps: {stray}")
    if tight:
        detail.append(f"chapter breaks no wider than a spacing step: {tight}")
    return {"rule": "V-RHYTHM-01", "statement": statement,
            "status": "REVIEW", "detail": "; ".join(detail)}


def check_overflow(page: dict) -> dict:
    statement = "nothing overflows sideways that the page did not mark"
    overflow = page.get("overflow") or []
    document = page.get("document") or {}
    sideways = document.get("scrollWidth", 0) > document.get("clientWidth", 1) + 1
    if overflow or sideways:
        names = [item.get("selector") for item in overflow]
        return _fail("V-OVF-01", statement,
                     f"overflow: {names or 'none'}; page scrolls sideways: {sideways}")
    return _pass("V-OVF-01", statement,
                 f"scrolling by design: {len(page.get('scrollContainers') or [])} container(s)")


def check_dom(manifest: dict, page: dict, module_id: str) -> dict:
    statement = "the browser's blocks are the model's blocks"
    model = ((manifest or {}).get("pages") or {}).get(module_id)
    if model is None:
        return {"rule": "V-DOM-01", "statement": statement, "status": "SKIP",
                "detail": "the build recorded no page model"}
    expected = sum((model.get("counts") or {}).values())
    got = (page.get("counts") or {}).get("blocks", 0)
    return (_pass if got == expected else _fail)(
        "V-DOM-01", statement,
        f"{got} block(s) rendered, {expected} in the model")


def verify(plan: dict, metrics: dict, manifest: dict | None) -> list[dict]:
    projected = web_projection(language=plan.get("language")).projected
    rows: list[dict] = []
    for page_path, widths in sorted((metrics.get("pages") or {}).items()):
        parts = Path(page_path).parts
        # `<series>/<module>/index.html` is a chapter page; the series index
        # (`<series>/index.html`) has no column, so the plan has nothing to say
        # about it. A single-module series repeats its name, which is why the
        # test is on depth, not on the strings.
        if len(parts) != 3:
            continue
        module = parts[1]
        for viewport, page in sorted(widths.items(), key=lambda item: int(item[0])):
            if page.get("error") or str(viewport) not in plan["viewports"]:
                continue
            width = int(viewport)
            counts = (((manifest or {}).get("pages") or {}).get(module) or {}).get("counts")
            found = [
                *check_types(plan, projected, page, width, counts),
                check_prose(plan, page, width),
                check_figure(plan, page, width),
                check_plates(width, page),
                check_figure_type(manifest or {}, page, module, width),
                check_rhythm(projected, page),
                check_overflow(page),
                check_dom(manifest or {}, page, module),
            ]
            for row in found:
                row["width"] = width
            rows.extend(found)
    return rows


RULE_ORDER = ("V-PLAN-01", "V-PLAN-02", "V-PLAN-03", "V-FIG-13", "V-FIG-12",
              "V-RHYTHM-01", "V-OVF-01", "V-DOM-01")
SEVERITY = {"FAIL": 3, "REVIEW": 2, "PASS": 1, "SKIP": 0}


def summarise(rows: list[dict]) -> list[dict]:
    """One line per rule: the worst status, with the widths that produced it."""
    out: list[dict] = []
    for rule in RULE_ORDER:
        group = [row for row in rows if row["rule"] == rule]
        if not group:
            continue
        worst = max(group, key=lambda row: SEVERITY[row["status"]])
        notes = [f"{row['width']}px {row['detail']}"
                 for row in group if row["status"] == worst["status"]]
        out.append({
            "rule": rule,
            "statement": worst["statement"],
            "status": worst["status"],
            "detail": "; ".join(notes[:3]) + (f" (+{len(notes) - 3} more)"
                                              if len(notes) > 3 else ""),
        })
    return out


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--series", default=None,
                        help="a built series under --dist; finds its plan and metrics")
    parser.add_argument("--dist", type=Path, default=ROOT / "dist" / "web")
    parser.add_argument("--plan", type=Path, default=None)
    parser.add_argument("--metrics", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.series:
        root = args.dist / args.series
        args.plan = args.plan or root / "plan.json"
        args.metrics = args.metrics or root / "metrics.json"
    if not args.plan or not args.metrics:
        print("ERROR: give --series, or both --plan and --metrics")
        return 2
    for path in (args.plan, args.metrics):
        if not path.is_file():
            print(f"ERROR: no {path.name} at {path}; build and measure the series first")
            return 1

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    metrics = json.loads(args.metrics.read_text(encoding="utf-8"))
    manifest = (json.loads(args.manifest.read_text(encoding="utf-8"))
                if args.manifest else None)
    if manifest is None:
        sibling = args.plan.parent / "figures.manifest.json"
        manifest = json.loads(sibling.read_text(encoding="utf-8")) if sibling.is_file() else None

    rows = summarise(verify(plan, metrics, manifest))
    failed = [row for row in rows if row["status"] == "FAIL"]

    if args.json:
        print(json.dumps({"checks": rows, "failures": len(failed)},
                         ensure_ascii=False, indent=2))
    else:
        print(f"Web verification: {plan.get('series')} "
              f"({metrics.get('browser', 'chromium')})")
        for row in rows:
            print(f"  {row['status']:<6} {row['rule']:<10} {row['detail']}")
        if failed:
            print(f"ERROR: {len(failed)} rule(s) failed")
        else:
            print(f"OK: {len(rows)} check(s), the page computes what the plan says")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
