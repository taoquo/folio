# Kami 六个月观察：哪些改进值得 Folio 借

> 本文只做判断，不做实施。所有数字来自实际命令，可复核。
> 调研时间：2026-11-10。分支：`Enhanced`。
> 对象：`github.com/tw93/kami`，V1.4.2（2026-05-10）到 V1.20.0（2026-10-29）：337 个提交、25 个发布。

---

## 0. 结论

1. Kami 这半年几乎没有加"新能力"，它做的是**把"好看"变成一次可执行的判决**：一条交付命令、一份活阈值、一套按门禁分类的标注语料、一组针对 CJK 屏幕排版的实测结论。
2. 我们的检查器比它细（渲染器 box tree、已批准基线、11 条实测规则、stage 构图），但出口是散的：一个能力一条命令，CI 里排成一行。它反过来：能力少，出口一个。**这一条最值得借。**
3. 它的 CJK 屏幕结论值得借，但借之前有个前提：**我们的中文阅读页正文只有 1.5% 汉字**。今天加任何 CJK 规则，都没有页面能证明它生效。

---

## 1. 它这半年做了什么

按能力分组，不按时间。括号里是发布号。

### 1.1 交付门禁：从"一串命令"到"一个判决"

- `build.py --deliver`（V1.17.0）按固定顺序跑完全部门禁，渲染，导出每页 PNG，给 `READY` / `NOT READY`；单独命令保留，只为调试某一个门禁。
- 检查结果分四类：`ERROR` 阻断、`WARN` 交给人看页面图、`GAP` 是素材缺口（`[DATA NEEDED]`）、`SKIP` 说明为什么没跑。措辞不同，读者不用猜。
- 失败不覆盖上一份好文件（V1.12.0 / V1.13.0）；隐藏文本、可见性存疑的 HTML、像本地路径的远程 URL 都不能让检查通过。
- 同一条判决同时供 CLI 和 MCP（`kami_deliver`，V1.18.0），工具表与门禁表由测试对齐。

### 1.2 阈值、门禁、语料三者绑定

- `references/checks_thresholds.json` 是活输入：改一个数字就改门禁，密度 0.25 / 0.50、孤行 ≤2 词且 <15 字符、简历填充 0.83–0.95、页差 ≤0.12。
- `scripts/tests/corpus/<gate>/{flag,pass}/` 是按门禁分目录的标注语料，渲染后判定。改阈值前先跑，**翻转的夹具是这次改动的代价，不是噪声**。
- 它把阈值写成数据、把语料写成反面证据，于是"这个数字调多少"变成可讨论的问题，而不是口味之争。

### 1.3 字体：可移植性与"谁真的画了字"

- V1.18.0：韩文在 macOS Preview 和 MuPDF 里是空白，因为 WeasyPrint 把 CID-keyed CFF 子集化成了 Poppler 能画、Quartz 画不出的 PDF。修法不是换字体，是在渲染前把 CFF 转成 TrueType 副本并缓存（`font_compat.py`）。
- 同一发布：`hangul.py` 在渲染副本里给韩文词插 U+2060，只在词间断行。WeasyPrint 不认 `word-break: keep-all`。
- V1.11.0：每份 PDF 检查"真正画出 CJK 的那个家族"，而不是"字体嵌入了没有"。字体栈写错、回退到系统无衬线，渲染完全正常，只有这一项能发现。
- V1.16.0：WeasyPrint 70 让 `target-counter` 全部变 0，`--verify` 逐条比对目录锚点与页码，因为 `0` 是"看起来合法"的文本。

### 1.4 屏幕端 CJK 工艺（对我们最直接）

- V1.19.0 字体栈按"文本在哪里渲染"排序；中文自托管 WOFF2 子集，`unicode-range` 限定 CJK、全角标点、`“”` 和 `…`，拉丁页面不下载；子集保留 `halt`（`--layout-features=kern,liga,halt`）。
- V1.19.0 中文/日文去掉 `text-wrap: pretty`、`text-wrap: balance`、`line-break: strict`、`word-break: keep-all`，加 `hanging-punctuation: allow-end`；行内 chip 用 `display: inline` + `nowrap`，不用 `inline-block`。
- V1.19.0 屏幕字号四级、12px 地板、两级文字颜色、同心圆角（内圆角 = 外圆角 − 间距）。
- V1.20.0 表格首末列贴齐正文边缘：此前单元格内边距让表格文字比上方标题缩进一截。

### 1.5 产物可追溯

- `--chart`（V1.18.0）把 JSON 画成 SVG，spec 嵌进 `data-kami-spec`；`--check-charts` 从 spec 重新生成再比对，手改一个标签同样失败。
- 内容 IR 先校验结构再排版（V1.17.0 / V1.12.0），覆盖检查拒绝隐藏文本（V1.13.0）。

### 1.6 发布工程

原子渲染、失败保留上一份、ZIP 按 allowlist 打包、`claude plugin eval` 端到端评测加 `evals/score.py` 确定性复核。这部分是分发，不是排版。

---

## 2. 我们的实测对照

| 维度 | Folio 今天 | Kami | 判断 |
|---|---|---|---|
| 静态规则 | 51 条 `W-*` | 规则集内嵌 `lint.py` | 我们更细 |
| 实测规则 | 11 条 `V-*`（Chromium 实测） | PDF 像素 + 版面几何 | 各有所长 |
| 断行判定 | 读渲染器 box tree | 读 PDF 文本块 | 我们更准 |
| 门禁出口 | 多命令，CI 串行 | `--deliver` 一个判决 | 它更整 |
| 阈值 | 代码常量 + 校准注释 | JSON 活输入 | 各有代价 |
| CJK 屏幕 | 有规则，无内容 | 有规则，有内容 | 见 2.3 |
| 字体可移植 | 未检查 | CFF→TrueType | 见 2.5 |

### 2.1 表格文字比正文缩进 10px

在 1280 宽渲染中文系列，取第一个表格首个单元格的文字左缘，与上方段落文字左缘比较：

```text
paragraphTextLeft  260.0
firstCellTextLeft  270.0
inset               10.0     (cellPaddingLeft = 10px)
```

`assets/templates/web/base.css` 给 `.tbl th, .tbl td` 统一 `padding: var(--web-space-3) var(--web-space-5)`，首末列的内边距把整张表推离了文字边。这就是 Kami V1.20.0 修掉的同一个缺陷。

### 2.2 中文标题的 `text-wrap: balance` 让每行只填 76%

`base.css` 有 6 处 `text-wrap: balance`。把标题换成一段中文，在三个宽度比 `balance` 与 `auto` 的行宽：

| 宽度 | balance | auto |
|---|---|---|
| 390 | 3 行，267 / 267 / 267，每行 76% | 3 行，327 / 327 / 149，前两行 93% |
| 768 | 2 行，386 / 416，76% 与 82% | 2 行，653 / 149，97% |
| 1280 | 2 行，386 / 416，51% 与 55% | 2 行，743 / 59，98% |

行数一样，总宽一样，差别只在分配。拉丁标题两端齐平更好看，中文的习惯是除末行外每行排满。**同一属性对两种文字给出相反答案**，所以正确做法不是删掉它，是按文字系统分流。

### 2.3 中文阅读页正文只有 1.5% 汉字

`references/fixtures/web/attention/attention.frag.html` 的 `language` 是 `zh-Hans-CN`，但正文是英文论文：

```text
han=354  latin=23735  han_share=1.47%
h2/h3 共 22 个，汉字标题 0 个
```

于是：W 规则里所有"中文行宽、中文行距、汉字断行"的判断，V 规则里所有 CJK 实测，今天都跑在一个 98.5% 是英文的页面上。`corpus.py` 自己的 docstring 就警告过这件事（"a corpus that quietly becomes all-Latin is the failure this guards against"），只是没管到 Web 这一侧。

### 2.4 共享码位由拉丁字体提供

中文系列的字族栈是 Source Serif 4 在前、LXGW WenKai 在后（这是有意的：英文正文保持全站同一套衬线）。浏览器按字形逐个解析，于是 `…`、`“”`、`—` 这些两种文字共用的码位全部落到 Source Serif 4：

```text
字数 20px：      栈      Source Serif 4    LXGW WenKai
…   U+2026      16.4        16.4              20.0
—   U+2014      16.24       16.24             20.0
“   U+201C       8.3         8.3               7.0
中  U+4E2D      20.0        20.0              20.0
```

省略号和破折号的面选择会改变步进宽度（16.4 / 16.24 对 20）。今天这 6 个省略号全在数学式 `x₁, …, xₙ` 里，所以页面上看不出问题；这同样是等中文正文到位才暴露的问题。

### 2.5 中文阅读页向读者发 24 MB 字体

```text
dist/web/fonts/JetBrainsMono.woff2            54K
dist/web/fonts/LXGWWenKai-Regular.ttf         24M
dist/web/fonts/SourceSerif4Variable-Roman.ttf  1.1M
```

页面里三个 `@font-face` 都指向原文件：无子集、无 WOFF2（拉丁与中文）、无 `unicode-range`。中文系列只要出现一个汉字就整份下载。英文系列只引 JetBrains Mono，不受影响，说明投影层已经按语言过滤了字族，缺的只是**同一字族的交付形态**。

---

## 3. 建议借的

按杠杆排序。每条给：借什么、为什么、怎么做、怎么验证、代价。

### B1 先给中文阅读页一份真的中文夹具（前置）

- **为什么**：2.3 之下，B2 到 B4 全部无法验证。先有内容，再谈规则。
- **怎么做**：新增一份 `references/fixtures/web/` 的阅读页，正文中文占比 > 60%，必须包含：中文标题（长到 390 宽换行）、全角标点贴行尾、`“”` 与 `…`、中英混排段、含中文的表格、含中文的图注。与 attention 并列，不替换它。
- **怎么验证**：`corpus.py coverage` 式的脚本报出每份 Web 夹具的汉字占比，低于阈值即失败。
- **代价**：一份内容（写作量），加一条占比检查（小）。

### B2 单一交付出口

- **为什么**：我们已经有 `box_inspector`、`quality_vector`、`document_baseline`、`fidelity`、`verify`、`web-plan --gate`，但一个目标要走完全部检查，得靠 CI YAML 记住顺序。顺序是人记的，就会漏。
- **怎么做**：`folio.py deliver <target>`，固定顺序、单一判决。沿用我们已有的三值语言（PASS / REVIEW / FAIL），**不要**引入总分，这与 `quality_vector.py` 的立场一致。末尾打印一份固定的评审清单，并要求逐张看页面图。
- **怎么验证**：`deliver` 的每一步必须是既有函数的调用，不许新增判定逻辑；测试断言"`deliver` 的检查集合 == 单独命令的并集"，新加一个门禁不进 `deliver` 即失败。
- **代价**：中等。新增一个编排层，但它是唯一新增的抽象。

### B3 阈值登记表 + 按门禁分类的语料

- **为什么**：这正是我们自己路线图里的 P5（`references/web/rules.yaml`）。Kami 多给了一样东西：**改阈值必须说明哪些夹具翻转**。
- **怎么做**：按 P5 推进；补 `tests/corpus/<rule>/{pass,flag}/` 的 Web 侧语料，先覆盖断行、行宽、表格对齐三类。
- **怎么验证**：改登记表中的一个数字，语料报告列出翻转项；没有翻转项说明这条阈值没有被测到。
- **代价**：中。语料要写，但每条规则只写两份。

### B4 CJK 字体交付：子集 + WOFF2 + `unicode-range`

- **为什么**：2.5 的 24 MB，以及 2.4 的码位归属。两件事同一个修法。
- **怎么做**：构建期按系列实际用字（加常用字兜底）子集化 CJK 面，输出 WOFF2；`unicode-range` 覆盖 CJK、全角标点、`“”…`；保留 `halt` 特性；拉丁面同样转 WOFF2。全角标点的码位由 CJK 面持有，拉丁字母仍走 Source Serif。
- **怎么验证**：`dist/web/*/index.html` 的字体总字节设上限（例如 1 MB）；实测 `…` 的面归属与步进宽度；英文系列仍然只下载 mono。
- **代价**：中。需要 `fonttools`（已在依赖里）与一个子集步骤；子集化让"字体字节"成为可回归的量。

### B5 表格外缘贴齐正文

- **为什么**：2.1 的 10px，读者一眼能看出表格没有和标题对齐。
- **怎么做**：`.tbl th:first-child, .tbl td:first-child { padding-left: 0 }`，末列同理；需要底色或斑马纹的表格保留内距并通过修饰类退回。
- **怎么验证**：新增实测规则（V-*）：表格首个单元格文字左缘 == 段落文字左缘，误差 ≤ 0.5px；末列右缘同理。
- **代价**：小。

### B6 `text-wrap` 按文字系统分流

- **为什么**：2.2 的实测。拉丁标题保留 `balance`，CJK 标题交给 `auto`。
- **怎么做**：用已有的逐块 `lang` 投影，在 `:lang(zh)` 下把标题的 `text-wrap` 覆盖为 `auto`；不要全局删除。
- **怎么验证**：实测规则：CJK 标题的非末行填充率 ≥ 0.90；拉丁标题维持现状。
- **代价**：小。

### B7 字体格式可移植性

- **为什么**：我们全仓是 TTF，今天没有 CID-CFF 风险；但 `SourceSerif4Variable-Roman.ttf` 是变量字体，PDF 里以 `Source-Serif-4,` 之类的名字出现，且一份 PDF 里出现 9 个子集。变量字体在部分阅读器里的实例化行为没有保证。
- **怎么做**：在 `verify` 的字体检查里加一项**格式**判定：内嵌字体必须是 glyf/TrueType；变量字体在渲染前实例化为静态字重，或在报告里明确标注。若将来接入 OTF/CFF，再加转换步骤。
- **怎么验证**：`pdffonts` 的类型列 + 一个"变量字体已实例化"的断言。
- **代价**：小到中，取决于是否真的引入了 CFF。

### B8 渲染原子写

- **为什么**：`render_html_to_pdf` 直接写目标；一次失败的渲染会留下半份文件，而我们的基线比对假定产物完整。
- **怎么做**：写临时文件再 `os.replace`；失败时保留上一份。
- **怎么验证**：注入一个渲染失败，断言旧产物仍在、且未被截断。
- **代价**：极小。

### 次要两条

- **B9 文档里的 CSS 片段也是产物**：`references/design.md` 有大量 ` ```css ` 代码块，今天只被 `check_links.py` 跳过。Kami 用同一套模板规则扫描文档里的 fenced CSS/HTML，反例用 `/* avoid */` 标注。我们有 token 体系，做这件事成本很低。
- **B10 区分"素材不够"与"排坏了"**：Kami 的 `resume_thin_source` 在两页都合格但总和不足时，报数据缺口而不是版式错误。我们 `page_contracts` 只报页数；溢出或欠页时，先判内容量再判版式，措辞应当不同。

---

## 4. 明确不借

| 它做的东西 | 为什么不借 |
|---|---|
| 韩文支持（`hangul.py`、韩文模板、字体回退链） | 我们没有 `ko`。加一种文字是产品决定，不是工艺改进。若将来加，`hangul.py` 的 U+2060 做法直接可用。 |
| MCP server、插件市场、skill 打包、站点 SEO | 分发层。我们已经有 CLI 与 AGENTS.md 这条路，不需要第二套。 |
| LLM 端到端评测（`evals/` + `claude plugin eval`） | 成本高，与"确定性格门禁"的哲学不同。可留作以后：`score.py` 用 regex 复核 LLM 产物这一点值得记。 |
| 模板内联 CSS | 我们也是这么做的，互相印证，不必改。 |
| 从网站提取品牌色（`brand_extract.py`） | 我们已有 theme 体系与 `scaffold_theme_scheme.py`；把"对比度不达 4.5:1 就压暗"这条规则吸收进现有工具即可，不必新建脚本。 |
| 六种语言的 README | 我们是中英一对，是明确约定。 |
| Social Cards（1242×1660、8 种纸色、一 section 一图） | 那是海报与投放物料，不是文档。我们真正的缺口是**分享链接没有预览**：全部页面零 `og:` 标签，阅读页连 `description` 都没有，而卡片要的文字 `series.json` 里已经有了。分析与方案见 `docs/exploration/og-share-metadata.md`（已按该文 P0–P3 实施，见其 §11）。 |
| 页面密度 0.25 / 0.50 这种两档阈值 | 我们的 `quality_vector` 已有 `page_fill_cv`、`thin_page_ratio`、末行比，分档更细。它的两档是简化，不是进步。 |

另外一条**它做得对、但我们不必照搬**的：模板各自内联全文 token，靠 `--sync` 检查漂移。我们的投影机制更强，保持现状。

---

## 5. 需要拍板的三件事

1. **先补中文夹具，还是先做交付出口？**
   我倾向先补夹具：B2 到 B6 里有四条依赖它，而它本身一天能做完。先做 B2 则会在没有内容的情况下把门禁定型。
2. **`folio.py deliver` 的判决语言用哪套？**
   我们已有 PASS / REVIEW / FAIL（`quality_vector`）与 `OK:` / `ERROR:`（脚本状态）。Kami 的 READY / NOT READY 是给"一份可交付文件"用的第三人称结论。三者是否要收敛成一套，需要定。
3. **字体子集化的边界**：按系列用字子集（最小，但换内容就要重建），还是按常用字表子集（稳定，但仍有冗余）？
   前者把"页面字数"变成构建输入，后者牺牲一部分体积换可预测性。

---

## 附：本次测量的复现方式

- 2.1 / 2.2 / 2.4：Playwright（`channel="chrome"`，Chromium 157）打开构建产物，用 `Range.getClientRects()` 读行盒，用 canvas `measureText` 比较字面步进。
- 2.3：`<script>/<style>` 剥离后统计 `[一-鿿]` 与 `[A-Za-z]`。
- 2.5：`ls -lh dist/web/fonts`，与 `@font-face` 的 `src` 对照。
- 构建命令：`folio.py web --series references/fixtures/web/attention --out <tmp> --verify`。

这些探针目前是临时脚本；若采纳 B4、B5、B6，它们应当落成 `web_measure.py` 里的 `V-*` 规则，而不是留在 `docs/` 里。
