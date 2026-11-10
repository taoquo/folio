# Web 场景的重新定位与重设计（探索备忘录）

> 性质：**假说与选项，不是结论**。目的是把「Web 规范该怎么定位、该改哪里、该长什么样」变成可讨论、可验证的命题。
> 日期：2026-10-24
> 范围：只讨论 Web 场景规范与其产物形态；不重写引擎，不改已发布的 PDF/PPTX 行为。

---

## 0. 一句话假说

**Web 不是引擎的一个分支，而是与「简历 / 长文档 / 一页纸 / 演示」并列的第五类场景。**

在 Folio 里，一个「场景」不是一篇说明文，而是**四件套**：模板 + 页面契约 + 示例 + 门禁。Web 目前是唯一只有说明文、没有四件套的场景——这解释了它为什么「写得好但管不住」，也决定了重设计的重点不是再写一版更长的规范，而是**给 Web 补齐场景形态**，再把规范写成这套形态的说明书。

---

## 1. 定位校验：仓库证据

### 1.1 本项目的「场景」是怎么实现的

| 场景 | 模板 | 页面契约 | 示例 | 门禁 |
|---|---|---|---|---|
| one-pager / letter / long-doc / portfolio / resume / equity-report / changelog | `assets/templates/*.html`（14 个 HTML target） | `scripts/page_contracts.py` 页数区间 | `assets/demos/`（21 份 PDF/PNG） | `build.py --verify`（页数、字体、占位符） |
| slides | `slides.py` / `slides-en.py` | PPTX 契约 | demo-agent-slides | `--verify` + `--check-rhythm` |
| diagram | Drawing DSL + 23 类模板 | 宿主契约（a4 / letter / slide / responsive） | 23 类目录产物 | `verify-drawing-host` + 目录基线 |
| **Web** | **无** | **无** | **无** | **无** |

这不是「还差一点」：**14 个 HTML 场景全部有四件套，Web 一件都没有。**

### 1.2 引擎里已经存在、可以直接复用的资产

重新设计不需要从零造地基——引擎已经有三块与 Web 直接相关的资产：

| 资产 | 位置 | 对 Web 的意义 |
|---|---|---|
| 颜色角色投影 | `scripts/projection.py`：`color.text.primary` → `--color-text-primary` | Web 的 token 层可以**直接由引擎生成**，而不是手抄 |
| IR → HTML writer | `scripts/document_ir/writers/html.py` | 同一份语义模型已经能输出 HTML，只是当前输出的是印刷模板的 class |
| 响应式图形宿主 | `scripts/drawing/hosting.py`：`HostContract("responsive-html", "html-responsive", 960, 540, "px", …, 12, …)` | 图形已经知道怎么进入「响应式 Web 槽位」，且带 12px 最小字号约束 |
| 静态页主题烘焙 | `scripts/build_static_theme.py` | 已经能把主题写进「浏览器直接打开」的页面 |
| 页面契约机制 | `scripts/page_contracts.py` | Web 可以有自己的契约表（不是页数，而是区域/状态/视口矩阵） |

**结论**：Web 缺的不是地基，是**场景层**。

### 1.3 定位判断

用户给的定义是：引擎 = 颜色主题 + 绘图 DSL + 大规则；Web = 面向 Web 场景的排版扩展。

这个定义与仓库结构一致，而且能解释三个此前的困惑：

1. **为什么 Web 规范里没有行高、字重、间距？** 因为这些属于「大规则」，本该由引擎定义（引擎确实定义了：行高 4 档、字重 2 档 + 禁用 900/100、字距 8 条、4pt 基准 7 档、圆角 13 处、阴影 2 种、对比度 8 行）。Web 规范不是「应该有」，而是**应该引用**。
2. **为什么 Web 规范缺断点、交互态、动效、表单？** 因为印刷场景没有这些东西，引擎从未定义。这些是 Web 场景**必须自己定义**的增量，不是引擎的失职。
3. **为什么 Web 规范「看起来什么都有、用起来处处要猜」？** 因为它把「引擎该给的」和「场景该给的」混在一篇散文里，各写了一半：抄了引擎的 token 名（且抄的是陈旧那一版），却漏了引擎的度量；发明了 768px，却没定义视口模型。

---

## 2. 新定位下重读 13 个问题

按「谁该负责」重新分类，结论与上一版审计**不同**：大部分问题从「规范写错了」变成「场景没成形」。

### 2.1 四类归因

| 类别 | 定义 | 修法 | 影响面 |
|---|---|---|---|
| **A. 场景债** | Web 场景该有、但没有 | 补进 Web 规范与产物 | 只动 Web |
| **B. 继承失败** | 引擎已有，Web 没引用/抄错了 | 改成引用引擎 + 一条 lint | 只动 Web（+一条检查） |
| **C. 引擎配合** | 引擎需要提供新能力或修正既有缺陷 | 改引擎 token/文档 | 动引擎，需评估回归 |
| **D. 架构缺口** | 场景四件套缺失 | 新增模板/契约/示例/门禁 | 新产物，低风险 |

### 2.2 逐项重分类

| # | 原问题 | 新归因 | 理由 |
|---|---|---|---|
| 1 | 8 步工作流无完成判据 | **A 场景债** | 流程规范是场景层的事；印刷场景靠模板+契约，Web 没有模板才需要流程 |
| 2 | 三份契约字段不一致 | **A 场景债** | 场景层自造了三套交付清单 |
| 3 | 术语漂移（job/goal、motion/interaction） | **A 场景债** | 引擎术语稳定，漂移发生在场景层 |
| 4 | 42 条禁令分五处 | **A 场景债** | 引擎是手册（8 处禁令分散可接受），场景需要可执行清单却没做 |
| 5 | 契约可隐式（`:298`） | **A 场景债** | 场景层对自己交付物的降级 |
| 6 | 768px vs 660–760px 算术冲突 | **A 场景债** | 视口模型是 Web 场景的核心增量，引擎无此概念 |
| 7 | Selected 用色 vs 禁色 | **A 场景债** | 交互态语义是 Web 增量 |
| 8 | Reveal 位移 vs 不动正文 | **A 场景债** | 动效是 Web 增量 |
| 9 | failure vs error 边界 | **A 场景债** | 状态模型是 Web 增量 |
| 10 | 右栏两套规定 | **A 场景债** | 分册之间未对齐 |
| 11 | 缺行高/字重/字距/间距/圆角/阴影/对比度 | **B 继承失败** | 引擎全有（见 §1.3），Web 一个字没引用 |
| 12 | 缺中文排版 | **B 继承失败** | 引擎有 0.3pt/0.02–0.05em/0.2–1pt 整套规则 |
| 13 | token 名与值失效 | **B 继承失败 + C 引擎缺陷** | 引擎 `design.md` §1 手写块本身陈旧（`--brand:`/`--parchment:`/`--stone #85776F`），Web 抄了陈旧块；生成的角色表才是现行 |
| 14 | 状态色死锁（要 error/success，无状态色，禁第二强调色） | **C 引擎配合** | 引擎有 `color.status.positive/caution/negative/informative`，但是**金融语义**；Web 需要**交互态语义**，需要新增/映射 role |
| 15 | 16–19px 正文 vs 引擎 pt×1.33 得到 12–15px | **C 引擎配合（或 Web 显式覆盖）** | 引擎的屏幕阶梯覆盖不到 16px+；Web 要么派生并上调，要么声明偏离理由 |
| 16 | serif「may」vs「不要把衬线强推进密集 UI」 | **C 引擎配合** | 引擎不变量 #4「单衬线，`--sans == --serif`」与 Web 运营 UI 的 sans 需求冲突 |
| 17 | 缺表单、ARIA、打印、暗色 | **A 场景债（新域）** | 印刷场景没有表单/ARIA；这是 Web 真正的新增域，不是引擎遗漏 |
| 18 | 0 示例、0 HTML、0 截图 | **D 架构缺口** | 场景没有产物，自然没有示例 |
| 19 | 四篇互不引用、与引擎零引用 | **D 架构缺口** | 场景层没有「引用引擎」的机制 |

### 2.3 计数

- **A 场景债：11 项**（流程、契约、术语、禁令、视口、交互、动效、状态、分册、表单/ARIA、新域）
- **B 继承失败：3 项**（度量、中文、token 名值）
- **C 引擎配合：3 项**（状态色语义、屏幕字号、UI 字族）
- **D 架构缺口：2 项**（无产物、无引用机制）

**这组数字改变了修复策略**：11/19 只需要动 Web；3/19 是「别自己发明，去引用」；只有 3/19 需要引擎配合。

---

## 3. 外部实践：成熟设计系统怎么处理「引擎 + Web 场景」

搜索接口不可用，以下为直接抓取的原文要点（链接见文末）。

### 3.1 GOV.UK Design System

- **响应式字号阶梯**：以 640px 为断点分「大屏 / 小屏」两张表；正文 19px（大屏）/ 16px（小屏）；标题 48/36/27/24/19/16。
- **行高以 5px 为倍数**，形成纵向节奏（如 19px 字号配 25px 行高）。
- **版心 1020px**；推荐 two-thirds 布局，**每行不超过 75 字符**；移动优先、单列起步。
- 栅格：full / half / third / two-thirds / quarter / three-quarters，可加 `-from-desktop` 变体。
- 输出用 rem/em，保证缩放。

### 3.2 U.S. Web Design System（USWDS）

- **正文至少 16px**（font-size 5）；正文常用 token 5–8。
- **行长 45–90 字符**，长文目标 **66 字符**（measure 1–5）。
- **行高**：标题 1–1.35，长文 **≥1.5**；行高与字号一起做字体归一化。
- **间距以 8px 为基数**（0.5=4px、1=8px、2=16px…），并且**间距 token 同时充当断点**：mobile 320 / mobile-lg 480 / tablet 640 / tablet-lg 880 / desktop 1024 / desktop-lg 1200 / widescreen 1400。
- **Token 架构**：family + size + line-height 三元组，`typeset()` 一次设置；token → utilities → components → patterns → templates。
- 段落用空白分隔、不缩进；标题上方留白 ≥ 下方 1.5 倍；正文两侧至少 1/2/4–5 个 spacing unit。

### 3.3 WCAG 2.2（可作为硬门禁的数字）

- **2.5.8 Target Size (Minimum) AA**：目标至少 **24×24 CSS px**，或满足 24px 圆的间距例外。
- **1.4.10 Reflow AA**：320 CSS px 宽（横向滚动内容为 256 高）下不出现二维滚动；表格可作为例外，但要放进自己的滚动容器，且表格前后的标题/搜索/分页仍须 reflow。
- **1.4.4 Resize Text**：文本可放大到 200%。
- 粘性/固定元素不得遮挡焦点（与 2.4.11 相关联）。

### 3.4 W3C Design Tokens（DTCG）

- token = `$value` + `$type`，支持 **group / alias / `$deprecated` / 复合 token**（typography、shadow、border、transition）。
- 明确「单一事实源 + 翻译到各平台」的定位。

### 3.5 llms.txt

- 面向 agent 的站点索引约定：一个 Markdown 文件 + 分节链接，让 agent 先读索引再按需取页。
- 对 Folio 的启示：**Web 规范本身也该有一个 agent 入口**（现在四篇散文没有索引、没有链接）。

### 3.6 共同架构与「可借 / 不可借」

成熟系统的共同结构：

```
design tokens（单一事实源）
   → base / global styles（排版、颜色、间距）
   → components（按钮、表单、表格…）
   → patterns（组合）
   → templates（整页）
   ↑ 每一层都有可执行检查
```

| 可借 | 不可借 |
|---|---|
| token 单一事实源 + 别名/弃用机制 | 组件库（Folio 明确不是组件库） |
| 响应式字号阶梯 + 行高倍数 | 它们的视觉身份（字体、色彩） |
| 行长 45–90 / 66 目标 | 构建链（Sass/JS 框架） |
| 8px/4px 间距基准 + 断点即 token | 组件级 API 设计 |
| WCAG 数字做硬门禁 | 多品牌主题体系（Folio 已有 `FOLIO_THEME`） |
| 模板 + 示例 + 检查三件套 | — |

---

## 4. Web 场景的增量能力：到底能多做什么

### 4.1 与印刷的能力差

| 能力 | 印刷（PDF/PPTX） | Web | 对规范的含义 |
|---|---|---|---|
| 版心 | 固定 A4/Letter | 流式 + 断点 | Web 必须定义视口模型（引擎没有） |
| 分页 | 固定页数契约 | 无分页，滚动 | 契约从「页数」变成「区域 + 状态 + 视口」 |
| 交互 | 无 | hover/focus/selected/active | 必须定义状态语义（引擎没有） |
| 动效 | 无 | 有 | 必须定义动效语义（引擎没有） |
| 表单 | 无 | 有 | 必须定义输入/校验/错误（引擎没有） |
| 可访问性 | 字体/对比度 | 语义树/键盘/读屏 | 必须定义 ARIA/焦点序（引擎没有） |
| 链接 | 脚注 | 超链接/锚点/目录 | 阅读页的方位机制 |
| 数据 | 静态图 | 可交互图 + 数据表 | Drawing DSL 已有 responsive 宿主 |
| 分发 | 文件 | 托管/分享/搜索 | 业务价值所在 |

### 4.2 候选业务场景

| # | 场景 | 用到的 Web 增量 | 引擎复用 | 产物成本 | 可门禁 | 优先级假说 |
|---|---|---|---|---|---|---|
| 1 | **文档上网页**（long-doc/研报 → 阅读页） | 流式、目录、来源、链接 | 高（IR + 排版 + 图） | 中 | 高（几何/可读性可测） | **P0** |
| 2 | **评审工作台**（文档审阅队列） | 状态、动效、表单、键盘 | 中（token + 图） | 中高 | 中（状态覆盖可测） | P1 |
| 3 | **带批注的混合页**（文档 + 操作面板） | 区域分离、状态、动效 | 中 | 高 | 中 | P2 |
| 4 | **数据页/仪表盘** | 响应式图 + 数据表 | 高（Drawing DSL） | 中 | 高（图可读性/表格） | P1 |
| 5 | **索引/发布页**（changelog、portfolio、release notes） | 导航、锚点、分享 | 高 | 低 | 中 | P1 |
| 6 | **托管交付物**（同一 IR → HTML） | 全部 | 很高（IR HTML writer） | 低 | 高 | **P0** |

**判断**：P0 的两个场景（1、6）共享同一条技术路径——**IR → 响应式 HTML**，而且正好复用引擎已有的三块资产。工作台（2）才是真正需要新定义状态/表单/ARIA 的场景，适合放到第二阶段。

---

## 5. 三种从零设计的架构

### Option A：指导层（维持现状，修数字）

- 形态：四篇 Markdown，不产物。
- 成本：最低（2–3 天）。
- 效果：可读性提升，但「两个 agent 做出不同页面」的问题不变。
- 适用：只把 Web 当「给 agent 的设计建议」，不承诺交付物。

### Option B：场景产品线（模板优先）

- 形态：`assets/templates/web/{reading,workspace,hybrid}.html` + CSS + 契约 + demo + 检查脚本；规范退化为「模板说明书」。
- 成本：中（1–2 周）。
- 效果：与印刷场景同构，可验证、可复制。
- 风险：模板一旦发布就要维护响应式与多语言。

### Option C：引擎宿主配置（Web 作为一种输出宿主）

- 形态：`FOLIO_OUTPUT=web` 或 `build.py web-*`，复用 IR HTML writer + projection + drawing responsive host；Web 规范写成「宿主契约」（类似 Drawing DSL 的 `a4-portrait` / `responsive-html`）。
- 成本：中高（需动 build/pipeline，但主要是接线）。
- 效果：最彻底——同一份内容模型可出 PDF/PPTX/HTML，且 token 天然同源。
- 风险：会触碰 `build.py` 与 IR writer，需要回归测试与保真度对比。

### Option D：分阶段混合（假说推荐）

- **D1（1 周）**：Web 场景先做一个 **reading 模板 + 契约 + demo + 三个门禁**（token 同源、对比度、320px reflow），走 Option B 的形态。
- **D2（1–2 周）**：把它接到 IR HTML writer 上，形成 Option C 的第一条通道（文档上网页）。
- **D3（2 周+）**：再扩 workspace 场景（状态/表单/ARIA），此时才需要引擎补 3 项能力。

**理由**：B 立刻解决「没有产物」的架构缺口；C 的收益最大但依赖 B 的模板作参照；workspace 的复杂度最高，放最后。

### 权衡表

| 维度 | A | B | C | D |
|---|---|---|---|---|
| 与仓库结构一致性 | 低 | **高** | 高 | **高** |
| 可验证性 | 低 | 高 | **最高** | 高 |
| 初期成本 | **最低** | 中 | 中高 | 中 |
| 长期维护 | 低 | 中 | 中 | 中 |
| 触碰引擎 | 无 | 无 | 中 | 分阶段 |
| 业务价值 | 低 | 中 | **高** | 高 |

---

## 6. 新规范的内容架构（草案，待验证）

### 6.1 文档结构

```
references/web/
  web-host.md        宿主契约：视口/断点/行长/字号/间距/状态/动效/a11y/表单
  web-reading.md     阅读页配方：骨架 + 必需区域 + 状态 + 验收
  web-workspace.md   工作台配方：骨架 + 状态矩阵 + 交互 + 表单 + 验收
  web-checklist.md   带编号、带证据、带脚本名的门禁清单
```

原则：
- `web-host.md` 是**唯一**定义数字的地方；另外三篇只引用。
- 每一行数字都标注来源：`engine:<design.md 章节>` / `wcag:<条款>` / `uswds:<token>` / `derived`。
- 删除「哲学段落」与「流程建议」的混写：流程单独一节，且每步给完成判据。

### 6.2 数字来源表（候选值，待验证）

| 项 | 候选值 | 来源 | 与引擎关系 |
|---|---|---|---|
| 正文下限 | 16px | USWDS / GOV.UK | 覆盖引擎 pt×1.33（13.3px） |
| 字号阶梯 | 12 / 14 / 16 / 19 / 24 / 32 / 48 / 64 | GOV.UK + USWDS 合并 | 新增屏幕阶梯，声明偏离理由 |
| 行高 | 标题 1.10–1.30 / 密集 1.40–1.45 / 正文 1.50–1.65 | 引擎三档 + USWDS ≥1.5 | 继承；把引擎「禁 1.60+」限定为印刷 |
| 行长 | 45–90，目标 66；Folio 取 60–75 | USWDS / GOV.UK | 新增 |
| 间距 | 4px 基准：2/4/8/16/24/32/48/80 | 引擎 4pt 七档（已注明 =4px） | 直接继承 |
| 圆角 | 2 / 4 / 8 / 16px | 引擎 2/4/6/8/16pt | 换算继承 |
| 阴影 | ring + whisper 两种，给参数 | 引擎已给参数 | 直接继承 |
| 对比度 | 正文 4.5:1 / 大字与图形 3:1 | 引擎实测表 + WCAG | 直接继承 |
| 点击目标 | 24×24（AA），主路径 40px | WCAG 2.5.8 + 原规范意图 | 新增，兼容原 40px |
| 断点 | 320（测试下限）/ 640 / 1024 / 1280 | WCAG reflow + GOV.UK 640 + USWDS | 新增 |
| 状态 | loading / empty / error / disabled / selected / success | 原规范 | 新增映射到 `color.status.*` |
| 动效 | 5 档时长/距离（原表） | 原规范 | 保留，补 easing 与 reduced-motion |
| 中文 | 字距 0.02–0.05em、行长按字符数、标点 | 引擎中文规则 | 继承并改 px→em |

### 6.3 产物结构

```
assets/templates/web/reading.html      # 静态 HTML + CSS，无框架
assets/templates/web/workspace.html
assets/demos/web-reading.png           # 320 / 768 / 1440 三张截图
scripts/web_contracts.py               # 区域、状态、视口矩阵
scripts/check_web.py                   # token 同源、对比度、reflow、目标尺寸
tests/test_web_contracts.py            # 契约与模板一致
```

门禁最小集（可先做三条）：
1. **token 同源**：模板里的 `var(--color-*)` 必须在引擎角色表里存在。
2. **对比度**：正文/大字/图形三档实测。
3. **320px reflow**：无横向滚动，表格在自身滚动容器内。

---

## 7. 验证计划

| 验证 | 方法 | 通过标准 |
|---|---|---|
| 可执行性 | 复跑盲测（同一 prompt，只给新规范） | 猜测项从 20 降到 ≤8；决定率 ≥80% |
| 一致性 | token lint + 契约测试 | 0 漂移 |
| 可访问性 | 对比度 + reflow + 目标尺寸脚本 | 全绿 |
| 与引擎不冲突 | 同一内容分别出 PDF 与 Web，做排版对照 | 字号/行长/行高在各自介质内合理，且可解释 |
| 业务可用 | 用一份真实长文档走完整链路 | 产物可发布、可分享 |

---

## 8. 待决策问题（需要你拍板）

1. **身份**：Web 是「指导层」（A）还是「交付物场景」（B/C）？
2. **输出**：是否允许静态 HTML 成为 `build.py` 的正式 target（像 PDF/PPTX/SVG 一样）？
3. **范围**：第一版只做阅读页（文档上网页），还是同时做工作台？
4. **UI 字族**：是否允许 Web 引入 sans/functional 字族？这会与引擎不变量 #4（单衬线）冲突，需要明确豁免或新增 role。
5. **状态色**：在主题 profile 新增 `color.status.*` 的 UI 语义 role，还是让 Web 定义映射？
6. **屏幕字号**：以引擎 pt 阶梯派生（×1.33 得 12–15px）还是独立定义 16–19px 并声明偏离？
7. **中文**：本轮是否纳入中文 Web 排版（字距/行长/标点）？
8. **交互**：允许最小 JS（渐进增强），还是纯 CSS？

---

## 9. 外部参考（抓取原文）

- GOV.UK Design System — Type scale: https://design-system.service.gov.uk/styles/type-scale/
- GOV.UK Design System — Layout: https://design-system.service.gov.uk/styles/layout/
- U.S. Web Design System — Typography: https://designsystem.digital.gov/components/typography/
- U.S. Web Design System — Spacing units: https://designsystem.digital.gov/design-tokens/spacing-units/
- U.S. Web Design System — Using type: https://designsystem.digital.gov/design-tokens/typesetting/overview/
- WCAG 2.2 — 2.5.8 Target Size (Minimum): https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html
- WCAG 2.2 — 1.4.10 Reflow: https://www.w3.org/WAI/WCAG22/Understanding/reflow.html
- W3C Design Tokens Format Module: https://www.designtokens.org/tr/drafts/format/
- llms.txt: https://llmstxt.org/
