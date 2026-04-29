---
name: folio
description: 'Typeset professional documents: one-pagers, long docs, letters, portfolios, resumes, slide decks, equity reports, and changelogs. Warm parchment, cinnabar-coral accent, serif-led hierarchy. CN uses LXGW WenKai, EN uses Charter. Triggers on "做 PDF / 排版 / 一页纸 / 白皮书 / 作品集 / 简历 / PPT / slides / 研报 / 更新日志", or "build me a resume / make a one-pager / design a slide deck / turn this into a PDF / write an equity report / format release notes / make this presentable".'
---

# folio

**Folio** - the paper your deliverables land on.

Good content deserves good paper. One design language across eight document types: warm parchment canvas, cinnabar-coral accent, serif-led hierarchy, tight editorial rhythm.

Folio delivers professional documents across eight templates and fourteen diagram types.

## Step 0 · Load brand profile (if exists)

Before anything else, check for a brand profile:

1. `~/.config/folio/brand.md` (global user config, XDG-compliant, preferred)
2. `~/.folio/brand.md` (legacy fallback)

If found, parse the YAML frontmatter for structured fields and treat the Markdown body below the frontmatter as freeform habit notes. If no profile exists, continue without interruption.

### Layer A — Placeholder substitution

Apply at template edit time: replace matching `{{...}}` placeholders in the HTML body with profile values before building.

| Profile field | Template placeholder(s)                                                                 |
| ------------- | --------------------------------------------------------------------------------------- |
| `name`        | `{{NAME}}`, `{{作者}}`, `{{AUTHOR}}`                                                    |
| `role_title`  | `{{ROLE_TITLE}}` or the nearest role-title slot with inline example text               |
| `email`       | `{{EMAIL}}`                                                                             |
| `website`     | `{{WEBSITE}}`, `{{WEBSITE / SOCIAL}}`                                                   |
| `github`      | `{{GITHUB_URL}}` (expand to `https://github.com/<value>`); also fill `{{GITHUB_ID}}`   |
| `x`           | `{{X_URL}}` (expand to `https://x.com/<value>`); also fill `{{X_ID}}`                  |
| `city`        | `{{CITY}}` or the nearest city slot in CN templates                                     |
| `country`     | `{{COUNTRY_OR_REGION}}`                                                                 |

Rule: explicit instructions in the current conversation always override profile values (e.g. "sign it as Alex" beats `name: Tang`). Profile fills slots only — if the template has no matching placeholder, do not insert the field.

Fields such as `company`, `tagline`, `date_format`, and `signature_block` are context defaults today, not universal placeholders. Use them only when the active template already has a natural slot or the user explicitly asks for them.

### Layer B — Session defaults

Apply when the current request is ambiguous. Use profile fields to fill in missing signal silently; do not skip clarification questions for genuinely unclear intent (e.g. "make a document" still warrants asking which type).

| Ambiguous signal         | Profile field        | Behavior                                                                  |
| ------------------------ | -------------------- | ------------------------------------------------------------------------- |
| No language stated       | `language`           | Use `cn` / `en` path                                                      |
| No doc type stated       | `default_doc_type`   | Use as fallback, still ask if truly ambiguous                             |
| No output format stated  | `output_format`      | `pdf` / `pptx` / `both`                                                   |
| No page size stated      | `page_size`          | `a4` or `letter`                                                          |
| Currency context unclear | `currency_locale`    | `USD` → $, M/B; `CNY` → 元, 万/亿                                         |
| Tone unclear             | `tone`               | `formal` → deferential register; `casual` → relaxed; `balanced` → default |
| Footer unclear           | `footer_note`        | Append standing disclaimer if present                                     |
| TOC decision unclear     | `always_include_toc` | `true` → keep the long-doc TOC section instead of removing it             |

### Layer C — Visual customization

Apply after template content is filled, before calling `build.py`:

- `brand_color`: edit the `--brand` CSS variable in the template `<style>` block. Warn if the hue departs significantly from cinnabar-coral — the warm palette constraint (parchment + neutrals) remains in force regardless.
- `logo`: use it only where the active template already has an image slot or the user explicitly asks to add one. Portfolio has the clearest built-in image placeholders; otherwise keep the layout text-first.

### Layer D — Habit notes

Treat the Markdown body below the YAML frontmatter as additional voice and style context, merged with `references/writing.md` guidance. When a note names a specific document type ("equity reports: dense, cite inline"), apply it when that doc type is active. Habit notes are advisory: if the current document's content does not fit a stated preference, follow the content.

### Guardrails (preserve editorial judgment)

These six rules apply to every layer above. Weight them equally with the field table.

1. **Profile is a fallback, not a first resort.** When the current request already carries tone, urgency, or subject-specific signal, use that signal. Profile fills gaps only.
2. **Editorial judgment can override any layer silently.** If a profile field would harm this specific document, skip it. No explanation needed. Example: `tone: formal` in profile, but the user hands over a playful changelog — follow the changelog's voice.
3. **Vary surface details across documents.** Even when author, brand_color, and company all come from profile, each document's opening hook, chart selection, section order, and density must be chosen fresh for the current content. Two equity reports should not look like clones.
4. **Profile fills slots, never introduces new content.** If the template has no `{{EMAIL}}` placeholder, do not insert a contact line because `email` exists in profile.
5. **Apply silently, do not announce.** Never write "applied your profile defaults" or any similar note in the output. Profile disappears into the background.
6. **Habit notes are advisory, not mandatory.** They describe tendencies ("I prefer dense reports"), not hard rules. When content does not fit, follow the content.

### Precedence

```
explicit prompt  >  editorial judgment for this document  >  habit notes  >  frontmatter defaults  >  built-in defaults
```

---

## Step 1 · Decide the language

**Match the user's language.** Chinese -> `*.html` / `slides.py`. English -> `*-en.html` / `slides-en.py`. Other languages should be routed explicitly by script coverage and verified manually. Reference docs are shared English specs.

When ambiguous (e.g. a one-word command like "resume"), ask a one-liner rather than guess.

| User language                 | HTML templates                                                 | Slides template                                            |
| ----------------------------- | -------------------------------------------------------------- | ---------------------------------------------------------- |
| Chinese (primary)             | `*.html`                                                       | `slides.py`                                                |
| English                       | `*-en.html`                                                    | `slides-en.py`                                             |
| Other languages (best-effort) | choose CJK or EN path by script coverage, then verify manually | choose `slides.py` or `slides-en.py`, then verify manually |

Always use `CHEATSHEET.md` and `references/*.md` for design, writing, production, and diagram guidance.

## Step 2 · Pick the document type

| User says                                                          | Document      | CN template          | EN template             |
| ------------------------------------------------------------------ | ------------- | -------------------- | ----------------------- |
| "one-pager / 方案 / 执行摘要 / exec summary"                       | One-Pager     | `one-pager.html`     | `one-pager-en.html`     |
| "white paper / 白皮书 / 长文 / 年度总结 / technical report"        | Long Doc      | `long-doc.html`      | `long-doc-en.html`      |
| "formal letter / 信件 / 辞职信 / 推荐信 / memo"                    | Letter        | `letter.html`        | `letter-en.html`        |
| "portfolio / 作品集 / case studies"                                | Portfolio     | `portfolio.html`     | `portfolio-en.html`     |
| "resume / resume / CV / 简历"                                      | Resume        | `resume.html`        | `resume-en.html`        |
| "slides / PPT / deck / 演示"                                       | Slides        | `slides.py`          | `slides-en.py`          |
| "个股研报 / equity report / 估值分析 / investment memo / 股票分析" | Equity Report | `equity-report.html` | `equity-report-en.html` |
| "更新日志 / changelog / release notes / 版本记录"                  | Changelog     | `changelog.html`     | `changelog-en.html`     |

> Long deck (>20 slides): also read Deck Recipe (design.md section 8).

If unsure, ask a one-liner about the scenario rather than guess.

### Diagrams (primitives, not a 7th doc type)

When the user asks for **a diagram inside** a document or deck (not a standalone document), route to `assets/diagrams/` rather than a top-level template. Common hosts: long-doc, portfolio, one-pager, equity-report, and slides.

| User says                                                      | Diagram       | Template                             |
| -------------------------------------------------------------- | ------------- | ------------------------------------ |
| "架构图 / architecture / 系统图 / components diagram"          | Architecture  | `assets/diagrams/architecture.html`  |
| "流程图 / flowchart / 决策流 / branching logic"                | Flowchart     | `assets/diagrams/flowchart.html`     |
| "象限图 / quadrant / 优先级矩阵 / 2×2 matrix"                  | Quadrant      | `assets/diagrams/quadrant.html`      |
| "柱状图 / bar chart / 分类对比 / grouped bars"                 | Bar Chart     | `assets/diagrams/bar-chart.html`     |
| "折线图 / line chart / 趋势 / 股价 / time series"              | Line Chart    | `assets/diagrams/line-chart.html`    |
| "环形图 / donut / pie / 占比 / 分布结构"                       | Donut Chart   | `assets/diagrams/donut-chart.html`   |
| "状态机 / state machine / 状态图 / lifecycle"                  | State Machine | `assets/diagrams/state-machine.html` |
| "时间线 / timeline / 里程碑 / milestones / roadmap"            | Timeline      | `assets/diagrams/timeline.html`      |
| "泳道图 / swimlane / 跨角色流程 / cross-team flow"             | Swimlane      | `assets/diagrams/swimlane.html`      |
| "树状图 / tree / hierarchy / 层级 / 组织架构"                  | Tree          | `assets/diagrams/tree.html`          |
| "分层图 / layer stack / 分层架构 / OSI / stack"                | Layer Stack   | `assets/diagrams/layer-stack.html`   |
| "维恩图 / venn / 交集 / overlap / 集合关系"                    | Venn          | `assets/diagrams/venn.html`          |
| "K 线 / candlestick / OHLC / 股价走势 / price history"         | Candlestick   | `assets/diagrams/candlestick.html`   |
| "瀑布图 / waterfall / 收入桥 / revenue bridge / decomposition" | Waterfall     | `assets/diagrams/waterfall.html`     |

Read `references/diagrams.md` before drawing - it has the selection guide, folio token map, and the AI-slop anti-pattern table. For HTML documents, extract the `<svg>` block from the template and drop it into a `<figure>`. For slides, reuse the diagram structure as a slide visual instead of treating the HTML file itself as a deliverable.

Before drawing, always ask: **would a well-written paragraph teach the reader less than this diagram?** If no, don't draw.

**Auto-select charts from data.** When content contains numerical data, choose the chart type and embed it without waiting for the user to specify. Decision tree (first match wins):

| Data shape                                                             | Chart          |
| ---------------------------------------------------------------------- | -------------- |
| Has open/high/low/close fields, or per-day price                       | Candlestick    |
| Has + and - contributions that sum to a total (bridge, waterfall, P&L) | Waterfall      |
| One series, values sum to ~100%, items ≤ 6                             | Donut          |
| One series, values sum to ~100%, items ≥ 7                             | Bar            |
| Two or more series across time (months, quarters, years)               | Line Chart     |
| One series across time, large count changes dominate (not rate)        | Bar Chart      |
| Multiple categories, same time snapshot, 2+ series                     | Bar Chart      |
| 2×2 strategic or priority positioning                                  | Quadrant       |
| Hierarchical data with depth ≥ 2                                       | Tree           |
| Process with decision branches                                         | Flowchart      |
| Cross-team or cross-role process with ≥ 3 actors                       | Swimlane       |
| Set overlaps or shared attributes between 2-3 groups                   | Venn           |
| Category comparison, single series, no time axis                       | Bar Chart      |

When data fits multiple types, prefer the one that shows variance most clearly. Always embed inside a `<figure>` with a caption that states the insight, not just the data range.

## Step 2.1 · Source and material pass

Run this before distilling or filling content when the document depends on facts or materials outside the user's draft. Skip it only for personal drafts where the user already supplied everything needed.

### Source check

Trigger when the document mentions a specific company, product, person, release date, version, funding round, metric, market fact, technical spec, or any current fact likely to change.

- Use primary sources before writing: user-provided material, official site, docs, filings, press release, app store page, or repo release
- Keep a short note of source names and dates for facts that drive the document
- If sources conflict or a fact cannot be checked quickly, ask the user instead of choosing silently
- Avoid current-sounding claims such as "latest", "recent", "new", version numbers, launch dates, or financial figures unless they are checked

### Material check

Trigger when the document is about a company, product, project, venue, or personal brand.

Confirm the materials that make the subject recognizable before layout:

| Need          | Required when                        | Accept                                                              |
| ------------- | ------------------------------------ | ------------------------------------------------------------------- |
| Logo          | Any branded document                 | User file or official SVG/PNG                                       |
| Product image | Physical product / venue / object    | Official image, user image, or marked gap                           |
| UI screenshot | App / SaaS / website / tool          | Current screenshot, official product image, or user capture         |
| Brand colors  | Branded one-pager / portfolio / deck | Official value, extracted asset value, or keep folio cinnabar-coral |
| Fonts         | Only if brand typography matters     | Official font, close system fallback, or folio default              |

If a required item is missing, use a compact gap table and ask once. Do not replace missing material with generic imagery, approximate logo drawings, or invented values.

### Materials status block

After the material check, output a structured status block before continuing. This is a one-shot transparency display, not a question:

```
Materials status:
- Logo: OK assets/client-logo.svg
- Brand colors: OK #B83D2E mapped to --brand
- Product screenshot: MISSING (proceeding with folio default placeholder)
- UI screenshot: not required for this doc type
```

Use `OK`, `MISSING`, or `not required`. If a required item is missing and no user input arrived, ask once with the gap table; otherwise continue silently.

## Step 2.5 · Distill raw content (if applicable)

**Auto-detect whether to distill.** Do not ask the user; judge from the input:

| Skip distill (fill directly)                                       | Run distill                                                         |
| ------------------------------------------------------------------ | ------------------------------------------------------------------- |
| Content has explicit section labels matching template structure    | Raw prose without section structure                                 |
| Metrics already quantified with units in place                     | Numbers scattered or implied, not extracted                         |
| User wrote "use this as-is" / "直接用这个" / "原封不动"            | User pasted multi-source dump (chat / email thread / multiple docs) |
| Content count matches template (e.g. 4 metrics for 4 metric cards) | Content count mismatches template (too many or too few items)       |
| One coherent voice with consistent claims                          | Conflicting claims or duplicate facts across sources                |

When in doubt, run distill. Distill is cheap; rebuilding a misaligned doc is not.

When the user hands over **raw material** (meeting notes, brain dump, existing doc in different format, chat transcript, scattered points):

1. **Extract**: pull out every factual claim, number, date, name, source, material reference, and action item
2. **Classify**: map each extract to the target template's sections (see `references/writing.md` for section structure per doc type)
3. **Gap-check**: list what the template needs but the raw content doesn't have - include missing facts, missing proof, and missing materials
4. **Ask once**: share the gap table with the user. Do not guess to fill gaps.

Example gap-check:

| Template needs    | Found                       | Missing                      |
| ----------------- | --------------------------- | ---------------------------- |
| 4 metric cards    | "8 years", "50-person team" | 2 more quantifiable results  |
| 3-5 core projects | 2 mentioned                 | at least 1 more with outcome |
| Materials         | logo file provided          | product screenshot source    |

Then proceed to Step 2.6 (slides) or the layout note (all other doc types) with structured, distilled content.

## Step 2.6 · Deck pre-flight (slides only)

Skip this step for every doc type except slides.

Before drafting any slide, confirm these six points with the user. Ask all six in one shot, not one at a time:

| #   | Question                                                                                                                |
| --- | ----------------------------------------------------------------------------------------------------------------------- |
| 1   | **Audience + venue** - who is in the room, and is it live keynote, investor 1:1, or async share link?                   |
| 2   | **Length target** - presentation time or slide count? (15 min: ~10 slides / 30 min: ~20 slides / 45 min: ~25-30 slides) |
| 3   | **Source material** - what content is already ready: outline, doc, notes, data?                                         |
| 4   | **Images** - are screenshots, charts, logos, or product images available, or are gaps expected?                         |
| 5   | **Hard constraints** - brand colors, required logo, PPTX-only vs. PDF+PPTX, any slides that must exist?                 |
| 6   | **Format confirmation** - slides deck, or a one-pager that looks like a deck?                                           |

If the user has already answered any of these in the conversation, skip only those questions.

## Step 2.7 · Layout note (transparent, non-blocking)

Before loading specs and filling the template, write a short editor-style note stating the layout intent: template choice, length target, narrative arc, embedded diagrams, material status, and output formats. Match the document's language. Keep it under 80 words, written as prose, not a status panel. Continue immediately after; do not wait.

Example (CN):

> 排版意图：Equity Report 中文版，2 页 A4。先立论与目标价，进入估值 (DCF 与可比公司)，落于催化剂与风险。中段嵌一张营收趋势折线和 FY26 收入桥瀑布。Logo 已就位，产品图暂缺，header 改走纯文字。输出 HTML 与 PDF。

Example (EN):

> Layout intent: Equity Report (EN), two pages A4. Open with thesis and price target, run through valuation (DCF and comparables), close on catalysts and risks. A revenue line chart and an FY26 waterfall sit mid-doc. Logo is in hand; product image is absent, so the header stays text-only. Output: HTML and PDF.

The note is for transparency, not approval. If the user pushes back, adjust; otherwise proceed to Step 3.

---

## Step 3 · Load the right amount of spec

Pick the tier that matches the task. Default to the lowest tier that covers the work.

| Tier                    | When                                                                               | Read                                                 |
| ----------------------- | ---------------------------------------------------------------------------------- | ---------------------------------------------------- |
| **Content-only**        | Updating text, swapping bullets, translating an existing doc. CSS stays untouched. | `CHEATSHEET.md` only                                 |
| **Layout tweak**        | Adjusting spacing, moving sections, changing font size within spec. CSS touched.   | `CHEATSHEET.md` + template (tokens already inline)   |
| **New document**        | Building from scratch or from raw content.                                         | Full design spec + writing spec + template           |
| **Sources / materials** | Company, product, market, launch, funding, specs, or branded subject.              | `writing.md` source rules + user/source material     |
| **Deck (>20 slides)**   | Long presentation needing Part Divider, Code Cards, section headers.               | Full design spec + Deck Recipe (design.md section 8) |
| **Troubleshoot**        | Rendering bug, font issue, page overflow.                                          | `production.md` (+ design spec if CSS is the cause)  |
| **Diagram**             | Embedding SVG in a doc.                                                            | `diagrams.md` only (has its own token map)           |

You can always escalate mid-task if the work turns out to need more than the initial tier.

The full spec files for reference:

- Design: `references/design.md`
- Writing: `references/writing.md`
- Production: `references/production.md`
- Diagrams: `references/diagrams.md`

## Step 4 · Fill content into the template

- For HTML documents, copy the nearest `.html` template into your working area; don't write the whole file from scratch
- For slides, copy `slides.py` / `slides-en.py` and edit the content blocks; the deliverable is `output.pptx`
- Keep styling changes minimal and inside the existing system. Content edits come first; only touch tokens or layout rules when the task actually requires it
- Content follows `writing.md`: data over adjectives, distinctive phrasing over industry clichés
- **Before filling, read the quality bar for your document type** in `writing.md` section "Quality bars by document type". Structure is necessary but not sufficient: a resume bullet needs Action + Scope + Result + Business Outcome; an equity report needs variant perception + quantified catalysts; slides need assertion-evidence titles. Meeting the quality bar is as important as filling every placeholder.

### Fill PDF metadata (WeasyPrint reads these into the PDF)

Every template has meta placeholders in `<head>`. Fill all four before building:

| Placeholder (CN)                     | Placeholder (EN)                            | Rule                                                                                                                              |
| ------------------------------------ | ------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `{{作者}}`                           | `{{AUTHOR}}`                                | Resume/letter/portfolio: use the person's name from the doc. All others: leave as-is (build script infers from git config or env) |
| `{{摘要}}`                           | `{{DESCRIPTION}}`                           | Extract one sentence (≤150 chars) from the first 2 paragraphs                                                                     |
| `{{关键词}}`                         | `{{KEYWORDS}}`                              | 3-5 keywords from the title + section headings, comma-separated                                                                   |
| `{{文档标题}}` / `{{信件主题}}` etc. | `{{DOC_TITLE}}` / `{{LETTER_SUBJECT}}` etc. | Infer from the H1 or `.header .title` text                                                                                        |

`<meta name="generator" content="Folio">` is already fixed in the template; do not change it.

**Author inference**: `build.py` automatically sets PDF `/Author` metadata from:

1. `git config user.name` (primary)
2. `FOLIO_AUTHOR` environment variable (fallback)
3. `"Folio"` (final fallback)

For personal documents (resume/letter/portfolio), the HTML `<meta name="author">` should match the person's name in the content. For non-personal documents (one-pager/long-doc), leave the placeholder as-is and let the build script infer it.

## Step 4.5 · Auto-select output format

Do not ask the user which format to export. Decide from context:

| Signal                                             | Output                     | Why                                                           |
| -------------------------------------------------- | -------------------------- | ------------------------------------------------------------- |
| HTML document request                              | HTML + PDF                 | PDF is the default deliverable, HTML is the editable source   |
| Slides / PPT / deck                                | PPTX                       | Current slide templates build directly to PowerPoint          |
| Slides that explicitly need PDF sharing            | PPTX + follow-up PDF export | PDF is a downstream export step, not the primary build target |
| "分享" / "发朋友圈" / "share" / "post" / "preview" | + PNG                      | Social platforms and messaging need images                    |
| "嵌入" / "插图" / "embed in another doc"           | PNG only                   | Used as material inside other documents                       |
| User explicitly says a format                      | Follow the user            | Explicit request overrides auto-selection                     |

For HTML documents, PDF always ships. For slides, PPTX is the primary output. PNG follows sharing context.

## Step 5 · Build & verify

```bash
python3 scripts/build.py --verify           # build all templates + page count + font check + slides
python3 scripts/build.py --verify resume-en # single target full verification
python3 scripts/build.py --verify slides    # single slide deck verification
python3 scripts/build.py --check-rhythm     # slide rhythm check for slides / slides-en
python3 scripts/build.py --check-placeholders path/to/filled.html
python3 scripts/build.py --check            # CSS rule violations only (fast, no build)
```

Source templates intentionally keep `{{...}}` fields. Run placeholder checks on completed documents, not on the template library.

Visual anomalies (tag double rectangle, font fallback, page break issues) -> `production.md` Part 4.

## Fonts

**Chinese**

- Main serif: LXGWWenKai-Regular.ttf (400 weight) + LXGWWenKai-Medium.ttf (500 weight, real bold)
- Templates use dual @font-face declarations: Regular for body text, Medium for headings
- Both files are open-source. Keep them available in the workspace for local preview and remote fallback, but do not bundle them inside Claude Desktop skill ZIPs
- Fallback chain baked into templates: Source Han Serif SC -> Noto Serif CJK SC -> Songti SC -> STSong -> Georgia

**English**

- Single serif: Charter (system-bundled, macOS/iOS), used for both headlines and body
- No separate sans: `--sans: var(--serif)`, one font per page
- Fallback: Georgia (cross-platform) / Palatino / Times New Roman

Font files next to HTML with relative `@font-face` paths is the most stable setup. `scripts/package-skill.sh` excludes LXGW WenKai TTFs from the Claude Desktop ZIP.

**Font auto-recovery (Claude Desktop)**

Before building Chinese documents, check font files. If missing, download into `assets/fonts/`:

```bash
# Check
test -f assets/fonts/LXGWWenKai-Regular.ttf || {
  curl -fsSL "https://raw.githubusercontent.com/lxgw/LxgwWenKai/main/fonts/TTF/LXGWWenKai-Regular.ttf" \
    -o assets/fonts/LXGWWenKai-Regular.ttf
  curl -fsSL "https://raw.githubusercontent.com/lxgw/LxgwWenKai/main/fonts/TTF/LXGWWenKai-Medium.ttf" \
    -o assets/fonts/LXGWWenKai-Medium.ttf
}
```

Run once before building. If network is unavailable, WeasyPrint falls back to Source Han Serif SC.

## Feedback protocol

When the user gives **vague visual feedback** ("looks off", "太挤了", "not elegant"), do not guess. Ask back with current values:

| User says                        | Ask about                                                                   |
| -------------------------------- | --------------------------------------------------------------------------- |
| "太挤了" / "too cramped"         | Which element? Line-height (current: X)? Padding (current: Y)? Page margin? |
| "太松了" / "too loose"           | Same direction, reversed                                                    |
| "颜色不对" / "color feels wrong" | Which element? Brand blue overused? A gray reading too cool?                |
| "不够好看" / "not polished"      | Font rendering? Alignment? Whitespace distribution? Hierarchy unclear?      |
| "看着不专业" / "unprofessional"  | Content wording? Or layout (alignment, consistency)?                        |

Template response: "X is currently set to Y. Would you like (a) [specific alternative within spec] or (b) [another option]?"

Never say "I'll adjust the spacing" without naming the exact property and its new value.

---

## When not to use this skill

- User explicitly wants Material / Fluent / Tailwind default - different design language
- Need dark / cyberpunk / futurist aesthetic (this is deliberately anti-future)
- Need saturated multi-color (this has one accent)
- Need cartoon / animation / illustration style (this is editorial)
- Web dynamic app UI (this is for print / static documents)

---

Next: **apply Step 3's tier table to decide what to read**, then copy the matching template and start filling.
