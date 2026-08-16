import json
from copy import deepcopy
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from drawing.compiler import DEFAULT_COMPILER_REGISTRY
from diagram_catalog import (
    PLACEHOLDER_RE,
    compare_visual_baseline,
    create_visual_baseline,
    fill_template,
    load_catalog,
    render_catalog,
)


class DiagramCatalogTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = load_catalog()

    def test_catalog_covers_all_official_diagram_targets(self) -> None:
        expected = set(DEFAULT_COMPILER_REGISTRY.kinds)
        actual = {item["kind"] for item in self.payload["diagrams"]}

        self.assertEqual(expected, actual)

    def test_catalog_reports_current_drawing_dsl_coverage_honestly(self) -> None:
        dsl_kinds = {
            item["kind"]
            for item in self.payload["diagrams"]
            if item["mode"] == "drawing-dsl"
        }

        self.assertEqual(set(DEFAULT_COMPILER_REGISTRY.kinds), dsl_kinds)

    def test_every_html_baseline_resolves_all_placeholders(self) -> None:
        for item in self.payload["diagrams"]:
            if item["mode"] != "html-template":
                continue
            source = (ROOT / item["source"]).read_text(encoding="utf-8")
            filled = fill_template(source, item.get("replacements", {}))

            self.assertFalse(PLACEHOLDER_RE.findall(filled), item["kind"])

    def test_fixture_is_stable_json(self) -> None:
        encoded = json.dumps(self.payload, ensure_ascii=False, sort_keys=True)

        self.assertIn("drawing-dsl", encoded)
        self.assertNotIn("html-template", encoded)

    def test_catalog_escapes_replacement_values(self) -> None:
        self.assertEqual("&lt;script&gt;x&lt;/script&gt;", fill_template("{{value}}", {"value": "<script>x</script>"}))

    def test_aud_019_catalog_supports_external_output_paths(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            manifest = render_catalog(
                self.payload,
                root / "catalog",
                build_dsl=False,
                contact_sheet=root / "all.png",
                supported_sheet=root / "supported.png",
            )
            self.assertTrue(Path(manifest["diagrams"][0]["png"]).is_absolute())
            self.assertTrue((root / "catalog" / "manifest.json").exists())
            self.assertEqual("3.0", manifest["schema_version"])
            self.assertEqual(len(DEFAULT_COMPILER_REGISTRY.kinds), manifest["coverage"]["drawing_dsl"])
            for record in manifest["diagrams"]:
                self.assertEqual("page-preview", record["profile"])
                self.assertEqual("approved", record["approval_state"])
                self.assertEqual("generator-parity", record["baseline_category"])
                self.assertTrue(Path(record["svg"]).is_file())
                self.assertTrue(Path(record["pdf"]).is_file())
                self.assertEqual(64, len(record["digests"]["svg"]))
                self.assertEqual(64, len(record["digests"]["pdf"]))
                self.assertTrue(record["registry_key"])
                self.assertTrue(record["semantic_ids"])
                self.assertEqual([], record["diagnostics"])
                self.assertEqual(64, len(record["digests"]["png"]))
                self.assertEqual([1241, 1754], record["dimensions"]["output"])

    def test_visual_baseline_requires_explicit_approval_reason(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-empty reason"):
            create_visual_baseline({"diagrams": []}, "  ")

    def test_visual_baseline_detects_semantic_and_dimension_changes(self) -> None:
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow is not installed")

        with TemporaryDirectory() as temp:
            root = Path(temp)
            baseline_png = root / "baseline.png"
            current_png = root / "current.png"
            Image.new("RGB", (20, 12), "#F6F0EA").save(baseline_png)
            Image.new("RGB", (20, 12), "#F6F0EA").save(current_png)
            record = {
                "kind": "flowchart",
                "profile": "page-preview",
                "registry_key": "flowchart@3",
                "png": str(current_png),
                "semantic_ids": ["start", "finish"],
                "dimensions": {"source": [960, 540], "output": [20, 12]},
                "content_bounds": [2, 2, 18, 10],
                "digests": {"input": "input", "svg": "svg", "pdf": "pdf", "png": "png"},
            }
            manifest = {
                "schema_version": "3.0",
                "coverage": {
                    "catalog_types": 1,
                    "drawing_dsl_v3": 1,
                    "drawing_dsl_v2": 0,
                    "html_template_baseline": 0,
                },
                "contact_sheets": [],
                "diagrams": [record],
            }
            baseline_manifest = deepcopy(manifest)
            baseline_manifest["diagrams"][0]["png"] = str(baseline_png)
            baseline = create_visual_baseline(baseline_manifest, "Approved V3 release baseline")

            self.assertTrue(compare_visual_baseline(manifest, baseline)["passed"])

            changed = deepcopy(manifest)
            changed["diagrams"][0]["semantic_ids"] = ["finish", "start"]
            changed["diagrams"][0]["dimensions"]["output"] = [21, 12]
            report = compare_visual_baseline(changed, baseline)
            self.assertFalse(report["passed"])
        self.assertTrue(any("semantic_ids changed" in issue for issue in report["issues"]))
        self.assertTrue(any("dimensions changed" in issue for issue in report["issues"]))


def parse_selection_table(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    header_index = next(
        (
            index
            for index, line in enumerate(lines)
            if line.startswith("|") and "Kind" in line and "Reference payload" in line
        ),
        None,
    )
    if header_index is None:
        raise AssertionError(f"no kind/payload selection table found in {path}")

    columns = [cell.strip() for cell in lines[header_index].strip().strip("|").split("|")]
    kind_column = columns.index("Kind")
    payload_column = columns.index("Reference payload")
    rows: dict[str, str] = {}
    for line in lines[header_index + 2 :]:
        if not line.startswith("|"):
            break
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) <= max(kind_column, payload_column):
            continue
        rows[cells[kind_column].strip("`")] = cells[payload_column].strip("`")
    return rows


class DiagramSelectionTableTests(TestCase):
    """Guard the human-facing selection tables against registry drift."""

    documents = ("references/diagrams.md", "CHEATSHEET.md")

    @classmethod
    def setUpClass(cls) -> None:
        cls.expected = {
            item["kind"]: item["source"] for item in load_catalog()["diagrams"]
        }

    def test_tables_list_every_registered_kind(self) -> None:
        for document in self.documents:
            rows = parse_selection_table(ROOT / document)
            self.assertEqual(set(DEFAULT_COMPILER_REGISTRY.kinds), set(rows), document)

    def test_tables_point_at_registered_catalog_fixtures(self) -> None:
        for document in self.documents:
            rows = parse_selection_table(ROOT / document)
            self.assertEqual(self.expected, rows, document)

    def test_referenced_fixtures_exist_on_disk(self) -> None:
        for document in self.documents:
            for kind, payload in parse_selection_table(ROOT / document).items():
                self.assertTrue((ROOT / payload).is_file(), f"{document}:{kind}")
