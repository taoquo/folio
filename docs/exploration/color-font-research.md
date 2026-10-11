# 色彩与字体：探索性调研

> 覆盖探索方案 E0 之后的四项优先级调研。**本文只做调研，不做实施。**
>
> 所有数据来自实际命令，可复核。

**调研时间**：2026-10-11
**分支**：`dev/document-engine`
**前置**：`docs/exploration/color-font-current-state.md`（E0 盘点）

---

## 优先级 1：Theme 生效后模板能否去掉硬编码

### 1.1 结论：**可以，覆盖率达 98.7%**

| 模板 | `:root` 变量 | 可被 theme 覆盖 |
|---|---:|---:|
| changelog / changelog-en | 10 | **10/10** |
| equity-report / -en | 12 | **12/12** |
| letter / -en | 9 | **9/9** |
| long-doc / -en | 10 | **10/10** |
| one-pager / -en | 11 | **11/11** |
| portfolio / -en | 11 | 10/11 |
| resume / -en | 12 | **12/12** |
| **总计** | **150** | **148/150** |

### 1.2 未覆盖的 2 个变量是死变量

| 变量 | 值 | 位置 | 被引用 |
|---|---|---|---|
| `--brand-deep` | `#7E241C` | `portfolio.html`、`portfolio-en.html` | **0 次** |

**它们是声明了但从未使用的变量。**

**修正**：前一版把它记为「应加入 theme 的派生色」。实际上没有页面读它，加入 theme 只会保留一个无人使用的令牌。

### 1.2 补充：18 个变量声明但未使用

据此对全部模板做了一次检查：

| 模板 | 未使用的变量 |
|---|---|
| `changelog-en` | `--border-soft`、`--mono` |
| `changelog` | `--border-soft`、`--sans` |
| `equity-report-en` | `--mono` |
| `resume-en` | `--sand`、`--brand-tint-strong` |
| `one-pager` / `-en` | `--sand`、`--sans` |
| 其余 | 见复核命令 |
| **总计** | **18** |

**这意味着**：模板 `:root` 里有 18/150 是死声明。它们**不影响覆盖率结论**，但会误导「模板需要哪些颜色」的判断。

### 1.3 内联硬编码：27 处

| 模板 | 内联色值数 |
|---|---:|
| changelog / -en、long-doc / -en | 3 each |
| equity-report / -en、resume | 2 each |
| 其余 8 个 | 1 each |
| **总计** | **27** |

**这些是 `:root` 之外直接写的色值**，theme 无法覆盖。

### 1.4 覆盖率结论

> **模板的 `:root` 变量几乎全部可由 theme 提供。** 剩余工作是把 27 处内联色值提升为变量，并补 1 个派生色。

**复核**：

```bash
python3 - <<'PY'
import sys, re, glob; sys.path.insert(0,'scripts')
import style_resolver as sr
from pathlib import Path
theme_vals = set(v.value.upper() for k, v in sr.resolve(genre='one-pager').values.items()
                 if k.startswith(('colors.','accent.')) and v.value)
for f in sorted(glob.glob('assets/templates/*.html')):
    t = Path(f).read_text(encoding='utf-8')
    m = re.search(r':root\s*\{(.*?)\}', t, re.DOTALL)
    d = dict(re.findall(r'--([a-z-]+):\s*(#[0-9A-Fa-f]{6})', m.group(1)))
    print(Path(f).name, sum(1 for v in d.values() if v.upper() in theme_vals), '/', len(d))
PY
```

---

## 优先级 2：颜色源一致性

### 2.1 四个源的规模

| 来源 | 颜色数 |
|---|---:|
| `tokens.json` | 8 |
| theme profile（经 resolver） | **14** |
| 模板 `:root` | 11 |
| Drawing theme | 12 |

### 2.2 值的分布

| 分类 | 数量 |
|---|---:|
| 出现在 2+ 个源 | **12** |
| **只出现在 1 个源** | **5** |

**那 5 个只存在于 Drawing theme**：`#74665F`、`#9C8470`、`#B9ACA3`、`#D7CBC2`、`#8B8078`

**它们是图表专用的中性色阶**，文档模板中**出现 0 次**。

### 2.3 发现一处真实漂移 🔴

| 语义名 | theme | 模板 | Drawing theme | 判定 |
|---|---|---|---|---|
| `olive` | `#5A4A43` | `#5A4A43` | `#5A4A43` | 一致 |
| **`stone`** | `#85776F` | `#85776F` | **`#74665F`** | **漂移** |
| `paper` | `#F6F0EA` | `#F6F0EA` | `#F6F0EA` | 一致 |
| `surface` | `#FBF7F3` | `#FBF7F3` | `#FBF7F3` | 一致 |
| `border` | `#E9DED4` | `#E9DED4` | `#E9DED4` | 一致 |
| `brand` | `#B83D2E` | `#B83D2E` | `#B83D2E` | 一致 |

**`stone` 在两个域是不同的颜色**：

| | 值 | 用途 |
|---|---|---|
| 文档 | `#85776F` | 次级文字 |
| 图表 | `#74665F` | 图注/标签 |

**这不是 bug，而是未被承认的差异** —— 同一个名字，两个值，**没有文档说明为什么**。

### 2.4 一致性结论

| 项 | 状态 |
|---|---|
| 值是否一致 | **12/17 一致，5 个图表专用，1 个真实漂移** |
| 是否有机制保证 | ❌ 无 |
| 漂移检测 | ❌ 无 |

**建议**：这 5 个图表专用色应**显式命名**（如 `diagram.neutral.*`），`stone` 的差异应**记录理由或统一**。

---

## 优先级 3：色彩语义模型探索

### 3.1 现有颜色按方案的四个域分类

| 色彩域 | 数量 | 颜色 |
|---|---:|---|
| **品牌 Brand** | **4** | `accent.brand`、`accent.tint`、`accent.tint_strong`、`accent.tag_bg` |
| **结构 Structural** | **10** | `paper`、`surface`、`sand`、`border`、`border_soft`、`text`、`text_warm`、`charcoal`、`olive`、`stone` |
| **语义 Semantic** | **0** | — |
| **数据可视化 Data** | **0** | — |

### 3.2 状态语义色的现状

只有 2 个，且**只在 equity-report 中使用**：

```css
--positive:  #B83D2E;   /* 朱砂红本身 */
--negative:  #85776F;   /* stone */
```

**问题**：`positive` 用的是**品牌色**，`negative` 用的是**次级文字色**。

**这意味着**：涨跌用「品牌红 vs 灰」，而非「绿 vs 红」。**对中文财经语境可能合理**（红涨绿跌），但**对英文读者可能反直觉**。

**这是一个未被记录的设计决策。**

### 3.3 方案 A/B/C 的评估

| 方案 | 内容 | 当前基础 | 判断 |
|---|---|---|---|
| **A** 单层用途 Token | 扁平 8–10 个 | **已接近** | theme profile 就是这个形态 |
| **B** 三层（primitive → semantic → role） | 完整分层 | 有骨架无层级 | 需要证明价值 |
| **C** 两层语义 Token | 折中 | **最匹配** | 无需组件层 |

### 3.4 关键判断

**当前不是「缺少层级」，而是「缺少语义域」**：

| 现状 | 需要 |
|---|---|
| 品牌 4 + 结构 10 | 品牌 ✅ / 结构 ✅ |
| 无状态语义 | **需建立**（positive/caution/negative/informative） |
| 无数据色板 | **需建立**（categorical/sequential/diverging） |
| 文档与图表两套 | **需共享词汇** |

**方案的 A/B/C 讨论的是「层级深度」，但实际缺口是「域覆盖」。**

**建议路径**：先补域（状态 + 数据），再讨论层级。

---

## 优先级 4：字体角色扩展

### 4.1 当前角色

| Profile | body | roles |
|---|---|---|
| `folio-editorial-zh-v1` | ✅ | `heading_1`、`heading_2`、`caption` |
| `folio-editorial-en-v1` | ✅ | 同 |
| `folio-one-pager-*` | ✅ | **无** |
| `folio-letter-*` | ✅ | **无** |

**只有 2 个 profile 定义了角色**，其余仅定义 body。

### 4.2 实际的字族使用

| 变量 | 模板数 |
|---|---:|
| `--serif` | 14 |
| `--sans` | 14 |
| `--mono` | **4** |

**`--sans` 全部指向 `var(--serif)`** —— 名义上有三族，**实际只有两族**（serif + mono）。

### 4.3 候选角色的真实需求

| 角色 | 实际使用 | 判断 |
|---|---|---|
| `body` | 14 模板 | ✅ 已有 |
| `heading` | 14 模板 | ✅ 已有 |
| `caption` | — | ✅ 已有 |
| **`code`** | **2 个模板用 `<pre>/<code>`** | ⚠️ **需求低** |
| **`data`**（tabular） | **14 个模板用 `tabular-nums`** | ✅ **需求高** |
| **`math`** | **0 个模板含数学符号** | ❌ **无需求** |

**关键发现**：

| 角色 | 方案预期 | 实际需求 |
|---|---|---|
| `code` | 基础角色 | **只有 2 个模板** |
| `math` | 方案 B 提出 | **0 个模板** |
| `data` | 方案 B 提出 | **14 个模板**（最高） |

### 4.4 字体角色结论

> **方案假设的 `math` 角色无需求，`code` 需求低，真正的缺口是 `data`。**

`tabular-nums` 在 14 个模板中使用，但**没有一个 profile 把它定义为角色** —— 它是**散落在 CSS 中的属性**，不是可配置的角色。

**建议**：

| 优先 | 动作 |
|---|---|
| 1 | 把 `data`（tabular numerals）提升为角色 |
| 2 | `code` 作为可选角色（2 个模板需要） |
| 3 | `math` **暂不建立**（无需求证据） |

---

## 综合发现

### 与方案假设的差异

| 方案假设 | 实际情况 |
|---|---|
| 需要建立 FontManifest | ✅ **已有** |
| 需要设计语言回退 | ✅ **已有**（3 profile + 4 链） |
| 色彩需要从零探索 | ⚠️ **有骨架**，缺「域」而非「层级」 |
| `math` 是需要的角色 | ❌ **0 个模板有需求** |
| `code` 是基础角色 | ⚠️ **仅 2 个模板** |
| Token 层级是关键问题 | ❌ **域覆盖是关键问题** |

### 真实缺口（按证据强度）

| # | 缺口 | 证据 |
|---|---|---|
| 1 | **状态语义色缺失** | 只有 2 个，且用品牌色充当 positive |
| 2 | **数据色板缺失** | categorical/sequential/diverging 全无 |
| 3 | **`data` 角色缺失** | 14 个模板用 tabular-nums，无角色定义 |
| 4 | **`stone` 漂移** | 文档 `#85776F` vs 图表 `#74665F` |
| 5 | **27 处内联色值** | theme 无法覆盖 |
| 6 | **`--brand-deep` 未纳入 theme** | portfolio 专用派生色 |

### 不是缺口的

| 项 | 理由 |
|---|---|
| Token 层级（A/B/C） | 当前 14 个值，无层级压力 |
| `math` 角色 | 无需求证据 |
| FontManifest | 已存在 |
| 语言回退 | 已存在 |

---

## 建议的下一步

按证据强度排序：

| 优先 | 事项 | 类型 |
|---|---|---|
| 1 | 补状态语义色（4 个）与数据色板（3 类） | 设计 + PoC |
| 2 | 建立文档/图表共享的色彩词汇 | 架构 |
| 3 | 把 `data` 提升为字体角色 | 小改 |
| 4 | 处理 `stone` 漂移（记录理由或统一） | 决策 |
| 5 | 27 处内联色值提升为变量 + 补 `--brand-deep` | 重构 |
| 6 | 建立颜色源一致性检查 | 工具 |

**第 1 项是最大缺口** —— 方案讨论的「Token 分层」在当前规模下不是瓶颈，「语义域缺失」才是。

---

## 复核命令

```bash
# 优先级 1：theme 覆盖率
python3 - <<'PY'
import sys, re, glob; sys.path.insert(0,'scripts')
import style_resolver as sr
from pathlib import Path
t = set(v.value.upper() for k, v in sr.resolve(genre='one-pager').values.items()
        if k.startswith(('colors.','accent.')) and v.value)
tot = cov = 0
for f in sorted(glob.glob('assets/templates/*.html')):
    x = Path(f).read_text(encoding='utf-8')
    m = re.search(r':root\s*\{(.*?)\}', x, re.DOTALL)
    d = dict(re.findall(r'--([a-z-]+):\s*(#[0-9A-Fa-f]{6})', m.group(1)))
    tot += len(d); cov += sum(1 for v in d.values() if v.upper() in t)
print(f'{cov}/{tot}')
PY

# declared but unread variables
python3 - <<'PY'
import re, glob
from pathlib import Path
for f in sorted(glob.glob('assets/templates/*.html')):
    x = Path(f).read_text(encoding='utf-8')
    m = re.search(r':root\s*\{(.*?)\}', x, re.DOTALL)
    if not m: continue
    body = x[:m.start()] + x[m.end():]
    for name in re.findall(r'--([a-z-]+):', m.group(1)):
        if f'var(--{name})' not in body:
            print(f'{Path(f).name}: --{name}')
PY

# 优先级 2：stone 漂移
grep -n "stone" scripts/drawing/theme/folio.py assets/templates/one-pager.html

# 优先级 3：语义色
grep -rhoE '\-\-(positive|negative|warning)[a-z-]*:' assets/templates/*.html | sort -u

# 优先级 4：tabular 与数学
grep -rl "tabular-nums" assets/templates/*.html | wc -l
grep -rlE "√|∑|∫" assets/templates/*.html | wc -l
```
