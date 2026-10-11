# 颜色令牌的结构与扩展设计

> 回答：令牌怎么分层、怎么命名、怎么加一个新的而不把系统搞乱。
>
> 所有数字来自实测。

**分支**：`dev/document-engine`
**日期**：2026-10-11
**前置**：`color-scheme-storage-design.md`（存哪里）、`color-font-support-audit.md`（为什么不生效）

---

## 一、先看今天的扩展成本

### 实测：改一个颜色要动多少处

把品牌色 `#B83D2E` 换成别的：

| 项 | 数量 |
|---|---:|
| 包含该色值的文件 | **62** |
| 出现次数 | **169** |

而这一个值在主题里被 **5 个语义令牌**同时使用：

```
accent.brand
status.positive
data.category_1
data.sequential_4
data.diverging_positive
```

**它们必须一起变** —— 但今天没有任何机制保证这一点。`color_sources.py` 只能事后发现它们不一致。

### 实测：令牌层的冗余

| 项 | 数量 |
|---|---:|
| 主题令牌 | **36** |
| 不同色值 | **24** |
| 一值多令牌 | **7 组** |

最高的一组：`#B83D2E` 被 **5 个令牌**使用；`#E9DED4` 被 `colors.sand`、`colors.border`、`data.diverging_neutral` 三个使用。

**这不是错误** —— 它们是**语义别名**（品牌色同时是「正向」和「图表第一类」）。但它说明**缺少一层**：现在只能用「重复同一个值」表达别名。

### 实测：命名没有一处是机械一致的

拿主题路径与模板 CSS 变量按值对照：

| profile 路径 | CSS 变量 | 机械一致 |
|---|---|---|
| `colors.paper` | `--parchment` | 否 |
| `colors.surface` | `--ivory` | 否 |
| `colors.text` | `--near-black` | 否 |
| `colors.text_warm` | `--dark-warm` | 否 |
| `accent.brand` | `--brand` | 否 |
| `status.positive` | `--status-positive` | 否 |

**按值能在模板中找到的 13 个令牌中，0 个名字机械一致。**
（其余令牌没有进入这个模板，或没有对应的 CSS 变量。）

沿值匹配还会撞车：`colors.sand` 与 `colors.border` 同值，`accent.tint_strong` 与 `accent.tag_bg` 同值 —— 工具无法从值反推是哪个令牌。

**后果**：路径名与变量名是两套独立发明的命名，中间必须有一张手工维护的映射表。**加一个令牌就要同时想两个名字，并记住去改那张表。**

### 实测：schema 不需要改

```
colors:  additionalProperties=允许任意名
accent:  additionalProperties=允许任意名
status:  additionalProperties=允许任意名
data:    additionalProperties=允许任意名
```

**这是好消息**：在既有域里加令牌**不需要动 schema**。

### 所以真正的扩展成本在

| 处 | 是否必须改 |
|---|---|
| profile YAML | ✅ 必须 |
| schema | ❌ 不用 |
| `DOMAIN_FIELDS` | ❌ 不用（它是域级的） |
| **映射表**（路径 → CSS 变量） | ⚠️ **必须**，这是手工耦合 |
| 模板 `:root` 声明 | ⚠️ 用到了才要 |
| 消费方 | ✅ 必须 |

**两处是手工耦合，其中一处（映射表）完全可以消除。**

---

## 二、三个结构性缺陷

| # | 缺陷 | 后果 |
|---|---|---|
| S1 | **没有原始色板层** | 5 个令牌重复同一个值；改色要改 5 处且无同步保证 |
| S2 | **命名不机械** | 每加一个令牌要发明两个名字 + 手工维护映射表 |
| S3 | **没有省略规则** | `data` 的 14 个令牌必须逐个手写，否则采纳色系时图表色板无主（存储设计 B4） |

---

## 三、目标结构：三层

```yaml
# references/profiles/theme/folio-classic-v1.yaml
version: 1

# 第一层：原始色板。只被 color 层引用，模板永远不读。
palette:
  cinnabar:      "#B83D2E"
  cinnabar-tint: "#F7E6E1"
  cinnabar-deep: "#7E241C"
  parchment:     "#F6F0EA"
  ivory:         "#FBF7F3"
  sand:          "#E9DED4"
  ink:           "#191514"
  warm-800:      "#3A312D"
  warm-700:      "#5A4A43"
  warm-500:      "#85776F"
  slate-600:     "#5A6B7A"
  amber-700:     "#A8722C"

profiles:
  folio-classic-v1:
    default: true

    # 第二层：语义角色。模板只读这一层。
    color:
      surface:
        page:      { palette: parchment }
        card:      { palette: ivory }
        sunken:    { palette: sand }
      text:
        primary:   { palette: ink }
        secondary: { palette: warm-700 }
        muted:     { palette: warm-500 }
      border:
        default:   { palette: sand }
        soft:      "#E8DED6"          # 也可以直接写字面值
      accent:
        brand:     { palette: cinnabar }
        tint:      { palette: cinnabar-tint }
        tint-strong: { palette: cinnabar-tint }
        tag:       { palette: cinnabar-tint }
      status:
        positive:  { palette: cinnabar }
        caution:   { palette: amber-700 }
        negative:  { palette: slate-600 }
        informative: { palette: slate-600 }
      data:
        category-1: { palette: cinnabar }
        # ... 省略则继承基础色板，见 3.3
```

### 3.1 命名规则：一条，机械可导

```
color.text.primary   →   --color-text-primary
color.status.positive →  --color-status-positive
palette.cinnabar      →   --palette-cinnabar（仅内部）
```

**规则**：`<层>.<路径>` → `--<层>-<路径>`，点与下划线都换成连字符。

**投影层按这条规则生成变量名，不再需要映射表。** 这是 S2 的修法，也是「加令牌不用改第二处」的关键。

**校验**：一个测试断言每个投影出的变量名等于其派生名。任何手工特例都会让它失败。

### 3.2 别名：一个值可以在多个角色上

`accent.brand`、`status.positive`、`data.category-1` 都指向 `palette.cinnabar`。

今天它们各自持有 `"#B83D2E"`；之后它们**引用同一个色板项**。

**改品牌色 = 改 `palette.cinnabar` 一行**，五个角色自动跟随。

### 3.3 省略规则：哪些层可以不写

| 层 | 可否省略 | 省略时 |
|---|---|---|
| `palette` | 否 | — |
| `color.surface` / `text` / `border` / `accent` | 否 | 校验要求这些角色存在 |
| **`color.status`** | **是** | 从 `accent.brand` 派生（现状的约定：正向即品牌色） |
| **`color.data`** | **是** | 从基础色板派生出一条分类色序 |

**这一条直接解掉存储设计的 B4**：采纳一个色系时，如果不打算单独设计图表配色，就省略 `data`。只有想独立定义图表色的方案才写它。

### 3.4 模板只读 `color` 层

| 层 | 谁读 |
|---|---|
| `palette` | 只有 `color` 层内部的解析 |
| `color` | 模板、投影、图表主题桥 |
| `palette-*` 变量 | **模板禁止引用** |

一条检查：模板中出现 `var(--palette-` 即失败。

---

## 四、加一个令牌：目标流程

```yaml
# 1. 新色 → 加进 palette（若它确实是新的原始色）
palette:
  teal-600: "#0F6F6A"

# 2. 新角色 → 加进 color
color:
  accent:
    link: { palette: teal-600 }
```

```html
<!-- 3. 在需要它的模板里使用 -->
a { color: var(--color-accent-link); }
```

```bash
# 4. 四项检查
python3 scripts/profile_check.py         # 形状与语义
python3 scripts/projection.py check      # 是否投影、是否被读
python3 scripts/color_sources.py check   # 四个源是否一致
python3 scripts/build.py && python3 scripts/document_baseline.py compare
```

**只碰两个文件，不碰 schema，不碰映射表，不碰所有权表。**

对照今天：profile + 映射表 + 模板 + （可能的 schema）—— 四处以上，其中一处靠人记。

---

## 五、治理规则：一个令牌凭什么存在

令牌不是免费的。它要有：

| 条件 | 检查方式 |
|---|---|
| 被投影 | `projection.py check` |
| 至少一个模板或图表读它 | 同上（消费门禁，修复计划 Phase 6） |
| 删掉它会改变产物 | 同上 |
| 与另一个令牌**不同值**或**不同职责** | 人工；同值同职责 = 合并 |

最后一条针对实测的 7 组重复。**同值同职责的令牌应该合并**；同值不同职责的保留，但应该指向同一个 `palette` 项 —— 那时「同值」不再是重复，而是显式的别名。

---

## 六、迁移路径（增量，不推倒）

### 阶段 1：加层，不改模板

- schema 增加 `palette` 与 `color` 两个域（现有四个域保持不变）
- 主题文件把 `colors`/`accent`/`status`/`data` 的 24 个不同值提成 `palette`，再把现有令牌改写成 `{palette: ...}` 引用
- `projection` 生成 `--color-*` 变量
- **同时生成一段兼容别名**，把旧变量名指过去：

```css
/* 迁移期别名，模板改完后逐条删除 */
--parchment: var(--color-surface-page);
--ivory:     var(--color-surface-card);
--brand:     var(--color-accent-brand);
```

模板一个字不改，产物不变。

**验收**：默认主题下全部产物字节不变。

### 阶段 2：模板逐个迁移

模板从 `var(--parchment)` 改成 `var(--color-surface-page)`。

**验收**：每迁一个模板，`document_baseline` 必须显示该文档无变化（值相同，只是名字变了）。

### 阶段 3：删别名

**一条检查让别名自己消失**：别名若已无任何消费者，`projection.py check` 报错要求删除。否则别名会永久留下，成为第七处命名。

### 阶段 4：旧域退休

模板与检查都迁完后，`colors`/`accent`/`status`/`data` 从 schema 移除。

**注意**：`color_sources.py`、`build_color_schemes.py` 现在读平面域，需同步。

---

## 七、迁移前后的对照

### 改品牌色

| | 今天 | 之后 |
|---|---|---|
| 改几处 | 5 个令牌 + 模板字面值 | `palette.cinnabar` **一行** |
| 同步保证 | 无，靠 `color_sources` 事后发现 | 引用关系本身保证 |
| 涉及文件 | 62 个含该值 | 1 个 |

### 加一个令牌

| | 今天 | 之后 |
|---|---|---|
| 文件 | profile + 映射表 + 模板 | profile + 模板 |
| 名字 | 想两个（路径名、变量名） | 想一个，另一个派生 |
| 忘记改映射表 | 静默失效 | 不可能（派生） |

### 采纳一个新色系

| | 今天 | 之后 |
|---|---|---|
| 要写的值 | 36 个令牌逐一手写；`data` 14 个没有对应 → 阻塞 | 一条 `palette` + 角色引用；`data` 可省略继承 |
| 图表色板 | 无主 | 继承或显式声明，二选一 |

---

## 八、这个设计不做什么

| 不做 | 原因 |
|---|---|
| 做四层（primitive → semantic → component → document role） | 实测 36 个令牌、24 个值，没有组件层的压力 |
| 为每个模板建专用令牌 | 会退化成 alias 网络；模板读语义角色 |
| 把图表主题合并进来 | 图表是 12 令牌固定交换单元，合并是独立决策 |
| 自动从色板生成整套色相阶梯 | 需要色彩科学（OKLCH 等），当前不需要；要时再说 |
| 用 `extends` 让色系继承色系 | 难追踪；用「省略即继承默认」代替 |

---

## 九、待你决定

| # | 问题 | 选项 | 倾向 |
|---|---|---|---|
| 1 | 层数 | 两层（palette + color）/ 三层（+ document role） | **两层**：没有实测压力 |
| 2 | 命名前缀 | `--color-*` / 保留无前缀但强制派生 | **`--color-*`**：层级可见 |
| 3 | `color` 的二级分组 | `color.text.primary` / `color.text-primary` | **点分**：可派生、可遍历 |
| 4 | 字面值允许吗 | `{palette: x}` 与 `"#RRGGBB"` 并存 / 必须走 palette | **并存**：一次性颜色不必进色板 |
| 5 | 旧域何时退休 | 立即 / 迁移完成后 | **完成后** |
| 6 | 别名保留多久 | 由检查强制删除 | 同 |

**第 4 项值得说明**：强制所有色值都进 `palette` 会让色板膨胀。允许字面值，但**别名优先** —— 一个值被两个以上角色使用时，它就是色板项。

---

## 十、与其它设计的关系

```
存储设计（存哪里）
    └── 本设计（令牌怎么组织）    ← 你在这里
            └── 修复计划 Phase 1（颜色进投影）
                    └── 色系才真正生效
```

**依赖顺序**：Phase 1 先落地（否则投影不存在，派生命名没有出口），然后本设计的阶段 1 可以一次做完。

---

## 十一、复核命令

```bash
# 改一个色要动多少处
grep -rl "B83D2E" assets references scripts index.html index-zh.html | wc -l
grep -rc "B83D2E" assets/templates/*.html assets/diagrams/*.html | awk -F: '{s+=$2} END {print s}'

# 令牌冗余
python3 -c "
import yaml
from collections import defaultdict
from pathlib import Path
t = yaml.safe_load(Path('references/profiles/theme/folio-classic-v1.yaml').read_text())['profiles']['folio-classic-v1']
vals = [(f'{d}.{k}', str(v).upper()) for d in ('colors','accent','status','data') for k, v in (t.get(d) or {}).items()]
d = defaultdict(list)
for k, v in vals: d[v].append(k)
print(len(vals), '令牌 /', len(d), '不同值')
for v, ks in d.items():
    if len(ks) > 1: print(' ', v, '->', ', '.join(ks))
"

# 命名是否机械一致（今天的答案：0 个一致）
python3 -c "
import re, yaml
from pathlib import Path
t = yaml.safe_load(Path('references/profiles/theme/folio-classic-v1.yaml').read_text())['profiles']['folio-classic-v1']
tpl = Path('assets/templates/one-pager.html').read_text()
m = re.search(r':root\s*\{', tpl); end = tpl.index('}', m.end())
decl = dict((n, v.strip().strip(chr(34))) for n, v in re.findall(r'--([a-z0-9-]+)\s*:\s*([^;]+);', tpl[m.end():end]))
by_value = {v.upper(): n for n, v in decl.items()}
for d in ('colors','accent','status'):
    for k, v in (t.get(d) or {}).items():
        css = by_value.get(str(v).upper())
        if css:
            print(f'{d}.{k} -> --{css}')
"

# schema 是否需要为新增令牌而改（答案：不需要）
python3 -c "
import json
from pathlib import Path
p = json.loads(Path('references/schemas/profile/theme.schema.json').read_text())['properties']['profiles']['additionalProperties']['properties']
print({k: type(v.get('additionalProperties')).__name__ for k, v in p.items() if 'additionalProperties' in v})
"
```
