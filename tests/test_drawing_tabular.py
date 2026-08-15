import codecs
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from drawing.compiler import DEFAULT_COMPILER_REGISTRY
from drawing.tabular import MAX_ROWS, load_tabular_chart


BASE_INPUT = {
    "format": "csv",
    "encoding": "utf-8",
    "delimiter": ",",
    "header": True,
    "missing": {"tokens": ["", "NA"], "policy": "error"},
    "locale": "en-US",
    "coercion": {"number": "strict-decimal", "date": "iso-8601", "decimal": ".", "thousands": None},
}


class DrawingTabularTests(TestCase):
    def test_maintained_csv_and_cjk_tsv_fixtures_compile_deterministically(self) -> None:
        for name in ("bar-import.json", "line-zh-import.json"):
            path = ROOT / "references" / "fixtures" / "tabular" / name
            with self.subTest(name=name):
                first = load_tabular_chart(path)
                second = load_tabular_chart(path)
                self.assertEqual(first, second)
                result = DEFAULT_COMPILER_REGISTRY.compile_payload(first)
                self.assertEqual(first["kind"], result.kind)
        self.assertIsNone(load_tabular_chart(ROOT / "references" / "fixtures" / "tabular" / "line-zh-import.json")["series"][0]["values"][1])

    def test_utf8_bom_headerless_and_explicit_column_indexes(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "data.csv").write_bytes(codecs.BOM_UTF8 + "A,1\nB,2\n".encode("utf-8"))
            config = self._bar_config("data.csv")
            config["input"].update(encoding="utf-8-sig", header=False)
            config["mapping"] = {
                "category": 0,
                "series": [{"id": "value", "label": "Value", "column": 1}],
            }
            path = root / "config.json"
            path.write_text(json.dumps(config), encoding="utf-8")

            payload = load_tabular_chart(path)
            self.assertEqual(["A", "B"], payload["categories"])
            self.assertEqual([1.0, 2.0], payload["series"][0]["values"])

    def test_remote_formula_ambiguous_missing_and_duplicate_header_fail_closed(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            cases = []

            remote = self._bar_config("https://example.com/data.csv")
            cases.append(("remote", remote, "remote"))

            (root / "formula.csv").write_text("Category,Value\nA,=1+2\n", encoding="utf-8")
            cases.append(("formula", self._bar_config("formula.csv"), "formula"))

            (root / "ambiguous.csv").write_text("Category;Value\nA;1,23\n", encoding="utf-8")
            ambiguous = self._bar_config("ambiguous.csv")
            ambiguous["input"].update(delimiter=";", format="csv")
            ambiguous["input"]["coercion"].update(decimal=".", thousands=",")
            cases.append(("ambiguous", ambiguous, "ambiguous"))

            (root / "missing.csv").write_text("Category,Value\nA,NA\n", encoding="utf-8")
            cases.append(("missing", self._bar_config("missing.csv"), "missing"))

            (root / "duplicate.csv").write_text("Category,Category\nA,1\n", encoding="utf-8")
            cases.append(("duplicate", self._bar_config("duplicate.csv"), "headers"))

            for name, config, message in cases:
                path = root / f"{name}.json"
                path.write_text(json.dumps(config), encoding="utf-8")
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, message):
                    load_tabular_chart(path)

    def test_candlestick_waterfall_and_resource_bound_compile(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "candles.csv").write_text(
                "Id,Date,Open,High,Low,Close\nd1,2026-08-01,10,12,9,11\n",
                encoding="utf-8",
            )
            candle = self._config("candlestick", "candles.csv")
            candle["mapping"] = {field: field.title() for field in ("id", "date", "open", "high", "low", "close")}
            candle_path = root / "candle.json"
            candle_path.write_text(json.dumps(candle), encoding="utf-8")
            self.assertEqual("candlestick", DEFAULT_COMPILER_REGISTRY.compile_payload(load_tabular_chart(candle_path)).kind)

            (root / "waterfall.csv").write_text(
                "Id,Label,Value,Kind\na,Gain,2,delta\ns,Subtotal,12,subtotal\n",
                encoding="utf-8",
            )
            waterfall = self._config("waterfall", "waterfall.csv")
            waterfall["mapping"] = {"id": "Id", "label": "Label", "value": "Value", "kind": "Kind"}
            waterfall["chart"] = {"start": 10, "end": 12}
            waterfall_path = root / "waterfall.json"
            waterfall_path.write_text(json.dumps(waterfall), encoding="utf-8")
            self.assertEqual("waterfall", DEFAULT_COMPILER_REGISTRY.compile_payload(load_tabular_chart(waterfall_path)).kind)

            rows = "Category,Value\n" + "\n".join(f"C{i},{i}" for i in range(MAX_ROWS + 1)) + "\n"
            (root / "large.csv").write_text(rows, encoding="utf-8")
            large = self._bar_config("large.csv")
            large_path = root / "large.json"
            large_path.write_text(json.dumps(large), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "exceeds"):
                load_tabular_chart(large_path)

    def _config(self, kind: str, filename: str) -> dict:
        return {
            "schema_version": "1.0",
            "kind": kind,
            "title": "Imported chart",
            "input": {"path": filename, **json.loads(json.dumps(BASE_INPUT))},
            "mapping": {},
        }

    def _bar_config(self, filename: str) -> dict:
        config = self._config("bar-chart", filename)
        config["mapping"] = {
            "category": "Category",
            "series": [{"id": "value", "label": "Value", "column": "Value"}],
        }
        return config
