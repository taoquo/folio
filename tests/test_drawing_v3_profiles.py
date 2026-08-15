import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from PIL import Image
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from diagram_export import export_pdf, export_png
from drawing.compiler import DEFAULT_COMPILER_REGISTRY
from renderers.svg import render_svg


class DrawingV3OutputProfileTests(TestCase):
    def test_three_profiles_export_svg_png_and_pdf(self) -> None:
        payload = json.loads((ROOT / "references" / "fixtures" / "flowchart" / "linear.json").read_text())

        with TemporaryDirectory() as temp:
            output = Path(temp)
            for profile in ("artifact", "embed", "page-preview"):
                with self.subTest(profile=profile):
                    result = DEFAULT_COMPILER_REGISTRY.compile_payload(payload, profile)
                    svg_path = output / f"{profile}.svg"
                    png_path = output / f"{profile}.png"
                    pdf_path = output / f"{profile}.pdf"
                    svg_path.write_text(render_svg(result.scene, result.profile), encoding="utf-8")

                    export_png(
                        svg_path, png_path, profile=result.profile,
                        title=result.plan.title, language=result.plan.language,
                    )
                    export_pdf(svg_path, pdf_path, result.plan.title, result.plan.language, result.profile)

                    self.assertGreater(svg_path.stat().st_size, 100)
                    with Image.open(png_path) as image:
                        self.assertEqual(1241 if profile == "page-preview" else 1920, image.width)
                        if profile == "page-preview":
                            self.assertEqual(1754, image.height)
                        self.assertGreater(image.height, 0)
                    reader = PdfReader(str(pdf_path))
                    self.assertEqual(1, len(reader.pages))
                    page = reader.pages[0]
                    width = float(page.mediabox.width)
                    height = float(page.mediabox.height)
                    if profile == "page-preview":
                        self.assertAlmostEqual(595.28, width, delta=1)
                        self.assertAlmostEqual(841.89, height, delta=1)
                    else:
                        self.assertAlmostEqual(720, width, delta=1)
                        self.assertAlmostEqual(405, height, delta=1)
