#!/usr/bin/env python3
"""Build a static reading-page series from a module fragment.

A series is a directory:

    series.json
    <module>.frag.html      # the chapters, nothing else

`series.json` carries the delivery facts the page cannot invent: series title,
lead, and one entry per module (number, name, summary, status, package,
optional external link). The builder injects the engine's theme variables, the
base stylesheet, the table of contents and the module blocks, then writes

    dist/web/<series>/index.html
    dist/web/<series>/<module>/index.html

    python3 scripts/build_web.py --series dist/web/attention
    python3 scripts/build_web.py --series dist/web/attention --verify
    python3 scripts/build_web.py --series dist/web/attention --verify \
        --source /tmp/ain.txt --level 3
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import sys
from dataclasses import replace as replace_fields
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import web_contracts as C  # noqa: E402
import web_figures as WF  # noqa: E402
import web_page as WP  # noqa: E402
import web_plan  # noqa: E402

TEMPLATES = ROOT / "assets" / "templates" / "web"

# Chrome strings follow the series language. They are page furniture, not
# content, so they live with the builder rather than in each fragment.
UI = {
    "zh": {
        "back_series": "返回系列文档",
        "to_top": "回到顶部",
        "toc": "章节目录",
        "rail": "章节刻度",
        "series": "SERIES",
        "module": "MODULE ARCHIVE",
        "external": "外链",
        "source": "来源",
        "figure": "图",
        "skip": "跳到正文",
    },
    "en": {
        "back_series": "Series index",
        "to_top": "Top",
        "toc": "Contents",
        "rail": "Sections",
        "series": "SERIES",
        "module": "MODULE ARCHIVE",
        "external": "External",
        "source": "Source",
        "figure": "Figure",
        "skip": "Skip to content",
    },
}


def ui_for(language: str) -> dict[str, str]:
    return UI["en"] if not language.lower().startswith("zh") else UI["zh"]


def style_css(language: str, theme: str | None) -> tuple[str, str]:
    """The injected variable layer and the resolved theme name.

    Three layers, in order: the theme's colour roles, the profile's regular
    values, and the viewport plan's value patches. The last one is the only
    place a width changes a size, and it changes nothing but a value.
    """
    import projection

    theme_layer = projection.style_projection("web-reading", language, theme=theme)
    web_layer = projection.web_projection("web-reading", language, include_viewport_aliases=False)
    plan_layer = web_plan.plan_css(web_plan.viewport_plan(language))[0]
    # The scheme's own name, not the word "default": the manifest is provenance,
    # and a reader of it has to be able to name the scheme the page was built
    # in. Every colour the projection emits records that source.
    schemes = {
        value.split(":", 1)[1]
        for value in theme_layer.sources.values()
        if value.startswith("theme:")
    }
    name = schemes.pop() if len(schemes) == 1 else (theme or "default")
    css = "\n\n".join(part.strip() for part in (theme_layer.css, web_layer.css, plan_layer)
                      if part.strip())
    if ":root" not in css:
        css = ":root {\n" + css + "\n}"
    return css, name


def font_face_css(language: str, out_dir: Path, page_dir: Path) -> str:
    """Embed every face the profile names, or say nothing when there is none.

    Files are copied once per build into `<out>/fonts/`, and each page points
    at them relative to its own depth. The engine's font stack is the authority;
    this only makes the families it names real rather than assumed.
    """
    import projection

    faces = projection.web_font_faces(language)
    if not faces:
        return "/* No embedded face is declared for this language. */"
    blocks: list[str] = []
    missing: list[str] = []
    for face in faces:
        family, filename = face["family"], face["file"]
        source = ROOT / "assets" / "fonts" / filename
        if not source.is_file():
            missing.append(filename)
            continue
        target = out_dir / "fonts" / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.is_file() or target.stat().st_size != source.stat().st_size:
            shutil.copy2(source, target)
        relative = os.path.relpath(target, page_dir).replace(os.sep, "/")
        weight = f'  font-weight: {face["weight"]};\n' if face["weight"] else ""
        blocks.append(
            "@font-face {\n"
            f'  font-family: "{family}";\n'
            f'  src: url("{relative}") format("{face.get("format") or "truetype"}");\n'
            f"{weight}"
            "  font-display: swap;\n"
            "}"
        )
    if missing:
        blocks.append(f"/* not bundled: {', '.join(missing)}; the fallback stack applies. */")
    return "\n".join(blocks)


RAIL_SCRIPT = """(function () {
  var root = document.documentElement;
  var links = [].slice.call(document.querySelectorAll('.rail a'));
  // The chapters, not the rail entries, are what scroll: the rail is hidden on
  // a narrow screen, and a hidden element reports no position to track.
  var chapters = [].slice.call(document.querySelectorAll('.chapter'));
  var sections = chapters.length ? chapters
    : links.map(function (a) { return document.querySelector(a.getAttribute('href')); })
      .filter(Boolean);
  var progress = document.querySelector('.topbar .progress');
  var now = document.querySelector('.topbar .now');
  var current = null;

  function labelFor(id) {
    var link = links.filter(function (a) { return a.getAttribute('href') === '#' + id; })[0];
    var label = link && link.querySelector('.label');
    if (label) return label.textContent;
    var section = document.getElementById(id);
    var heading = section ? section.querySelector('h2') : null;
    if (!heading) return '';
    // The number is its own span, so the heading's text runs "04Title".
    var num = heading.querySelector('.num');
    var rest = num ? heading.textContent.replace(num.textContent, '') : heading.textContent;
    rest = rest.replace(/\\s+/g, ' ').trim();
    return num ? num.textContent + ' ' + rest : rest;
  }

  function activate(id) {
    if (id === current) return;
    current = id;
    links.forEach(function (a) {
      a.setAttribute('aria-current', a.getAttribute('href') === '#' + id ? 'true' : 'false');
    });
    if (now) now.textContent = labelFor(id);
  }

  function update() {
    if (progress) {
      var span = root.scrollHeight - window.innerHeight;
      var ratio = span > 0 ? Math.min(1, Math.max(0, window.scrollY / span)) : 0;
      progress.style.transform = 'scaleX(' + ratio + ')';
    }
    if (!sections.length) return;
    var line = window.innerHeight * 0.25;
    var id = sections[0].id;
    for (var i = 0; i < sections.length; i += 1) {
      if (sections[i].getBoundingClientRect().top <= line) id = sections[i].id;
    }
    var atBottom = window.innerHeight + window.scrollY >=
      root.scrollHeight - 2;
    if (atBottom) id = sections[sections.length - 1].id;
    activate(id);
  }

  var queued = false;
  function onScroll() {
    if (queued) return;
    queued = true;
    window.requestAnimationFrame(function () { queued = false; update(); });
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  window.addEventListener('resize', onScroll);
  window.addEventListener('load', update);
  update();
})();"""


def rail_from(model: WP.Page) -> str:
    """The side rail: one entry per chapter, read from the page model."""
    items = []
    for index, chapter in enumerate(model.chapters):
        current = "true" if index == 0 else "false"
        items.append(
            f'  <li><a href="#{chapter.id}" aria-current="{current}">'
            f'<span class="tick"></span>'
            f'<span class="label">{chapter.number} {chapter.title}</span></a></li>'
        )
    return "<ol>\n" + "\n".join(items) + "\n</ol>"


def toc_from(model: WP.Page) -> str:
    """The contents list: number, title and summary, from the page model."""
    items = []
    for chapter in model.chapters:
        items.append(
            f'  <li><a href="#{chapter.id}"><span class="num">{chapter.number}</span>'
            f'<span class="name">{chapter.title}</span>'
            f'<span class="sum">{chapter.summary}</span></a></li>'
        )
    return "\n".join(items)


def rail_legacy(fragment: str) -> str:
    """The rollback path (`FOLIO_WEB_MODEL=off`): chapter chrome from regexes."""
    items = []
    for index, match in enumerate(re.finditer(
        r'<section class="chapter" id="([^"]+)"[^>]*>\s*<h2><span class="num">(\d+)</span>(.*?)</h2>',
        fragment,
        re.S,
    )):
        anchor, number, title = match.groups()
        current = "true" if index == 0 else "false"
        items.append(
            f'  <li><a href="#{anchor}" aria-current="{current}">'
            f'<span class="tick"></span>'
            f'<span class="label">{number} {title.strip()}</span></a></li>'
        )
    return "<ol>\n" + "\n".join(items) + "\n</ol>"


def toc_legacy(fragment: str) -> str:
    items = []
    for match in re.finditer(
        r'<section class="chapter" id="([^"]+)"[^>]*data-sum="([^"]*)"[^>]*>\s*<h2><span class="num">(\d+)</span>(.*?)</h2>',
        fragment,
        re.S,
    ):
        anchor, summary, number, title = match.groups()
        items.append(
            f'  <li><a href="#{anchor}"><span class="num">{number}</span>'
            f'<span class="name">{title.strip()}</span>'
            f'<span class="sum">{summary}</span></a></li>'
        )
    return "\n".join(items)


def index_rail(modules: list[dict]) -> str:
    items = []
    for index, module in enumerate(modules):
        current = "true" if index == 0 else "false"
        items.append(
            f'  <li><a href="#m{module["num"]}" aria-current="{current}">'
            f'<span class="tick"></span>'
            f'<span class="label">{module["num"]} {module["name"]}</span></a></li>'
        )
    return "<ol>\n" + "\n".join(items) + "\n</ol>"


def source_block(module: dict, ui: dict[str, str]) -> str:
    """The work a case reads. A fixture has no work to name and returns empty.

    The page is a reading page, so its provenance is the source, not the engine
    that set it. Keeping the two apart is what stops a case from turning into a
    report about the code that produced it.
    """
    source = module.get("source") or {}
    if not source:
        return ""
    work = html.escape(source.get("work", ""))
    author = html.escape(source.get("author", ""))
    year = html.escape(str(source.get("year", "")))
    url = source.get("url", "")
    title = (f'<a href="{html.escape(url)}">{work}</a>' if url else work)
    parts = " · ".join(part for part in (title, author, year) if part)
    return (f'<p class="source" data-folio-source="true">'
            f'<span class="source-label">{ui["source"]}</span> {parts}</p>')


def module_block(module: dict, ui: dict[str, str]) -> str:
    external = (
        f'<a class="module-link" href="{module["external"]}">{ui["external"]}</a>'
        if module.get("external") else ""
    )
    source = source_block(module, ui)
    if source:
        # A case states what it reads; a status badge would state what the
        # engine has implemented, which is not a fact about the content.
        meta = source
    else:
        status = module.get("status", "")
        meta = (
            f'<span class="badge" data-status="{status}">{status}</span>'
            f'<code class="pkg">{module.get("package", "")}</code>{external}'
        )
    return (
        f'  <li class="module-block" id="m{module["num"]}">'
        f'<span class="module-num">{module["num"]}</span>'
        f'<h2><a href="./{module["id"]}/index.html">{module["name"]}</a></h2>'
        f'<p class="module-summary">{module["summary"]}</p>'
        f'<div class="module-meta">{meta}</div></li>'
    )



FIGURE_PLACEHOLDER = re.compile(r"<!--FOLIO:FIGURE:([a-z0-9-]+)-->")


def mark_plate(variant: str, rendered: WF.RenderedFigure,
               *, axis_label: str | None = None) -> tuple[str, str]:
    """The plate as the page carries it, and the hash of that markup.

    The drawing is composed for one band, so a figure carries one plate per
    class, each marked with the class CSS shows it in and the stage it was
    composed on. The hash covers the markup without its own `data-folio-sha`
    attribute, so a checker can recompute it by dropping that one attribute:
    a plate that stops matching its manifest record is a stale build, not a
    rendering difference.

    ``axis_label`` is set only when the plates disagree about the reading
    direction, because then the figure's single `data-axis` cannot speak for
    every plate and the plate has to state its own.
    """
    attrs = (
        f'class="figure-svg" data-folio-plate="{variant}" '
        f'data-folio-stage="{rendered.stage[0]}x{rendered.stage[1]}"'
    )
    if axis_label:
        attrs += f' data-axis="{axis_label}"'
    base = rendered.svg.replace("<svg ", f"<svg {attrs} ", 1)
    # The embed profile writes `style="display:block;width:100%"` on the root,
    # and an inline style outranks the stylesheet -- including the rule that
    # hides the plates this viewport is not showing. The page owns the plate's
    # size, so the inline copy goes.
    base = base.replace(' style="display:block;width:100%;height:auto"', "", 1)
    digest = hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]
    return base.replace("<svg ", f'<svg data-folio-sha="{digest}" ', 1), digest


def figure_block(figure_id: str, entry: dict, variants: dict[str, WF.RenderedFigure],
                 number: int, prefix: str, figure_word: str = "图",
                 folio_id: str = "") -> str:
    wide = variants.get("wide") or variants[next(iter(variants))]
    attributes = [
        # The figure is a block like any other: the page model gives it the same
        # role and id vocabulary, so W-STR-06 can compare counts without a
        # special case for drawings.
        'data-folio-role="figure"',
        f'data-folio-id="{folio_id or figure_id}"',
        f'data-folio-drawing="{figure_id}"',
        # The wide plate is the one a print view and a reader without CSS get,
        # so the figure-level record names it.
        f'data-folio-sha="{wide.svg_sha}"',
        f'data-kind="{wide.kind}"',
        f'data-axis="{wide.axis}"',
        f'data-folio-plates="{",".join(variants)}"',
    ]
    if list(variants) == [WF.SINGLE_PLATE]:
        # No class composed, so every class shows the authored plate. The
        # attribute tells the checker the missing classes are the figure's, not
        # a build that forgot to emit them.
        attributes.append('data-folio-single="true"')
    if wide.composition:
        attributes.append(f'data-composition="{wide.composition}"')
    if entry.get("example"):
        attributes.append('data-example="true"')
    # The reader gets a caption, not the figure's provenance. Composition and
    # axis stay on `data-composition` / `data-axis` and in the manifest, where
    # W-FIG-01 compares them; repeating them under the plate made every caption
    # read like a compiler trace.
    caption = f"{figure_word} {prefix}-{number} · {entry['caption']}"
    plates = "".join(variants[key].svg for key in variants)
    return (
        f'<figure class="figure" {" ".join(attributes)}>'
        f"{plates}<figcaption>{html.escape(caption)}</figcaption></figure>"
    )


def render_figures(
    module: dict,
    series_figures: dict[str, dict],
    fragment: str,
    *,
    page_theme: str,
    prefix: str,
    strict: bool,
    language: str | None = None,
    figure_word: str = "图",
    figure_ids: dict[str, str] | None = None,
) -> tuple[str, dict[str, dict]]:
    rendered: dict[str, dict[str, WF.RenderedFigure]] = {}
    uncomposed: dict[str, tuple[str, ...]] = {}
    variants = web_plan.figure_variants(language)
    bands = {item["key"]: item["band"] for item in variants}
    max_bands = {item["key"]: item["max_band"] for item in variants}
    page = web_plan.geometry(language)
    # The title's ceiling is a share of H2, not H2 itself: a figure must not
    # compete with the section heading above it. Its floor is H3, so the title
    # reads as a heading rather than as another line of body.
    title_px = (page["h3"], page["h2"] * C.FIGURE_FIT["title_h2_ratio"])
    for figure_id in module.get("figures", []):
        if figure_id not in series_figures:
            raise SystemExit(f"ERROR: figure {figure_id!r} is used by {module['id']} but not declared")
        entry = series_figures[figure_id]
        composed, missing = WF.render_plates(
            Path(module["_dir"]) / entry["fixture"],
            figure_id,
            bands=bands,
            max_bands=max_bands,
            title_px=title_px,
            page_theme=page_theme,
            composition=entry.get("composition"),
        )
        plates: dict[str, WF.RenderedFigure] = {}
        axes = {figure.axis for figure in composed.values()}
        for variant, figure in composed.items():
            if strict and figure.diagnostics:
                detail = ", ".join(f"{item['level']}:{item['code']}" for item in figure.diagnostics)
                raise SystemExit(f"ERROR: figure {figure_id!r} has diagnostics: {detail}")
            markup, digest = mark_plate(
                variant, figure, axis_label=figure.axis if len(axes) > 1 else None)
            plates[variant] = replace_fields(figure, svg=markup, svg_sha=digest)
        rendered[figure_id] = plates
        uncomposed[figure_id] = missing

    used: set[str] = set()
    number = 0

    def replace(match: re.Match) -> str:
        nonlocal number
        figure_id = match.group(1)
        if figure_id not in rendered:
            raise SystemExit(f"ERROR: placeholder {figure_id!r} has no rendered figure")
        used.add(figure_id)
        number += 1
        return figure_block(figure_id, series_figures[figure_id], rendered[figure_id],
                            number, prefix, figure_word,
                            folio_id=(figure_ids or {}).get(figure_id, ""))

    fragment = FIGURE_PLACEHOLDER.sub(replace, fragment)
    if "<!--FOLIO:FIGURE:" in fragment:
        raise SystemExit("ERROR: a figure placeholder is malformed or undeclared")
    unused = set(rendered) - used
    if unused:
        raise SystemExit(f"ERROR: figures rendered but not placed: {sorted(unused)}")
    manifest = {figure_id: WF.figure_manifest_entry(plates, uncomposed[figure_id])
                for figure_id, plates in rendered.items()}
    return fragment, manifest


def render(template: str, values: dict[str, str]) -> str:
    for key, value in values.items():
        template = template.replace("{{" + key + "}}", value)
    return template


def build(series_dir: Path, out_dir: Path, theme: str | None, *, strict: bool = False) -> list[Path]:
    data = json.loads((series_dir / C.SERIES_FILE).read_text(encoding="utf-8"))
    base_css = (TEMPLATES / "base.css").read_text(encoding="utf-8")
    module_template = (TEMPLATES / "module.html").read_text(encoding="utf-8")
    index_template = (TEMPLATES / "series-index.html").read_text(encoding="utf-8")
    language = str(data.get("language") or "zh-Hans-CN")
    ui = ui_for(language)
    root, page_theme = style_css(language, theme)
    prefix = data.get("figure_prefix", "W")
    series_figures = {entry["id"]: entry for entry in data.get("figures", [])}
    manifest: dict = {
        "series": data["series"],
        "language": language,
        "page_theme": page_theme,
        "drawing_theme": WF.drawing_theme_for(page_theme),
        "figures": {},
        "pages": {},
    }

    written: list[Path] = []
    for module in data["modules"]:
        module = dict(module)
        module["_dir"] = str(series_dir)
        fragment = (series_dir / module["fragment"]).read_text(encoding="utf-8")
        # The model runs on the source, before figures are expanded: the
        # markup it annotates is the one the reader's builder produced, and a
        # block's role cannot change because a drawing was inlined into it.
        model = None
        if WP.mode() != "off":
            fragment, model = WP.model_fragment(fragment)
        figure_ids = {
            block.figure: block.id for block in model.blocks() if block.figure
        } if model is not None else {}
        fragment, module_manifest = render_figures(
            module, series_figures, fragment,
            page_theme=page_theme, prefix=prefix, strict=strict,
            language=language,
            figure_word=ui["figure"], figure_ids=figure_ids,
        )
        manifest["figures"][module["id"]] = module_manifest
        if model is not None:
            manifest["pages"][module["id"]] = {
                "chapters": [
                    {"id": chapter.id, "number": chapter.number,
                     "title": chapter.title, "blocks": len(chapter.blocks)}
                    for chapter in model.chapters
                ],
                "counts": model.counts(),
            }
        target = out_dir / data["series"] / module["id"] / "index.html"
        page = render(module_template, {
            "LANG": language,
            "FONT_FACE": font_face_css(language, out_dir, target.parent),
            "THEME_ROOT": root,
            "BASE_CSS": base_css,
            "SERIES_TITLE": data["title"],
            "TITLE": module["title"],
            # A single-module series repeats its own name in the tab otherwise.
            "PAGE_TITLE": (
                module["title"] if module["title"] == data["title"]
                else f'{module["title"]} · {data["title"]}'
            ),
            "KICKER": module["kicker"],
            "LEAD": module["lead"],
            "KIND": module.get("kind") or data.get("kind") or "case",
            "SOURCE": source_block(module, ui),
            "TOC": toc_from(model) if model else toc_legacy(fragment),
            "TOC_LABEL": ui["toc"],
            "RAIL": rail_from(model) if model else rail_legacy(fragment),
            "RAIL_LABEL": ui["rail"],
            "RAIL_SCRIPT": RAIL_SCRIPT,
            "SECTIONS": fragment,
            "BACK_SERIES": ui["back_series"],
            "TO_TOP": ui["to_top"],
            "MODULE_LABEL": ui["module"],
            "SKIP": ui["skip"],
        })
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(page, encoding="utf-8")
        written.append(target)

    target = out_dir / data["series"] / "index.html"
    index = render(index_template, {
        "LANG": language,
        "FONT_FACE": font_face_css(language, out_dir, target.parent),
        "THEME_ROOT": root,
        "BASE_CSS": base_css,
        "SERIES_TITLE": data["title"],
        "SERIES_KICKER": data.get("kicker", data["title"]),
        "SERIES_LEAD": data["lead"],
        "SERIES_LABEL": ui["series"],
        "MODULES": "\n".join(module_block(module, ui) for module in data["modules"]),
        "RAIL": index_rail(data["modules"]),
        "RAIL_LABEL": ui["rail"],
        "RAIL_SCRIPT": RAIL_SCRIPT,
        "SKIP": ui["skip"],
    })
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(index, encoding="utf-8")
    written.append(target)

    manifest_path = out_dir / data["series"] / "figures.manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # The plan travels with the build. `web_verify.py` compares the browser's
    # computed values with these, so a page that drifts from its plan is a
    # failed build rather than a matter of taste.
    plan_path = out_dir / data["series"] / "plan.json"
    plan = web_plan.plan_document(language)
    plan["series"] = data["series"]
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    written.append(plan_path)
    return written


def verify(series_dir: Path, out_dir: Path, level: int, source: Path | None) -> int:
    import check_web

    failures = 0
    series_root = out_dir / json.loads((series_dir / C.SERIES_FILE).read_text(encoding="utf-8"))["series"]
    manifest = series_root / "figures.manifest.json"
    pages = [series_root / "index.html", *sorted(series_root.glob("*/index.html"))]
    for page in pages:
        argv = [str(page), "--level", str(level), "--series-dir", str(series_root)]
        if manifest.is_file():
            argv += ["--figures-manifest", str(manifest)]
        if source is not None and page.parent != series_root:
            argv += ["--source", str(source)]
        failures += check_web.main(argv)
    return 0 if failures == 0 else 1


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--series", type=Path, required=True, help="directory holding series.json")
    parser.add_argument("--out", type=Path, default=ROOT / "dist" / "web")
    parser.add_argument("--theme", default=None,
                        help="colour scheme; unset reads FOLIO_THEME, then the default")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--source", type=Path, default=None)
    parser.add_argument("--level", type=int, default=3, choices=(1, 2, 3))
    parser.add_argument("--strict-figures", action="store_true",
                        help="treat figure WARNING/TASTE diagnostics as build failures")
    args = parser.parse_args(argv)

    # The same rule as the document build: the flag wins, then the environment,
    # then the profile marked default. A page built with FOLIO_THEME set must
    # not come out in another scheme because only the flag was read.
    theme = args.theme or (os.environ.get("FOLIO_THEME") or "").strip() or None
    pages = build(args.series, args.out, theme, strict=args.strict_figures)
    for page in pages:
        print(f"OK: wrote {page}")
    if args.verify:
        return verify(args.series, args.out, args.level, args.source)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
