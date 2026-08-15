from __future__ import annotations

import csv
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any


MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_ROWS = 1000
MAX_COLUMNS = 64
SUPPORTED_KINDS = {"bar-chart", "line-chart", "candlestick", "waterfall"}
SUPPORTED_ENCODINGS = {"utf-8", "utf-8-sig"}
SUPPORTED_LOCALES = {"en-US", "en-GB", "zh-CN", "zh-TW"}
REMOTE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")


@dataclass(frozen=True)
class TabularRules:
    missing_tokens: tuple[str, ...]
    missing_policy: str
    decimal: str
    thousands: str | None


def load_tabular_chart(config_path: str | Path) -> dict[str, Any]:
    config_file = Path(config_path)
    config = json.loads(config_file.read_text(encoding="utf-8"))
    _exact_object(config, "tabular config", {"schema_version", "kind", "title", "input", "mapping", "chart"}, {"schema_version", "kind", "title", "input", "mapping"})
    if config["schema_version"] != "1.0":
        raise ValueError("tabular config schema_version must be 1.0")
    kind = config["kind"]
    if kind not in SUPPORTED_KINDS:
        raise ValueError("tabular import supports bar-chart, line-chart, candlestick, and waterfall")
    if not isinstance(config["title"], str) or not config["title"].strip():
        raise ValueError("tabular chart title must be a non-empty string")

    input_spec = config["input"]
    _exact_object(
        input_spec, "input",
        {"path", "format", "encoding", "delimiter", "header", "missing", "locale", "coercion"},
        {"path", "format", "encoding", "delimiter", "header", "missing", "locale", "coercion"},
    )
    source = _local_source(config_file, input_spec["path"])
    encoding = input_spec["encoding"]
    if encoding not in SUPPORTED_ENCODINGS:
        raise ValueError("tabular encoding must be explicit utf-8 or utf-8-sig")
    format_name = input_spec["format"]
    if format_name not in {"csv", "tsv"}:
        raise ValueError("tabular format must be csv or tsv")
    delimiter = input_spec["delimiter"]
    if not isinstance(delimiter, str) or len(delimiter) != 1 or delimiter in {"\r", "\n", '"'}:
        raise ValueError("tabular delimiter must be one explicit safe character")
    if format_name == "tsv" and delimiter != "\t":
        raise ValueError("TSV input requires an explicit tab delimiter")
    if format_name == "csv" and delimiter == "\t":
        raise ValueError("CSV input cannot use the TSV tab delimiter")
    if not isinstance(input_spec["header"], bool):
        raise ValueError("tabular header must be an explicit boolean")
    locale = input_spec["locale"]
    if locale not in SUPPORTED_LOCALES:
        raise ValueError("tabular locale is unsupported")
    rules = _rules(input_spec["missing"], input_spec["coercion"], delimiter)
    rows = _read_rows(source, encoding, delimiter)
    columns, data_rows = _columns(rows, input_spec["header"])
    if len(data_rows) > MAX_ROWS:
        raise ValueError(f"tabular input exceeds {MAX_ROWS} data rows")

    chart = config.get("chart", {})
    if not isinstance(chart, dict):
        raise ValueError("chart must be an object")
    blocked = {"schema_version", "kind", "title", "categories", "series", "periods", "contributions", "locale"}
    if set(chart) & blocked:
        raise ValueError("chart options cannot override normalized semantic fields")
    payload: dict[str, Any] = {
        "schema_version": "3.0",
        "kind": kind,
        "title": config["title"].strip(),
        "locale": locale,
        "source": source.name,
        **chart,
    }
    mapping = config["mapping"]
    if kind in {"bar-chart", "line-chart"}:
        payload.update(_series_payload(kind, mapping, columns, data_rows, rules))
    elif kind == "candlestick":
        payload["periods"] = _candlestick_payload(mapping, columns, data_rows, rules)
    else:
        payload["contributions"] = _waterfall_payload(mapping, columns, data_rows, rules)
    return payload


def _exact_object(value: Any, name: str, allowed: set[str], required: set[str]) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    unknown = sorted(set(value) - allowed)
    missing = sorted(required - set(value))
    if unknown:
        raise ValueError(f"{name} has unknown field: {unknown[0]}")
    if missing:
        raise ValueError(f"{name} is missing required field: {missing[0]}")


def _local_source(config_file: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("tabular input path must be a non-empty local path")
    if REMOTE_RE.match(value) or value.startswith("//"):
        raise ValueError("remote tabular resources are not allowed")
    path = Path(value)
    source = path if path.is_absolute() else config_file.parent / path
    if not source.is_file():
        raise ValueError("tabular input file does not exist")
    if source.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"tabular input exceeds {MAX_FILE_BYTES} bytes")
    return source


def _rules(missing: Any, coercion: Any, delimiter: str) -> TabularRules:
    _exact_object(missing, "missing", {"tokens", "policy"}, {"tokens", "policy"})
    tokens = missing["tokens"]
    if not isinstance(tokens, list) or len(tokens) > 16 or any(not isinstance(item, str) for item in tokens) or len(tokens) != len(set(tokens)):
        raise ValueError("missing tokens must be an explicit unique string array with at most 16 items")
    if missing["policy"] not in {"error", "null"}:
        raise ValueError("missing policy must be error or null")
    _exact_object(
        coercion, "coercion", {"number", "date", "decimal", "thousands"},
        {"number", "date", "decimal", "thousands"},
    )
    if coercion["number"] != "strict-decimal" or coercion["date"] != "iso-8601":
        raise ValueError("tabular coercion must use strict-decimal numbers and iso-8601 dates")
    decimal, thousands = coercion["decimal"], coercion["thousands"]
    if decimal not in {".", ","} or thousands not in {None, ".", ","} or decimal == thousands:
        raise ValueError("decimal and thousands separators are invalid or ambiguous")
    if delimiter in {decimal, thousands}:
        raise ValueError("delimiter cannot equal a declared numeric separator")
    return TabularRules(tuple(tokens), missing["policy"], decimal, thousands)


def _read_rows(source: Path, encoding: str, delimiter: str) -> list[list[str]]:
    try:
        with source.open("r", encoding=encoding, newline="") as handle:
            rows = list(csv.reader(handle, delimiter=delimiter, strict=True))
    except UnicodeError as exc:
        raise ValueError("tabular input does not match the declared encoding") from exc
    except csv.Error as exc:
        raise ValueError("tabular input is malformed") from exc
    if not rows:
        raise ValueError("tabular input is empty")
    if len(rows) > MAX_ROWS + 1:
        raise ValueError(f"tabular input exceeds {MAX_ROWS} data rows")
    width = len(rows[0])
    if width < 1 or width > MAX_COLUMNS or any(len(row) != width for row in rows):
        raise ValueError(f"tabular rows must have a consistent width between 1 and {MAX_COLUMNS}")
    for row in rows:
        for cell in row:
            if _formula_like(cell):
                raise ValueError("spreadsheet formula-like cells are not allowed")
    return rows


def _formula_like(value: str) -> bool:
    text = value.lstrip()
    if not text:
        return False
    if text[0] in {"=", "+", "@"}:
        return True
    return text.startswith("-") and bool(re.search(r"[A-Za-z_()*/+]", text[1:]))


def _columns(rows: list[list[str]], header: bool) -> tuple[dict[str | int, int], list[list[str]]]:
    if header:
        names = [item.strip() for item in rows[0]]
        if any(not item for item in names) or len(names) != len(set(names)):
            raise ValueError("tabular headers must be non-empty and unique")
        data = rows[1:]
        columns: dict[str | int, int] = {name: index for index, name in enumerate(names)}
    else:
        data = rows
        columns = {index: index for index in range(len(rows[0]))}
    if not data:
        raise ValueError("tabular input contains no data rows")
    return columns, data


def _column(columns: dict[str | int, int], value: Any, name: str) -> int:
    if value not in columns:
        raise ValueError(f"mapping {name} references an unknown column")
    return columns[value]


def _missing(value: str, rules: TabularRules, field: str) -> str | None:
    text = value.strip()
    if text in rules.missing_tokens:
        if rules.missing_policy == "error":
            raise ValueError(f"missing value is not allowed for {field}")
        return None
    return text


def _number(value: str, rules: TabularRules, field: str) -> float | None:
    text = _missing(value, rules, field)
    if text is None:
        return None
    sign = ""
    if text.startswith("-"):
        sign, text = "-", text[1:]
    if not text:
        raise ValueError(f"{field} is not an unambiguous decimal number")
    if text.count(rules.decimal) > 1:
        raise ValueError(f"{field} is not an unambiguous decimal number")
    integer, separator, fraction = text.partition(rules.decimal)
    if rules.thousands and rules.thousands in integer:
        escaped = re.escape(rules.thousands)
        if not re.fullmatch(rf"\d{{1,3}}(?:{escaped}\d{{3}})+", integer):
            raise ValueError(f"{field} has ambiguous thousands grouping")
        integer = integer.replace(rules.thousands, "")
    elif not integer.isdigit():
        raise ValueError(f"{field} is not an unambiguous decimal number")
    if separator and (not fraction or not fraction.isdigit()):
        raise ValueError(f"{field} is not an unambiguous decimal number")
    normalized = sign + integer + ("." + fraction if separator else "")
    number = float(normalized)
    if not number == number or number in {float("inf"), float("-inf")}:
        raise ValueError(f"{field} must be finite")
    return number


def _series_payload(
    kind: str,
    mapping: Any,
    columns: dict[str | int, int],
    rows: list[list[str]],
    rules: TabularRules,
) -> dict[str, Any]:
    _exact_object(mapping, "mapping", {"category", "series"}, {"category", "series"})
    category_column = _column(columns, mapping["category"], "category")
    series_specs = mapping["series"]
    if not isinstance(series_specs, list) or not 1 <= len(series_specs) <= 3:
        raise ValueError("mapping series must contain 1-3 items")
    normalized_specs = []
    for index, item in enumerate(series_specs):
        _exact_object(item, f"series[{index}]", {"id", "label", "column"}, {"id", "label", "column"})
        if any(not isinstance(item[field], str) or not item[field].strip() for field in ("id", "label")):
            raise ValueError("series id and label must be non-empty strings")
        normalized_specs.append((item, _column(columns, item["column"], f"series[{index}].column")))
    if len({item[0]["id"] for item in normalized_specs}) != len(normalized_specs):
        raise ValueError("series ids must be unique")
    categories = []
    series = [{"id": item["id"], "label": item["label"], "values": []} for item, _ in normalized_specs]
    for row_index, row in enumerate(rows, start=1):
        category = _missing(row[category_column], rules, f"row {row_index} category")
        if category is None or not category:
            raise ValueError("chart categories cannot be missing")
        categories.append(category)
        for output, (_, column) in zip(series, normalized_specs):
            value = _number(row[column], rules, f"row {row_index} {output['id']}")
            if value is None and kind != "line-chart":
                raise ValueError("only line-chart may normalize missing numerical values to null")
            output["values"].append(value)
    return {"categories": categories, "series": series}


def _candlestick_payload(
    mapping: Any,
    columns: dict[str | int, int],
    rows: list[list[str]],
    rules: TabularRules,
) -> list[dict[str, Any]]:
    fields = {"id", "date", "open", "high", "low", "close"}
    _exact_object(mapping, "mapping", fields, fields)
    positions = {field: _column(columns, mapping[field], field) for field in fields}
    result = []
    for row_index, row in enumerate(rows, start=1):
        item_id = _missing(row[positions["id"]], rules, f"row {row_index} id")
        item_date = _missing(row[positions["date"]], rules, f"row {row_index} date")
        if not item_id or not item_date or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", item_date):
            raise ValueError("candlestick id must be present and date must use ISO YYYY-MM-DD")
        item = {"id": item_id, "date": item_date}
        for field in ("open", "high", "low", "close"):
            value = _number(row[positions[field]], rules, f"row {row_index} {field}")
            if value is None:
                raise ValueError("candlestick numerical values cannot be missing")
            item[field] = value
        result.append(item)
    return result


def _waterfall_payload(
    mapping: Any,
    columns: dict[str | int, int],
    rows: list[list[str]],
    rules: TabularRules,
) -> list[dict[str, Any]]:
    _exact_object(mapping, "mapping", {"id", "label", "value", "kind"}, {"id", "label", "value"})
    positions = {field: _column(columns, column, field) for field, column in mapping.items()}
    result = []
    for row_index, row in enumerate(rows, start=1):
        item_id = _missing(row[positions["id"]], rules, f"row {row_index} id")
        label = _missing(row[positions["label"]], rules, f"row {row_index} label")
        value = _number(row[positions["value"]], rules, f"row {row_index} value")
        if not item_id or not label or value is None:
            raise ValueError("waterfall id, label, and value cannot be missing")
        item: dict[str, Any] = {"id": item_id, "label": label, "value": value}
        if "kind" in positions:
            kind = _missing(row[positions["kind"]], rules, f"row {row_index} kind")
            if kind not in {"delta", "subtotal"}:
                raise ValueError("waterfall kind must be delta or subtotal")
            item["kind"] = kind
        result.append(item)
    return result
