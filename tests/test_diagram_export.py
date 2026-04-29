import importlib.util
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


exports = load_module("diagram_export", "diagram_export.py")


class DiagramExportTests(TestCase):
    @mock.patch("diagram_export.subprocess.run")
    def test_export_png_uses_rsvg_convert(self, run_mock) -> None:
        run_mock.return_value.returncode = 0
        with TemporaryDirectory() as tmp:
            svg_path = Path(tmp) / "demo.svg"
            png_path = Path(tmp) / "demo.png"
            svg_path.write_text("<svg/>", encoding="utf-8")

            exports.export_png(svg_path, png_path, width=1600)

        run_mock.assert_called_once()
        command = run_mock.call_args[0][0]
        self.assertEqual("rsvg-convert", command[0])

    @mock.patch("diagram_export.HTML")
    def test_export_pdf_wraps_svg_in_single_page_html(self, html_mock) -> None:
        instance = html_mock.return_value
        with TemporaryDirectory() as tmp:
            svg_path = Path(tmp) / "demo.svg"
            pdf_path = Path(tmp) / "demo.pdf"
            svg_path.write_text("<svg/>", encoding="utf-8")

            exports.export_pdf(svg_path, pdf_path, "Demo")

        instance.write_pdf.assert_called_once()
