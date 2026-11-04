"""The stage belongs to the host, and only the geometry moves with it.

A drawing's type tiers are units on its stage, so the same drawing delivered in a
narrow column loses its smallest text to arithmetic. The fix is not a bigger
plate (that scales the type and the empty margin together) and not a payload
width (the author would be changing the drawing's units to fit a column). The
host names the stage; the family scales its chrome into it and leaves the type
alone, so the type-to-stage ratio rises as the stage falls.

These tests pin the five invariants the mechanism exists to guarantee:

    S1  only the host decides the stage; a payload cannot declare one
    S2  geometry scales with the stage, the type scale does not
    S3  a label is never split mid-word to make it fit
    S4  the same fixture and band always choose the same stage
    S5  the default stage is the identity composition: `scaled(1.0)` returns
        the same geometry, so it never moves for a reason of its own. A rule
        that holds on every stage (the connector-label reach) does move it,
        and that move is approved in the visual baseline rather than excused
        by a branch.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from drawing.canvas_contract import CANVAS_WIDTH, GRAPH_CANVAS, canvas_issues  # noqa: E402
from drawing.compiler import DEFAULT_COMPILER_REGISTRY  # noqa: E402
from drawing.output.viewport import PAGE_PREVIEW_MARGIN, _framing_margin  # noqa: E402
from drawing.stage import (  # noqa: E402
    DEFAULT_STAGE,
    MIN_STAGE_WIDTH,
    STAGE_AWARE,
    StageSpec,
    require_aware,
    use,
)
from drawing.typography.fit import _wrap  # noqa: E402
from drawing.validation.models import DrawingCompilationError  # noqa: E402

FIXTURES = ROOT / "references" / "fixtures" / "web" / "attention" / "figures"


def architecture_payload() -> dict:
    return {
        "schema_version": "3.0",
        "kind": "architecture",
        "title": "Two tiers",
        "layout": "horizontal-layers",
        "layers": [{"id": "L0", "label": "Client"}, {"id": "L1", "label": "Service"}],
        "nodes": [
            {"id": "a", "kind": "external", "label": "Reader", "layer": "L0"},
            {"id": "b", "kind": "service", "label": "Renderer", "layer": "L1"},
        ],
        "edges": [{"source": "a", "target": "b", "kind": "primary"}],
    }


def compile_at(stage: StageSpec, payload: dict | None = None):
    return DEFAULT_COMPILER_REGISTRY.compile_payload(
        payload or architecture_payload(), "page-preview", "folio", "full", "practitioner", stage=stage)


class HostOwnsTheStageTests(unittest.TestCase):
    """S1: a stage is an input to the compile, never a field in the drawing."""

    def test_a_payload_that_declares_a_width_is_refused(self) -> None:
        issues = canvas_issues({"width": 1200}, kind="architecture", band=GRAPH_CANVAS)
        self.assertEqual(1, len(issues))
        self.assertIn("declared by the host", issues[0])
        with self.assertRaises(DrawingCompilationError) as caught:
            DEFAULT_COMPILER_REGISTRY.compile_payload(
                {**architecture_payload(), "width": 1200})
        self.assertIn("CP002", str(caught.exception))

    def test_a_payload_without_a_width_takes_the_hosts(self) -> None:
        self.assertEqual([], canvas_issues({}, kind="architecture", band=GRAPH_CANVAS, stage=528))
        result = compile_at(StageSpec(528))
        self.assertEqual(528, result.scene.width)

    def test_a_family_that_cannot_scale_refuses_a_stage(self) -> None:
        self.assertIn("architecture", STAGE_AWARE)
        self.assertNotIn("flowchart", STAGE_AWARE)
        require_aware("architecture", StageSpec(528))
        require_aware("flowchart", DEFAULT_STAGE)
        with self.assertRaises(ValueError):
            require_aware("flowchart", StageSpec(528))

    def test_the_refusal_reaches_the_caller_as_a_diagnostic(self) -> None:
        with self.assertRaises(DrawingCompilationError) as caught:
            DEFAULT_COMPILER_REGISTRY.compile_payload(
                {"kind": "flowchart", "nodes": [], "edges": []}, stage=StageSpec(528))
        self.assertEqual("CP004", caught.exception.diagnostics[0].code)
        self.assertIn("stage-aware kinds", str(caught.exception))

    def test_the_canvas_floor_follows_the_stage(self) -> None:
        # The height band is layout math measured in stage units, so a stage
        # narrowed for a host band scales its floor with it. Holding the
        # 960-unit floor would leave a canvas the composition no longer fills.
        self.assertEqual(GRAPH_CANVAS.minimum, GRAPH_CANVAS.minimum_at(CANVAS_WIDTH))
        self.assertEqual([], canvas_issues(
            {"height": 200}, kind="architecture", band=GRAPH_CANVAS, stage=336))
        self.assertEqual(1, len(canvas_issues(
            {"height": 200}, kind="architecture", band=GRAPH_CANVAS, stage=CANVAS_WIDTH)))

    def test_a_stage_is_a_grid_width_inside_the_supported_range(self) -> None:
        with self.assertRaises(ValueError):
            StageSpec(350)
        with self.assertRaises(ValueError):
            StageSpec(MIN_STAGE_WIDTH - 8)
        with self.assertRaises(ValueError):
            StageSpec(CANVAS_WIDTH + 4)


class GeometryScalesTypeDoesNotTests(unittest.TestCase):
    """S2: chrome is in stage units; the type scale is not."""

    def test_nodes_shrink_and_the_type_does_not(self) -> None:
        wide = compile_at(DEFAULT_STAGE)
        small = compile_at(StageSpec(528))

        wide_sizes = {run.size for node in wide.scene.nodes for run in node.text_runs}
        small_sizes = {run.size for node in small.scene.nodes for run in node.text_runs}
        self.assertEqual(wide_sizes, small_sizes)
        self.assertGreater(max(node.box.w for node in wide.scene.nodes),
                           max(node.box.w for node in small.scene.nodes))

    def test_the_type_to_stage_ratio_rises_as_the_stage_falls(self) -> None:
        ratios = []
        for width in (CANVAS_WIDTH, 660, 528):
            scene = compile_at(StageSpec(width)).scene
            tiers = [run.size for node in scene.nodes for run in node.text_runs]
            ratios.append(min(tiers) / scene.width)
        self.assertEqual(sorted(ratios), ratios)
        self.assertLess(ratios[0], ratios[-1])

    def test_the_framing_margin_stays_a_margin(self) -> None:
        # Held at 24 units, the frame would take six percent of a 400-unit stage.
        self.assertEqual(PAGE_PREVIEW_MARGIN, _framing_margin())
        with use(StageSpec(528)):
            self.assertEqual(13, _framing_margin())
        with use(StageSpec(MIN_STAGE_WIDTH)):
            self.assertEqual(8, _framing_margin())


class LabelFitTests(unittest.TestCase):
    """S3: a label that does not fit is reported, never cut in half."""

    def test_a_single_word_is_not_split_on_a_composed_stage(self) -> None:
        with use(StageSpec(528)):
            self.assertEqual(("Positional",), _wrap("Positional", 10, 12))

    def test_the_default_stage_keeps_the_legacy_split(self) -> None:
        # The artifact path has always split here; changing it would move every
        # published 960-unit baseline for a reason that belongs to the web host.
        self.assertEqual(("Posit", "ional"), _wrap("Positional", 10, 12))


class DefaultStageTests(unittest.TestCase):
    """S5: the authored stage composes through the identity geometry.

    'Nothing moves' is the wrong claim: a rule that applies to every stage --
    the distance a connector label may keep from its own line -- moves the
    authored plate too. What this class holds is that the *stage mechanism*
    adds nothing: no scaled constant, no alternate branch.
    """

    def test_an_explicit_default_stage_is_the_default(self) -> None:
        import web_figures

        fixture = FIXTURES / "transformer.json"
        implicit = web_figures.render_figure(fixture, "transformer", page_theme=None)
        explicit = web_figures.render_figure(
            fixture, "transformer", page_theme=None, stage=DEFAULT_STAGE)

        self.assertEqual(implicit.svg, explicit.svg)
        self.assertEqual(CANVAS_WIDTH, implicit.stage[0])
        self.assertIsNone(implicit.band)
        self.assertIsNone(implicit.manifest_entry()["band"])

    def test_the_default_frame_is_the_ink_plus_its_margin(self) -> None:
        import web_figures

        figure = web_figures.render_figure(
            FIXTURES / "transformer.json", "transformer", page_theme=None)
        ink, view = figure.ink_box, figure.view_box

        if ink[0] - PAGE_PREVIEW_MARGIN >= 0:
            self.assertEqual(PAGE_PREVIEW_MARGIN, ink[0] - view[0])
        if ink[1] - PAGE_PREVIEW_MARGIN >= 0:
            self.assertEqual(PAGE_PREVIEW_MARGIN, ink[1] - view[1])


class BandCompositionTests(unittest.TestCase):
    """S4: the same fixture and band choose the same stage, twice running."""

    def test_composing_for_a_band_is_deterministic(self) -> None:
        import web_figures

        fixture = FIXTURES / "transformer.json"
        first = web_figures.render_figure(fixture, "transformer", page_theme=None, band=660)
        second = web_figures.render_figure(fixture, "transformer", page_theme=None, band=660)

        self.assertEqual(first.stage, second.stage)
        self.assertEqual(first.view_box, second.view_box)
        self.assertEqual(first.svg_sha, second.svg_sha)

    def test_a_composed_figure_meets_the_type_floor_and_the_shape_band(self) -> None:
        import web_figures

        figure = web_figures.render_figure(
            FIXTURES / "transformer.json", "transformer", page_theme=None, band=660)
        aspect = figure.view_box[3] / figure.view_box[2]
        low, high = web_figures.C.FIGURE["rendered_aspect"]

        self.assertGreaterEqual(figure.min_font_px, web_figures.C.FIGURE_FIT["delivered_target_px"])
        self.assertTrue(low <= aspect <= high, aspect)
        self.assertEqual(660.0, figure.band)


class BoundaryTypeTests(unittest.TestCase):
    """A boundary is geometry both passes see, and type is placed around it."""

    @staticmethod
    def _boundary_fixture() -> dict:
        return {
            "schema_version": "3.0",
            "kind": "architecture",
            "title": "Render pipeline",
            "layout": "horizontal-layers",
            "layers": [
                {"id": "edge", "label": "Edge", "row_policy": "pipeline"},
                {"id": "core", "label": "Core", "row_policy": "pipeline"},
                {"id": "state", "label": "State", "row_policy": "centered"},
            ],
            "groups": [
                {
                    "id": "pipeline",
                    "label": "Render Pipeline",
                    "kind": "boundary",
                    "layer": "core",
                    "members": ["gateway", "farm"],
                    "layout_policy": "pipeline",
                },
            ],
            "nodes": [
                {"id": "editor", "kind": "external", "label": "Editor", "layer": "edge"},
                {"id": "gateway", "kind": "service", "label": "Gateway", "layer": "core", "group": "pipeline"},
                {"id": "farm", "kind": "service", "label": "Farm", "layer": "core", "group": "pipeline"},
                {"id": "store", "kind": "store", "label": "Store", "layer": "state"},
            ],
            "edges": [
                {"source": "editor", "target": "gateway", "kind": "secondary", "label": "submit"},
                {"source": "gateway", "target": "farm", "kind": "primary"},
                {"source": "farm", "target": "store", "kind": "primary", "label": "persist"},
            ],
        }

    def test_the_drawn_frame_is_the_one_the_layout_used(self) -> None:
        from drawing.grammar.architecture import DEFAULT_ARCHITECTURE_GRAMMAR
        from drawing.layout.regions import region_frames

        stage = StageSpec(528)
        result = compile_at(stage, self._boundary_fixture())
        grammar = DEFAULT_ARCHITECTURE_GRAMMAR.scaled(stage.scale)
        frames = {
            region.id: box
            for region, box in region_frames(result.plan, result.layout.boxes, grammar)
        }
        drawn = {region.id: region.box for region in result.scene.regions if region.box is not None}

        self.assertEqual(set(frames), set(drawn))
        for name, box in frames.items():
            self.assertEqual((box.x, box.y, box.w, box.h),
                             (drawn[name].x, drawn[name].y, drawn[name].w, drawn[name].h))

    def test_no_label_straddles_a_boundary_and_none_runs_along_its_edge(self) -> None:
        result = compile_at(StageSpec(528), self._boundary_fixture())
        frames = [region.box for region in result.scene.regions if region.box is not None]

        for edge in result.scene.edges:
            for box in frames:
                for y in (edge.points[0][1], edge.points[-1][1]):
                    self.assertNotIn(y, (box.y, box.y + box.h))
                label = edge.label_box
                if label is None:
                    continue
                inside = (label.x >= box.x + 4 and label.y >= box.y + 4
                          and label.x + label.w <= box.x + box.w - 4
                          and label.y + label.h <= box.y + box.h - 4)
                outside = (label.x + label.w + 4 <= box.x or box.x + box.w + 4 <= label.x
                           or label.y + label.h + 4 <= box.y or box.y + box.h + 4 <= label.y)
                self.assertTrue(inside or outside, (edge.id, label, box))

    def test_a_printed_connector_label_stays_beside_its_own_line(self) -> None:
        from drawing.connectors.labels import LABEL_REACH, _distance_to_route

        result = compile_at(StageSpec(528), self._boundary_fixture())
        printed = [edge for edge in result.scene.edges if edge.label_box]
        self.assertTrue(printed)
        for edge in printed:
            self.assertLessEqual(_distance_to_route(edge.label_box, list(edge.points)), LABEL_REACH)

    def test_the_default_stage_places_labels_by_the_same_rule(self) -> None:
        # The reach cap used to be a composed-stage rule, which let an authored
        # plate print a word far from its line while a narrow plate dropped the
        # same word. One rule now; the default stage is stable because
        # `scaled(1.0)` is the identity, not because it is exempt.
        from drawing.connectors.labels import LABEL_REACH, _distance_to_route

        result = compile_at(DEFAULT_STAGE, self._boundary_fixture())
        printed = [edge for edge in result.scene.edges if edge.label_box]
        self.assertTrue(printed)
        for edge in printed:
            self.assertLessEqual(
                _distance_to_route(edge.label_box, list(edge.points)), LABEL_REACH)


if __name__ == "__main__":
    unittest.main()
