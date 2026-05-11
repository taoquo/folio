import importlib.util
import io
import sys
from pathlib import Path
from unittest import TestCase, mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

SPEC = importlib.util.spec_from_file_location("folio_cli", SCRIPTS_DIR / "folio.py")
folio = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = folio
SPEC.loader.exec_module(folio)


class FolioCliTests(TestCase):
    def test_list_targets_prints_all_target_groups(self) -> None:
        stdout = io.StringIO()
        with mock.patch("sys.stdout", stdout):
            code = folio.main(["folio.py", "list-targets"])

        text = stdout.getvalue()
        self.assertEqual(0, code)
        self.assertIn("HTML targets:", text)
        self.assertIn("one-pager", text)
        self.assertIn("Diagram targets:", text)
        self.assertIn("diagram-architecture", text)
        self.assertIn("Artifact targets:", text)
        self.assertIn("artifact-architecture-demo", text)
        self.assertIn("Slide targets:", text)
        self.assertIn("slides-en", text)

    def test_package_delegates_to_package_script(self) -> None:
        with mock.patch.object(folio.subprocess, "run") as run_mock:
            run_mock.return_value.returncode = 0
            code = folio.main(["folio.py", "package"])

        self.assertEqual(0, code)
        command = run_mock.call_args[0][0]
        self.assertEqual(["bash", str(ROOT / "scripts" / "package-skill.sh")], command)
        self.assertEqual(ROOT, run_mock.call_args.kwargs["cwd"])

    def test_verify_delegates_to_build_script_with_target(self) -> None:
        with mock.patch.object(folio.subprocess, "run") as run_mock:
            run_mock.return_value.returncode = 0
            code = folio.main(["folio.py", "verify", "resume-en"])

        self.assertEqual(0, code)
        command = run_mock.call_args[0][0]
        self.assertEqual([sys.executable, str(ROOT / "scripts" / "build.py"), "--verify", "resume-en"], command)
