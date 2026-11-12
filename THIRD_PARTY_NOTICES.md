# Third-party notices

Folio's own code and templates are MIT-licensed; see `LICENSE`. This file covers
the third-party fonts and the vendored layout engine that the repository
redistributes, with the licence text each one requires.

## Fonts

All three fonts are redistributed unmodified under the SIL Open Font License
1.1. The licence requires that the copyright notice and the licence travel with
the font files, so each entry names its own copy of the text.

| File | Copyright | Licence |
|---|---|---|
| `assets/fonts/LXGWWenKai-Regular.ttf`, `assets/fonts/LXGWWenKai-Medium.ttf` | Copyright 2021-2026 LXGW, with Reserved Font Names; Copyright 2020 The Klee Project Authors | SIL OFL 1.1, `third_party/OFL-LXGWWenKai.txt` |
| `assets/fonts/SourceSerif4Variable-Roman.ttf` | Copyright 2014-2023 Adobe, with Reserved Font Name "Source" | SIL OFL 1.1, `third_party/OFL-SourceSerif4.txt` |
| `assets/fonts/JetBrainsMono.woff2` | Copyright 2020 The JetBrains Mono Project Authors | SIL OFL 1.1, `third_party/OFL-JetBrainsMono.txt` |

Upstream projects:

- LXGW WenKai: https://github.com/lxgw/LxgwWenKai
- Source Serif 4: https://github.com/adobe-fonts/source-serif
- JetBrains Mono: https://github.com/JetBrains/JetBrainsMono

The two LXGW WenKai TTF files are about 24 MB each. They stay in the repository
so a clone renders Chinese documents immediately, but `scripts/package-skill.sh`
excludes them from `dist/folio.zip`; the skill downloads them from the upstream
project when they are missing. The licence text is bundled in both cases.

The full OFL 1.1 text, without a specific copyright line, is
`third_party/OFL-1.1.txt`.

## Diagram layout

`scripts/vendor/elk.bundled.js` is the elkjs 0.13.0 browser bundle, used by the
Drawing DSL as the deterministic layout backend.

- Upstream: https://github.com/kieler/elkjs, built from Eclipse Layout Kernel
  (https://github.com/eclipse-elk/elk).
- Licence: Eclipse Public License 2.0 OR GPL-3.0-or-later, at the recipient's
  choice. Folio uses it under EPL-2.0. The full text is
  `third_party/EPL-2.0.txt`.
- Source: the bundle is unmodified. Its source is the upstream repository above;
  the vendored copy exists because the layout stage must run without a package
  install.

Eclipse Layout Kernel is a trademark of the Eclipse Foundation. The upstream
project's notice also records its project home,
https://projects.eclipse.org/projects/modeling.elk, and the secondary GPL-3.0
option at https://www.gnu.org/licenses/gpl-3.0-standalone.html.

## Python dependencies

WeasyPrint, python-pptx, PyYAML, Pillow and the other packages in
`requirements-ci.txt` are installed, not redistributed, so their notices stay
with those packages.
