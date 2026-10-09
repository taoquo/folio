"""The font manifest is a build input, not a description of the host.

Fonts decide pagination, so a substitution must be a reviewable decision. These
tests pin the manifest's integrity and the gate that reads it.
"""

import hashlib
import re
import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build


class FontManifestIntegrityTests(TestCase):
    def setUp(self) -> None:
        self.manifest = build.load_font_manifest()
        self.assertTrue(self.manifest, "font manifest should be readable")

    def test_manifest_declares_the_bundled_families(self) -> None:
        families = set(self.manifest["families"])
        self.assertIn("LXGW WenKai", families)
        self.assertIn("JetBrains Mono", families)
        self.assertIn("Charter", families)

    def test_bundled_font_hashes_match_the_files_on_disk(self) -> None:
        text = build.FONT_MANIFEST.read_text(encoding="utf-8")
        entries = re.findall(
            r"path: (assets/fonts/[^\n]+)\n\s+sha256: ([a-f0-9]{64})\n\s+bytes: (\d+)",
            text,
        )
        self.assertGreaterEqual(len(entries), 3, "expected every bundled font to be hashed")
        for rel_path, digest, size in entries:
            with self.subTest(font=rel_path):
                path = ROOT / rel_path
                self.assertTrue(path.is_file(), f"{rel_path} should exist")
                self.assertEqual(digest, hashlib.sha256(path.read_bytes()).hexdigest())
                self.assertEqual(int(size), path.stat().st_size)

    def test_charter_is_declared_as_a_system_dependency(self) -> None:
        # The manifest must not imply Charter ships with the repo.
        text = build.FONT_MANIFEST.read_text(encoding="utf-8")
        charter_block = text.split("body_en:", 1)[1].split("fallback_chains:", 1)[0]
        self.assertIn("kind: system", charter_block)
        self.assertIn("sha256: null", charter_block)

    def test_fallback_groups_cover_every_document_family(self) -> None:
        groups = self.manifest["acceptable_substitutes"]
        self.assertEqual({"en", "zh", "diagram"}, set(groups))
        for name, entries in groups.items():
            with self.subTest(group=name):
                self.assertTrue(entries, f"group {name} should list approved substitutes")


class UnsanctionedFontDetectionTests(TestCase):
    def setUp(self) -> None:
        self.manifest = build.load_font_manifest()

    def test_declared_families_are_accepted(self) -> None:
        for font in ("RATJMB+Charter", "MHZCTQ+LXGW-WenKai", "KTPBXU+JetBrains-Mono"):
            with self.subTest(font=font):
                self.assertEqual([], build.find_unsanctioned_fonts({font}, self.manifest))

    def test_subset_prefixes_do_not_hide_a_family(self) -> None:
        self.assertEqual(
            [],
            build.find_unsanctioned_fonts({"AAAAAA+Charter-Roman"}, self.manifest),
        )

    def test_unlisted_font_is_reported(self) -> None:
        found = build.find_unsanctioned_fonts({"XXXXXX+DejaVu-Serif"}, self.manifest)
        self.assertEqual(["DejaVu-Serif"], found)

    def test_groups_are_not_interchangeable(self) -> None:
        # Verdana is a sanctioned diagram fallback but never a document one.
        self.assertEqual(
            [],
            build.find_unsanctioned_fonts({"X+Verdana"}, self.manifest, group="diagram"),
        )
        self.assertEqual(
            ["Verdana"],
            build.find_unsanctioned_fonts({"X+Verdana"}, self.manifest, group="en"),
        )

    def test_claimed_fallbacks_are_accepted(self) -> None:
        # These reach the page for decorative glyphs Source Serif 4 omits, and
        # were claimed deliberately rather than left as unexplained output.
        for font in ("RATJMB+Times-Roman", "HAAAAA+STSongti-SC-Regular",
                     "IPQIAU+Hiragino-Mincho-ProN-Light"):
            with self.subTest(font=font):
                self.assertEqual([], build.find_unsanctioned_fonts({font}, self.manifest))

    def test_known_unsanctioned_records_stay_as_history(self) -> None:
        # The register documents what the host used to resolve; it is not an
        # exemption mechanism, so a font in it that is not also claimed is
        # still reported.
        recorded = set(self.manifest["known_unsanctioned"])
        self.assertIn("Times-Roman", recorded)
        self.assertIn("STSongti-SC-Regular", recorded)
        self.assertIn("Hiragino-Mincho-ProN-Light", recorded)

    def test_source_serif_is_the_bundled_english_primary(self) -> None:
        self.assertIn("Source Serif 4", self.manifest["families"])
        text = build.FONT_MANIFEST.read_text(encoding="utf-8")
        block = text.split("body_en:", 1)[1].split("body_en_fallback:", 1)[0]
        self.assertIn("kind: bundled", block)
        self.assertIn("SourceSerif4Variable-Roman.ttf", block)

    def test_missing_manifest_disables_the_check_instead_of_failing_open(self) -> None:
        # An absent manifest yields no patterns; callers must treat that as
        # "cannot judge" rather than "everything is fine".
        self.assertEqual({}, build.load_font_manifest(Path("/nonexistent/fonts.yaml")))
        self.assertEqual([], build.find_unsanctioned_fonts({"X+DejaVu"}, {}))
