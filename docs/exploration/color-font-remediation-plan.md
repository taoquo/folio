# 修复计划：让色彩与字体真正到达页面

> 依据：`color-font-support-audit.md` 的四个实验。
>
> 本计划修复「已解析但未生效」这一反复出现的模式。

**分支**：`dev/document-engine`
**日期**：2026-10-11

---

## 一、总目标与验收

### 要修的问题

| # | 问题 | 证据 |
|---|---|---|
| P1 | 颜色不进投影层，主题对页面零影响 | 改 `accent.brand` 为蓝，PDF 字节不变 |
| P2 | 文档没有主题选择入口 | `grep FOLIO_THEME` 无结果 |
| P3 | `invariants` 声明但无人读，冷色主题能过全部门禁 | 蓝色主题下 `--check` 与 `profile_check` 均通过 |
| P4 | 字体不进投影层 | 改 `body.family` 与 `size_pt`，PDF 字节不变 |
| P5 | `roles` 无消费者 | 仅 `migration.py` 数数量 |
| P6 | `font_fallback` 无消费者 | 全代码只出现在所有权表 |
| P7 | 投影产出的 8 个变量无人读 | 模板引用 `--folio-*` 数为 0 |
| P8 | 没有「profile 字段 → 产物」的消费门禁 | 上述问题全靠人工排查 |

### 全局验收标准

| 项 | 标准 |
|---|---|
| 默认主题 | **所有文档产物字节不变**（基线保持绿） |
| 非默认主题 | 有像素级证据证明颜色/字体确实改变 |
| 冷色主题 | 被不变量检查**拒绝** |
| 未消费字段 | 被门禁**拒绝** |
| 回归 | 全部测试与 16 项门禁通过 |
| 可回滚 | 每一项都有 `FOLIO_*` 开关或可逆改动 |

### 三条设计原则

1. **模板保留字面值作为默认，投影作为覆盖。** 实验 4 已证明注入位置在模板 `:root` 之后，同优先级后者胜。这样模板仍能独立渲染（AGENTS.md 的要求），且默认主题下产物不变。
2. **每项都走既有 `FOLIO_*` 开关模式**，可配置回滚，不是一个不可逆的重构。
3. **新增字段必须同时新增消费者与证明消费者工作的测试。** 本仓库已五次踩到「定义即完成」的坑：YAML 解析器、投影层 8 个变量、`roles`、`font_fallback`、`invariants`。

---

## Phase 0：冻结与基线

**前置条件**：当前 38 个未提交文件先完成 review 与提交。本计划的改动会与它们混在一起，无法单独审查。

| 项 | 动作 |
|---|---|
| 记录 | `document_baseline.py compare` 的当前状态 |
| 记录 | 16 个目标的 PDF 哈希、页数、字体清单 |
| 记录 | `fidelity.py measure` 的 SSIM（当前 0.9887 / 7-7 一致） |
| 记录 | `projection.py check` 输出（当前通过） |
| 建立 | 一个「默认主题下产物不变」的对照脚本 |

**验收**：上述四项快照写入 `docs/exploration/plan-baseline.md`，后续每个 Phase 都与它对比。

---

## Phase 1：颜色进入投影层

**修 P1**

### 改动

**`scripts/projection.py`** —— 新增颜色映射表，与既有 `VARIABLE_MAP` 并列：

```python
COLOUR_VARIABLE_MAP: dict[str, str] = {
    # 结构
    "colors.paper":        "--parchment",
    "colors.surface":      "--ivory",
    "colors.sand":         "--sand",
    "colors.border":       "--border",
    "colors.border_soft":  "--border-soft",
    "colors.text":         "--near-black",
    "colors.text_warm":    "--dark-warm",
    "colors.charcoal":     "--charcoal",
    "colors.olive":        "--olive",
    "colors.stone":        "--stone",
    # 品牌
    "accent.brand":        "--brand",
    "accent.tint":         "--brand-tint",
    "accent.tint_strong":  "--brand-tint-strong",
    "accent.tag_bg":       "--tag-bg",
    # 状态
    "status.positive":     "--status-positive",
    "status.caution":      "--status-caution",
    "status.negative":     "--status-negative",
    "status.informative":  "--status-informative",
    "status.positive_tint":    "--status-positive-tint",
    "status.caution_tint":     "--status-caution-tint",
    "status.negative_tint":    "--status-negative-tint",
    "status.informative_tint": "--status-informative-tint",
}
```

**刻意不进映射的**：

| 项 | 原因 |
|---|---|
| `data.*`（14 项） | 文档模板不使用分类色；接入需先决定「图表专用」还是「文档可用」（见 Phase 8） |
| `--rule-warm` | 模板局部值，不属于主题 |
| `--brand-deep` | 已确认为死变量并移除 |

**`style_projection()`** 改为遍历两张表，来源追踪保持逐项记录。

### 验收

| 检查 | 期望 |
|---|---|
| `projection.py check` | 通过 |
| 默认主题下 16 个基线目标 | **不变**（主题值与模板字面值当前同值） |
| `accent.brand` 改为 `#1F6FEB` 后重建 one-pager | PDF 哈希改变；新色像素 > 0；旧色像素 == 0 |
| 还原后 | 哈希回到 `a4fbc863b92b6201` |
| 页数 | 全部不变 |

### 回滚

`FOLIO_STYLE_PROJECTION=off`（既有开关），或移除映射表。

### 风险

投影会把模板**没有声明**的变量也注入（如 one-pager 无 `--charcoal`）。CSS 中未使用的自定义属性无副作用，但会让注入块变长 —— 需要在 `check()` 中确认注入块非空且括号平衡。

---

## Phase 2：主题选择入口

**修 P2**

### 改动

| 文件 | 改动 |
|---|---|
| `scripts/style_resolver.py` | 新增 `theme_profile_names()`；`resolve(names=...)` 已支持，补未知主题名的**显式报错**（列出可用项，不静默回退） |
| `scripts/projection.py` | `style_projection(genre, language, theme=None)`；`combined(..., theme=None)` 透传为 `names={"theme": theme}` |
| `scripts/document_build.py` | 读取 `FOLIO_THEME`；模块 docstring 补开关说明 |
| `scripts/build.py` | `--theme` 参数（构建时选主题），用于产出对照样例 |
| `references/schemas/document-1.0.schema.json` | **待定**：IR 是否加 `theme` 字段 |

**关于 IR 是否加字段**：IR 禁止声明样式**值**。主题名是**引用**，与既有的 `genre` 同类。建议加，但列为本 Phase 的可选项 —— 先做环境变量，IR 字段单独评估。

### 验收

| 检查 | 期望 |
|---|---|
| `FOLIO_THEME=folio-classic-v1`（默认） | 产物不变 |
| 注册第二个主题后 `FOLIO_THEME=其他` | 产物改变，且颜色符合第二套值 |
| `FOLIO_THEME=不存在的名字` | **显式报错**并列出可用主题，不静默回退 |
| 未设 `FOLIO_THEME` | 行为与今天一致 |

### 回滚

不设环境变量即回到今天的行为。

---

## Phase 3：不变量变成真检查

**修 P3**

### 改动

新增 `scripts/theme_check.py`（或并入 `profile_check.py`），检查 theme profile：

| 检查 | 规则 | 依据 |
|---|---|---|
| 暖色不变量 | `colors.paper/surface/sand` 与中性色的色相落在暖区，或饱和度低于阈值 | `invariants.palette: warm` |
| 禁冷灰 | 冷灰清单应用到 **profile 值**，不只模板 | `invariants.forbid_cool_grays` |
| 强调色数量 | 色相种类 > 1 即失败 | `invariants.accents_per_document: 1` |
| **对比度** | 文档侧色对的 WCAG 校验 | 新增 |
| 序列化 | `status.*` 与 `status.*_tint` 两两配对存在 | 语义完整性 |

**对比度是新增能力**：图表侧已有 `_TEXT_ON_SURFACE` / `_GRAPHIC_ON_SURFACE` 配对检查，文档侧没有等价物。需要定义文档色对：

```
(text, paper)          (text, surface)        (text, brand_tint)
(olive, paper)         (stone, paper)
(status.positive, paper)  (status.negative, paper)  ...
(status.positive, status.positive_tint)  ...
(status.*, paper) 作反向文字时
```

阈值沿用图表侧的 `NORMAL_TEXT_MINIMUM` / `LARGE_TEXT_MINIMUM` / `GRAPHIC_MINIMUM`。

### 验收

| 检查 | 期望 |
|---|---|
| 当前主题 | 通过 |
| `brand` 改为 `#1F6FEB` | **失败**（暖色不变量 + 对比度 + 与图表不一致） |
| `paper` 改为冷灰 | **失败**（禁冷灰，且现在扫 profile 不只扫模板） |
| 新增第二个强调色 | **失败**（强调色数量） |
| 刻意做出低对比度的 `status` 值 | **失败** |

**这一 Phase 把审计里「冷色主题能过全部门禁」的漏洞补上。**

---

## Phase 4：字体进入投影层

**修 P4**

### 改动

**`scripts/projection.py`** 新增字体映射：

```python
FONT_VARIABLE_MAP = {
    "body.family": "--serif",
}
```

**这是本 Phase 的硬前提，且当前是坏的。** `body.family` 解析结果是**列表**，而 `_css_value` 只处理 bool / 数字 / 字符串，列表会落进 `str(value)` 分支。实测：

```python
_css_value("body.family", ["LXGW WenKai", "Source Han Serif SC"])
# → "['LXGW WenKai', 'Source Han Serif SC']"      ← 非法 CSS
```

直接接进投影会产出**浏览器忽略、渲染器报错**的样式表。必须先加：

```python
def _css_font_stack(value: list[str]) -> str:
    """A resolved family list as a CSS font stack."""
    # → '"LXGW WenKai", "Source Han Serif SC", Georgia, serif'
```

并让 `_css_value` 在遇到列表时走它，而不是 `str()`。

**`--mono`**：模板中为 `"JetBrains Mono", "SF Mono", "Fira Code", ...`。它对应哪个 profile 字段需要先确认（`roles.code.family` 目前未定义）—— 若未定义，本 Phase 只做 `--serif`，`--mono` 留到 Phase 5。

### 验收

| 检查 | 期望 |
|---|---|
| 默认 profile | **产物字节不变** |
| `body.family` 改为明显不同的字体 | PDF 改变，且 `pdffonts` 显示新字体 |
| 页数 | **必须在契约内**（字体改变会重排） |
| `fidelity.py measure` | 7/7 仍一致 |
| `build.py --check-orphans` | 通过 |
| `spacing_probe.py compare` | 通过 |

### 风险（本计划最高）

**字体改变会重排文档**：行长、行数、标题跨行、表格列宽、总页数都可能变。这正是 AGENTS.md 记录的风险点。

**缓解**：默认字体下必须字节不变；换字体的验收要包含页数契约、孤行、保真度三项，且**页数变化只在契约允许范围内才算通过**。

### 回滚

`FOLIO_STYLE_PROJECTION=off`。

---

## Phase 5：`roles` 与 `font_fallback` 的消费者

**修 P5、P6**

### 改动

| 字段 | 消费者设计 |
|---|---|
| `roles.data.numerals: tabular` | 投影为 `--folio-numerals: tabular-nums`；14 个模板的 `font-variant-numeric` 改为读它 |
| `roles.code.family` | 投影为 `--mono`。**已确认 `roles.code` 目前不存在**，需先定义该角色 |
| `language.font_fallback.serif` | 与 `body.family` 合并：family 在前，fallback 追加在后，去重 |
| `roles.heading_1/2` 的 `size_pt`/`weight`/`keep_with_next` | **暂不投影**：它们是排版度量，接入会改版式（同类风险），单列评估 |

### 验收

| 检查 | 期望 |
|---|---|
| 默认 profile | **产物字节不变** |
| 把 `numerals` 改为 `proportional` | 14 个模板的数字对齐改变（像素证据） |
| `font_fallback` 改变 | 字体栈改变，但默认字体仍解析到同一文件 |
| 模板中 `var(--folio-numerals)` 引用数 | 从 0 变为 14 |

---

## Phase 6：消费门禁

**修 P7、P8**

### 改动

扩展 `scripts/projection.check()`：

| 检查 | 规则 |
|---|---|
| 投影变量必须被读 | 每个投影出的 `--x` 必须在至少 1 个模板中被 `var(--x)` 引用；否则报「projected but unread」 |
| 主题令牌必须被投影或声明例外 | 每个 theme 颜色令牌必须在映射表中，或在显式 `NOT_PROJECTED` 表中**附理由** |
| profile 字段必须被消费或声明例外 | 对 typography / language / taste 同样处理 |
| 例外表本身要有效 | 例外表中列出的键必须真的存在（防止删字段后留垃圾） |

### 验收

| 检查 | 期望 |
|---|---|
| 当前状态（Phase 1/4/5 之前） | **失败** —— 报出 8 个未读度量变量、37 个未投影颜色 |
| Phase 1/4/5 之后 | **通过** |
| 新增一个没人用的 profile 字段 | **失败** |
| 新增一个没人读的投影变量 | **失败** |

**这一 Phase 是元修复**：它让「已定义但未生效」在 CI 里无法通过，而不是靠人工排查。

---

## Phase 7：第二套主题值（色系落地）

**这是「换色系」真正的内容工作**

### 产出

| 主题 | 定位 |
|---|---|
| `folio-classic-v1` | 现有，暖羊皮纸 |
| `folio-editorial-v1` | 更中性，低饱和，适合长文档 |
| `folio-contrast-v1` | 高对比，适合打印/低质量输出 |

每套都要：

1. 给出全部 37 个令牌的值；
2. 通过 Phase 3 的暖色、禁冷灰、强调色、对比度检查；
3. 通过 Phase 6 的消费门禁；
4. 生成对照页（3 个主题 × 5 个文档类型），产出 HTML 验收页。

### 验收

| 检查 | 期望 |
|---|---|
| 三套主题均可构建 | 全部 16 个目标成功 |
| 每套主题的对比度检查 | 通过 |
| 对照页 | 三列并排，同一内容同一版式，只有颜色不同 |
| 页数 | 三套主题下**页数一致**（颜色不应影响分页） |

**页数一致是重要验收**：它证明「换主题不重排」，与仓库已有的「切换主题不得重排文档」的主张一致。

---

## Phase 8：图表与文档的色桥（大，最后做）

**这是审计里唯一需要架构决策的部分**

### 问题

Drawing theme 是 **12 令牌的固定交换单元**：

- 每个令牌在 dark / terminal 中都要有对应；
- 测试断言 `assertEqual(12, len(colors))`；
- `theme_token_map` 做逐令牌替换；
- 新字段在深色主题中会继承浅色默认值 → 对比度门禁失败。

### 选项

| 选项 | 内容 | 代价 |
|---|---|---|
| 8a | 三个图表主题各补一套 data 色板（12 → 26 令牌） | 改断言、三套新值、全部对比度重验 |
| 8b | 保持 12 令牌，图表色板从**文档主题**读取（新增一条解析路径） | 图表不再自成一体，需处理图表独立渲染的场景 |
| 8c | **不做**：图表与文档各自拥有配色，只保证「同名的值一致」（现状 + Phase 3 的一致性检查） | 报告里图表与正文可能色调不同 |

**建议先 8c**，把 8a/8b 作为独立决策，因为它需要先回答「图表是否应该跟随文档主题」。

### 验收（若做 8a/8b）

| 检查 | 期望 |
|---|---|
| 三个图表主题 | 全部通过对比度 |
| `theme_token_map` 覆盖测试 | 通过 |
| 同报告内图表与正文的品牌色 | 同值 |
| 图表独立渲染（`folio.py render-drawing`） | 仍可选择任意主题 |

---

## 二、顺序与依赖

```
Phase 0  冻结与基线
   │
   ├─► Phase 1  颜色进投影 ──┐
   │                          ├─► Phase 6  消费门禁（需要 1/4/5 完成）
   ├─► Phase 2  主题选择入口 ─┤
   │                          │
   ├─► Phase 3  不变量检查 ───┤
   │                          │
   ├─► Phase 4  字体进投影 ───┤
   │                          │
   └─► Phase 5  roles 消费者 ─┘
                              │
                              ├─► Phase 7  第二套主题值
                              │
                              └─► Phase 8  图表色桥（独立决策）
```

| Phase | 规模 | 依赖 |
|---|---|---|
| 0 冻结与基线 | 小 | 当前 review 完成 |
| 1 颜色进投影 | **小**（实验已证明） | 0 |
| 2 主题选择入口 | 小 | 0 |
| 3 不变量检查 | 中 | 0 |
| 4 字体进投影 | 中（重排风险） | 0 |
| 5 roles 消费者 | 中 | 0 |
| 6 消费门禁 | 小（元修复） | 1、4、5 |
| 7 第二套主题值 | **大**（设计 + 对比度） | 1、2、3、6 |
| 8 图表色桥 | 大（架构决策） | 7 |

**Phase 1–3 可以并行**，互不冲突（不同文件）。**Phase 4 与 5 都碰 `projection.py`，需串行。**

---

## 三、每个 Phase 的统一验收流程

```bash
# 1. 默认主题：产物必须不变
python3 scripts/build.py
python3 scripts/document_baseline.py compare
python3 scripts/assets.py check

# 2. 逐字节对照（Phase 0 建立的快照）
diff <(shasum -a 256 assets/examples/*.pdf) docs/exploration/plan-baseline.sha256

# 3. 门禁
python3 -m ruff check .
python3 -m unittest discover -s tests
for c in corpus document_baseline assets projection diagnostics \
         corpus_matrix pipeline architecture profile_check color_sources; do
  python3 scripts/$c.py check 2>/dev/null || python3 scripts/$c.py validate 2>/dev/null || \
  python3 scripts/$c.py compare 2>/dev/null || python3 scripts/$c.py gaps 2>/dev/null || \
  python3 scripts/$c.py rollback-drill 2>/dev/null
done
python3 scripts/build.py --check && python3 scripts/build.py --sync && \
python3 scripts/build.py --verify && python3 scripts/build.py --check-placeholders && \
python3 scripts/build.py --check-index && python3 scripts/build.py --check-rhythm

# 4. 版式未受影响
python3 scripts/fidelity.py measure
python3 scripts/spacing_probe.py compare --genre one-pager
```

**每个 Phase 都必须先证明「默认主题下零变化」，再证明「改变主题确实生效」。** 顺序不能反。

---

## 四、风险登记

| # | 风险 | 影响 | 缓解 |
|---|---|---|---|
| R1 | 投影覆盖模板 → 模板独立渲染与引擎产物不一致 | 中 | 保留字面值作默认；文档明确说明；`FOLIO_STYLE_PROJECTION=off` 可完全复原 |
| R2 | 字体投影导致重排 | **高** | 默认字体字节不变；换字体验收含页数契约 + 孤行 + 保真度 |
| R3 | 颜色投影影响分页 | 低 | Phase 7 验收要求三套主题页数一致 |
| R4 | 第二套主题对比度不达标 | 中 | Phase 3 先建检查，再写主题 |
| R5 | 消费门禁误报（合法的未消费字段） | 中 | 显式例外表 + 理由；例外表本身也校验 |
| R6 | IR 加 `theme` 字段违反「IR 无样式」原则 | 中 | 主题名是引用而非值，与 `genre` 同类；单独评估，先做环境变量 |
| R7 | 改动与未提交的 38 个文件混杂 | **高** | Phase 0 强制先完成 review 与提交 |

---

## 五、不做

| 项 | 原因 |
|---|---|
| PPTX 字体一致性 | 用户指示稍后分析 |
| `math` 字体角色 | 0 个模板有数学符号 |
| `roles.heading_*` 的度量投影 | 会改版式，与字体投影同风险，单列评估 |
| `taste` 域消费 | **已确认无消费者**：`grep taste` 的命中只有 CLI 帮助文本与 `profile_check` 的存在性检查。需要先定义它该做什么 |
| 深色文档主题 | 需要重新设计全部色对，属 Phase 7 的扩展 |
| 27 处中剩余的 14 处 `@page` 背景 | 渲染器限制，无法变量化 |

---

## 六、完成定义

计划完成的判定：

1. **改 `accent.brand` 为蓝色，文档变蓝** —— 有像素证据；
2. **改 `body.family`，PDF 用新字体** —— `pdffonts` 证据；
3. **冷色主题被拒绝** —— 门禁失败并给出理由；
4. **没有字段定义后无人消费** —— 门禁失败，不是人工发现；
5. **默认主题下全部产物字节不变** —— 基线保持绿；
6. **三套主题可切换且页数一致** —— 对照页可复现；
7. 全部测试与门禁通过，且每一项都可配置回滚。
