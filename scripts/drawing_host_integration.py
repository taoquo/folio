from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from typing import Any

from drawing.compiler import DEFAULT_COMPILER_REGISTRY
from drawing.hosting import embed_html_figure, embed_pptx_slot, verify_host


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "references" / "fixtures"
HOST_FIXTURES = FIXTURES / "hosting"


def _compile(path: Path, profile: str, theme: str = "folio"):
    payload = json.loads(path.read_text(encoding="utf-8"))
    return DEFAULT_COMPILER_REGISTRY.compile_payload(payload, profile, theme)


def build_host_integration_sources(
    output_dir: str | Path,
    *,
    theme: str = "folio",
    variant: str = "plain",
) -> dict[str, dict[str, Any]]:
    if variant == "motion":
        raise ValueError("motion is CSS-driven and cannot be used for the PPTX host integration source")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    diagrams = output / "diagrams"

    tree_fixture = FIXTURES / "minimal" / "tree.json"
    bar_fixture = FIXTURES / "minimal" / "bar-chart.json"
    timeline_fixture = FIXTURES / "minimal" / "timeline.json"
    architecture_fixture = FIXTURES / "minimal" / "architecture.json"
    line_fixture = FIXTURES / "minimal" / "line-chart.json"
    chinese_fixture = HOST_FIXTURES / "line-chart-zh.json"

    a4 = output / "host-a4-long-doc.html"
    embed_html_figure(
        _compile(tree_fixture, "embed", theme), fixture=tree_fixture,
        host_file=HOST_FIXTURES / "a4-long-doc.html", output_host=a4,
        artifact_dir=diagrams, contract_key="a4-portrait", slot="structure",
        caption="The single root keeps the structural hierarchy bounded and immediately scannable.",
        variant=variant,
    )
    embed_html_figure(
        _compile(bar_fixture, "embed", theme), fixture=bar_fixture,
        host_file=a4, output_host=a4, artifact_dir=diagrams,
        contract_key="a4-portrait", slot="data",
        caption="The initial category establishes an exact baseline for every later comparison.",
        variant=variant,
    )

    letter = output / "host-letter-document.html"
    embed_html_figure(
        _compile(timeline_fixture, "embed", theme), fixture=timeline_fixture,
        host_file=HOST_FIXTURES / "letter-document.html", output_host=letter,
        artifact_dir=diagrams, contract_key="letter-portrait", slot="milestones",
        caption="Three ordered milestones fit the shorter Letter page without compressing their labels.",
        variant=variant,
    )

    chinese = output / "host-a4-chinese.html"
    embed_html_figure(
        _compile(chinese_fixture, "embed", theme), fixture=chinese_fixture,
        host_file=HOST_FIXTURES / "a4-chinese.html", output_host=chinese,
        artifact_dir=diagrams, contract_key="a4-portrait", slot="trend",
        caption="验证通过率连续上升，并在第三阶段达到百分之百。",
        variant=variant,
    )

    deck_base = output / "host-slide-16x9-base.pptx"
    deck = output / "host-slide-16x9.pptx"
    result = subprocess.run(
        [sys.executable, str(HOST_FIXTURES / "seven-slide-deck.py"), str(deck_base)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "seven-slide deck fixture failed")
    embed_pptx_slot(
        _compile(architecture_fixture, "artifact", theme), fixture=architecture_fixture,
        host_file=deck_base, output_host=deck, artifact_dir=diagrams,
        slot="architecture", caption="The bounded component view preserves one clear system focus on the slide.",
        slide_index=3, profile="artifact", variant=variant,
    )
    embed_pptx_slot(
        _compile(line_fixture, "embed", theme), fixture=line_fixture,
        host_file=deck, output_host=deck, artifact_dir=diagrams,
        slot="trend", caption="The second point rises above the first and makes the direction immediately visible.",
        slide_index=5, profile="embed", variant=variant,
    )

    products = {
        "host-a4-long-doc": {"path": a4, "kind": "html", "host": "a4-portrait", "pages": (2, 2)},
        "host-letter-document": {"path": letter, "kind": "html", "host": "letter-portrait", "pages": (1, 1)},
        "host-a4-chinese": {"path": chinese, "kind": "html", "host": "a4-portrait", "pages": (1, 1)},
        "host-slide-16x9": {"path": deck, "kind": "pptx", "host": "slide-16x9", "slides": 7},
    }
    for item in products.values():
        item["manifests"] = verify_host(item["path"])
    deck_base.unlink(missing_ok=True)
    return products


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: drawing_host_integration.py OUTPUT_DIR")
        return 2
    products = build_host_integration_sources(argv[1])
    print(f"OK: built {len(products)} drawing host integration sources")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
