import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from PIL import Image, ImageChops
from pypdf import PdfReader
from pptx import Presentation


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from drawing.hosting import host_contract, verify_hosted_html, verify_hosted_pptx
from drawing_host_integration import build_host_integration_sources


BUILD_SPEC = importlib.util.spec_from_file_location("folio_host_build", SCRIPTS / "build.py")
build = importlib.util.module_from_spec(BUILD_SPEC)
assert BUILD_SPEC.loader is not None
sys.modules[BUILD_SPEC.name] = build
BUILD_SPEC.loader.exec_module(build)


class DrawingHostIntegrationTests(TestCase):
    def test_all_four_host_contract_fixtures_render_and_verify(self) -> None:
        html_builder, _, dependency_error = build._load_pdf_build_deps()
        self.assertIsNone(dependency_error)
        self.assertIsNotNone(html_builder)

        with TemporaryDirectory() as temp:
            root = Path(temp)
            products = build_host_integration_sources(root / "sources")

            self.assertEqual(set(build.HOST_INTEGRATION_TARGETS), set(products))
            expected_pages = {
                "host-a4-long-doc": (2, (595.28, 841.89)),
                "host-letter-document": (1, (612.0, 792.0)),
                "host-a4-chinese": (1, (595.28, 841.89)),
            }
            for name, (page_count, page_size) in expected_pages.items():
                with self.subTest(host=name):
                    source = Path(products[name]["path"])
                    manifests = verify_hosted_html(source)
                    pdf = root / f"{name}.pdf"
                    html_builder(str(source), base_url=str(source.parent)).write_pdf(str(pdf))
                    reader = PdfReader(str(pdf))
                    self.assertEqual(page_count, len(reader.pages))
                    for page in reader.pages:
                        self.assertAlmostEqual(page_size[0], float(page.mediabox.width), delta=1)
                        self.assertAlmostEqual(page_size[1], float(page.mediabox.height), delta=1)
                    self.assertTrue(all(item["fixture_sha256"] and item["artifact_sha256"] for item in manifests))
                    self._assert_pdf_content_inside_page(pdf, root / f"{name}-raster")

            a4_text = "\n".join(page.extract_text() or "" for page in PdfReader(str(root / "host-a4-long-doc.pdf")).pages)
            self.assertIn("Category", a4_text)
            self.assertIn("Series", a4_text)

            deck = Path(products["host-slide-16x9"]["path"])
            manifests = verify_hosted_pptx(deck)
            presentation = Presentation(deck)
            self.assertEqual(7, len(presentation.slides))
            self.assertEqual({"artifact", "embed"}, {item["profile"] for item in manifests})
            self.assertEqual(2, len(manifests))
            contract = host_contract("slide-16x9")
            for manifest in manifests:
                image = manifest["placement"]["image"]
                self.assertGreaterEqual(image[0], contract.safe_left)
                self.assertGreaterEqual(image[1], contract.safe_top)
                self.assertLessEqual(image[0] + image[2], contract.width - contract.safe_right + 0.002)
                self.assertLessEqual(image[1] + image[3], contract.height - contract.safe_bottom + 0.002)

    def _assert_pdf_content_inside_page(self, pdf: Path, raster_root: Path) -> None:
        pdftoppm = shutil.which("pdftoppm")
        if not pdftoppm:
            self.skipTest("pdftoppm is required by the release environment")
        raster_root.mkdir(parents=True)
        prefix = raster_root / "page"
        result = subprocess.run(
            [pdftoppm, "-r", "72", "-png", str(pdf), str(prefix)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        pages = sorted(raster_root.glob("page-*.png"))
        self.assertTrue(pages)
        for page in pages:
            with Image.open(page) as image:
                rgb = image.convert("RGB")
            parchment = Image.new("RGB", rgb.size, "#F6F0EA")
            paper = Image.new("RGB", rgb.size, "#FFFFFF")
            foreground = ImageChops.darker(
                ImageChops.difference(rgb, parchment).convert("L"),
                ImageChops.difference(rgb, paper).convert("L"),
            ).point(lambda value: 255 if value > 8 else 0)
            bounds = foreground.getbbox()
            self.assertIsNotNone(bounds)
            assert bounds is not None
            self.assertGreater(bounds[0], 0)
            self.assertGreater(bounds[1], 0)
            self.assertLess(bounds[2], rgb.width)
            self.assertLess(bounds[3], rgb.height)
