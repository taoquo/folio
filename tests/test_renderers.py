"""The renderer boundary, capability negotiation, manifests and rollback.

The point of these tests is that Folio can change what produces a document
without changing what a document is, and can always get back.
"""

import json
import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from renderers.base import (
    CapabilityRequirement,
    Downgrade,
    RendererError,
    RendererInfo,
    RenderRequest,
    negotiate,
)
from renderers.manifest import ArtifactManifest, build_manifest, sha256_value
from renderers.weasy import WeasyPrintRenderer, available


class CapabilityNegotiationTests(TestCase):
    def _info(self, **caps) -> RendererInfo:
        return RendererInfo(name="test", version="1.0", capabilities=dict(caps))

    def test_a_native_feature_is_satisfied(self) -> None:
        report = negotiate(self._info(footnotes="native"),
                           (CapabilityRequirement("footnotes", "hard", "notes"),))
        self.assertTrue(report.ok)
        self.assertIn("footnotes", report.satisfied)
        self.assertEqual((), report.downgrades)

    def test_an_unsupported_hard_feature_blocks_the_render(self) -> None:
        report = negotiate(self._info(footnotes="unsupported"),
                           (CapabilityRequirement("footnotes", "hard", "notes"),))
        self.assertFalse(report.ok)
        self.assertEqual(1, len(report.missing))

    def test_an_unsupported_soft_feature_does_not_block_but_is_recorded(self) -> None:
        report = negotiate(self._info(math="unsupported"),
                           (CapabilityRequirement("math", "soft", "equations"),))
        self.assertTrue(report.ok)
        self.assertTrue(report.downgrades)

    def test_partial_support_is_recorded_as_a_downgrade(self) -> None:
        # The failure mode this prevents: a feature silently becoming something
        # else while the build still reports success.
        report = negotiate(self._info(page_floats="partial"),
                           (CapabilityRequirement("page_floats", "hard", "figures"),))
        self.assertTrue(report.ok)
        self.assertEqual("page_floats", report.downgrades[0].feature)
        self.assertIn("partial", report.downgrades[0].resolved)

    def test_an_unknown_feature_is_unsupported_not_assumed(self) -> None:
        report = negotiate(self._info(), (CapabilityRequirement("teleport", "hard", "?"),))
        self.assertFalse(report.ok)

    def test_lenient_mode_records_the_miss_rather_than_hiding_it(self) -> None:
        report = negotiate(self._info(), (CapabilityRequirement("teleport", "hard", "?"),),
                           strict=False)
        self.assertTrue(report.ok)
        self.assertTrue(report.downgrades)

    def test_report_serialises(self) -> None:
        report = negotiate(self._info(math="emulated"),
                           (CapabilityRequirement("math", "soft", "equations"),))
        payload = report.to_json()
        json.dumps(payload)
        self.assertIn("downgrades", payload)


class WeasyPrintAdapterTests(TestCase):
    def setUp(self) -> None:
        if not available():
            self.skipTest("WeasyPrint is not installed")
        self.renderer = WeasyPrintRenderer()

    def test_probe_reports_an_engine_and_version(self) -> None:
        info = self.renderer.probe()
        self.assertEqual("weasy", info.name)
        self.assertNotEqual("absent", info.version)
        self.assertIn("pdf", info.outputs)

    def test_capabilities_cover_the_declared_vocabulary(self) -> None:
        from renderers.weasy import FEATURES

        capabilities = self.renderer.probe().capabilities
        for feature in FEATURES:
            with self.subTest(feature=feature):
                self.assertIn(feature, capabilities)

    def test_capability_levels_are_from_the_known_set(self) -> None:
        from renderers.base import CAPABILITY_LEVELS

        for feature, level in self.renderer.probe().capabilities.items():
            with self.subTest(feature=feature):
                self.assertIn(level, CAPABILITY_LEVELS)

    def test_every_capability_claim_carries_its_evidence(self) -> None:
        evidence = self.renderer.capability_evidence()
        self.assertEqual(len(self.renderer.probe().capabilities), len(evidence))
        for item in evidence:
            with self.subTest(feature=item.feature):
                self.assertTrue(item.method)

    def test_paged_media_is_claimed_native(self) -> None:
        # The whole document path depends on it; a lower level would mean the
        # adapter is reporting something other than what it does.
        self.assertEqual("native", self.renderer.probe().level("paged_media"))

    def test_rendering_a_template_produces_a_pdf(self) -> None:
        import tempfile

        source = ROOT / "assets" / "templates" / "one-pager.html"
        if not source.is_file():
            self.skipTest("template not present")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.pdf"
            request = RenderRequest(source=str(source), base_url=source.parent, output=out)
            artifacts = self.renderer.render(request)
            self.assertTrue(artifacts.primary.is_file())
            self.assertGreater(artifacts.metrics.pages or 0, 0)

    def test_a_missing_hard_capability_refuses_before_rendering(self) -> None:
        import tempfile

        source = ROOT / "assets" / "templates" / "one-pager.html"
        if not source.is_file():
            self.skipTest("template not present")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.pdf"
            request = RenderRequest(
                source=str(source),
                base_url=source.parent,
                output=out,
                requirements=(CapabilityRequirement("vertical_writing", "hard", "vertical text"),),
            )
            with self.assertRaises(RendererError):
                self.renderer.render(request)
            self.assertFalse(out.is_file(), "nothing should be written when refused")

    def test_inspection_reads_fonts_and_pages(self) -> None:
        import tempfile

        source = ROOT / "assets" / "templates" / "one-pager.html"
        if not source.is_file():
            self.skipTest("template not present")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.pdf"
            request = RenderRequest(source=str(source), base_url=source.parent, output=out)
            artifacts = self.renderer.render(request)
            inspection = self.renderer.inspect(artifacts)
            self.assertTrue(inspection["exists"])
            self.assertGreater(inspection["pages"], 0)
            self.assertTrue(inspection["fonts"])

    def test_conformance_report_includes_evidence(self) -> None:
        from renderers.weasy import conformance

        payload = conformance()
        json.dumps(payload)
        self.assertIn("renderer", payload)
        self.assertTrue(payload["evidence"])


class ManifestTests(TestCase):
    def _manifest(self, **overrides) -> ArtifactManifest:
        base = {
            "document_id": "doc",
            "renderer_name": "weasy",
            "renderer_version": "68.1",
            "primary": Path("/tmp/nonexistent.pdf"),
        }
        base.update(overrides)
        return ArtifactManifest(**base)

    def test_a_manifest_records_the_engine_and_artifact(self) -> None:
        payload = self._manifest(pages=2, fonts=("Charter",)).to_json()
        self.assertEqual("weasy", payload["renderer"]["name"])
        self.assertEqual(68.1, float(payload["renderer"]["version"]))
        self.assertEqual(2, payload["artifact"]["pages"])

    def test_a_downgrade_makes_the_manifest_degraded(self) -> None:
        manifest = self._manifest(downgrades=(Downgrade(
            feature="math", requested="equations", resolved="emulated support",
            reason="engine reports emulated").to_json(),))
        self.assertTrue(manifest.degraded)
        self.assertIn("downgrade", manifest.summary())

    def test_a_clean_render_is_not_degraded(self) -> None:
        self.assertFalse(self._manifest().degraded)

    def test_manifest_is_written_beside_the_artifact(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "doc.pdf"
            pdf.write_bytes(b"%PDF-1.4")
            manifest = self._manifest(primary=pdf)
            path = manifest.write()
            self.assertTrue(path.is_file())
            self.assertEqual("doc.pdf.manifest.json", path.name)

    def test_a_missing_artifact_has_a_null_digest_not_a_fake_one(self) -> None:
        payload = self._manifest(primary=Path("/tmp/definitely-not-here.pdf")).to_json()
        self.assertIsNone(payload["artifact"]["sha256"])

    def test_environment_fingerprint_is_recorded(self) -> None:
        payload = self._manifest().to_json()
        self.assertIn("python", payload["environment"])
        self.assertIn("platform", payload["environment"])

    def test_value_digest_is_stable(self) -> None:
        self.assertEqual(sha256_value({"a": 1, "b": 2}), sha256_value({"b": 2, "a": 1}))

    def test_build_manifest_from_a_real_render(self) -> None:
        if not available():
            self.skipTest("WeasyPrint is not installed")
        import tempfile

        source = ROOT / "assets" / "templates" / "one-pager.html"
        if not source.is_file():
            self.skipTest("template not present")
        renderer = WeasyPrintRenderer()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.pdf"
            request = RenderRequest(source=str(source), base_url=source.parent, output=out,
                                    requirements=(CapabilityRequirement("paged_media", "hard", "paged"),))
            report = renderer.validate_request(request)
            artifacts = renderer.render(request)
            manifest = build_manifest(
                document_id="one-pager",
                renderer_info=renderer.probe(),
                artifact=artifacts,
                inspection=renderer.inspect(artifacts),
                capability_report=report,
                input_value=source.read_text(encoding="utf-8"),
            )
            # The digest is computed from the file, so the manifest must be
            # read while the artifact still exists. That is the intended
            # behaviour: a digest for a deleted file would be a lie.
            payload = manifest.to_json()
        self.assertIsNotNone(payload["artifact"]["sha256"])
        self.assertTrue(payload["fonts"])
        self.assertIsNotNone(payload["input"]["digest"])


class ProtocolConformanceTests(TestCase):
    def test_the_adapter_satisfies_the_protocol(self) -> None:
        from renderers.base import Renderer

        if not available():
            self.skipTest("WeasyPrint is not installed")
        self.assertIsInstance(WeasyPrintRenderer(), Renderer)

    def test_the_protocol_does_not_expose_engine_internals(self) -> None:
        from renderers.base import Renderer

        for banned in ("html_dom", "css_box", "tex_node", "typst_context", "page_tree"):
            with self.subTest(attribute=banned):
                self.assertFalse(hasattr(Renderer, banned))


class PipelineTests(TestCase):
    def test_the_default_pipeline_is_the_ir_path(self) -> None:
        # The default was reverted once, when the two paths differed visually.
        # It returned after the writer began filling the template's own markup
        # and a per-genre comparison reported SSIM 1.0000 for every type.
        import pipeline

        self.assertEqual("ir", pipeline.resolve(None).mode)

    def test_the_template_path_stays_available_for_rollback(self) -> None:
        import pipeline

        self.assertEqual("template", pipeline.resolve("legacy").primary)
        self.assertEqual("legacy", pipeline.resolve(None).rollback)

    def test_the_default_can_be_rolled_back_by_configuration(self) -> None:
        import pipeline

        self.assertEqual("template", pipeline.resolve("legacy").primary)
        self.assertEqual("legacy", pipeline.resolve(None).rollback)

    def test_each_mode_selects_a_primary(self) -> None:
        import pipeline

        for mode in pipeline.MODES:
            with self.subTest(mode=mode):
                selected = pipeline.resolve(mode)
                self.assertIn(selected.primary, {"template", "ir"})

    def test_an_unknown_mode_is_rejected_rather_than_defaulted(self) -> None:
        import pipeline

        with self.assertRaises(pipeline.PipelineError):
            pipeline.resolve("not-a-mode")

    def test_every_mode_can_reach_legacy(self) -> None:
        import pipeline

        for mode in pipeline.MODES:
            with self.subTest(mode=mode):
                self.assertIn(pipeline.resolve(mode).rollback, pipeline.PIPELINES)

    def test_the_rollback_drill_passes(self) -> None:
        import pipeline

        payload = pipeline.rollback_drill()
        self.assertTrue(payload["ok"])

    def test_the_drill_checks_configuration_only_rollback(self) -> None:
        import pipeline

        checks = " ".join(str(s.get("check", "")) for s in pipeline.rollback_drill()["steps"])
        self.assertIn("configuration-only", checks)


class LayoutPolicyTests(TestCase):
    def test_a_policy_is_built_from_a_page_profile(self) -> None:
        import profile_check
        from document_ir.layout_policy import policy_for

        profiles = profile_check.load_profiles()
        policy = policy_for(profiles["page"]["a4-long-doc-v1"], name="a4-long-doc-v1")
        self.assertEqual("soft", policy.breaks.page_count_mode)
        self.assertEqual(2, policy.widow_lines)
        self.assertTrue(policy.keeps)

    def test_a_hard_contract_is_carried_through(self) -> None:
        import profile_check
        from document_ir.layout_policy import policy_for

        profiles = profile_check.load_profiles()
        body = profiles["page"]["a4-resume-v1"]
        policy = policy_for(body, name="a4-resume-v1")

        declared = body["page_count"]
        self.assertEqual("hard", policy.breaks.page_count_mode)
        # Read from the profile: the point is that a hard contract is carried
        # through, not that it holds one particular number.
        self.assertEqual(declared.get("exact") or declared.get("target"),
                         policy.breaks.page_count_target)

    def test_node_types_compile_to_real_css_selectors(self) -> None:
        import profile_check
        from document_ir.layout_policy import policy_for, to_css

        profiles = profile_check.load_profiles()
        css = to_css(policy_for(profiles["page"]["a4-long-doc-v1"], name="p"))
        # A semantic node name is not a CSS selector; emitting `heading` would
        # produce a stylesheet that silently matches nothing.
        self.assertNotIn("heading {", css)
        self.assertIn("h1, h2, h3, h4, h5, h6", css)
        self.assertIn("figure", css)

    def test_every_declaration_cites_its_intent(self) -> None:
        import profile_check
        from document_ir.layout_policy import policy_for, to_css

        profiles = profile_check.load_profiles()
        css = to_css(policy_for(profiles["page"]["a4-long-doc-v1"], name="p"))
        for line in css.splitlines():
            if line.strip().endswith("}") and "{" in line:
                with self.subTest(line=line[:40]):
                    self.assertIn("/* from", css[: css.index(line)])

    def test_policy_serialises(self) -> None:
        import profile_check
        from document_ir.layout_policy import policy_for

        profiles = profile_check.load_profiles()
        payload = policy_for(profiles["page"]["a4-resume-v1"], name="p").to_json()
        json.dumps(payload)
        self.assertIn("page_count", payload["breaks"])
