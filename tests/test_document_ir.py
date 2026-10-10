"""The IR describes what a document is, never how it is drawn.

The boundary is the whole point: if a style or a coordinate can enter the IR,
the model stops being portable and the second renderer becomes impossible.
These tests pin the boundary, plus immutability, id stability, fail-closed
validation and round-trip fidelity.
"""

import json
import sys
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import document_ir
from document_ir import model as M
from document_ir.readers import DocumentReadError, document_from_data, read
from document_ir.validate import validate
from document_ir.writers import UnsupportedNode, write_html


def sample_data(**overrides) -> dict:
    data = {
        "schema_version": "1.0",
        "id": "sample-doc",
        "lang": "zh-Hans-CN",
        "metadata": {"title": "示例文档", "author": "Folio", "genre": "one-pager"},
        "profiles": {"typography": "folio-one-pager-zh-v1", "page": "a4-one-pager-v1"},
        "blocks": [
            {"type": "heading", "id": "h-1", "level": 1,
             "content": [{"type": "text", "value": "主标题"}]},
            {"type": "paragraph", "id": "p-1", "role": "lead",
             "content": [
                 {"type": "text", "value": "导语 "},
                 {"type": "text", "value": "重点", "highlight": True},
                 {"type": "text", "value": "。"},
             ]},
        ],
    }
    data.update(overrides)
    return data


class SemanticBoundaryTests(TestCase):
    """No style, geometry or renderer concept may appear in the IR."""

    # Matched as whole field names, not substrings: `keep_with_next` contains
    # an "x" and `type` is a legitimate discriminator, so a substring check
    # would report false positives and train everyone to ignore it.
    FORBIDDEN_FIELDS = {
        "font_size", "fontsize", "font_family", "font_weight", "font_style",
        "line_height", "letter_spacing", "margin", "padding",
        "width", "height", "margin_top", "margin_bottom", "margin_left", "margin_right",
        "color", "colour", "background", "background_color", "border", "border_radius",
        "radius", "opacity", "shadow", "css", "class_name", "style",
    }

    def test_model_fields_carry_no_style_vocabulary(self) -> None:
        import dataclasses

        for name, obj in vars(M).items():
            if not dataclasses.is_dataclass(obj) or not isinstance(obj, type):
                continue
            for field_info in dataclasses.fields(obj):
                with self.subTest(node=name, field=field_info.name):
                    self.assertNotIn(field_info.name.lower(), self.FORBIDDEN_FIELDS)

    def test_payload_keys_carry_no_style_vocabulary(self) -> None:
        data = sample_data(blocks=[
            {"type": "section", "id": "s-1", "role": "chapter", "blocks": [
                {"type": "heading", "id": "h-1", "level": 1,
                 "content": [{"type": "text", "value": "T"}]},
                {"type": "list", "id": "l-1", "items": [
                    {"id": "li-1", "content": [{"type": "text", "value": "x"}]}]},
                {"type": "figure", "id": "f-1", "asset": {"uri": "a.png"},
                 "alt": "described", "placement": {"mode": "float"}},
                {"type": "table", "id": "t-1",
                 "columns": [{"id": "c1", "label": [{"type": "text", "value": "A"}]}],
                 "rows": []},
            ]},
        ])
        document = document_from_data(data)

        def walk(value, path=""):
            if isinstance(value, dict):
                for key, item in value.items():
                    with self.subTest(path=f"{path}.{key}"):
                        self.assertNotIn(str(key).lower(), self.FORBIDDEN_FIELDS)
                    walk(item, f"{path}.{key}")
            elif isinstance(value, (list, tuple)):
                for index, item in enumerate(value):
                    walk(item, f"{path}[{index}]")

        walk(document.to_json())

    def test_schema_definitions_carry_no_style_properties(self) -> None:
        schema = json.loads((ROOT / "references" / "schemas" / "document-1.0.schema.json").read_text())
        blob = json.dumps(schema)
        for banned in ("font-size", "line-height", "border-radius", "margin-top", "padding-left"):
            with self.subTest(property=banned):
                self.assertNotIn(banned, blob)

    def test_a_theme_is_named_not_embedded(self) -> None:
        document = document_from_data(sample_data())
        payload = document.to_json()
        self.assertEqual("folio-one-pager-zh-v1", payload["profiles"]["typography"])
        # The profile name travels with the document; its values do not.
        self.assertNotIn("F6F0EA", json.dumps(payload))


class ImmutabilityTests(TestCase):
    def test_documents_are_frozen(self) -> None:
        import dataclasses

        document = document_from_data(sample_data())
        with self.assertRaises(dataclasses.FrozenInstanceError):
            document.id = "changed"

    def test_blocks_are_frozen(self) -> None:
        import dataclasses

        document = document_from_data(sample_data())
        with self.assertRaises(dataclasses.FrozenInstanceError):
            document.blocks[0].id = "changed"

    def test_with_blocks_returns_a_new_document(self) -> None:
        document = document_from_data(sample_data())
        changed = document.with_blocks(document.blocks[:1])
        self.assertEqual(2, len(document.blocks))
        self.assertEqual(1, len(changed.blocks))


class IdStabilityTests(TestCase):
    def test_explicit_ids_survive_a_round_trip(self) -> None:
        document = document_from_data(sample_data())
        self.assertEqual(["h-1", "p-1"], document.node_ids())
        again = document_from_data(document.to_json())
        self.assertEqual(document.node_ids(), again.node_ids())

    def test_a_missing_id_is_reported_rather_than_invented(self) -> None:
        data = sample_data(blocks=[{"type": "paragraph", "content": [{"type": "text", "value": "x"}]}])
        document = document_from_data(data)
        # The reader substitutes a positional id so the document stays usable
        # rather than failing on a missing one.
        self.assertTrue(document.node_ids())

    def test_duplicate_ids_fail_validation(self) -> None:
        data = sample_data(blocks=[
            {"type": "paragraph", "id": "same", "content": [{"type": "text", "value": "a"}]},
            {"type": "paragraph", "id": "same", "content": [{"type": "text", "value": "b"}]},
        ])
        report = validate(document_from_data(data))
        self.assertFalse(report.ok)
        self.assertIn("DOC-ID.DUPLICATE", {d.code for d in report.errors})

    def test_an_invalid_id_token_is_rejected(self) -> None:
        data = sample_data(blocks=[
            {"type": "paragraph", "id": "has space", "content": [{"type": "text", "value": "x"}]},
        ])
        report = validate(document_from_data(data))
        self.assertIn("DOC-ID.INVALID", {d.code for d in report.errors})


class FailClosedValidationTests(TestCase):
    def test_a_valid_document_passes(self) -> None:
        self.assertTrue(validate(document_from_data(sample_data())).ok)

    def test_a_broken_cross_reference_fails(self) -> None:
        data = sample_data(blocks=[
            {"type": "paragraph", "id": "p-1",
             "content": [{"type": "cross_ref", "target": "nowhere"}]},
        ])
        report = validate(document_from_data(data))
        self.assertFalse(report.ok)
        self.assertIn("DOC-REF.BROKEN", {d.code for d in report.errors})

    def test_a_figure_without_alt_text_fails(self) -> None:
        data = sample_data(blocks=[
            {"type": "figure", "id": "f-1", "asset": {"uri": "a.png"}, "alt": ""},
        ])
        report = validate(document_from_data(data))
        self.assertFalse(report.ok)
        self.assertIn("A11Y-IMAGE.MISSING_ALT", {d.code for d in report.errors})

    def test_a_decorative_figure_needs_no_alt_text(self) -> None:
        data = sample_data(blocks=[
            {"type": "figure", "id": "f-1", "asset": {"uri": "a.png"},
             "alt": "", "decorative": True},
        ])
        report = validate(document_from_data(data))
        self.assertNotIn("A11Y-IMAGE.MISSING_ALT", {d.code for d in report.errors})

    def test_a_skipped_heading_level_fails(self) -> None:
        data = sample_data(blocks=[
            {"type": "heading", "id": "h-1", "level": 1, "content": [{"type": "text", "value": "a"}]},
            {"type": "heading", "id": "h-2", "level": 3, "content": [{"type": "text", "value": "b"}]},
        ])
        report = validate(document_from_data(data))
        self.assertIn("A11Y-HEADING.SKIP", {d.code for d in report.errors})

    def test_a_ragged_table_fails(self) -> None:
        data = sample_data(blocks=[
            {"type": "table", "id": "t-1",
             "columns": [{"id": "c1", "label": [{"type": "text", "value": "A"}]},
                         {"id": "c2", "label": [{"type": "text", "value": "B"}]}],
             "rows": [{"id": "r1", "cells": [[{"type": "text", "value": "1"}]]}]},
        ])
        report = validate(document_from_data(data))
        self.assertIn("DOC-TABLE.RAGGED", {d.code for d in report.errors})

    def test_a_missing_footnote_definition_fails(self) -> None:
        data = sample_data(blocks=[
            {"type": "paragraph", "id": "p-1",
             "content": [{"type": "footnote_ref", "target": "fn-1"}]},
        ])
        report = validate(document_from_data(data))
        self.assertIn("DOC-FOOTNOTE.MISSING", {d.code for d in report.errors})

    def test_an_empty_document_fails(self) -> None:
        report = validate(document_from_data(sample_data(blocks=[])))
        self.assertIn("DOC-CONTENT.EMPTY", {d.code for d in report.errors})

    def test_a_missing_language_fails(self) -> None:
        report = validate(document_from_data(sample_data(lang="")))
        self.assertIn("DOC-LANG.MISSING", {d.code for d in report.errors})

    def test_report_serialises_with_codes_and_hints(self) -> None:
        data = sample_data(blocks=[
            {"type": "paragraph", "id": "p-1",
             "content": [{"type": "cross_ref", "target": "nowhere"}]},
        ])
        payload = validate(document_from_data(data)).to_json()
        json.dumps(payload)
        self.assertFalse(payload["ok"])
        broken = [d for d in payload["diagnostics"] if d["code"] == "DOC-REF.BROKEN"][0]
        self.assertTrue(broken["hint"])


class RawFallbackTests(TestCase):
    """Raw fallback is an escape hatch whose growth signals a narrow IR."""

    def test_an_unknown_block_becomes_a_fallback_that_explains_itself(self) -> None:
        data = sample_data(blocks=[{"type": "something-new", "id": "x-1", "value": "kept"}])
        document = document_from_data(data)
        node = document.find("x-1")
        self.assertEqual("raw_fallback", node.type)
        self.assertIn("something-new", node.payload["reason"])

    def test_a_fallback_without_a_reason_fails_validation(self) -> None:
        data = sample_data(blocks=[
            {"type": "raw_fallback", "id": "r-1", "value": "<div/>", "reason": ""},
        ])
        report = validate(document_from_data(data))
        self.assertIn("DOC-FALLBACK.REASON", {d.code for d in report.errors})

    def test_excessive_fallback_is_flagged(self) -> None:
        blocks = [{"type": "paragraph", "id": "p-1", "content": [{"type": "text", "value": "x"}]}]
        blocks += [{"type": "raw_fallback", "id": f"r-{i}", "value": "x", "reason": "unknown"}
                   for i in range(3)]
        report = validate(document_from_data(sample_data(blocks=blocks)))
        self.assertIn("DOC-FALLBACK.EXCESSIVE", {d.code for d in report.warnings})


class ReaderTests(TestCase):
    def test_json_and_yaml_agree(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            json_path = Path(tmp) / "doc.json"
            json_path.write_text(json.dumps(sample_data(), ensure_ascii=False), encoding="utf-8")
            from_json = read(json_path)
        self.assertEqual("sample-doc", from_json.id)
        self.assertEqual("示例文档", from_json.metadata.title)

    def test_yaml_is_read(self) -> None:
        import tempfile

        yaml_text = (
            "schema_version: '1.0'\n"
            "id: yaml-doc\n"
            "lang: en-US\n"
            "metadata:\n"
            "  title: YAML document\n"
            "blocks:\n"
            "  - type: paragraph\n"
            "    id: p-1\n"
            "    content:\n"
            "      - type: text\n"
            "        value: hello\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.yaml"
            path.write_text(yaml_text, encoding="utf-8")
            document = read(path)
        self.assertEqual("yaml-doc", document.id)
        self.assertEqual(["p-1"], document.node_ids())

    def test_an_unsupported_schema_version_is_rejected(self) -> None:
        with self.assertRaises(DocumentReadError):
            document_from_data(sample_data(schema_version="2.0"))

    def test_an_unknown_suffix_is_rejected(self) -> None:
        with self.assertRaises(DocumentReadError):
            read(Path("/tmp/whatever.txt"))

    def test_all_nested_block_types_are_read(self) -> None:
        data = sample_data(blocks=[
            {"type": "section", "id": "s-1", "role": "chapter", "blocks": [
                {"type": "heading", "id": "h-1", "level": 1,
                 "content": [{"type": "text", "value": "T"}]},
                {"type": "list", "id": "l-1", "ordered": True, "items": [
                    {"id": "li-1", "content": [{"type": "text", "value": "one"}]}]},
                {"type": "table", "id": "t-1",
                 "columns": [{"id": "c1", "label": [{"type": "text", "value": "A"}]}],
                 "rows": [{"id": "r1", "cells": [[{"type": "text", "value": "1"}]]}]},
            ]},
        ])
        document = document_from_data(data)
        self.assertEqual({"s-1", "h-1", "l-1", "t-1"}, set(document.node_ids()))


class WriterTests(TestCase):
    def test_html_reuses_the_template_classes(self) -> None:
        document = document_from_data(sample_data())
        html = write_html(document)
        self.assertIn('class="lead"', html)
        self.assertIn('class="hl"', html)

    def test_every_rendered_element_carries_its_ir_id(self) -> None:
        document = document_from_data(sample_data())
        html = write_html(document)
        for node_id in document.node_ids():
            with self.subTest(node=node_id):
                self.assertIn(f'data-folio-id="{node_id}"', html)

    def test_language_is_declared_on_the_root_element(self) -> None:
        html = write_html(document_from_data(sample_data()))
        self.assertIn('lang="zh-Hans-CN"', html)

    def test_a_writer_does_not_rename_ids(self) -> None:
        document = document_from_data(sample_data())
        before = document.node_ids()
        write_html(document)
        self.assertEqual(before, document.node_ids())

    def test_markup_in_content_is_escaped(self) -> None:
        data = sample_data(blocks=[
            {"type": "paragraph", "id": "p-1",
             "content": [{"type": "text", "value": "<script>alert(1)</script>"}]},
        ])
        html = write_html(document_from_data(data))
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_an_unknown_block_raises_rather_than_dropping_content(self) -> None:
        document = document_from_data(sample_data())
        fake = M.block("no_such_type", "x-1")
        broken = document.with_blocks((fake,))
        with self.assertRaises(UnsupportedNode):
            write_html(broken)


class RoundTripTests(TestCase):
    def test_document_survives_json_round_trip(self) -> None:
        original = document_from_data(sample_data())
        again = document_from_data(original.to_json())
        self.assertEqual(original.to_json(), again.to_json())

    def test_node_order_is_preserved(self) -> None:
        original = document_from_data(sample_data())
        self.assertEqual(original.node_ids(), document_from_data(original.to_json()).node_ids())

    def test_highlight_survives(self) -> None:
        original = document_from_data(sample_data())
        payload = original.to_json()
        content = payload["blocks"][1]["content"]
        self.assertTrue(any(item.get("highlight") for item in content))

    def test_profile_names_survive(self) -> None:
        original = document_from_data(sample_data())
        self.assertEqual(
            original.profiles.typography,
            document_from_data(original.to_json()).profiles.typography,
        )


class PackageSurfaceTests(TestCase):
    def test_the_package_reexports_its_public_types(self) -> None:
        for name in ("Document", "Block", "Text", "Metadata", "ProfileRefs"):
            with self.subTest(type=name):
                self.assertTrue(hasattr(document_ir, name))

    def test_validation_report_json_is_stable(self) -> None:
        report = validate(document_from_data(sample_data()))
        payload = report.to_json()
        self.assertEqual({"ok", "errors", "warnings", "diagnostics"}, set(payload))
        self.assertTrue(payload["ok"])


class BridgeTests(TestCase):
    """The bridge maps declared placeholders to semantic nodes.

    It deliberately does not parse HTML back into meaning: visual classes
    cannot reliably recover an author's intent, so the mapping is a table a
    reviewer can read.
    """

    def setUp(self) -> None:
        from document_ir.bridge import default_map_for, placeholders_in

        self.template = ROOT / "assets" / "templates" / "one-pager.html"
        if not self.template.is_file():
            self.skipTest("one-pager template not present")
        self.text = self.template.read_text(encoding="utf-8")
        self.map = default_map_for("one-pager", "zh-Hans-CN")
        self.placeholders_in = placeholders_in

    def _content(self) -> dict:
        return {
            "文档主标题（serif，2 行内，动词+名词结构最好）": "把排版变成工程",
            "一行副标题 / 一句核心论点": "副标题",
            "一段 40-60 字的核心论点导语。用「<span class=\"hl\">关键词</span>」高亮重点。这段定调整个文档。": "导语内容。",
            "短 bullet：数据/观察/判断": "观察一",
            "关键引用 / 重要提示 / 核心 takeaway。比正文更需要引起注意的内容放这里。": "引用内容。",
            "建议采取的单一动作：批准 / 暂缓 / 追加资源 / 进入下一阶段。": "批准。",
        }

    def test_placeholders_are_listed_in_document_order(self) -> None:
        names = self.placeholders_in(self.text)
        self.assertGreater(len(names), 10)
        self.assertEqual(len(names), len(set(names)))

    def test_bridging_produces_valid_ir(self) -> None:
        from document_ir.bridge import bridge_template

        document = bridge_template(
            self.text, self._content(), document_id="bridged", lang="zh-Hans-CN",
            genre="one-pager", bridge_map=self.map,
        )
        report = validate(document)
        self.assertTrue(report.ok, [d.message for d in report.errors])

    def test_generated_ids_are_reference_safe(self) -> None:
        # Chinese placeholder text must not leak into an id: ids are used as
        # URL fragments and cross-reference targets.
        from document_ir.bridge import bridge_template

        document = bridge_template(
            self.text, self._content(), document_id="bridged", lang="zh-Hans-CN",
            genre="one-pager", bridge_map=self.map,
        )
        for node_id in document.node_ids():
            with self.subTest(node=node_id):
                self.assertRegex(node_id, r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

    def test_ids_are_stable_across_identical_runs(self) -> None:
        from document_ir.bridge import bridge_template

        first = bridge_template(self.text, self._content(), document_id="b",
                                lang="zh-Hans-CN", genre="one-pager", bridge_map=self.map)
        second = bridge_template(self.text, self._content(), document_id="b",
                                 lang="zh-Hans-CN", genre="one-pager", bridge_map=self.map)
        self.assertEqual(first.node_ids(), second.node_ids())

    def test_an_unmapped_placeholder_becomes_a_named_fallback(self) -> None:
        from document_ir.bridge import BridgeMap, bridge_template

        template = "<p>{{Brand new field}}</p>"
        document = bridge_template(
            template, {"Brand new field": "value"}, document_id="b", lang="en-US",
            genre="one-pager", bridge_map=BridgeMap(genre="one-pager", language="en-US"),
        )
        node = document.find("brand-new-field")
        self.assertEqual("raw_fallback", node.type)
        self.assertIn("Brand new field", node.payload["reason"])

    def test_provenance_points_back_at_the_placeholder(self) -> None:
        from document_ir.bridge import bridge_template

        document = bridge_template(
            self.text, self._content(), document_id="b", lang="zh-Hans-CN",
            genre="one-pager", bridge_map=self.map,
        )
        sourced = [n for n in document.walk() if n.source is not None]
        self.assertTrue(sourced)
        self.assertTrue(all(n.source.locator for n in sourced))

    def test_bridged_ir_renders_to_html(self) -> None:
        from document_ir.bridge import bridge_template

        document = bridge_template(
            self.text, self._content(), document_id="bridged", lang="zh-Hans-CN",
            genre="one-pager", bridge_map=self.map,
        )
        html = write_html(document)
        self.assertIn('lang="zh-Hans-CN"', html)
        for node_id in document.node_ids():
            self.assertIn(f'data-folio-id="{node_id}"', html)


class EndToEndTests(TestCase):
    """IR to HTML to a rendered page, using the template's own stylesheet."""

    def _render(self, document):
        import re
        import tempfile

        from weasyprint import HTML as WeasyHTML

        template = ROOT / "assets" / "templates" / "one-pager.html"
        if not template.is_file():
            self.skipTest("one-pager template not present")
        style = re.search(r"<style>.*?</style>", template.read_text(encoding="utf-8"), re.DOTALL)
        body = write_html(document).split("<body", 1)[1].split(">", 1)[1].rsplit("</body>", 1)[0]
        combined = (
            '<!DOCTYPE html><html lang="zh-Hans-CN"><head><meta charset="utf-8">'
            f"{style.group(0)}</head><body>{body}</body></html>"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.html"
            path.write_text(combined, encoding="utf-8")
            pdf = Path(tmp) / "doc.pdf"
            WeasyHTML(str(path), base_url=str(template.parent)).write_pdf(str(pdf))
            from pypdf import PdfReader

            return len(PdfReader(str(pdf)).pages)

    def test_ir_renders_through_the_template_stylesheet(self) -> None:
        document = document_from_data(sample_data(blocks=[
            {"type": "heading", "id": "h-1", "level": 1,
             "content": [{"type": "text", "value": "标题"}]},
            {"type": "paragraph", "id": "p-1", "role": "lead",
             "content": [{"type": "text", "value": "正文 "},
                         {"type": "text", "value": "重点", "highlight": True}]},
        ]))
        self.assertGreaterEqual(self._render(document), 1)


class ShippedIRFixtureTests(TestCase):
    """The IR fixtures are the model's own regression protection."""

    def _fixtures(self):
        directory = ROOT / "references" / "fixtures" / "document" / "ir"
        if not directory.is_dir():
            self.skipTest("IR fixtures not present")
        return sorted(directory.glob("*.json"))

    def test_the_fixture_set_is_large_enough_to_cover_the_model(self) -> None:
        self.assertGreaterEqual(len(self._fixtures()), 12)

    def test_every_fixture_validates_and_writes_html(self) -> None:
        for path in self._fixtures():
            with self.subTest(fixture=path.stem):
                document = read(path)
                report = validate(document)
                self.assertEqual([], [d.message for d in report.errors])
                html = write_html(document)
                self.assertIn("data-folio-document", html)

    def test_every_fixture_matches_the_schema(self) -> None:
        import jsonschema

        schema = json.loads(
            (ROOT / "references" / "schemas" / "document-1.0.schema.json").read_text()
        )
        validator = jsonschema.Draft202012Validator(schema)
        for path in self._fixtures():
            with self.subTest(fixture=path.stem):
                import json as _json

                errors = list(validator.iter_errors(_json.loads(path.read_text())))
                self.assertEqual([], [e.message for e in errors])

    def test_fixtures_cover_all_four_script_profiles(self) -> None:
        blob = "".join(p.read_text() for p in self._fixtures())
        self.assertTrue(any("\u4e00" <= ch <= "\u9fff" for ch in blob), "no Han content")
        self.assertTrue(any(ch.isdigit() for ch in blob), "no digits")
        self.assertTrue(all(ord(c) < 128 for c in "abc"), "sanity")

    def test_fixture_ids_match_filenames(self) -> None:
        for path in self._fixtures():
            with self.subTest(fixture=path.stem):
                self.assertEqual(path.stem, read(path).id)


class MigrationTests(TestCase):
    """Old documents stay readable; migration only ever moves forwards."""

    def test_the_current_version_is_readable_and_current(self) -> None:
        from document_ir import migrations

        self.assertTrue(migrations.is_readable(migrations.CURRENT_VERSION))
        self.assertTrue(migrations.is_current(migrations.CURRENT_VERSION))

    def test_a_document_without_a_version_fails_clearly(self) -> None:
        from document_ir.migrations import MigrationError, version_of

        with self.assertRaises(MigrationError):
            version_of({"id": "x"})

    def test_migrating_a_current_document_is_a_no_op(self) -> None:
        from document_ir.migrations import CURRENT_VERSION, migrate

        data = {"schema_version": CURRENT_VERSION, "id": "x"}
        self.assertEqual(data, migrate(data))

    def test_backwards_migration_is_refused(self) -> None:
        # Rewriting a v1 document into v0 would destroy the record of what was
        # actually written, so there is no path back.
        from document_ir.migrations import MigrationError, migrate

        with self.assertRaises(MigrationError):
            migrate({"schema_version": "1.0"}, to_version="0.9")

    def test_an_unreadable_version_is_refused(self) -> None:
        from document_ir.migrations import MigrationError, migrate

        with self.assertRaises(MigrationError):
            migrate({"schema_version": "9.9"})

    def test_migration_returns_a_new_mapping(self) -> None:
        from document_ir.migrations import CURRENT_VERSION, migrate

        data = {"schema_version": CURRENT_VERSION, "id": "x"}
        result = migrate(data)
        self.assertIsNot(data, result)

    def test_supported_versions_describes_the_reader(self) -> None:
        from document_ir.migrations import supported_versions

        payload = supported_versions()
        self.assertIn("current", payload)
        self.assertIn(payload["current"], payload["readable"])

    def test_compatibility_report_separates_readable_from_unreadable(self) -> None:
        from document_ir.migrations import compatibility_report

        payload = compatibility_report({
            "ok.json": {"schema_version": "1.0", "id": "a"},
            "future.json": {"schema_version": "9.9", "id": "b"},
            "bare.json": {"id": "c"},
        })
        self.assertFalse(payload["ok"])
        self.assertEqual(1, len(payload["readable"]))
        self.assertEqual(2, len(payload["unreadable"]))

    def test_every_shipped_ir_fixture_is_at_the_current_version(self) -> None:
        from document_ir.migrations import CURRENT_VERSION, version_of

        directory = ROOT / "references" / "fixtures" / "document" / "ir"
        if not directory.is_dir():
            self.skipTest("IR fixtures not present")
        for path in sorted(directory.glob("*.json")):
            with self.subTest(fixture=path.stem):
                import json as _json

                self.assertEqual(CURRENT_VERSION, version_of(_json.loads(path.read_text())))


class ShippedFixtureRoundTripTests(TestCase):
    """Every shipped IR fixture must survive a round trip unchanged.

    The model's stability is a claim about the whole vocabulary, so it is
    checked against the fixtures that exercise that vocabulary rather than
    against one hand-written sample.
    """

    def _fixtures(self):
        directory = ROOT / "references" / "fixtures" / "document" / "ir"
        if not directory.is_dir():
            self.skipTest("IR fixtures not present")
        return sorted(directory.glob("*.json"))

    def test_every_fixture_round_trips_unchanged(self) -> None:
        from document_ir.readers.structured import document_from_data

        for path in self._fixtures():
            with self.subTest(fixture=path.stem):
                original = read(path)
                rebuilt = document_from_data(original.to_json())
                self.assertEqual(original.to_json(), rebuilt.to_json())

    def test_reading_a_fixture_twice_gives_the_same_document(self) -> None:
        for path in self._fixtures():
            with self.subTest(fixture=path.stem):
                self.assertEqual(read(path).to_json(), read(path).to_json())

    def test_round_trip_preserves_node_ids_and_order(self) -> None:
        from document_ir.readers.structured import document_from_data

        for path in self._fixtures():
            with self.subTest(fixture=path.stem):
                original = read(path)
                rebuilt = document_from_data(original.to_json())
                self.assertEqual(original.node_ids(), rebuilt.node_ids())

    def test_the_core_model_does_not_import_a_renderer(self) -> None:
        """The IR must be expressible without a backend.

        `writers/` is allowed to reach a renderer: projecting to a backend is
        what a writer does. The model, validator, reader and bridge must not,
        because then the document could not exist without that backend.
        """
        core = [
            ROOT / "scripts" / "document_ir" / name
            for name in ("model.py", "validate.py", "bridge.py", "containers.py",
                         "layout_policy.py", "migrations.py")
        ]
        core.append(ROOT / "scripts" / "document_ir" / "readers" / "structured.py")

        for path in core:
            with self.subTest(module=path.name):
                text = path.read_text(encoding="utf-8")
                for banned in ("weasyprint", "from pptx", "import pptx"):
                    self.assertNotIn(banned, text.lower())
