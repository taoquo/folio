"""The engine's newer surfaces: assets, build conditions, language claims.

Each of these exists to stop a specific over-claim. An asset manifest stops a
document pointing at a file that moved. A build manifest stops two builds being
compared when they ran under different conditions. A language report stops a
configuration file being mistaken for evidence of support.
"""

import json
import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_manifest  # noqa: E402
import language_support  # noqa: E402

import assets  # noqa: E402


class BuildManifestTests(TestCase):
    def test_a_manifest_records_the_build_conditions(self) -> None:
        manifest = build_manifest.capture()
        payload = manifest.to_json()
        for key in ("folio_commit", "python_version", "renderer", "font_manifest_hash",
                    "locale", "build_options"):
            with self.subTest(key=key):
                self.assertIn(key, payload)

    def test_the_fingerprint_is_stable_for_the_same_conditions(self) -> None:
        self.assertEqual(
            build_manifest.capture().fingerprint,
            build_manifest.capture().fingerprint,
        )

    def test_only_tracked_environment_variables_are_recorded(self) -> None:
        # Recording everything would make two manifests differ for reasons that
        # cannot change a page.
        import os

        os.environ["FOLIO_TEST_UNRELATED"] = "x"
        try:
            manifest = build_manifest.capture()
        finally:
            del os.environ["FOLIO_TEST_UNRELATED"]
        self.assertNotIn("FOLIO_TEST_UNRELATED", manifest.to_json()["build_options"])

    def test_pipeline_is_recorded_when_set(self) -> None:
        manifest = build_manifest.capture({"FOLIO_PIPELINE": "ir"})
        self.assertEqual("ir", manifest.to_json()["build_options"]["FOLIO_PIPELINE"])

    def test_a_differing_field_is_named(self) -> None:
        import tempfile

        first = build_manifest.capture()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.json"
            path.write_text(json.dumps(first.to_json()), encoding="utf-8")
            second = build_manifest.capture({"FOLIO_PIPELINE": "legacy"})
            result = build_manifest.compare_files(path, second)
        self.assertFalse(result["ok"])
        self.assertIn("build_options", result["differences"])

    def test_an_unreadable_manifest_is_reported_not_ignored(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text("{not json", encoding="utf-8")
            result = build_manifest.compare_files(path, build_manifest.capture())
        self.assertFalse(result["ok"])
        self.assertIn("error", result)


class AssetTests(TestCase):
    def test_scan_finds_generated_artifacts(self) -> None:
        manifest = assets.scan_diagrams()
        self.assertTrue(manifest.assets)
        for asset in manifest.assets.values():
            with self.subTest(asset=asset.asset_id):
                self.assertTrue(asset.artifacts)

    def test_a_recorded_asset_resolves(self) -> None:
        manifest = assets.scan_diagrams()
        issues = assets.check(manifest)
        self.assertEqual([], [i for i in issues if i.severity == "error"])

    def test_a_missing_artifact_is_reported(self) -> None:
        manifest = assets.AssetManifest()
        manifest.assets["diagram.ghost"] = assets.Asset(
            asset_id="diagram.ghost", kind="diagram",
            artifacts=[assets.AssetArtifact(format="svg", path="assets/no/such.svg")],
        )
        issues = assets.check(manifest)
        self.assertTrue(any(i.code == "ASSET-ARTIFACT.MISSING" for i in issues))

    def test_a_changed_artifact_is_reported(self) -> None:
        manifest = assets.AssetManifest()
        manifest.assets["diagram.x"] = assets.Asset(
            asset_id="diagram.x", kind="diagram",
            artifacts=[assets.AssetArtifact(
                format="svg", path="assets/manifest.json".replace("manifest.json", "demos/demo-architecture.svg"),
                sha256="0" * 64)],
        )
        issues = assets.check(manifest)
        self.assertTrue(any(i.code in {"ASSET-ARTIFACT.CHANGED", "ASSET-ARTIFACT.MISSING"} for i in issues))

    def test_an_asset_without_a_source_says_so(self) -> None:
        manifest = assets.AssetManifest()
        manifest.assets["diagram.y"] = assets.Asset(
            asset_id="diagram.y", kind="diagram",
            artifacts=[assets.AssetArtifact(format="svg", path="x.svg")],
            note="no source found; this artifact cannot be rebuilt",
        )
        payload = manifest.to_json()
        self.assertIn("note", payload["assets"][0])

    def test_a_document_reference_is_matched_by_stem(self) -> None:
        found = assets.references_in({"asset": {"uri": "generated/svg/architecture.svg"}})
        self.assertIn("diagram.architecture", found)


class LanguageSupportTests(TestCase):
    def test_a_language_with_fixtures_is_supported(self) -> None:
        statuses = {s.tag: s for s in language_support.survey()}
        self.assertEqual("supported", statuses["en-US"].level)
        self.assertEqual("supported", statuses["zh-Hans-CN"].level)

    def test_a_language_without_fixtures_makes_no_claim(self) -> None:
        statuses = {s.tag: s for s in language_support.survey()}
        for tag in ("ja-JP", "ko-KR"):
            with self.subTest(tag=tag):
                self.assertEqual("untested", statuses[tag].level)
                self.assertIn("must not be described", statuses[tag].claim)

    def test_an_rtl_language_reaches_partial_not_supported(self) -> None:
        # A fixture exists for Arabic, so it is no longer untested. Shaping,
        # however, is not verified, so it must not be described as supported.
        statuses = {s.tag: s for s in language_support.survey()}
        self.assertEqual("partial", statuses["ar-SA"].level)
        self.assertTrue(statuses["ar-SA"].limits)

    def test_every_level_has_a_stated_claim(self) -> None:
        for level in ("supported", "partial", "untested", "unsupported"):
            with self.subTest(level=level):
                self.assertIn(level, language_support.CLAIM)

    def test_limits_are_stated_rather_than_implied(self) -> None:
        statuses = language_support.survey()
        untested = [s for s in statuses if s.level == "untested"]
        for status in untested:
            with self.subTest(tag=status.tag):
                self.assertTrue(status.limits)

    def test_a_profile_alone_is_not_evidence(self) -> None:
        # 中文 has both a profile and fixtures; a language with only a profile
        # must not reach the supported level.
        for status in language_support.survey():
            with self.subTest(tag=status.tag):
                if status.level == "supported":
                    self.assertGreater(status.fixtures, 0)


class DiagnosticsTests(TestCase):
    """Codes are a public surface, so their shape and their history matter."""

    def setUp(self) -> None:
        import diagnostics

        self.diagnostics = diagnostics

    def test_every_emitted_code_follows_the_convention(self) -> None:
        inventory = self.diagnostics.scan()
        offenders = [f.code for f in inventory.off_convention]
        self.assertEqual([], offenders[:5])

    def test_the_domain_vocabulary_is_declared(self) -> None:
        for domain in ("DOC", "STYLE", "LAYOUT", "FONT", "ASSET",
                       "RENDER", "A11Y", "QA"):
            with self.subTest(domain=domain):
                self.assertIn(domain, self.diagnostics.DOMAINS)

    def test_a_conforming_code_is_accepted(self) -> None:
        for code in ("DOC-ID.DUPLICATE", "ASSET-ARTIFACT.MISSING",
                     "A11Y-IMAGE.MISSING_ALT", "LAYOUT-HEADING.ORPHANED"):
            with self.subTest(code=code):
                self.assertTrue(self.diagnostics.conforms(code))

    def test_a_malformed_code_is_refused(self) -> None:
        for code in ("doc-id.duplicate", "DOCID", "DOC_", "-DOC.ID", "DOC..ID"):
            with self.subTest(code=code):
                self.assertFalse(self.diagnostics.conforms(code))

    def test_a_renamed_code_still_explains_its_replacement(self) -> None:
        # A code used outside the repository keeps working, and says what to
        # move to; a silent rename would break every check looking for it.
        for old, new in self.diagnostics.LEGACY.items():
            with self.subTest(code=old):
                self.assertTrue(self.diagnostics.conforms(new))
                self.assertEqual(new, self.diagnostics.replaced_by(old))

    def test_the_registry_does_not_report_its_own_table(self) -> None:
        inventory = self.diagnostics.scan()
        files = {f.file for f in inventory.off_convention}
        self.assertNotIn("scripts/diagnostics.py", files)

    def test_explaining_a_code_names_its_domain(self) -> None:
        payload = self.diagnostics.explain("DOC-ID.DUPLICATE")
        self.assertEqual("DOC", payload["domain"])
        self.assertTrue(payload["domain_meaning"])


class BaselineGovernanceTests(TestCase):
    def test_an_unattended_run_cannot_approve_a_baseline(self) -> None:
        import os

        import document_baseline

        os.environ["CI"] = "true"
        try:
            self.assertIsNotNone(document_baseline.unattended_environment())
        finally:
            del os.environ["CI"]

    def test_an_interactive_run_may_approve(self) -> None:
        import os

        import document_baseline

        for key in ("CI", "GITHUB_ACTIONS"):
            os.environ.pop(key, None)
        os.environ["FOLIO_ALLOW_UNATTENDED_APPROVAL"] = "1"
        try:
            self.assertIsNone(document_baseline.unattended_environment())
        finally:
            del os.environ["FOLIO_ALLOW_UNATTENDED_APPROVAL"]
