import importlib.util
import json
import sys
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from drawing.compiler import DEFAULT_COMPILER_REGISTRY
from drawing.theme import (
    DARK_THEME,
    DEFAULT_FOLIO_THEME,
    TERMINAL_THEME,
    THEME_PROFILE_NAMES,
    contrast_ratio,
    contrast_violations,
    normalize_theme_profile,
    register_theme_profile,
    resolve_theme,
    retheme_scene,
    theme_profile_names,
    theme_token_map,
    unregister_theme_profile,
    with_tokens,
)

SPEC = importlib.util.spec_from_file_location("folio_cli_theme", SCRIPTS_DIR / "folio.py")
folio = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = folio
SPEC.loader.exec_module(folio)

CATALOG = json.loads((ROOT / "references/fixtures/diagram-catalog.json").read_text(encoding="utf-8"))
BUILT_IN = ("folio", "dark", "terminal")
COLOR_KEYS = ("fill", "stroke", "background")


def _payload(item: dict) -> dict:
    return json.loads((ROOT / item["source"]).read_text(encoding="utf-8"))


def _mask_colors(value, key=None):
    """Return the scene payload with every color-bearing leaf masked."""
    if isinstance(value, dict):
        return {name: _mask_colors(item, name) for name, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_mask_colors(item, key) for item in value]
    if isinstance(value, str) and key in COLOR_KEYS:
        return "<color>"
    return value


def _color_values(value, key=None, found=None):
    found = [] if found is None else found
    if isinstance(value, dict):
        for name, item in value.items():
            _color_values(item, name, found)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _color_values(item, key, found)
    elif isinstance(value, str) and key in COLOR_KEYS and value.startswith("#"):
        found.append(value.lower())
    return found


class DrawingThemeProfileTests(TestCase):
    def test_v5_built_in_profiles_pass_wcag_contrast(self) -> None:
        for name in BUILT_IN:
            with self.subTest(theme=name):
                self.assertEqual((), contrast_violations(resolve_theme(name)))

    def test_v5_profile_registry_is_stable_and_sorted(self) -> None:
        self.assertEqual(BUILT_IN, THEME_PROFILE_NAMES)
        self.assertEqual(sorted(BUILT_IN), list(theme_profile_names()))
        self.assertIs(DEFAULT_FOLIO_THEME, resolve_theme("folio"))
        self.assertIs(DARK_THEME, resolve_theme("dark"))
        self.assertIs(TERMINAL_THEME, resolve_theme("terminal"))
        self.assertEqual("dark", normalize_theme_profile("dark"))
        with self.assertRaises(ValueError):
            normalize_theme_profile("sepia")

    def test_v5_every_theme_token_is_a_full_palette(self) -> None:
        reference = asdict(DEFAULT_FOLIO_THEME)
        colors = {key for key, value in reference.items() if value.startswith("#")}
        self.assertEqual(12, len(colors))
        for name in BUILT_IN:
            tokens = asdict(resolve_theme(name))
            with self.subTest(theme=name):
                self.assertEqual(set(reference), set(tokens))
                self.assertTrue(all(len(tokens[key]) == 7 for key in colors))
                self.assertEqual(reference["serif"], tokens["serif"])
                self.assertEqual(reference["mono"], tokens["mono"])

    def test_v5_register_theme_profile_rejects_unreadable_palette(self) -> None:
        unreadable = with_tokens(DEFAULT_FOLIO_THEME, near_black="#F6F0EA")
        with self.assertRaises(ValueError) as caught:
            register_theme_profile("washed-out", unreadable)
        self.assertIn("WCAG contrast", str(caught.exception))
        with self.assertRaises(ValueError):
            resolve_theme("washed-out")

    def test_v5_register_theme_profile_accepts_safe_palette_and_round_trips(self) -> None:
        safe = with_tokens(DARK_THEME, brand="#F2A18C", brand_tint="#4C2C24")
        self.assertEqual((), contrast_violations(safe))
        register_theme_profile("dark-warm", safe)
        try:
            self.assertIs(safe, resolve_theme("dark-warm"))
            self.assertIn("dark-warm", theme_profile_names())
            with self.assertRaises(ValueError):
                register_theme_profile("dark-warm", safe)
        finally:
            unregister_theme_profile("dark-warm")
        self.assertNotIn("dark-warm", theme_profile_names())

    def test_v5_register_theme_profile_rejects_bad_names(self) -> None:
        for name in ("", "dark theme", "dark/theme", "dark_theme"):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    register_theme_profile(name, DARK_THEME)

    def test_v5_built_in_profiles_cannot_be_removed(self) -> None:
        for name in BUILT_IN:
            with self.subTest(theme=name):
                with self.assertRaises(ValueError):
                    unregister_theme_profile(name)
                self.assertIn(name, theme_profile_names())

    def test_v5_token_map_covers_every_color_token(self) -> None:
        mapping = theme_token_map(DEFAULT_FOLIO_THEME, DARK_THEME)
        folio_tokens = asdict(DEFAULT_FOLIO_THEME)
        dark_tokens = asdict(DARK_THEME)
        for key, value in folio_tokens.items():
            if value.startswith("#"):
                self.assertEqual(dark_tokens[key], mapping[value.lower()])
        identity = theme_token_map(DARK_THEME, DARK_THEME)
        self.assertTrue(all(key == value.lower() for key, value in identity.items()))


class DrawingRethemeTests(TestCase):
    def test_v5_retheme_preserves_geometry_text_and_reading_order(self) -> None:
        for item in CATALOG["diagrams"]:
            base = DEFAULT_COMPILER_REGISTRY.compile_payload(_payload(item), "artifact", "folio")
            for name in ("dark", "terminal"):
                themed = DEFAULT_COMPILER_REGISTRY.compile_payload(_payload(item), "artifact", name)
                with self.subTest(kind=item["kind"], theme=name):
                    self.assertEqual(
                        _mask_colors(base.scene.to_dict()),
                        _mask_colors(themed.scene.to_dict()),
                    )
                    self.assertEqual(base.scene.reading_order, themed.scene.reading_order)
                    self.assertEqual(base.scene.width, themed.scene.width)
                    self.assertEqual(base.scene.height, themed.scene.height)

    def test_v5_retheme_replaces_every_folio_color(self) -> None:
        folio_values = {
            value.lower()
            for value in asdict(DEFAULT_FOLIO_THEME).values()
            if isinstance(value, str) and value.startswith("#")
        }
        for item in CATALOG["diagrams"]:
            for name in ("dark", "terminal"):
                result = DEFAULT_COMPILER_REGISTRY.compile_payload(_payload(item), "artifact", name)
                painted = set(_color_values(result.scene.to_dict()))
                painted.add(result.scene.background.lower())
                allowed = {
                    value.lower()
                    for value in asdict(resolve_theme(name)).values()
                    if isinstance(value, str) and value.startswith("#")
                }
                with self.subTest(kind=item["kind"], theme=name):
                    self.assertEqual(set(), painted - allowed)
                    self.assertEqual(set(), painted & folio_values - allowed)

    def test_v5_retheme_is_identity_for_the_source_theme(self) -> None:
        result = DEFAULT_COMPILER_REGISTRY.compile_payload(
            _payload(CATALOG["diagrams"][0]), "artifact", "folio"
        )
        self.assertIs(result.scene, retheme_scene(result.scene, DEFAULT_FOLIO_THEME))


class DrawingThemeCompilationTests(TestCase):
    def test_v5_every_catalog_kind_compiles_clean_on_every_theme(self) -> None:
        for item in CATALOG["diagrams"]:
            for name in BUILT_IN:
                result = DEFAULT_COMPILER_REGISTRY.compile_payload(_payload(item), "artifact", name)
                with self.subTest(kind=item["kind"], theme=name):
                    self.assertEqual([], [str(entry) for entry in result.diagnostics])
                    self.assertEqual(name, result.theme)
                    self.assertEqual(resolve_theme(name).parchment, result.scene.background)

    def test_v5_unknown_theme_is_rejected_at_the_compiler_boundary(self) -> None:
        with self.assertRaises(ValueError):
            DEFAULT_COMPILER_REGISTRY.compile_payload(
                _payload(CATALOG["diagrams"][0]), "artifact", "sepia"
            )

    def test_v5_scene_text_contrast_holds_on_every_theme(self) -> None:
        from drawing.validation.quality import NORMAL_TEXT_MINIMUM

        for name in BUILT_IN:
            theme = resolve_theme(name)
            ratio = contrast_ratio(theme.near_black, theme.parchment)
            with self.subTest(theme=name):
                self.assertIsNotNone(ratio)
                self.assertGreaterEqual(ratio, NORMAL_TEXT_MINIMUM)


class DrawingThemeCliTests(TestCase):
    def test_v5_theme_choices_are_registry_derived(self) -> None:
        self.assertEqual(BUILT_IN, folio.DRAWING_THEMES)

    def test_v5_render_drawing_theme_changes_the_png_canvas(self) -> None:
        fixture = str(ROOT / "references/fixtures/v3/state-machine.json")
        with TemporaryDirectory() as temp:
            light = Path(temp) / "light.png"
            dark = Path(temp) / "dark.png"
            self.assertEqual(0, folio.main([
                "folio.py", "render-drawing", fixture,
                "--profile", "artifact", "--format", "png", "--output", str(light),
            ]))
            self.assertEqual(0, folio.main([
                "folio.py", "render-drawing", fixture,
                "--profile", "artifact", "--format", "png",
                "--theme", "dark", "--output", str(dark),
            ]))
            self.assertTrue(light.exists() and dark.exists())
            self.assertNotEqual(light.read_bytes(), dark.read_bytes())

    def test_v5_render_drawing_theme_swaps_svg_tokens(self) -> None:
        fixture = str(ROOT / "references/fixtures/v3/bar-chart.json")
        with TemporaryDirectory() as temp:
            output = Path(temp) / "terminal.svg"
            self.assertEqual(0, folio.main([
                "folio.py", "render-drawing", fixture,
                "--profile", "artifact", "--format", "svg",
                "--theme", "terminal", "--output", str(output),
            ]))
            markup = output.read_text(encoding="utf-8")
            self.assertIn(TERMINAL_THEME.parchment, markup)
            self.assertNotIn(DEFAULT_FOLIO_THEME.brand, markup)
            self.assertNotIn(DEFAULT_FOLIO_THEME.near_black, markup)

    def test_v5_theme_flag_is_available_on_every_drawing_subcommand(self) -> None:
        parser = folio.build_parser()
        actions = {
            action.dest: action
            for action in parser._subparsers._group_actions  # noqa: SLF001
        }
        subparsers = actions["command"].choices
        for name in (
            "render-drawing", "check-drawing", "validate-drawing", "draw-metrics",
            "draw-scene", "draw-plan", "draw-semantic", "draw-layout",
            "batch-render-drawings", "review-drawing", "embed-drawing",
        ):
            with self.subTest(command=name):
                flags = {
                    flag
                    for action in subparsers[name]._actions  # noqa: SLF001
                    for flag in action.option_strings
                }
                self.assertIn("--theme", flags)

    def test_v5_unknown_theme_is_rejected_by_the_cli(self) -> None:
        with self.assertRaises(SystemExit):
            folio.build_parser().parse_args([
                "render-drawing", "x.json", "--theme", "sepia", "--output", "x.svg",
            ])
