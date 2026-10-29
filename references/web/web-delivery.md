# Web delivery and structure

## 1. What ships

A module is one self-contained HTML file. Its stylesheet is inline, its figures
are inline SVG, and it needs no build step when it is opened.

| Rule | Statement | Check |
|---|---|---|
| W-DLV-01 | A page has no external stylesheet. `<style>` is inline. | `W-DLV-01` |
| W-DLV-01b | A page has no external script. Reading needs none. | `W-DLV-01b` |
| W-DLV-03 | A module lives at `<series>/<module>/index.html`; changing one module re-uploads one page. | `W-DLV-03` |
| W-DLV-04 | The top bar carries exactly one link, in the page language: `← 返回系列文档` or `← Series index`. | `W-DLV-04` |
| W-DLV-05 | No `download` attribute, no `file://`, no embedded working files. | `W-DLV-05` / `W-DLV-05b` |
| W-DLV-09 | A Chinese page embeds the profile's CJK face through `@font-face`. | `W-DLV-09` |

The theme and screen scale are injected at build time from
`references/profiles/theme/*.yaml` and `references/profiles/web/folio-v1.yaml`
through `scripts/projection.py`. Authors never write a colour, size, family,
spacing value or radius. The `<html lang>` value and the chrome labels come from
`series.json`'s `language`; the two skeletons below show the Chinese labels.

## 2. Module archive skeleton

```html
<body class="doc module-archive" id="top">
  <header class="topbar"><a class="back" href="../index.html">← 返回系列文档</a></header>
  <main class="page">
    <header class="doc-head">
      <p class="kicker">MODULE ARCHIVE · <span>module name</span></p>
      <h1>Module title</h1>
      <p class="lead">One sentence: what this module decides.</p>
    </header>
    <nav class="toc" aria-label="章节目录">
      <li><a href="#s01"><span class="num">01</span><span class="name">…</span><span class="sum">…</span></a></li>
    </nav>
    <section class="chapter" id="s01" data-sum="one-line summary">
      <h2><span class="num">01</span>Chapter title</h2>
      …
    </section>
    <nav class="doc-nav"><a href="../index.html">返回系列文档</a><span class="dot">·</span><a href="#top">回到顶部</a></nav>
  </main>
  <nav class="rail" aria-label="章节刻度">
    <ol>
      <li><a href="#s01" aria-current="true"><span class="tick"></span><span class="label">01 Chapter title</span></a></li>
    </ol>
  </nav>
</body>
```

## 3. Series index skeleton

```html
<body class="doc series-index" id="top">
  <main class="page">
    <header class="doc-head">
      <p class="kicker">SERIES · …</p>
      <h1>Series title</h1>
      <p class="lead">…</p>
    </header>
    <ul class="module-grid">
      <li class="module-block" data-status="已实现">
        <span class="module-num">01</span>
        <h2><a href="./module/index.html">Module</a></h2>
        <p class="module-summary">…</p>
        <div class="module-meta">
          <span class="badge" data-status="已实现">已实现</span>
          <code class="pkg">package-name</code>
        </div>
      </li>
    </ul>
  </main>
</body>
```

A module that has no page does not occupy a block (W-STR-03). The builder writes
the index from `series.json`, so the block count and the page count agree.

| Rule | Statement | Check |
|---|---|---|
| W-STR-01 | The page declares one of the two skeletons; required regions are present. | `W-STR-01` / `W-STR-01b` |
| W-STR-02 | After `doc-head` there is no status-badge row, identity KPI row or evidence note. That information is already in the index block or the body. | `W-STR-02` |
| W-STR-03 | Unbuilt modules do not appear on the index. | builder |
| W-STR-04 | Status vocabulary is closed. | `W-STR-04` |

## 4. Reading rail

Every generated page carries a section scale on the right edge: one tick per
region, in document order — chapters on a module page, module blocks on a
series index. The tick for the chapter in view grows and
thickens; hovering or focusing a tick shows the chapter title. It is a
position indicator, not a second table of contents.

```html
<nav class="rail" aria-label="章节刻度">
  <ol>
    <li><a href="#s01" aria-current="true"><span class="tick"></span><span class="label">01 Abstract</span></a></li>
    <li><a href="#s02" aria-current="false"><span class="tick"></span><span class="label">02 Introduction</span></a></li>
  </ol>
</nav>
```

| Rule | Statement | Check |
|---|---|---|
| W-DLV-06 | One tick per region (chapter or module), same order and anchors as the page's own navigation. | `W-DLV-06` |
| W-DLV-07 | Every tick labels its region; the nav has an accessible name; exactly one tick is `aria-current="true"`. The title shows on hover and on keyboard focus. | `W-DLV-07` |
| W-DLV-08 | The active tick follows the viewport. Inline script only (no external script); without it the ticks still navigate, so the rail degrades to links. | `W-DLV-08` |

The rail is hidden at 900px and below, where there is no room beside the
column, and in print. It is exempt from the density table: ticks are not
content.

## 5. Information uniqueness

The same fact is stated once and referenced afterwards. Package state and
integration state are separate statements, not one badge pretending to be both.

Closed vocabulary — five meanings, each with a Chinese and an English label:

| Meaning | Chinese | English | Group |
|---|---|---|---|
| implemented | `已实现` | `Implemented` | package |
| code-verified | `代码验证` | `Code-verified` | package |
| spec | `规范` | `Spec` | integration |
| engine parity | `引擎对照` | `Engine parity` | integration |
| planned | `规划中` | `Planned` | integration |

A word outside this list is a finding: a reader cannot compare modules whose
states were invented per page. The Chinese and English labels are the same five
statements, not a second taxonomy.

A content component that carries a meaning declares it with `data-role`, drawn
from the ten semantic roles (`delivered`, `info`, `component`, `passed`,
`attention`, `enhance`, `risk`, `change`, `input`, `pending`). A phase bar
without one is a `W-COL-07` finding: its colour would have to be guessed.
