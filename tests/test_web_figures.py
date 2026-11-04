"""A page figure composed for the width it will actually be shown at.

The standalone artifact keeps the 960-unit stage. A figure inside a reading page
is composed for the band the page delivers it in, so the two obligations of a
plate are both measured where the reader sees it: the smallest tier arrives at
7px or more, and the ink fills the plate instead of sitting in a margin.
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import web_contracts as C  # noqa: E402
import web_figures  # noqa: E402

from drawing.stage import StageSpec  # noqa: E402
from drawing.stage import use as stage_use
from drawing.typography.measure import measure_text  # noqa: E402
from drawing.validation.models import DrawingCompilationError  # noqa: E402

FIXTURES = ROOT / "references" / "fixtures" / "web" / "attention" / "figures"
BAND = float(C.FIGURE["slot"])


class ComposedFigureTests(unittest.TestCase):
    """Every figure in the series, composed for the regular reading band."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.figures = {
            path.stem: web_figures.render_figure(path, path.stem, page_theme=None, band=BAND)
            for path in sorted(FIXTURES.glob("*.json"))
        }

    def test_the_series_is_what_this_suite_thinks_it_is(self) -> None:
        self.assertGreaterEqual(len(self.figures), 4)

    def test_the_smallest_tier_is_delivered_at_the_floor(self) -> None:
        target = C.FIGURE_FIT["delivered_target_px"]
        for name, figure in self.figures.items():
            with self.subTest(figure=name):
                self.assertGreaterEqual(figure.min_font_px, target)

    def test_the_plate_is_filled_and_not_padded(self) -> None:
        for name, figure in self.figures.items():
            with self.subTest(figure=name):
                self.assertGreaterEqual(figure.coverage, C.FIGURE_FIT["coverage_min"])
                self.assertLessEqual(figure.margin_ratio, C.FIGURE_FIT["margin_ratio_max"])

    def test_the_plate_shape_stays_inside_the_page_band(self) -> None:
        # A plate is delivered at its host band, so its height in pixels is the
        # host's to choose and its *shape* is the drawing's. The band therefore
        # holds an aspect, which scaling preserves.
        low, high = C.FIGURE["rendered_aspect"]
        for name, figure in self.figures.items():
            with self.subTest(figure=name):
                aspect = figure.view_box[3] / figure.view_box[2]
                self.assertTrue(low <= aspect <= high, f"{name}: {aspect:.2f}")

    def test_the_svg_frames_exactly_what_the_manifest_records(self) -> None:
        for name, figure in self.figures.items():
            with self.subTest(figure=name):
                box = re.search(r'viewBox="([^"]+)"', figure.svg)
                self.assertIsNotNone(box)
                self.assertEqual(
                    " ".join(str(value) for value in figure.view_box), box.group(1))

    def test_the_manifest_names_the_band_and_the_stage_it_earned(self) -> None:
        for name, figure in self.figures.items():
            with self.subTest(figure=name):
                entry = figure.manifest_entry()
                self.assertEqual(BAND, entry["band"])
                self.assertEqual(figure.stage[0], entry["stage"][0])
                # One stage unit is at most one delivered pixel.
                self.assertLessEqual(figure.view_box[2], BAND)


READING = ROOT / "references" / "fixtures" / "web" / "reading-demo" / "figures"
NARROW = 335.0


class NarrowBandTests(unittest.TestCase):
    """The narrowest band the page serves, on a seven-node drawing with a legend."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.figure = web_figures.render_figure(
            READING / "release-gate.json", "release-gate", band=NARROW)

    def test_the_narrow_band_composes_instead_of_falling_back(self) -> None:
        # A single plate is delivered at the authored stage, which puts a
        # seven-node drawing at 2.8px in a phone column. The composition has to
        # happen, so the plate is no wider than the band it was composed for.
        self.assertLessEqual(self.figure.view_box[2], NARROW + 4)

    def test_the_floor_admits_a_miss_smaller_than_a_stage_step(self) -> None:
        target = C.FIGURE_FIT["delivered_target_px"]
        self.assertGreaterEqual(
            self.figure.min_font_px,
            target - C.FIGURE_FIT["delivered_tolerance_px"])

    def test_the_canvas_follows_the_stage_instead_of_the_authored_height(self) -> None:
        # 540 is the height the drawing was authored at. At a 336-unit stage the
        # same rows need less, and a canvas that keeps the authored height turns
        # the surplus into a hole above a bottom-pinned legend.
        width, height = self.figure.stage
        self.assertLess(height, 540)

    def test_nothing_is_left_between_the_last_row_and_the_legend(self) -> None:
        payload = json.loads((READING / "release-gate.json").read_text())
        width, height = (int(value) for value in self.figure.stage)
        stage = StageSpec(width)
        with stage_use(stage):
            result = web_figures._compile({**payload, "height": height},
                                          "folio", "page-preview", stage)
        self.assertIsNotNone(result.scene.legend)
        self.assertLessEqual(web_figures._unused_height(result.scene),
                             web_figures.CANVAS_SLACK + 8)


class ConnectorLabelTests(unittest.TestCase):
    """A connector label is part of the meaning, so the row has to hold it.

    ``dispatch`` was silently dropped from every plate: the row gap was 48 units
    and the word's box is 48, so the placer, which keeps four units of air from
    each node, had nowhere to put it. The layout now reserves the word's width
    before it places anything, at every band the page serves.
    """

    # The bands the plan requires this plate to name its transition in. The
    # narrowest band is not among them: at 335 the row has no room to spare,
    # and the plate keeps its shape and drops the word rather than splitting.
    REQUIRED = (960.0, 660.0, 541.0, 433.0)

    def test_the_labelled_transition_is_drawn_at_every_required_band(self) -> None:
        for band in self.REQUIRED:
            with self.subTest(band=band):
                figure = web_figures.render_figure(
                    READING / "release-gate.json", "release-gate", band=band)
                self.assertIn(">DISPATCH<", figure.svg)
                self.assertEqual([], [d for d in figure.diagnostics if d["code"] == "VQ108"])

    def test_a_label_never_reshapes_the_row(self) -> None:
        # The layout splits a reading group when its boxes cannot sit side by
        # side, not when one of its words cannot. A plate that grew a row to fit
        # a label would trade a word for the composition.
        payload = json.loads((READING / "release-gate.json").read_text())
        bare = {**payload, "edges": [
            {key: value for key, value in edge.items() if key != "label"}
            for edge in payload["edges"]]}
        stage = StageSpec(int(web_figures.render_figure(
            READING / "release-gate.json", "release-gate", band=NARROW).stage[0]))
        with stage_use(stage):
            labelled = web_figures._compile(payload, "folio", "page-preview", stage)
            unlabelled = web_figures._compile(bare, "folio", "page-preview", stage)

        def rows(scene):
            return sorted({node.box.y for node in scene.nodes})

        self.assertEqual(rows(unlabelled.scene), rows(labelled.scene))
        self.assertEqual(unlabelled.scene.height, labelled.scene.height)

    def test_the_reservation_is_the_word_plus_the_placer_clearance(self) -> None:
        from drawing.connectors.labels import NODE_CLEARANCE, label_width
        from drawing.layout.constraints import row_gap_requirements
        from drawing.layout.models import LayoutConstraintSet
        from drawing.models import VisualEdgePlan

        constraints = LayoutConstraintSet(
            axis="left-right", node_sizes={}, layer_order=(), node_order={},
            preferred_adjacency=(), spine=(), sidecars={}, port_preferences={},
            node_gap=48, layer_gap=48, edge_node_gap=24, edge_edge_gap=16)
        edge = VisualEdgePlan("e", "a", "b", "primary", "normal", label="dispatch")
        gaps = row_gap_requirements(["a", "b"], [edge], constraints, minimum_gap=16)
        self.assertEqual([label_width("DISPATCH") + 2 * NODE_CLEARANCE], gaps)
        # An unlabelled pair keeps the quieter gap it was measured with.
        self.assertEqual([16], row_gap_requirements(
            ["a", "b"], [], constraints, minimum_gap=16))


class EmptyBandTests(unittest.TestCase):
    """Coverage reads the ink's bounding box; this reads the hole inside it."""

    def test_every_plate_the_page_serves_is_free_of_internal_holes(self) -> None:
        limit = C.FIGURE_FIT["empty_band_max"]
        variants = web_plan_variants()
        for name in ("release-gate", "build-lifecycle", "sign-off"):
            for key, band in variants.items():
                with self.subTest(figure=name, variant=key):
                    figure = web_figures.render_figure(
                        READING / f"{name}.json", name, band=band)
                    self.assertLessEqual(figure.empty_band_units, limit)

    def test_a_hole_between_two_rows_is_measured(self) -> None:
        # Two rows a gap apart, with nothing between them: the band is the gap.
        from drawing.bounds import largest_empty_band
        from drawing.scene import ResolvedScene, SceneBox, SceneNode, SceneStyle, SceneText

        style = SceneStyle(stroke="#000000", stroke_width=1)
        nodes = (
            SceneNode("a", SceneBox(0, 0, 100, 60), style, ()),
            SceneNode("b", SceneBox(0, 180, 100, 60), style, ()),
        )
        scene = ResolvedScene(
            width=200, height=260, background="#fff",
            title=SceneText("", 0, 0, "#000", 12, "Inter"),
            regions=(), edges=(), nodes=nodes)
        units, height = largest_empty_band(scene)
        self.assertEqual(120, units)
        self.assertEqual(240, height)

    def test_the_historical_hole_fails_the_fit_verdict(self) -> None:
        import web_plan

        figure = web_figures.render_figure(
            READING / "release-gate.json", "release-gate", band=BAND)
        plate = replace(figure, empty_band_units=108).manifest_entry()
        errors, _notes = web_plan.fit_verdict({"variants": {"wide": plate}})
        self.assertTrue(any("108-unit band" in item for item in errors), errors)


def web_plan_variants() -> dict[str, float]:
    import web_plan

    return {item["key"]: item["band"] for item in web_plan.figure_variants()}


class LegendWrappingTests(unittest.TestCase):
    """A legend wider than the plate stacks instead of running off it."""

    def test_a_narrow_plate_wraps_the_legend_inside_its_box(self) -> None:
        payload = json.loads((READING / "release-gate.json").read_text())
        stage = StageSpec(336)
        with stage_use(stage):
            result = web_figures._compile(payload, "folio", "page-preview", stage)
        legend = result.scene.legend
        self.assertIsNotNone(legend)
        self.assertEqual(2, len({item.label.y for item in legend.items}))
        for item in legend.items:
            right = item.label.x + measure_text(
                item.label.text, item.label.size, item.label.family)
            self.assertLessEqual(right, legend.box.x + legend.box.w)
        self.assertGreaterEqual(legend.box.y, max(
            node.box.y + node.box.h for node in result.scene.nodes))


class TitleHierarchyTests(unittest.TestCase):
    """A figure title is a page heading: below H2, above H3, wherever it shows.

    The plate is shown across a whole class, so the title's largest delivery
    is at the class's widest band. That is where the ceiling binds, and it is
    the tier the composer chooses; the design band is where the floor is read.
    """

    @classmethod
    def setUpClass(cls) -> None:
        import web_plan
        cls.plan = web_plan
        variants = web_plan.figure_variants()
        cls.bands = {item["key"]: item["band"] for item in variants}
        cls.max_bands = {item["key"]: item["max_band"] for item in variants}
        page = web_plan.geometry()
        cls.heading = (page["h3"], page["h2"] * C.FIGURE_FIT["title_h2_ratio"])
        cls.narrow = web_figures.render_figure(
            READING / "release-gate.json", "release-gate",
            band=cls.bands["narrow"],
            band_range=(cls.bands["narrow"], cls.max_bands["narrow"]),
            title_px=cls.heading)

    def test_the_authored_title_is_kept_without_a_host_hierarchy(self) -> None:
        # The standalone artifact and the catalog still set 24 units; only a
        # host that declares a page scale asks for another size.
        figure = web_figures.render_figure(
            READING / "release-gate.json", "release-gate", band=BAND)
        self.assertEqual(24.0, figure.title_units)

    def test_the_title_drops_a_tier_when_24_units_would_pass_h2(self) -> None:
        # 24 units in the narrow class delivers 24.0px at the design band but
        # 31.5px at 480px of viewport, which is above the page's H2 share.
        self.assertLess(self.narrow.title_units, 24.0)
        self.assertGreaterEqual(self.narrow.title_units, C.FIGURE_FIT["title_tier_floor"])

    def test_the_title_stays_between_h3_and_the_h2_share_across_the_class(self) -> None:
        framed = self.narrow.view_box[2]
        at_design = self.narrow.title_units * self.bands["narrow"] / framed
        at_widest = self.narrow.title_units * self.max_bands["narrow"] / framed
        floor, ceiling = self.heading
        self.assertGreaterEqual(at_design, floor - C.FIGURE_FIT["title_floor_tolerance_px"])
        self.assertLessEqual(at_widest, ceiling)
        self.assertEqual(round(at_design, 2), round(self.narrow.title_px, 2))

    def test_the_manifest_records_the_units_and_the_delivery(self) -> None:
        entry = self.narrow.manifest_entry()
        self.assertEqual(self.narrow.title_units, entry["title_units"])
        self.assertEqual(round(self.narrow.title_px, 2), entry["title_px"])


class PlateProvenanceTests(unittest.TestCase):
    """A figure whose bands disagree about the reading axis says so per plate."""

    def test_axes_that_agree_stay_one_figure_fact(self) -> None:
        figure = web_figures.render_figure(READING / "release-gate.json", "release-gate",
                                           stage=StageSpec(960))
        entry = web_figures.figure_manifest_entry({"narrow": figure, "wide": figure})
        self.assertIn("axis", entry)
        self.assertNotIn("axis", entry["variants"]["narrow"])

    def test_axes_that_disagree_are_recorded_per_plate(self) -> None:
        figure = web_figures.render_figure(READING / "release-gate.json", "release-gate",
                                           stage=StageSpec(960))
        plates = {
            "narrow": replace(figure, axis="top-down"),
            "wide": replace(figure, axis="left-right"),
        }
        entry = web_figures.figure_manifest_entry(plates)
        self.assertEqual("top-down", entry["variants"]["narrow"]["axis"])
        self.assertEqual("left-right", entry["variants"]["wide"]["axis"])
        # The figure-level axis names the wide plate: it is the one the page
        # carries as its fallback, so `data-axis` and the manifest agree.
        self.assertEqual("left-right", entry["axis"])


class NoStageFitsTests(unittest.TestCase):
    """A band the drawing cannot compose for fails, rather than shipping 3.5px."""

    def test_an_impossible_shape_band_is_refused_with_a_diagnostic(self) -> None:
        # A host that asked for a plate three times taller than it is wide cannot
        # be satisfied by folding the drawing: the composition changes the shape
        # only within what the payload's own arrangement allows. `max_steps`
        # keeps the negative case quick -- a build that asks for the impossible
        # should not scan the walk.
        payload = {
            "schema_version": "3.0", "kind": "architecture", "title": "Two tiers",
            "layout": "horizontal-layers", "height": 500,
            "layers": [{"id": "L0", "label": "Client"}, {"id": "L1", "label": "Service"}],
            "nodes": [
                {"id": "a", "kind": "external", "label": "Reader", "layer": "L0"},
                {"id": "b", "kind": "service", "label": "Renderer", "layer": "L1"},
            ],
            "edges": [{"source": "a", "target": "b", "kind": "primary"}],
        }
        with self.assertRaises(DrawingCompilationError) as caught:
            web_figures.compose_for_band(payload, "folio", "page-preview", BAND,
                                         aspect_band=(2.5, 3.0), max_steps=2)
        diagnostic = caught.exception.diagnostics[0]
        self.assertEqual("CP005", diagnostic.code)
        self.assertIn("needs a different arrangement", diagnostic.hint or "")
        self.assertIn("aspect", diagnostic.message)


if __name__ == "__main__":
    unittest.main()
