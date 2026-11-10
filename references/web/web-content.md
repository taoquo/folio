# Web content and text

## 1. Three principles

1. **Nothing is deleted.** A module that follows a source document keeps every
   section, table, code block and number the source has.
2. **Everything becomes a component.** Prose that carries a structure — steps,
   stages, metrics, mappings — is not left as a paragraph. The table below is
   the mapping, and the checker asserts it.
3. **Evidence before assertion.** An implementation claim cites
   `file.py:42`. An industry convention cites sources. A spec-class module
   contains an engine-comparison section.

**Conclusion first.** A heading and its first sentence state the result, not the
chapter name. “The Transformer removes recurrence” beats “Model Architecture”.

## 2. Text feature to component

| Feature in the source | Component | Rule |
|---|---|---|
| ①②③ or numbered steps | `prose-list` | W-CNT-02 |
| three or more `→` in one line | `prose-list` or a pipeline figure | W-CNT-02 |
| two or more `key: value` pairs | list or `multi-card` | W-CNT-02 |
| metrics, thresholds, timeouts | `kpi-row` (at most 4 cards) | W-CNT-02 |
| stages, levels, schedules | `phase-seg`; each `.phase` declares `data-role` | W-CNT-02, W-COL-07 |
| one-sentence conclusion | `insight` | W-CNT-04 |
| mapping or field table | `table.tbl` | W-CNT-02 |
| cross-layer flow | `figure` (layered / pipeline) | W-CNT-02 |
| numbered formula or quoted expression | `p.formula` (mono, one expression per line) | W-CNT-02 |
| `file.py:42`, command or identifier inside a sentence | `code` (mono, inline) | review |

## 3. Prose rules

| Rule | Statement | Check |
|---|---|---|
| W-CNT-01 | Zero deletion against the declared source. | `W-CNT-01` |
| W-CNT-02 | Every matched feature is componentized. | `W-CNT-02` |
| W-CNT-03 | No block carries two independent clauses. `insight`, `card` and `lead` hold one idea; 150 characters is a signal, not the test. | `W-CNT-03` |
| W-CNT-04 | `insight` is one sentence: a conclusion, a warning or a principle. It is never a list header, never a long block, never a second copy of a nearby block. | review |
| W-CNT-05 | Evidence: `file:line` for implementation claims, sources for conventions, an engine-comparison section for spec modules. | `W-CNT-05` |

## 4. Titles

A title names a thing. Symbols that encode a relationship belong in the body.

| Banned in `h1`–`h4` | Replace with |
|---|---|
| `→` `←` `↔` | “至”, “从…到” |
| `+` `×` `=` `≠` | “与”, “定位：”, “不是” |
| `——` | “：” |
| `vs` | “与…的取舍” |
| `·` | “：” or a comma |

`figcaption` is the only exemption: `图 W-1 · 图意` uses `·` to separate the number from the statement.
Rule: **W-TXT-01**.

## 5. Numbering

- Chapter number is two digits, `01`…, one sequence per page.
- Figure numbers are continuous per page and carry the module prefix.
- Never `x-b` suffixes: insert or delete, then renumber the page.

Rules: **W-TXT-02** (chapters), **W-TXT-02b** (figures).

## 6. Figure captions

```
图 <prefix>-<n> · <what it shows>
Figure <prefix>-<n> · <what it shows>
```

The number is assigned by the builder in placement order. The composition and
the reading axis are not part of the caption: they live on the figure's
`data-composition` and `data-axis`, copied from the compiled plan rather than
chosen on the page, and W-FIG-01 compares them with the manifest.
Rule: **W-TXT-03**.

## 7. Two voices

| Voice | Engine font | Carries |
|---|---|---|
| Narrative | `var(--serif)` | body, headings, captions |
| Metadata | `var(--mono)` | numbers, paths, IDs, commands, code |

The engine has no sans: `--sans` is an alias of `--serif`. Do not introduce a
second family in a Web template; if a sans is ever needed, it is an engine type
role, not a page decision.

## 8. The page model

A module fragment is a string, but it is not unstructured. `scripts/web_page.py`
reads it once and returns every **top-level block** of every chapter — the `h2`,
the `h3`, the paragraphs, the lists, the insight and table wrappers, the
figures — each with a role from a closed vocabulary (`BLOCK_ROLES`) and an id
derived from its chapter.

Two consequences follow, and both are rules:

- **W-STR-05**: every top-level block on the built page carries
  `data-folio-role` and a unique `data-folio-id`. A block the model cannot name
  fails the build, because a component nobody declared is not a rendering
  detail.
- **W-STR-06**: the blocks Chromium renders equal the blocks the model counted.
  A block that disappears between the model and the page is a builder defect.

The model never re-serialises the DOM. A block is identified by the source span
of its start tag, and annotation inserts one attribute into that tag; the
fragment stays the skeleton, the way a print template does. Figure placeholders
are comments at model time and become `<figure>` blocks carrying the model's
role and id.

The chapter heading and the TOC summary come from the model too. They used to
be recovered with a regex over the whole fragment, which meant any attribute
added to an `h2` silently emptied the navigation.

`FOLIO_WEB_MODEL` selects the behaviour: `off` (no model, legacy chapter
regexes), `shadow` (build and validate it, leave the source alone), `on`
(annotate; the default). `shadow` and `off` are byte-identical, and a test holds
them that way.
