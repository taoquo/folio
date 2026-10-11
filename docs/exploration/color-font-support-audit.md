# 支持性排查：换色系、丰富配色、字体语义化

> 问题：如果要接入不同色系、让配色更丰富、或让字体更语义化，该怎么做？当前方案支持吗？
>
> 方法：四个实验 + 全链路消费者追踪。结论全部来自实测。

**分支**：`dev/document-engine`
**日期**：2026-10-11

---

## 摘要

| 诉求 | 结论 | 断点 |
|---|---|---|
| 换一整套色系 | **不支持** | 模型可解析，**投影层不携带颜色**，且文档没有选主题的入口 |
| 配色更丰富 | **半支持** | 词汇已就位（status 8 + data 14），**未接线**；不变量**无强制** |
| 字体语义化 | **不支持** | `roles` / `family` / `font_fallback` **都没有消费者** |

**一句话**：数据结构是对的，缺的是最后一段线。而这段线比预想的短 —— 见实验 4。

---

## 一、四个实验

### 实验 1：改主题色，文档会变吗

把 theme profile 的 `accent.brand` 改成 `#1F6FEB`（蓝）、`colors.paper` 改成 `#EAEFF6`（冷色），重建。

```
改前 a4fbc863b92b6201
改后 a4fbc863b92b6201
产物完全没变 —— 主题色不影响页面
```

**主题对文档的视觉影响为零。**

而且此时 `build.py --check`、`profile_check.py` 都通过 —— 一个冷色主题没被任何门禁拦住。

### 实验 2：改排版 profile，文档会变吗

把选中 profile 的 `body.size_pt` 从 10.5 改成 13.0。

```
改前 a4fbc863b92b6201
改后 a4fbc863b92b6201
未变
```

**排版 profile 对文档的视觉影响也为零。**

### 实验 3：图表侧呢

```bash
python3 scripts/folio.py render-drawing --theme folio   --output /tmp/a.png ...
python3 scripts/folio.py render-drawing --theme dark    --output /tmp/b.png ...
python3 scripts/folio.py render-drawing --theme terminal --output /tmp/c.png ...
```

```
folio     6fde09183b8e13fc
dark      900550e57645c24c
terminal  6bd16c189d648d65
```

**图表有三套主题，且真的生效。文档一套也没有。**

系统内部因此存在一个不对称：同一份报告里的图表可以换成深色，正文不行。

### 实验 4：只加一行映射，颜色就通了吗

`scripts/projection.py` 的 `VARIABLE_MAP` 增加一项：

```python
"accent.brand": "--brand",
```

主题色设为蓝色，重建：

```
改前 a4fbc863b92b6201
改后 e245485ebcf7ca3c → 颜色生效
```

像素级确认：

```
接近新品牌蓝 #1F6FEB 的像素: 2863
接近原朱砂红 #B83D2E 的像素: 0
```

**品牌色确实换成了蓝色，模板一个字未改。**

原因在注入位置：`projection.inject` 把投影块**追加在模板 `<style>` 的末尾**，同优先级下后者胜出。

**这一行就是整条断链的长度。**

（实验后已还原；工作区未保留该改动。）

---

## 二、断链在哪

```
Document IR
     │
     ▼
style_resolver.resolve()          ← 全部解析成功，带来源追踪
     │
     ├── theme.37 个颜色令牌 ......  ✅ 解析  →  ❌ projection 的 VARIABLE_MAP 无颜色
     ├── typography.body.family ...  ✅ 解析  →  ❌ 无任何消费者
     ├── typography.roles ..........  ✅ 解析  →  ❌ 只有 migration.py 数数量
     ├── language.font_fallback ....  ✅ 解析  →  ❌ 无任何消费者
     ├── taste .....................  ✅ 解析  →  ❌ 无消费者
     └── page ......................  ✅ 解析  →  ✅ 被 page_contracts 消费
     │
     ▼
projection.VARIABLE_MAP           ← 只有 8 项，全是排版度量
     │
     ▼
模板 <style>                       ← 160 处颜色字面值 + 32 处字族字面值
```

### 具体数字

| 项 | 数量 |
|---|---:|
| 模板 `:root` 颜色声明 | **160** |
| 模板 `:root` 字族声明 | **32** |
| `VARIABLE_MAP` 条目 | **8**（全为排版度量） |
| 其中颜色条目 | **0** |
| 其中字体条目 | **0** |
| 模板引用的 `--folio-*` 变量 | **0** |

最后一行是根因：**投影层产出的变量，模板一个都不读。**

### 各类信息的消费者

| 信息 | 解析 | 消费者 |
|---|---|---|
| `theme.colors` / `accent` / `status` / `data` | ✅ | ❌ 无 |
| `theme.invariants` | ✅ | ❌ **无** |
| `typography.body.size_pt` | ✅ | ⚠️ 投影为 `--folio-body-size`，**模板不读** |
| `typography.body.family` | ✅ | ❌ 无 |
| `typography.roles` | ✅ | ⚠️ 仅 `migration.py` 计数 |
| `language.font_fallback` | ✅ | ❌ 无 |
| `page.*` | ✅ | ✅ `page_contracts.py` |

`font_fallback` 在全部代码中只出现一次 —— 在 `DOMAIN_FIELDS` 的所有权表里。

---

## 三、三件事分别要做什么

### A. 换一整套色系

**要做的**

| 步 | 内容 | 规模 |
|---|---|---|
| A1 | `VARIABLE_MAP` 增加颜色映射：`accent.brand` → `--brand`、`colors.paper` → `--parchment` 等 | 约 20 行 |
| A2 | 模板改用投影变量（可选，见下） | 160 处 |
| A3 | 暴露主题选择：`resolve(names=...)` **已支持**，需要入口（`FOLIO_THEME` 或 document spec 字段） | 小 |
| A4 | 写第二个 theme profile | schema 已允许 |

**A2 可能不必要。** 实验 4 证明：模板字面值在前、投影在后，投影自然胜出。也就是说 **A1 + A3 + A4 就能换色系，模板不用动**。

**但要先决定一件事**：模板目前可以**独立渲染**（AGENTS.md 明确要求「模板仍能独自渲染」）。投影覆盖它，意味着「模板单独打开」与「引擎产物」会不一致。两个选项：

- 保留字面值作为默认，投影为覆盖 → 模板独立渲染仍可用旧色，产物用主题色。**推荐**，代价最小。
- 把字面值删掉，模板依赖投影 → 模板不再能独立渲染。

**A3 是新工作**。当前文档链路没有主题入口：

```bash
grep -rn "FOLIO_THEME\|--theme" scripts/document_build.py scripts/build.py scripts/projection.py
# 无输出
```

**A4 的工作量在颜色本身**。37 个令牌要给出第二套值，并保证对比度门禁通过（`profile_check` 会校验 schema，`color_sources` 会校验与图表主题的一致性）。

**风险**：浅色主题的对比度是按羊皮纸背景调的。深色主题需要重新验证全部 `--status-*` 与正文色对 —— 这正是图表主题已有的 `_TEXT_ON_SURFACE` 那套机制，文档侧没有等价物。

### B. 配色更丰富

**已有**：`status`（8）与 `data`（14）共 22 个令牌，可解析、有 schema、有所有权声明。

**缺的是三样**：

| 缺 | 说明 |
|---|---|
| 接线 | 同 A1：不投影就不生效 |
| **不变量强制** | `invariants.palette: warm`、`forbid_cool_grays: true`、`accents_per_document: 1` **没有任何代码读取** |
| 图表与文档的桥 | 图表是 12 令牌的固定交换单元（上轮结论），`data` 色板进不去 |

**「丰富」的边界问题**：`0006` 决策规定「单一强调色」，`design.md` 写「cinnabar 覆盖面积 ≤ 5%」。新增的 6 个分类色**在文档模板里没有使用**，所以目前不冲突；一旦接入正文，就需要决定它们是「图表专用」还是「文档可用」。

**建议**：把 `invariants` 变成真检查。现在改一个冷色主题，只有 `color_sources.py` 会因为「与图表主题不一致」报错 —— **它报的不是「主题不暖」**。`COOL_GRAY_BLOCKLIST` 只扫模板，不扫 profile。

### C. 字体语义化

**要做的**

| 步 | 内容 |
|---|---|
| C1 | 投影 `typography.body.family` → `--serif`；`roles.code.family` → `--mono` |
| C2 | `language.font_fallback` 与 `family` 合并成完整 font stack |
| C3 | `roles` 的每个角色投影成 CSS 变量或规则（现在无消费者） |
| C4 | 决定字体变化后的回归流程（页数/行长/孤行）—— `fidelity.py`、`page_contracts`、`orphans` 已有 |

**C1 是核心**：模板 `--serif` 现在是 14 处字面值，`--mono` 是 `"JetBrains Mono", "SF Mono", ...`。把它们改成读投影即可，机制与颜色完全相同。

**C3 的价值取决于是否真的需要**。调研已确认：

| 角色 | 实际需求 |
|---|---|
| `body` | 14 个模板 |
| `heading` | 14 个模板 |
| `caption` | 已声明 |
| `data` | **14 个模板用 `tabular-nums`，但无角色** |
| `code` | 2 个模板 |
| `math` | **0 个模板有数学符号** |

**建议先做 C1 + `data` 角色**，`math` 不做。

---

## 四、建议顺序

| 序 | 事项 | 依据 | 规模 |
|---|---|---|---|
| 1 | A1 颜色进投影 | 实验 4 证明一行即通 | 小 |
| 2 | A3 主题选择入口 | 没有入口就换不了 | 小 |
| 3 | B-不变量强制 | 现在冷色主题能过全部门禁 | 小 |
| 4 | C1 字体进投影 | 与 A1 同机制 | 小 |
| 5 | A4 第二套主题值 | 需要设计 + 对比度验证 | 中 |
| 6 | C3 `data` 角色 | 14 个模板有需求 | 中 |
| 7 | 图表 data 色板 | 需同时扩展三个图表主题 | 大 |

**第 1–4 项都很小，且互相独立。** 它们把「已解析但无用」变成「已生效」。

**第 5 项才是真正的工作量** —— 设计一套新的配色并验证它的对比度、灰阶层级和图表一致性。

---

## 五、这个排查顺带确认的两件事

**1. 本轮新增的 status / data 令牌，目前对产物没有影响**

我在 `color-font-prototype-report.md` 里写「模板接入 status 令牌」—— 准确的说法是：**模板的 `:root` 里写入了这些值作为字面量**，equity-report 的涨跌色与 changelog 的 breaking 标签因此改变。但**主题 profile 里的 status/data 仍然不生效**，与其它颜色一样。

**2. 「已定义但未生效」是一个反复出现的模式**

- YAML 解析器：theme 值全部为空（已修）
- 投影层：8 个度量变量，模板不读（未修）
- `roles`：声明了，只有计数器读（未修）
- `font_fallback`：声明了，无人读（未修）
- `invariants`：声明了，无人读（未修）

`census.py` 的 53 项里有「能力可达」的检查，但**可达之后是否被消费**，目前只有 `architecture.py` 对模块调用链做检查，没有对「profile 字段 → 产物」做检查。

**建议加一项门禁**：profile 里被消费的字段集合，与实际渲染产物中出现的值做对照。这正是 `color_sources.py` 对颜色源做的事，可以推广到 profile 字段。

---

## 六、复核命令

```bash
# 实验 1：改主题色，产物是否变化（当前应不变）
cp references/profiles/theme/folio-classic-v1.yaml /tmp/t.bak
sed -i '' 's/brand: "#B83D2E"/brand: "#1F6FEB"/' references/profiles/theme/folio-classic-v1.yaml
python3 scripts/build.py one-pager && shasum -a 256 assets/examples/one-pager.pdf
cp /tmp/t.bak references/profiles/theme/folio-classic-v1.yaml

# 实验 4：加一行映射再看（会变）
# 在 scripts/projection.py 的 VARIABLE_MAP 加 "accent.brand": "--brand"

# 投影层携带什么
grep -A12 "^VARIABLE_MAP" scripts/projection.py

# 模板是否读投影变量
grep -rho -- "--folio-[a-z-]*" assets/templates/*.html | sort -u | wc -l

# 各信息的消费者
grep -rn "font_fallback" scripts/ --include="*.py" | grep -v __pycache__
grep -rn "invariants" scripts/ --include="*.py" | grep -v __pycache__
grep -rn "\.roles" scripts/ --include="*.py" | grep -v __pycache__

# 图表侧的三套主题
for t in folio dark terminal; do
  python3 scripts/folio.py render-drawing --theme $t --output /tmp/c-$t.png references/fixtures/minimal/bar-chart.json
done
shasum -a 256 /tmp/c-*.png
```
