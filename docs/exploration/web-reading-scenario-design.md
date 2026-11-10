# Web 阅读页场景：重设方案（样式一律来自引擎）

> 状态：**设计提案，剩余 4 处待裁决**。
> 本轮新增原则：**色彩、字体、字号、行高、间距、圆角、阴影、实色、代码块——全部来自排版引擎；Web 模板不自定义任何样式值。**
> 日期：2026-10-24
> 目标稿：`/Users/shuke/Downloads/folio web.md`

---

## 0. 命名澄清（先回答「V1 是什么」）

上一轮我用了「v1 / 参考稿 / v2」三个词，容易混淆。现在固定如下：

| 名称 | 指什么 | 状态 |
|---|---|---|
| **现行规范** | 仓库 HEAD 里的四篇：`references/web-foundation.md`、`web-reading.md`、`web-workspace.md`、`web-checklist.md`（2026-05-10 提交引入） | 要被替换的**文档**，不是实现 |
| **目标稿** | 你给的 `/Users/shuke/Downloads/folio web.md`（178 行） | 新规范的骨架与判据来源 |
| **引擎** | `references/design.md` + `references/profiles/theme/*.yaml` + 投影 + Drawing DSL | 样式的唯一来源 |
| **旧草案** | 之前发现的 dangling 分支（`web-dense-layout` 等） | 已排除，不再作为依据 |

我此前说的「v1 四篇」= **现行规范四篇**。它不是实现，也不是目标稿。

---

## 1. 三个已定决策 + 本轮新增的一条硬约束

| 决策 | 含义 |
|---|---|
| 身份 | **指导层 + 交付物验证**，两者缺一不可 |
| 输出 | **静态 HTML**（单文件、样式内联、独立 URL） |
| 范围 | **只做阅读页**，不做工作台 |
| **新增硬约束** | **样式一律来自引擎**：Web 模板不出现 hex、不定义第二套字号、不引入第二套代码色、不改 `--accent`；主题由 `FOLIO_THEME` 注入 |

这条硬约束把上一轮 6 个冲突里的 5 个直接消掉，并改变了规范写法：Web 规范不再「规定颜色和字号」，而是「**引用引擎角色**」。

---

## 2. 引擎样式对照表（Web 唯一允许的写法）

### 2.1 主题与色彩

| 层 | 引擎来源 | Web 写法 | 说明 |
|---|---|---|---|
| 主题选择 | `FOLIO_THEME` → `references/profiles/theme/*.yaml` | 构建时选择 | 页面里不出现任何 hex |
| 表面 / 文字 / 边框 | `color.surface.*`、`color.text.*`、`color.border.*` | `var(--color-text-primary)` 等 | 投影层由 `scripts/projection.py` 生成 |
| L1 界面强调 | `color.accent.brand` / `brand-tint` / `tag` | `var(--color-accent-brand)` | 替换目标稿里的 `--accent` |
| L2 内容语义 | `color.semantic.*`（已落地，见 §2.2） | `var(--color-semantic-*)` | 10 个含义；每个 scheme 绑自己的调色板 |
| L3 图表取色 | 绘图主题读 `color.series.*`（6 个） | 图内自动取色 | 页面不指定图色 |

**禁止**：Web 模板写 hex / rgb / hsl；用组件 CSS 覆盖主题色；按文档编号分配主题色；引入第二套色板。

### 2.2 L2 语义色：已进入主题 Profile（C1 已实施）

目标稿的十色语义板（violet / blue / … / slate）是**它自己的配色**，不进入引擎。只借用它的**结构**：十个内容含义、每个含义一基一文字档。颜色由各 scheme 自己的调色板绑定，不引入任何外来色相。

三套 theme profile 中的 **`color.semantic.*`（20 个 role）**：

| 内容含义 | classic | forest | slate |
|---|---|---|---|
| `delivered` / `passed` / `enhance` | cinnabar-600 / -800 | pine-700 | azure-700 |
| `info` | slate-600 / warm-850 | forest-700 / -800 | slate-700 / -800 |
| `component` | sage-600 / warm-850 | forest-600 / -650 | slate-600 / -650 |
| `attention` | amber-600 | amber-600 | amber-600 |
| `risk` | slate-600 / warm-850 | forest-650 / -800 | slate-650 / -800 |
| `change` | warm-700 / warm-850 | forest-700 / -800 | slate-700 / -800 |
| `input` / `pending` | warm-500 / -800 | forest-500 / -650 | slate-500 / -650 |

三条设计判断：

1. **角色跨 scheme 固定，颜色来自引擎**：L2 只定义 10 个内容含义；每个 scheme 把它们绑到自己的调色板，不引入外来色相。
2. **两档是硬门禁**：基色对画布/卡片 ≥3:1（图形），文字档 ≥4.5:1（文字）。绑定只允许使用 scheme 已有的 palette 条目，因此不会出现目标稿那种对 parchment 只有 2.60:1 的黄色。
3. **不新增 palette 条目**：语义角色是别名层，指向既有的 cinnabar / amber / slate / sage / pine / forest / azure 与暖中性，`check_theme_schemes.py` 的 reach 检查因此仍然成立。

**门禁结果**：`check_theme_schemes.py` 三套 scheme 全绿（classic 23 palette / 42 roles，forest 与 slate 各 16 / 42）；`check_palette_scale.py`、`color_sources.py`、`build_color_reference.py --design --check`、`build.py --sync`、`ruff` 全部通过；`scaffold_theme_scheme.py` 不再新增 palette 条目，语义 role 是手写别名层，`build_scheme_comparison.py` 对比页与首页画廊已重建。

Web 模板从此只写 `var(--color-semantic-*)`，不出现任何 hex。

### 2.3 字体与字号

目标稿的「双声道 = Sans 叙述 + Mono 元数据」中，**Sans 无法沿用**——引擎规定：

```
--sans: var(--serif);   /* assets/templates/*.html:56 */
```

即引擎没有 sans，叙述与标题同为衬线。因此双声道改为：

| 声道 | 引擎字体 | 用途 |
|---|---|---|
| 叙述 | `var(--serif)`（Charter / Georgia / Palatino + LXGW / Source Han 回退） | 正文、标题、图注 |
| 元数据 | `var(--mono)`（JetBrains Mono + CJK 回退） | 数值、路径、ID、命令、代码 |

若未来确实需要 sans 叙述，正确做法是**给引擎加一个 type role**，而不是在 Web 模板里临时指定字族。

**字号**：目标稿的密度表（正文 12.5–14px、H2 17–20、上限 22）与引擎 pt 阶梯的屏幕换算**本来就吻合**：

| 引擎角色 | pt | ×1.33 | 取整 | 目标稿区间 | 判定 |
|---|---:|---:|---:|---|---|
| Display | 36 | 47.9 | 48 | — | 可用 |
| H1 | 22 | 29.3 | 29 | — | 可用 |
| H2 | 16 | 21.3 | 21 | 17–20（上限 22） | **落在上限内** |
| H3 | 13 | 17.3 | 17 | — | 可用 |
| Body Lead | 11 | 14.6 | 15 | 12.5–14（上限 14） | 略高于上限，长阅读段用 |
| **Body** | 10 | 13.3 | **13** | 12.5–14 | **正中区间** |
| Body Dense | 9.2 | 12.2 | 12 | 12.5–14 | 表格 / 辅助用 |
| Caption / Label / Tiny | 9 | 12.0 | 12 | — | 与 12px 下限一致 |

**结论：不需要新造字号体系。** 用引擎阶梯换算即可；现行规范里的 16–19px 才是例外（已作废）。

**行高**：沿用引擎三档（标题 1.10–1.30 / 密集 1.40–1.45 / 阅读 1.50–1.55）。引擎里「禁止 1.60+」的语境是印刷（原文写的是 "not print"），Web 不需要 1.6+，因此不冲突。

### 2.4 间距、圆角、阴影、实色、代码块

| 项 | 引擎来源 | Web 用法 |
|---|---|---|
| 间距 | `design.md` §3：4pt 基准七档（xs 2–3 … 3xl 80–120），并注明「4pt = 4px on screen」 | 目标稿的篇内边距 24–32px = `xl` 档；卡片 14–18px 取 `lg` 档（16–20）的 16 |
| 圆角 | 组件规格 2 / 4 / 6 / 8 / 16pt | 换算取整使用，不新增档位 |
| 阴影 | §5：ring shadow 与 whisper shadow，参数已给；禁止硬投影 | 直接换算 |
| 实色 | invariant 8：标签底色必须实色 hex，禁止 rgba | 沿用；Web 端同样不写 rgba 背景 |
| 代码块 | §4 `.code-block`：`--ivory` 底 + 0.5pt 边 + 6pt 圆角 + mono 9pt + 行高 1.5 | 直接换算为屏幕值（12px / 1.5） |
| 表格 | §4 `folio-table`：表头 warm、`.compact / .striped / .total` 变体 | 目标稿的 `table.tbl` 映射到这些既有样式 |

**代码块**：目标稿用的是 GitHub Primer light。按本轮约束，改为**引擎代码块**，Primer 不引入。若确实需要语法高亮色，应作为引擎的 code role 扩展，而不是 Web 层新增。

---

## 3. 目标稿与引擎的对账（更新后）

### 3.1 完全匹配，可直接引用

| 目标稿 | 引擎 |
|---|---|
| 画布 960；composition / axis / emphasis；focal ≤2 | `drawing-dsl.md:160`、`:26-30` |
| 节点三档 144×64 / 176×72 / 224×80 | `scripts/drawing/grammar/architecture.py:25-27` |
| 架构 ≤9、甘特 / 热图 ≤10 | `drawing-dsl.md:171-172` |
| contain-fit ≥75%；高度上限 4000 | `drawing-dsl.md:236`、`:249` |
| 文本量测 CJK 1.0 / serif 0.55 / mono 0.62 | `scripts/drawing/typography/measure.py:13` |
| 篇内边距 24–32（上限 40） | 间距 `xl` 档（24–32） |
| 正文 12.5–14 / H2 17–22 | 引擎 Body 13 / H2 21 |
| 实色标签、无 rgba | invariant 8 |
| 代码块底 / 边 / mono | §4 `.code-block` |

### 3.2 目标稿要求、引擎没有的

| 项 | 处理 |
|---|---|
| 10 色语义板 | **必须进主题 profile**（`color.semantic.*`），否则无法系统性换主题 |
| 两种页型 DOM 骨架 | 新建 Web 模板 |
| 页头三件套禁令 | 写进结构契约 |
| 内容组件映射（prose-list / kpi-row / phase-seg / insight / tbl） | 新建组件契约 + 检查 |
| 标题禁用符号 / 编号 / figcaption 句式 | 写进文字契约 + 检查 |
| 四类几何审计 + 视觉落地 + 盲区 | 扩展现有 `scripts/diagram_geometry.py` |
| 实证义务（文件:行号 / Sources / 引擎对照章） | 写进内容契约 + 检查 |
| 13 项验收 / 七步流程 | 写进验收篇 + 检查器 |
| 独立 URL 部署 | 写进交付契约 |

### 3.3 决策状态（C1 已实施，其余 3 项按倾向执行）

| # | 问题 | 决定 | 状态 |
|---|---|---|---|
| **C1** | L2 十色如何落地 | 进主题 profile `color.semantic.*`（三套 scheme 都定义，20 roles） | **已实施并通过全部门禁**（见 §2.2） |
| **C2** | 图表概念色：目标稿说图取 L2 语义色、同概念同色；引擎绘图主题只有 6 个 series | 先做 **10 概念 → 6 series 映射表**，不够再扩 series | 已定，写进 `web-figures.md` |
| **C3** | 行长（measure）：引擎没有；目标稿只给篇内边距 | **60–95 字符**，用渲染字符数验证 | 已定，写进 `web-visual.md` |
| **C4** | 几何 / 渲染审计的运行环境 | L1 静态进 CI；几何与渲染放 nightly 或本地 `--local` | 已定，写进 `web-acceptance.md` |

---

## 4. 规范形态：5 篇 + 4 件套

```
references/web/
  README.md          入口 + 规则 ID 索引 + 检查命令
  web-delivery.md    交付承载 + 两种页型骨架 + 信息唯一性
  web-content.md     内容三原则 + 组件映射 + 标题 / 编号 / 图注 / 双声道
  web-visual.md      密度 + 色彩（全部引用引擎 role）+ 代码块
  web-figures.md     Drawing DSL 宿主合同 + 四类几何审计
  web-acceptance.md  七步流程 + 13 项验收 + 规则↔检查映射
```

四件套：

| 件 | 路径 |
|---|---|
| 模板 | `assets/templates/web/{series-index,module}.html` + `base.css` |
| 契约 | `scripts/web_contracts.py`（页型 / 区域 / 词表 / 禁令 / 密度 / 验收） |
| 检查 | `scripts/check_web.py`（L1/L2/L4）、`scripts/web_geometry.py`（L3） |
| 示例 | `assets/demos/web-<series>/` + `references/fixtures/web/<series>.json` |

**规则 ID**：`W-DLV` / `W-STR` / `W-CNT` / `W-TXT` / `W-DEN` / `W-COL` / `W-FIG` / `W-GEO` / `W-ACC`。每条规则 = ID + 陈述 + 引擎来源 + 检查方式 + 严重度。

---

## 5. 逐章设计要点

### 5.1 交付（`web-delivery.md`）

单文件 HTML、`<style>` 内联、基座逐字节复用、独立 URL、顶栏唯一返回链接、禁下载、无外部 CSS。主题值由 `build_static_theme.py` 烘焙进 `:root`（它已经在处理「浏览器直接打开」的页面）。

| ID | 规则 | 检查 |
|---|---|---|
| W-DLV-01 | 自包含 HTML，无外部 CSS | 静态 |
| W-DLV-02 | 基座块哈希一致 | 静态 |
| W-DLV-03 | 独立 URL 路径 | 构建 |
| W-DLV-04 | 顶栏仅一个返回链接 | 静态 |
| W-DLV-05 | 禁下载 / 禁 base64 工作文件 | 静态 |

### 5.2 结构（`web-delivery.md`）

两种页型：`series-index`（模块 blocks，未建档不占位）、`module-archive`（topbar / doc-head / toc / section×N / doc-nav）。档案头之后禁止三件套。

| ID | 规则 | 检查 |
|---|---|---|
| W-STR-01 | DOM 骨架与类名白名单 | 静态 |
| W-STR-02 | 禁止页头三件套 | 静态 |
| W-STR-03 | 未建档模块不占位 | 构建 |
| W-STR-04 | 信息唯一 + 状态词封闭（已实现 / 代码验证 / 规范 / 引擎对照 / 规划中） | 静态 |

### 5.3 内容（`web-content.md`）

三原则：零删减、组件化、实证优先；结论先行。组件映射表（prose-list / kpi-row ≤4 / phase-seg / insight / tbl / 图）逐条变成检查断言；多子句禁令与 concl 四禁令。

| ID | 规则 | 检查 |
|---|---|---|
| W-CNT-01 | 零删减 | 源 / 渲染文本基线比对 |
| W-CNT-02 | 扫描判据命中即组件化 | 正则 + 组件断言 |
| W-CNT-03 | 多子句堆砌违规 | 启发式 + 人 |
| W-CNT-04 | concl 四禁令 | DOM + 文本 |
| W-CNT-05 | 实证义务（文件:行号 / Sources / 引擎对照章） | 正则 + 章节 |

### 5.4 文字（`web-content.md`）

标题禁用符号表（figcaption 唯一豁免）、编号规则、figcaption 句式、双声道（serif / mono）。

### 5.5 视觉（`web-visual.md`）

密度表全部**以引擎 token 表达**，不写新数值：

| 元素 | 引擎 token | 屏幕值 | 目标稿 |
|---|---|---|---|
| 篇内边距 | `xl` | 24–32px | 24–32（上限 40） |
| H2 | H2 | 21px | 17–20（上限 22） |
| 正文 | Body / Body Lead / Dense | 13 / 15 / 12 | 12.5–14 |
| 卡片内边距 | `lg` | 16–20px | 14–18 |
| 表格行高 | Body × 1.45 + 8–10 | ≈27–29px | 26–30（上限 32） |
| 图表高 | 宿主槽位 | 220–340px | 220–300（上限 340） |
| 死区 | 间距最小档 | ≤24px | ≤24 |
| 语义色比 | 像素直方图 | 80 / 15 / 5 | 80 / 15 / 5 |

色彩：L1 = `color.accent.*`；L2 = `color.semantic.*`（待 C1）；L3 = `color.series.*`（绘图主题）。禁令：不写 hex、不改 `--accent`、界面骨架不用语义色、代码块不染色、单图彩色 ≤4、跨文档同概念同色。

### 5.6 图表与几何（`web-figures.md`）

宿主合同：960 宽、页面高 220–340、架构 ≤9、甘特 / 热图 ≤10、节点三档、focal ≤2、title + desc + id、figcaption 句式、每章 ≥1 图。几何审计四类 + 视觉落地 + 盲区，扩展现有 `diagram_geometry.py`。

### 5.7 验收（`web-acceptance.md`）

七步流程 + 13 项验收。10 项机器判、2 项半自动、1 项人工。

---

## 6. 验证架构

| 层 | 内容 | 时机 | 依赖 |
|---|---|---|---|
| L1 静态 | 骨架 / 类名、token、标题符号、编号、figcaption、链接、标签配对、禁下载、基座哈希 | CI fast gate | 无 |
| L2 渲染 | 密度、行长、溢出、对比度、色比、点击目标 | nightly 或本地 | headless Chrome |
| L3 图形 | 形状 / 连接 / 碰撞 / 斜线 / 视觉落地 | CI 静态 + nightly 视觉 | 解析 + Chrome |
| L4 内容 | 零删减、组件化、多子句 | CI | 源文件 + 渲染文本 |
| L5 线上 | 独立 URL、外链、双页验证 | 发布后 | 人工 |

**关键约束**：L1 必须无浏览器可跑；L2/L3 允许 nightly。

---

## 7. 仓库接口

| 位置 | 动作 |
|---|---|
| `references/web/*.md` | 新增 5 篇 + README，替换现行四篇 |
| `references/profiles/theme/*.yaml` | 新增 `color.semantic.*`（C1 通过后） |
| `assets/templates/web/` | 新增 3 个文件 |
| `scripts/web_contracts.py` | 新增（单一事实源） |
| `scripts/check_web.py` / `web_geometry.py` | 新增（输出 `W-*` ID） |
| `scripts/build_web.py` | 新增（从 series JSON 生成 index + 烘焙模块页） |
| `references/fixtures/web/<series>.json` | 新增（模块元数据） |
| `assets/demos/web-<series>/` | 新增（截图 + 源 HTML） |
| `tests/test_web_contracts.py` | 新增 |
| `build.py` / CI | 小改：`web-*` target；L1 进 fast gate，L2/L3 进 nightly |

**与引擎既有机制的对接**

- 颜色：`projection.py` 产出 `--color-*` → 模板直接消费。
- 主题：`build_static_theme.py` 烘焙静态页 → Web 模板加入 `STATIC_SOURCES`。
- 图形：Drawing DSL 出 SVG → 页面只放槽位与 caption。
- IR：第一阶段不接；第二阶段再评估「同一 IR 出 Web」。

---

## 8. 迁移：现行四篇怎么处理

| 现行内容 | 处置 |
|---|---|
| `web-reading.md` 的阅读结构、布局模式、内容规则、反模式 | 保留并重写（加 ID 与检查） |
| `web-foundation.md` 的 Design Thesis、阅读页结构 | 保留为设计意图 |
| `web-foundation.md` 的 workspace 结构、workspace 骨架、交互语义、动效分层、状态门禁 | 删除 |
| `web-workspace.md` | 删除 |
| `web-checklist.md` 68 项 | 替换为 13 项验收 + 规则映射 |
| 768 / 660–760 / 16–19px / 40px / 12px 等旧数字 | 作废，改用引擎换算 + 目标稿密度表 |
| token 表（`--parchment` 等） | 删除，改为引用 theme profile |

迁移后自检：规范中不得再出现 workspace / dashboard / form / hover-only / state matrix，也不得出现 hex 色值或自定义字号。

---

## 9. 风险

| 风险 | 缓解 |
|---|---|
| 12–15px 正文的可读性 | 200% 缩放 + 320px reflow 必须过；长阅读段用 Body Lead 15px |
| 无 sans 导致密集技术文档偏「书」 | 先按引擎执行；若实测不够，再作为引擎 type role 增补，不在 Web 层临时加 |
| 语义色板需改三套 scheme | 用 `check_theme_schemes.py` 的对比度门禁 + `color_sources.py` 一致性检查兜底 |
| 几何审计依赖浏览器 | L1 独立可跑；几何放 nightly |
| 内容基线维护 | 基线随模块入库，变更时显式重录 |
| 规范再次漂移 | token 检查 + 引用而非抄写 + 规则 ID |

---

## 10. 验证计划

1. 单模块试点：一篇真实长文 → `module.html` + series index。
2. 13 项验收逐项跑，目标 10 机器 / 2 半自动 / 1 人工。
3. 320 / 768 / 1440 / 200% 四组截图，人审「紧而不挤」。
4. 两个模块做同概念同色、同组件同形检查。
5. 盲测：只读新规范的 agent 做一模块，统计猜测点 ≤8。
6. 换主题演练：`FOLIO_THEME=folio-slate-v1` 重建，页面应整体换色且无需改模板。
7. 发布演练：独立 URL + 返回系列链接 + 外链可达。

---

## 11. 下一步

1. **已完成**：C1 语义色进入主题 profile，20 roles × 3 schemes，门禁全绿。
2. 按已定倾向写规范正文：5 篇 + README，规则带 `W-*` ID。
3. 建四件套：`assets/templates/web/`、`scripts/web_contracts.py`、`scripts/check_web.py`、示例与 series JSON。
4. 单模块试点：一篇真实长文 → `module.html` + series index，跑 13 项验收。
5. 换主题演练：`FOLIO_THEME=folio-slate-v1` 重建，确认页面零 hex、整体换色。
6. 第一期只交付模块档案页，系列首页放第二期；几何审计按 C4 分 CI / nightly。
