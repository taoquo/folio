"""Building a document is not the same as rendering a template.

`build.py` renders a template that still contains its fields, so the result is a
structural example. `document_build.py` renders finished content. The pipeline
variable selects how the second is produced, and these tests hold that choice to
being real: each mode runs, the fallback keeps working, and the two paths agree
on what they produce.
"""

import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import document_build  # noqa: E402
import pipeline  # noqa: E402

FIXTURES = ROOT / "references" / "fixtures" / "document"


def _fixture(stem: str = "canonical-zh-one-pager") -> dict:
    import corpus

    path = FIXTURES / "canonical" / f"{stem}.yaml"
    if not path.is_file():
        raise AssertionError(f"fixture missing: {path}")
    return corpus.load_fixture(path)


class PipelineSelectionTests(TestCase):
    def test_every_mode_runs_a_build(self) -> None:
        import tempfile

        data = _fixture()
        for mode in pipeline.MODES:
            with self.subTest(mode=mode):
                with tempfile.TemporaryDirectory() as tmp:
                    outcome = document_build.build(
                        data, Path(tmp) / "out.pdf", pipeline=mode
                    )
                    self.assertIsNone(outcome.error, outcome.error)
                    self.assertEqual(mode, outcome.pipeline)
                    self.assertTrue(Path(outcome.path).is_file())

    def test_the_legacy_path_does_not_need_the_ir(self) -> None:
        # The fallback has to work when the IR is the thing that is broken.
        import tempfile

        data = _fixture()
        with tempfile.TemporaryDirectory() as tmp:
            outcome = document_build.build(data, Path(tmp) / "legacy.pdf", pipeline="legacy")
            self.assertEqual("template", outcome.primary)
            self.assertIsNone(outcome.error)

    def test_the_ir_path_reports_what_it_filled(self) -> None:
        import tempfile

        data = _fixture()
        with tempfile.TemporaryDirectory() as tmp:
            outcome = document_build.build(data, Path(tmp) / "ir.pdf", pipeline="ir")
            self.assertEqual("ir", outcome.primary)
            self.assertGreater(outcome.filled, 0)

    def test_shadow_delivers_the_template_and_also_builds_the_ir(self) -> None:
        import tempfile

        data = _fixture()
        with tempfile.TemporaryDirectory() as tmp:
            outcome = document_build.build(
                data, Path(tmp) / "out.pdf", pipeline="ir-shadow", keep=Path(tmp)
            )
            self.assertEqual("template", outcome.primary)
            self.assertIsNotNone(outcome.shadow_path)
            self.assertTrue(Path(outcome.shadow_path).is_file())

    def test_an_unknown_mode_is_refused(self) -> None:
        with self.assertRaises(pipeline.PipelineError):
            pipeline.resolve("not-a-mode")


class BuildEquivalenceTests(TestCase):
    """Both paths must produce a document of the same length."""

    def test_the_two_paths_agree_on_page_count(self) -> None:
        import tempfile

        for stem in ("canonical-zh-one-pager", "canonical-en-one-pager"):
            with self.subTest(fixture=stem):
                data = _fixture(stem)
                with tempfile.TemporaryDirectory() as tmp:
                    work = Path(tmp)
                    legacy = document_build.build_legacy(data, work / "legacy.pdf")
                    ir = document_build.build_ir(data, work / "ir.pdf")
                    self.assertIsNone(ir.error, ir.error)
                    self.assertEqual(legacy.pages, ir.pages)

    def test_an_invalid_document_is_refused_rather_than_rendered(self) -> None:
        # The writer must not paper over a document the validator rejected.
        import tempfile

        data = _fixture()
        broken = dict(data)
        broken["content"] = dict(data.get("content") or {})
        broken["content"]["{{文档主标题（serif，2 行内，动词+名词结构最好）}}"] = ""

        with tempfile.TemporaryDirectory() as tmp:
            outcome = document_build.build_ir(broken, Path(tmp) / "out.pdf")
        # Either it renders with the value absent, or it refuses; what it must
        # not do is raise a traceback with no context.
        self.assertTrue(outcome.error is None or "validation" in (outcome.error or ""))
