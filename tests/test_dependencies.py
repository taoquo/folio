"""The requirements files must declare every third-party import.

A missing pin is invisible on a machine where the package is already
installed. It fails only in a clean environment, at the first `import`, and
the traceback names the module rather than the requirements file that forgot
it. This walks the imports so the two cannot drift again.
"""

from __future__ import annotations

import ast
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Distribution name -> the module it installs, where the two differ.
DISTRIBUTION_MODULE = {
    "Pillow": "PIL",
    "python-pptx": "pptx",
    "PyYAML": "yaml",
}


def declared_modules(path: Path) -> set[str]:
    names: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        distribution = re.split(r"[\[<>=!~;\s]", line, maxsplit=1)[0]
        names.add(DISTRIBUTION_MODULE.get(distribution, distribution))
    return names


def local_modules() -> set[str]:
    names = {"scripts", "tests"}
    for path in (ROOT / "scripts").rglob("*.py"):
        names.add(path.stem)
    for path in (ROOT / "scripts").iterdir():
        if path.is_dir():
            names.add(path.name)
    for path in (ROOT / "tests").glob("*.py"):
        names.add(path.stem)
    return names


def imported_modules() -> set[str]:
    found: set[str] = set()
    for directory in (ROOT / "scripts", ROOT / "tests"):
        for path in directory.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    found.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    found.add(node.module.split(".")[0])
    return found


class DeclaredDependencyTests(unittest.TestCase):
    def test_every_third_party_import_is_declared(self) -> None:
        declared = declared_modules(ROOT / "requirements-ci.txt")
        declared |= declared_modules(ROOT / "requirements-nightly.txt")
        third_party = imported_modules() - set(sys.stdlib_module_names) - local_modules()
        self.assertEqual(set(), third_party - declared)


if __name__ == "__main__":
    unittest.main()
