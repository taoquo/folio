#!/usr/bin/env python3
"""Product CLI for Folio."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import re
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory

from build import DIAGRAM_ARTIFACT_TARGETS, DIAGRAM_TARGETS, HOST_INTEGRATION_TARGETS, HTML_TARGETS, PPTX_TARGETS


ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = ROOT / "scripts" / "build.py"
PACKAGE_SCRIPT = ROOT / "scripts" / "package-skill.sh"
DRAWING_PROFILES = ("artifact", "embed", "page-preview")
DRAWING_FORMATS = ("svg", "png", "pdf")
DRAWING_THEMES = ("folio", "dark", "terminal")
DRAWING_SIZES = ("compact", "standard", "wide")
DRAWING_DETAILS = ("essential", "standard", "full")
DRAWING_AUDIENCES = ("executive", "general", "practitioner")
DRAWING_VARIANTS = ("plain", "sketchy", "motion")
EXIT_VALID = 0
EXIT_INVALID_INPUT = 1
EXIT_DEPENDENCY = 2
EXIT_INTERNAL = 3


class DrawingDependencyError(RuntimeError):
    pass


def _load_architecture_input(path: str, title: str | None = None):
    from diagram_models import ArchitectureDiagramSpec, load_diagram_spec
    from diagram_semantic_planning import plan_architecture_from_text

    source = Path(path)
    content = source.read_text(encoding="utf-8")
    if source.suffix.lower() == ".json":
        spec = load_diagram_spec(json.loads(content))
    else:
        spec = plan_architecture_from_text(content, title or source.stem.replace("-", " ").title())
    if not isinstance(spec, ArchitectureDiagramSpec):
        raise ValueError("raw text input is supported for architecture diagrams only")
    return spec


def _compile_drawing_input(
    path: str,
    title: str | None = None,
    profile: str = "artifact",
    theme: str = "folio",
    detail: str = "full",
    audience: str = "general",
):
    from drawing.compiler import DEFAULT_COMPILER_REGISTRY

    source = Path(path)
    if source.suffix.lower() == ".json":
        payload = json.loads(source.read_text(encoding="utf-8"))
        return DEFAULT_COMPILER_REGISTRY.compile_payload(payload, profile, theme, detail, audience)
    return DEFAULT_COMPILER_REGISTRY.compile_architecture_spec(
        _load_architecture_input(path, title), profile, theme, detail, audience
    )


def _write_json(payload: object, output: str | None) -> int:
    content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if output:
        Path(output).write_text(content, encoding="utf-8")
    else:
        print(content, end="")
    return 0


def _write_text(content: str, output: str | None) -> int:
    if output:
        Path(output).write_text(content, encoding="utf-8")
    else:
        print(content, end="" if content.endswith("\n") else "\n")
    return EXIT_VALID


def _diagram_type_records() -> list[dict[str, object]]:
    from drawing.schema_registry import list_schema_contracts

    return [
        {
            **contract.to_dict(),
            "profiles": list(DRAWING_PROFILES),
            "formats": list(DRAWING_FORMATS),
        }
        for contract in list_schema_contracts()
    ]


def _list_diagram_types(output_format: str) -> int:
    records = _diagram_type_records()
    if output_format == "json":
        return _write_json({"types": records}, None)
    for item in records:
        print(
            f"{item['kind']}\tinput {item['input_schema_version']}\t"
            f"profiles {','.join(item['profiles'])}\tformats {','.join(item['formats'])}"
        )
    return EXIT_VALID


def _init_drawing(kind: str, language: str | None, output: str | None) -> int:
    from drawing.compiler import DEFAULT_COMPILER_REGISTRY
    from drawing.schema_registry import schema_contract

    contract = schema_contract(kind)
    payload = contract.load_minimal_payload()
    if language:
        payload["language"] = language
    DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
    return _write_json(payload, output)


def _route_diagram(request_path: str | None, args) -> int:
    """Recommend one diagram kind from a semantic brief, with a route trace."""
    from drawing.semantics import route_from_dict

    if request_path:
        try:
            payload = json.loads(Path(request_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"ERROR: routing request cannot be read: {exc}", file=sys.stderr)
            return EXIT_INVALID_INPUT
        if not isinstance(payload, dict):
            print("ERROR: routing request must be an object", file=sys.stderr)
            return EXIT_INVALID_INPUT
    else:
        payload = {}
    if args.content:
        payload["content"] = args.content
    if args.audience:
        payload["audience"] = args.audience
    if args.goal:
        payload["goal"] = args.goal
    if args.pattern:
        payload["pattern_hint"] = args.pattern
    if args.kind:
        payload["kind_hint"] = args.kind
    try:
        decision = route_from_dict(payload)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_INVALID_INPUT
    record = decision.to_dict()
    if args.format == "json":
        _write_json(record, args.output)
    else:
        if not decision.routable:
            print("ERROR: no diagram kind recommended")
        else:
            print(f"OK: {decision.pattern} -> {decision.kind} (confidence {decision.confidence})")
            if decision.alternatives:
                print("alternatives: " + ", ".join(decision.alternatives))
        for step in decision.trace:
            print(f"  {step.stage}: {step.detail}")
        for item in decision.diagnostics:
            print(f"  {item.level} {item.code}: {item.message}")
    return EXIT_VALID if decision.routable else EXIT_INVALID_INPUT


def _import_chart_data(config: str, output: str | None) -> int:
    from drawing.compiler import DEFAULT_COMPILER_REGISTRY
    from drawing.tabular import load_tabular_chart

    payload = load_tabular_chart(config)
    DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
    return _write_json(payload, output)


def _import_diagram(source: str, dialect: str, output: str | None, ledger_output: str | None) -> int:
    from drawing.compiler import DEFAULT_COMPILER_REGISTRY
    from drawing.importers import load_diagram_source

    payload, ledger = load_diagram_source(source, dialect=dialect)
    DEFAULT_COMPILER_REGISTRY.compile_payload(payload)
    if ledger_output:
        _write_json(ledger.to_dict(), ledger_output)
    elif not output:
        print(json.dumps(ledger.to_dict(), ensure_ascii=False, indent=2))
    return _write_json(payload, output)


def _safe_kind(path: str) -> str | None:
    source = Path(path)
    if source.suffix.lower() != ".json":
        return "architecture"
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload.get("kind") if isinstance(payload, dict) and isinstance(payload.get("kind"), str) else None


def _diagnostic_payload(items, *, stage: str, kind: str | None):
    from drawing.validation import diagnostic_envelopes

    return diagnostic_envelopes(items, stage=stage, kind=kind)


def _validate_drawing_command(path: str, output_format: str, profile: str, theme: str = "folio") -> int:
    from drawing.validation import DrawingCompilationError, DrawingDiagnostic

    kind = _safe_kind(path)
    try:
        result = _compile_drawing_input(path, profile=profile, theme=theme)
    except DrawingCompilationError as exc:
        diagnostics = _diagnostic_payload(exc.diagnostics, stage=exc.stage, kind=kind)
        status, code, metadata = "invalid", EXIT_INVALID_INPUT, None
    except json.JSONDecodeError as exc:
        item = DrawingDiagnostic(
            "ERROR", "CLI001", f"invalid JSON at line {exc.lineno}, column {exc.colno}",
            path=f"/{exc.lineno}:{exc.colno}", hint="Fix the JSON syntax and validate again.",
        )
        diagnostics = _diagnostic_payload((item,), stage="input", kind=kind)
        status, code, metadata = "invalid", EXIT_INVALID_INPUT, None
    except OSError:
        item = DrawingDiagnostic(
            "ERROR", "CLI002", "drawing input cannot be read",
            hint="Confirm that the input exists and is readable.",
        )
        diagnostics = _diagnostic_payload((item,), stage="input", kind=kind)
        status, code, metadata = "invalid", EXIT_INVALID_INPUT, None
    except ValueError as exc:
        item = DrawingDiagnostic("ERROR", "CLI003", str(exc), hint="Correct the authoring input and validate again.")
        diagnostics = _diagnostic_payload((item,), stage="input", kind=kind)
        status, code, metadata = "invalid", EXIT_INVALID_INPUT, None
    else:
        kind = result.kind
        diagnostics = _diagnostic_payload(result.diagnostics, stage="quality", kind=kind)
        status, code = "valid", EXIT_VALID
        metadata = result.metadata.to_dict() if result.metadata else None

    payload = {"status": status, "kind": kind, "profile": profile, "diagnostics": diagnostics, "metadata": metadata}
    if output_format == "json":
        _write_json(payload, None)
    else:
        for item in diagnostics:
            target = f" [{','.join(item['related_ids'])}]" if item["related_ids"] else ""
            print(f"{item['severity']} {item['code']}{target}: {item['message']}")
        print(f"OK: {kind} drawing is valid" if status == "valid" else f"ERROR: {kind or 'unknown'} drawing is invalid")
    return code


def _render_compilation(
    result, output: Path, output_format: str, width: int = 1920, variant: str = "plain"
) -> None:
    from diagram_export import export_pdf, export_png
    from renderers.svg import render_svg

    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix="folio-render-", dir=output.parent) as temp:
            temp_root = Path(temp)
            svg_path = temp_root / "drawing.svg"
            svg_path.write_text(render_svg(result.scene, result.profile, variant=variant), encoding="utf-8")
            artifact = svg_path
            if output_format == "png":
                artifact = temp_root / "drawing.png"
                export_png(
                    svg_path, artifact, width, profile=result.profile,
                    title=result.plan.title, language=result.plan.language,
                    background=result.scene.background,
                )
            elif output_format == "pdf":
                artifact = temp_root / "drawing.pdf"
                export_pdf(
                    svg_path, artifact, result.plan.title, result.plan.language,
                    result.profile, result.scene.background,
                )
            artifact.replace(output)
    except (OSError, RuntimeError) as exc:
        raise DrawingDependencyError("drawing export dependency or file operation failed") from exc


def _batch_sources(input_path: Path, output_dir: Path) -> list[tuple[str, Path]]:
    if input_path.is_file():
        return [(input_path.name, input_path)]
    if not input_path.is_dir():
        raise ValueError("batch input must be a JSON file or directory")
    output_resolved = output_dir.resolve()
    sources = []
    for path in input_path.rglob("*.json"):
        try:
            path.resolve().relative_to(output_resolved)
        except ValueError:
            sources.append((path.relative_to(input_path).as_posix(), path))
    return sorted(sources, key=lambda item: item[0])


def _batch_output_name(relative: str, output_format: str) -> str:
    stem = Path(relative).with_suffix("").as_posix().replace("/", "--")
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-._") or "drawing"
    digest = sha256(relative.encode("utf-8")).hexdigest()[:8]
    return f"{slug}-{digest}.{output_format}"


def _write_batch_report(report: dict[str, object], report_format: str, output: str | None, exit_code: int) -> int:
    if report_format == "json":
        content = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    else:
        lines = [
            f"{item['status'].upper()}: {item['input']}" + (f" -> {item['output']}" if item.get("output") else "")
            for item in report["items"]
        ]
        lines.append(
            f"{'OK' if exit_code == EXIT_VALID else 'ERROR'}: "
            f"{report.get('rendered', 0)} rendered, {report.get('failed', 0)} failed"
        )
        content = "\n".join(lines) + "\n"
    _write_text(content, output)
    return exit_code


def _batch_render_drawings(
    input_path: str,
    output_dir: str,
    output_format: str,
    profile: str,
    fail_fast: bool,
    report_format: str,
    report_output: str | None,
    theme: str = "folio",
    size: str = "standard",
    detail: str = "full",
    audience: str = "general",
    variant: str = "plain",
) -> int:
    from drawing.validation import DrawingCompilationError, DrawingDiagnostic
    from drawing.output import size_export_width

    width = size_export_width(size)
    destination = Path(output_dir)
    try:
        sources = _batch_sources(Path(input_path), destination)
    except (OSError, ValueError) as exc:
        item = DrawingDiagnostic("ERROR", "CLI010", str(exc), hint="Provide a readable JSON file or directory.")
        report = {"status": "invalid", "items": [], "diagnostics": _diagnostic_payload((item,), stage="input", kind=None)}
        return _write_batch_report(report, report_format, report_output, EXIT_INVALID_INPUT)
    if not sources:
        item = DrawingDiagnostic("ERROR", "CLI011", "batch input contains no JSON files")
        report = {"status": "invalid", "items": [], "diagnostics": _diagnostic_payload((item,), stage="input", kind=None)}
        return _write_batch_report(report, report_format, report_output, EXIT_INVALID_INPUT)

    destination.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    exit_code = EXIT_VALID
    for relative, source in sources:
        kind = _safe_kind(str(source))
        output_name = _batch_output_name(relative, output_format)
        output = destination / output_name
        try:
            result = _compile_drawing_input(
                str(source), profile=profile, theme=theme, detail=detail, audience=audience
            )
            _render_compilation(result, output, output_format, width, variant)
        except DrawingCompilationError as exc:
            output.unlink(missing_ok=True)
            records.append({
                "input": relative, "output": None, "kind": kind, "status": "invalid",
                "diagnostics": _diagnostic_payload(exc.diagnostics, stage=exc.stage, kind=kind),
            })
            exit_code = max(exit_code, EXIT_INVALID_INPUT)
        except (json.JSONDecodeError, ValueError):
            output.unlink(missing_ok=True)
            item = DrawingDiagnostic(
                "ERROR", "CLI012", "invalid drawing input",
                hint="Run validate-drawing on this input for detailed diagnostics.",
            )
            records.append({
                "input": relative, "output": None, "kind": kind, "status": "invalid",
                "diagnostics": _diagnostic_payload((item,), stage="input", kind=kind),
            })
            exit_code = max(exit_code, EXIT_INVALID_INPUT)
        except DrawingDependencyError:
            output.unlink(missing_ok=True)
            item = DrawingDiagnostic(
                "ERROR", "CLI013", "drawing dependency or output operation failed",
                hint="Run folio doctor and confirm that the output directory is writable.",
            )
            records.append({
                "input": relative, "output": None, "kind": kind, "status": "dependency-error",
                "diagnostics": _diagnostic_payload((item,), stage="export", kind=kind),
            })
            exit_code = EXIT_DEPENDENCY
        else:
            records.append({
                "input": relative, "output": output_name, "kind": result.kind, "status": "rendered",
                "diagnostics": _diagnostic_payload(result.diagnostics, stage="quality", kind=result.kind),
            })
        if fail_fast and exit_code != EXIT_VALID:
            break

    report = {
        "status": "ok" if exit_code == EXIT_VALID else "failed",
        "profile": profile,
        "format": output_format,
        "size": size,
        "detail": detail,
        "audience": audience,
        "variant": variant,
        "total": len(records),
        "rendered": sum(item["status"] == "rendered" for item in records),
        "failed": sum(item["status"] != "rendered" for item in records),
        "items": records,
        "diagnostics": [],
    }
    return _write_batch_report(report, report_format, report_output, exit_code)


def _list_drawing_hosts(output_format: str) -> int:
    from drawing.hosting import list_host_contracts

    records = [item.to_dict() for item in list_host_contracts()]
    if output_format == "json":
        return _write_json({"hosts": records}, None)
    for item in records:
        print(
            f"{item['key']}\t{item['medium']}\t{item['width']}x{item['height']} {item['unit']}\t"
            f"profile {item['default_profile']}\tartifact {item['artifact_format']}"
        )
    return EXIT_VALID


def _embed_drawing_host(args: argparse.Namespace) -> int:
    from drawing.hosting import embed_html_figure, embed_pptx_slot, host_contract

    contract = host_contract(args.host_contract)
    profile = args.profile or contract.default_profile
    result = _compile_drawing_input(args.fixture, profile=profile, theme=getattr(args, "theme", "folio"))
    variant = getattr(args, "variant", "plain")
    artifact_dir = args.artifact_dir or str(Path(args.output_host).parent / f"{Path(args.output_host).stem}-diagrams")
    if contract.medium in {"html-print", "html-responsive"}:
        manifest = embed_html_figure(
            result,
            fixture=args.fixture,
            host_file=args.host_file,
            output_host=args.output_host,
            artifact_dir=artifact_dir,
            contract_key=contract.key,
            slot=args.slot,
            caption=args.caption,
            profile=profile,
            variant=variant,
        )
    else:
        try:
            manifest = embed_pptx_slot(
                result,
                fixture=args.fixture,
                host_file=args.host_file,
                output_host=args.output_host,
                artifact_dir=artifact_dir,
                slot=args.slot,
                caption=args.caption,
                slide_index=args.slide_index,
                profile=profile,
                variant=variant,
            )
        except RuntimeError as exc:
            raise DrawingDependencyError("drawing host export dependency failed") from exc
    if args.format == "json":
        return _write_json(manifest, None)
    print(f"OK: embedded {result.kind} into {args.output_host} slot {args.slot}")
    return EXIT_VALID


def _verify_drawing_host(path: str, output_format: str) -> int:
    from drawing.hosting import verify_host

    manifests = verify_host(path)
    payload = {"status": "valid", "host": Path(path).name, "diagrams": manifests}
    if output_format == "json":
        return _write_json(payload, None)
    print(f"OK: {Path(path).name}: {len(manifests)} hosted diagram(s) verified")
    return EXIT_VALID


def _check_drawing(
    path: str,
    title: str | None,
    explain: bool,
    profile: str = "artifact",
    theme: str = "folio",
) -> int:
    result = _compile_drawing_input(path, title, profile, theme)
    drawing = result.plan
    diagnostics = result.diagnostics
    if explain:
        for line in getattr(drawing, "explanation", ()):
            print(f"OK: {line}")
    if not diagnostics:
        print("OK: drawing plan and resolved scene passed validation")
        return 0
    for item in diagnostics:
        print(str(item))
    return 1 if any(item.level == "ERROR" for item in diagnostics) else 0


def _drawing_metrics(
    path: str,
    title: str | None,
    output: str | None,
    profile: str = "artifact",
    theme: str = "folio",
) -> int:
    result = _compile_drawing_input(path, title, profile, theme)
    return _write_json(result.metrics.to_dict(), output)


def _run_build(args: list[str]) -> int:
    result = subprocess.run([sys.executable, str(BUILD_SCRIPT), *args], cwd=ROOT)
    return result.returncode


def _run_package() -> int:
    result = subprocess.run(["bash", str(PACKAGE_SCRIPT)], cwd=ROOT)
    return result.returncode


def _print_group(label: str, names: list[str]) -> None:
    print(f"{label}:")
    for name in names:
        print(f"  {name}")


def list_targets() -> int:
    _print_group("HTML targets", sorted(HTML_TARGETS))
    _print_group("Diagram targets", sorted(DIAGRAM_TARGETS))
    _print_group("Artifact targets", sorted(DIAGRAM_ARTIFACT_TARGETS))
    _print_group("Slide targets", sorted(PPTX_TARGETS))
    _print_group("Host integration targets", sorted(HOST_INTEGRATION_TARGETS))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build, verify, package, and diagnose Folio.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_cmd = subparsers.add_parser("build", help="Build all targets or one named target.")
    build_cmd.add_argument("target", nargs="?", help="Optional build target.")

    verify_cmd = subparsers.add_parser("verify", help="Verify all targets or one named target.")
    verify_cmd.add_argument("target", nargs="?", help="Optional verify target.")

    subparsers.add_parser("check", help="Run CSS and token checks.")
    subparsers.add_parser("doctor", help="Check local PDF/PPTX/diagram dependencies.")
    subparsers.add_parser("package", help="Build dist/folio.zip.")
    subparsers.add_parser("list-targets", help="List known build targets.")

    list_types = subparsers.add_parser("list-diagram-types", help="List registered authoring contracts.")
    list_types.add_argument("--format", choices=("text", "json"), default="text")

    init_drawing = subparsers.add_parser("init-drawing", help="Write a minimal valid authoring fixture.")
    init_drawing.add_argument("kind", help="Registered diagram kind.")
    init_drawing.add_argument("--language", help="Explicit output language code.")
    init_drawing.add_argument("--output", help="Optional JSON output path.")

    route_diagram = subparsers.add_parser("route-diagram", help="Recommend one diagram kind from a semantic brief.")
    route_diagram.add_argument("request", nargs="?", help="Optional routing request JSON path.")
    route_diagram.add_argument("--content", help="Content brief text used for keyword scoring.")
    route_diagram.add_argument("--audience", help="Audience: executive, general, or practitioner.")
    route_diagram.add_argument("--goal", help="Goal: compare, convince, explain, or track.")
    route_diagram.add_argument("--pattern", help="Explicit semantic pattern hint.")
    route_diagram.add_argument("--kind", help="Explicit diagram kind hint.")
    route_diagram.add_argument("--output", help="Optional JSON output path.")
    route_diagram.add_argument("--format", choices=("text", "json"), default="text")

    import_chart = subparsers.add_parser("import-chart-data", help="Normalize an explicit local CSV/TSV config into typed chart JSON.")
    import_chart.add_argument("config", help="Tabular import config JSON.")
    import_chart.add_argument("--output", help="Optional normalized chart JSON output path.")

    import_diagram = subparsers.add_parser("import-diagram", help="Convert an explicit local Mermaid or draw.io source into typed diagram JSON.")
    import_diagram.add_argument("source", help="Local Mermaid (.mmd) or draw.io (.drawio/.xml) file.")
    import_diagram.add_argument("--dialect", choices=("auto", "mermaid", "drawio"), default="auto")
    import_diagram.add_argument("--output", help="Optional diagram JSON output path.")
    import_diagram.add_argument("--ledger-output", help="Optional fidelity ledger JSON output path.")

    validate_drawing = subparsers.add_parser("validate-drawing", help="Validate through the production compiler boundary.")
    validate_drawing.add_argument("fixture", help="Registered diagram JSON or architecture raw text fixture.")
    validate_drawing.add_argument("--format", choices=("text", "json"), default="text")
    validate_drawing.add_argument("--profile", choices=DRAWING_PROFILES, default="artifact")
    validate_drawing.add_argument("--theme", choices=DRAWING_THEMES, default="folio", help="Named theme profile.")

    batch_render = subparsers.add_parser("batch-render-drawings", help="Render a deterministic file or directory batch.")
    batch_render.add_argument("input", help="JSON file or directory containing JSON fixtures.")
    batch_render.add_argument("--output-dir", required=True)
    batch_render.add_argument("--format", choices=DRAWING_FORMATS, default="svg")
    batch_render.add_argument("--profile", choices=DRAWING_PROFILES, default="artifact")
    batch_render.add_argument("--theme", choices=DRAWING_THEMES, default="folio", help="Named theme profile.")
    batch_render.add_argument("--size", choices=DRAWING_SIZES, default="standard", help="PNG export size knob.")
    batch_render.add_argument("--detail", choices=DRAWING_DETAILS, default="full", help="Decoration detail knob.")
    batch_render.add_argument("--audience", choices=DRAWING_AUDIENCES, default="general", help="Audience type-ramp knob.")
    batch_render.add_argument("--variant", choices=DRAWING_VARIANTS, default="plain", help="Render variant.")
    batch_render.add_argument("--fail-fast", action="store_true")
    batch_render.add_argument("--report-format", choices=("text", "json"), default="text")
    batch_render.add_argument("--report-output")

    list_hosts = subparsers.add_parser("list-drawing-hosts", help="List document and slide host contracts.")
    list_hosts.add_argument("--format", choices=("text", "json"), default="text")

    embed = subparsers.add_parser("embed-drawing", help="Compile and insert a drawing into an explicit HTML or PPTX slot.")
    embed.add_argument("fixture", help="Registered diagram JSON fixture.")
    embed.add_argument("--host-contract", required=True, choices=("a4-portrait", "letter-portrait", "slide-16x9", "responsive-html"))
    embed.add_argument("--host-file", required=True, help="HTML or PPTX file containing an explicit Folio diagram slot.")
    embed.add_argument("--output-host", required=True, help="Atomic output HTML or PPTX path.")
    embed.add_argument("--artifact-dir", help="Directory for the traced SVG or PNG artifact.")
    embed.add_argument("--slot", required=True, help="Exact figure or slide slot id.")
    embed.add_argument("--caption", required=True, help="Insight-led caption; must not repeat the title.")
    embed.add_argument("--profile", choices=DRAWING_PROFILES)
    embed.add_argument("--theme", choices=DRAWING_THEMES, default="folio", help="Named theme profile.")
    embed.add_argument("--variant", choices=DRAWING_VARIANTS, default="plain", help="Render variant; motion is rejected for PPTX hosts.")
    embed.add_argument("--slide-index", type=int, default=1, help="One-based slide index for PPTX hosts.")
    embed.add_argument("--format", choices=("text", "json"), default="text", help="Command result format.")

    verify_host = subparsers.add_parser("verify-drawing-host", help="Check hosted diagram sources, artifacts, captions, fit, and fallbacks.")
    verify_host.add_argument("host", help="Generated HTML or PPTX host.")
    verify_host.add_argument("--format", choices=("text", "json"), default="text")

    catalog = subparsers.add_parser("diagram-catalog", help="Render the registered diagram review catalog.")
    catalog.add_argument("--fixture")
    catalog.add_argument("--output-dir")
    catalog.add_argument("--skip-dsl-build", action="store_true")
    catalog.add_argument("--contact-sheet")
    catalog.add_argument("--supported-sheet")
    baseline_group = catalog.add_mutually_exclusive_group()
    baseline_group.add_argument("--baseline")
    baseline_group.add_argument("--write-baseline")
    catalog.add_argument("--approval-reason")
    catalog.add_argument("--baseline-report")

    for name, help_text in (
        ("draw-semantic", "Compile a registered diagram fixture to semantic JSON."),
        ("draw-plan", "Compile a registered diagram fixture to plan JSON."),
        ("draw-scene", "Compile a registered diagram fixture to ResolvedScene JSON."),
        ("draw-layout", "Compile a drawing fixture to layout geometry JSON."),
    ):
        command = subparsers.add_parser(name, help=help_text)
        command.add_argument("fixture", help="Registered diagram JSON or architecture raw text fixture.")
        command.add_argument("--title", help="Title for raw text fixtures.")
        command.add_argument("--output", help="Optional JSON output path.")
        command.add_argument("--explain-drawing", action="store_true", help="Include deterministic planning reasons.")
        command.add_argument("--profile", choices=DRAWING_PROFILES, default="artifact")
        command.add_argument("--theme", choices=DRAWING_THEMES, default="folio", help="Named theme profile.")

    drawing_check = subparsers.add_parser("check-drawing", help="Run semantic, grammar, geometry, and taste diagnostics.")
    drawing_check.add_argument("fixture", help="Registered diagram JSON or architecture raw text fixture.")
    drawing_check.add_argument("--title", help="Title for raw text fixtures.")
    drawing_check.add_argument("--explain-drawing", action="store_true", help="Print deterministic planning reasons.")
    drawing_check.add_argument("--profile", choices=DRAWING_PROFILES, default="artifact")
    drawing_check.add_argument("--theme", choices=DRAWING_THEMES, default="folio", help="Named theme profile.")

    metrics = subparsers.add_parser("draw-metrics", help="Output deterministic drawing regression metrics.")
    metrics.add_argument("fixture", help="Registered diagram JSON or architecture raw text fixture.")
    metrics.add_argument("--title", help="Title for raw text fixtures.")
    metrics.add_argument("--output", help="Optional JSON output path.")
    metrics.add_argument("--profile", choices=DRAWING_PROFILES, default="artifact")
    metrics.add_argument("--theme", choices=DRAWING_THEMES, default="folio", help="Named theme profile.")

    migrate = subparsers.add_parser("migrate-drawing", help="Migrate a V1 DrawingPlan JSON to V2.")
    migrate.add_argument("fixture", help="V1 or V2 DrawingPlan JSON.")
    migrate.add_argument("--output", help="Optional JSON output path.")

    schema = subparsers.add_parser("validate-drawing-schema", help="Validate a DrawingPlan against the V2 authoring contract.")
    schema.add_argument("fixture", help="DrawingPlan JSON.")

    bundle = subparsers.add_parser("bundle-drawing", help="Create an explicit overview/detail DrawingBundle.")
    bundle.add_argument("fixture", help="Architecture DrawingPlan JSON.")
    bundle.add_argument("--output", help="Optional JSON output path.")

    render = subparsers.add_parser("render-drawing", help="Render a drawing as SVG, PNG, or PDF.")
    render.add_argument("fixture", help="Registered diagram fixture or architecture raw text.")
    render.add_argument("--title", help="Title for raw text fixtures.")
    render.add_argument("--format", choices=DRAWING_FORMATS, default="svg")
    render.add_argument("--profile", choices=DRAWING_PROFILES, default="artifact")
    render.add_argument("--theme", choices=DRAWING_THEMES, default="folio", help="Named theme profile.")
    render.add_argument("--size", choices=DRAWING_SIZES, default="standard", help="PNG export size knob.")
    render.add_argument("--detail", choices=DRAWING_DETAILS, default="full", help="Decoration detail knob.")
    render.add_argument("--audience", choices=DRAWING_AUDIENCES, default="general", help="Audience type-ramp knob.")
    render.add_argument("--variant", choices=DRAWING_VARIANTS, default="plain", help="Render variant: plain, sketchy, or motion.")
    render.add_argument("--output", required=True, help="Output artifact path.")

    review = subparsers.add_parser("review-drawing", help="Write inspectable JSON and visual review artifacts.")
    review.add_argument("fixture", help="Registered diagram fixture or architecture raw text.")
    review.add_argument("--title", help="Title for raw text fixtures.")
    review.add_argument("--output-dir", required=True, help="Review bundle directory.")
    review.add_argument("--baseline", help="Optional baseline PNG for perceptual diff.")
    review.add_argument("--profile", choices=DRAWING_PROFILES, default="artifact")
    review.add_argument("--theme", choices=DRAWING_THEMES, default="folio", help="Named theme profile.")
    review.add_argument("--variant", choices=DRAWING_VARIANTS, default="plain", help="Render variant for the bundle SVG.")

    return parser


def _main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv[1:])

    if args.command == "build":
        return _run_build([args.target] if args.target else [])
    if args.command == "verify":
        command = ["--verify"]
        if args.target:
            command.append(args.target)
        return _run_build(command)
    if args.command == "check":
        return _run_build(["--check"])
    if args.command == "doctor":
        return _run_build(["--doctor"])
    if args.command == "package":
        return _run_package()
    if args.command == "list-targets":
        return list_targets()
    if args.command == "list-diagram-types":
        return _list_diagram_types(args.format)
    if args.command == "init-drawing":
        return _init_drawing(args.kind, args.language, args.output)
    if args.command == "route-diagram":
        return _route_diagram(args.request, args)
    if args.command == "import-chart-data":
        return _import_chart_data(args.config, args.output)
    if args.command == "import-diagram":
        return _import_diagram(args.source, args.dialect, args.output, args.ledger_output)
    if args.command == "validate-drawing":
        return _validate_drawing_command(args.fixture, args.format, args.profile, args.theme)
    if args.command == "batch-render-drawings":
        return _batch_render_drawings(
            args.input, args.output_dir, args.format, args.profile,
            args.fail_fast, args.report_format, args.report_output, args.theme,
            args.size, args.detail, args.audience, args.variant,
        )
    if args.command == "list-drawing-hosts":
        return _list_drawing_hosts(args.format)
    if args.command == "embed-drawing":
        return _embed_drawing_host(args)
    if args.command == "verify-drawing-host":
        return _verify_drawing_host(args.host, args.format)
    if args.command == "diagram-catalog":
        from diagram_catalog import main as diagram_catalog_main

        forwarded: list[str] = []
        for flag, value in (
            ("--fixture", args.fixture),
            ("--output-dir", args.output_dir),
            ("--contact-sheet", args.contact_sheet),
            ("--supported-sheet", args.supported_sheet),
            ("--baseline", args.baseline),
            ("--write-baseline", args.write_baseline),
            ("--approval-reason", args.approval_reason),
            ("--baseline-report", args.baseline_report),
        ):
            if value:
                forwarded.extend((flag, value))
        if args.skip_dsl_build:
            forwarded.append("--skip-dsl-build")
        return diagram_catalog_main(forwarded)
    if args.command == "draw-plan":
        result = _compile_drawing_input(args.fixture, args.title, args.profile, args.theme)
        drawing = result.plan
        payload = drawing.to_dict()
        if not args.explain_drawing:
            payload.pop("explanation", None)
        return _write_json(payload, args.output)
    if args.command == "draw-semantic":
        result = _compile_drawing_input(args.fixture, args.title, args.profile, args.theme)
        semantic = result.semantic
        if semantic is None:
            raise ValueError("A handwritten DrawingPlan has no upstream SemanticDiagram")
        return _write_json(semantic.to_dict(), args.output)
    if args.command == "draw-scene":
        result = _compile_drawing_input(args.fixture, args.title, args.profile, args.theme)
        return _write_json(result.scene.to_dict(), args.output)
    if args.command == "draw-layout":
        result = _compile_drawing_input(args.fixture, args.title, args.profile, args.theme)
        return _write_json(asdict(result.layout), args.output)
    if args.command == "check-drawing":
        return _check_drawing(args.fixture, args.title, args.explain_drawing, args.profile, args.theme)
    if args.command == "draw-metrics":
        return _drawing_metrics(args.fixture, args.title, args.output, args.profile, args.theme)
    if args.command == "migrate-drawing":
        from drawing.schema import migrate_v1_payload

        payload = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
        return _write_json(migrate_v1_payload(payload), args.output)
    if args.command == "validate-drawing-schema":
        from drawing.schema import normalize_plan_payload

        normalize_plan_payload(json.loads(Path(args.fixture).read_text(encoding="utf-8")))
        print("OK: drawing input conforms to schema version 2.0")
        return 0
    if args.command == "bundle-drawing":
        from drawing.bundle import bundle_drawing
        from drawing.models import DrawingPlan

        payload = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
        return _write_json(bundle_drawing(DrawingPlan.from_dict(payload)).to_dict(), args.output)
    if args.command == "render-drawing":
        from drawing.output import size_export_width

        result = _compile_drawing_input(
            args.fixture, args.title, args.profile, args.theme, args.detail, args.audience
        )
        output = Path(args.output)
        if args.profile == "page-preview" and args.size != "standard":
            print("WARNING: page-preview renders a fixed A4 raster; --size is ignored")
        if args.variant == "motion" and args.format != "svg":
            print("WARNING: motion is CSS-driven; static PNG and PDF exports degrade to plain")
        _render_compilation(result, output, args.format, size_export_width(args.size), args.variant)
        print(f"OK: wrote {args.format.upper()} to {output}")
        return 0
    if args.command == "review-drawing":
        from drawing.review import write_review_bundle

        result = _compile_drawing_input(args.fixture, args.title, args.profile, args.theme)
        if args.variant == "motion":
            print("WARNING: motion is CSS-driven; the bundle PNG and PDF degrade to plain")
        write_review_bundle(
            result.semantic,
            result.plan,
            result.layout,
            result.scene,
            args.output_dir,
            args.baseline,
            diagnostics=result.diagnostics,
            metrics=result.metrics,
            profile=result.profile,
            theme=result.theme,
            variant=args.variant,
            normalized_input=result.normalized_input,
            compilation_metadata=result.metadata,
        )
        print(f"OK: wrote drawing review bundle to {args.output_dir}")
        return 0

    parser.print_help()
    return 2


def main(argv: list[str]) -> int:
    from drawing.validation import DrawingCompilationError

    try:
        return _main(argv)
    except DrawingCompilationError as exc:
        for item in exc.diagnostics:
            print(str(item))
        return 1
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return EXIT_INVALID_INPUT
    except (DrawingDependencyError, OSError):
        print("ERROR: drawing dependency or file operation failed")
        return EXIT_DEPENDENCY
    except Exception:
        print("ERROR: internal Folio command failure")
        return EXIT_INTERNAL


if __name__ == "__main__":
    sys.exit(main(sys.argv))
