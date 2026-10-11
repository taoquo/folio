# 色系的存储与扩展设计

> 回答：色系存哪里、是不是独立配置文件、后续怎么扩展。
>
> 所有结论来自实测，探针脚本已清理，工作区干净。

**分支**：`dev/document-engine`
**日期**：2026-10-11

---

## 一、直接回答

| 问题 | 回答 |
|---|---|
| 是独立的配置文件吗？ | **采纳后的色系不是新格式** —— 它就是一个 theme profile，与现有 `folio-classic-v1` 同构 |
| 那探索用的 YAML 呢？ | 它是**候选草稿**，只服务于对照页；采纳后**提升**为 profile，不并存在生产链路里 |
| 后续怎么扩展？ | 加一个文件。但**当前有四处会拦住你**，见第三节 |

**一句话**：不要为色系新建一套配置。仓库已经有一处权威存储、一个 schema、一个解析器 —— 色系应该长在那里。

---

## 二、现状：三处存储，三种角色

| 存储 | 内容 | 谁在消费 |
|---|---|---|
| `references/profiles/theme/folio-classic-v1.yaml` | **1 个主题**，36 个令牌（colors 10 / accent 4 / status 8 / data 14） | `style_resolver` 解析 → 目前无人消费（审计结论） |
| `references/exploration/color-schemes.yaml` | **12 个候选**，各 21 个令牌 | 只有 `build_color_schemes.py` |
| `scripts/drawing/theme/folio.py` | 图表主题，**12 令牌固定交换单元** | 图表编译器 |

**三者互不引用**。`color_sources.py` 现在只检查「同名是否同值」，不检查它们是否应该在一起。

### 为什么不该新建第四处

现有的 theme profile 机制已经具备扩展所需的全部性质：

| 性质 | 现状 |
|---|---|
| 一个目录放多个方案 | ✅ 目录遍历 |
| 一个文件一个方案 | ✅ 也支持一个文件多个 |
| 按名字选择 | ✅ `resolve(names={"theme": ...})` |
| Schema 校验 | ⚠️ 只校验一个文件（见下） |
| 与解析器连通 | ✅ |
| 与投影连通 | ❌ 审计结论：颜色不进投影，需先修 |

---

## 三、实测到的四个阻塞点

### 🔴 B1：Schema 只校验一个硬编码文件

```python
# scripts/profile_check.py:592
PROFILE_FILES = {"theme": "folio-classic-v1.yaml"}
...
profile_path = PROFILES / kind / PROFILE_FILES.get(kind, "folio-v1.yaml")
```

**实测**：新建 `folio-probe-v1.yaml`，里面放一个 schema 明确禁止的键：

```
OK: profiles valid and consistent with the repository
```

**探针通过了。**

反向验证 —— 同样的非法键放进 `folio-classic-v1.yaml`：

```
ERROR theme:profiles.folio-classic-v1.colors.bogus_key: 1 is not of type 'string'
```

**检查本身有效，是覆盖面问题。** 这意味着今天新增任何色系文件都会**绕过 schema**，错的键名、漏的必填项、类型错误都不会被发现。

**修法**：`check_schemas` 遍历该 kind 目录下的**所有** `*.yaml`，而不是取一个文件名。

### 🟠 B2：未知主题名报错不可读

```python
resolve(genre="one-pager", names={"theme": "does-not-exist"})
# KeyError: 'theme'
```

用户看到 `KeyError: 'theme'`，既不知道哪些名字可用，也不知道是自己拼错了。需要列出可用 profile。

### 🟠 B3：多主题并存时，默认选择是隐式的

实测：放两个 `genre: shared` 的主题文件，不给名字时：

```
不给名字: theme = folio-classic-v1
给名字:   theme = folio-probe-v1
```

它**安静地**选了一个。`_best_match` 的设计文档说「没有语言可裁决的平局会被报告」，但实测 `ResolvedStyle.violations` 是空列表 —— **平局没有可见出口**。加第二个色系时，默认主题的归属会变成一个没人明说的隐式规则。

**修法**：显式声明默认（schema 加 `default: true`），并让解析器在**多个默认**或**没有默认**时报错。

### 🟠 B4：令牌覆盖有三个缺口

对照 theme profile 的 36 个令牌与方案的 21 个：

| 缺口 | 说明 |
|---|---|
| `accent.tint_strong`、`colors.charcoal` | **12 个方案全都没覆盖** |
| `rule-warm` | 方案里有，主题里没有 —— 它现在是模板局部值 |
| `data.*`（14 项） | **任何方案都没有对应** |

**后果**：方案不能直接当 profile 用。采纳之后，`data` 域会是空的，图表色板无人负责；`tint_strong` 与 `charcoal` 会沿用旧主题的值，出现「一套新色系配几个旧颜色」。

### 🟡 另外两处

**`invariants` 是文件级，不是 profile 级**。多个文件各有各的 `invariants`，一个冷色方案可以自己声明 `palette: cool` 而无人反对 —— 何况现在**根本没人读它**（审计结论）。

**候选不能放在 `references/profiles/` 下**。`profile_check.load_profiles` 把每个子目录当成一个 profile kind：

```python
for kind_dir in sorted(PROFILES.iterdir()):
```

放一个 `profiles/theme/candidates/` 会被认成第六种 kind。

---

## 四、推荐设计

### 4.1 存储布局

```
references/profiles/theme/
  folio-classic-v1.yaml        ← 默认（唯一 default: true）
  folio-warm-blue-v1.yaml      ← 一个方案一个文件
  folio-blue-institutional-v1.yaml
  ...
        │
        ├── style_resolver.resolve(names={"theme": "folio-warm-blue-v1"})
        │
        └── projection 投影为 CSS 变量（修复计划 Phase 1）

references/exploration/
  color-schemes.yaml           ← 候选草稿，只服务对照页；采纳后移入上面
```

**命名**：`folio-<方向>-v<n>`。方向用英文短名，不带空格，便于出现在环境变量与 URL 里。

**一个文件一个 profile**：schema 允许一个文件多个，但一个文件一个的 diff 与 review 都更清楚，也和现有文件一致。

### 4.2 选择机制

```bash
FOLIO_THEME=folio-warm-blue-v1     # 修复计划 Phase 2
```

三层优先级：

| 层 | 来源 | 说明 |
|---|---|---|
| 1 | 文档自己声明 | IR 的 `theme` 字段（待评估） |
| 2 | 环境变量 | `FOLIO_THEME` |
| 3 | profile 的 `default: true` | 恰好一个；多于一个或没有则报错 |

**默认必须唯一且显式**。这是 B3 的修法。

### 4.3 需要先做的 schema 与检查改动

| # | 改动 | 文件 | 规模 |
|---|---|---|---|
| 1 | `check_schemas` 遍历 kind 目录下所有文件 | `scripts/profile_check.py` | 小 |
| 2 | schema 增加 `default: boolean`，并要求全库恰好一个 | `theme.schema.json` + `profile_check.py` | 小 |
| 3 | 未知主题名报错并列出可用项 | `scripts/style_resolver.py` | 小 |
| 4 | `data` 域允许省略并继承基础色板 | schema + `style_resolver.py` | 中 |
| 5 | `rule-warm` 纳入主题（`colors.rule_warm`） | 三处 | 小 |
| 6 | 补齐 `accent.tint_strong`、`colors.charcoal` 到 12 个方案 | 探索 YAML | 小 |
| 7 | `invariants` 从文件级移到 profile 级，或明确它是全局的 | schema + 文件 | 小 |

**第 4 项值得说明**：色系是否必须手写 14 个图表色是个真问题。让 `data` 可省略、省略时继承基础色板，意味着「换个品牌色」不需要同时设计一套图表配色 —— 这是合理的默认。想单独定义图表色的方案再写。

### 4.4 探索文件的归宿

| 选项 | 内容 | 评价 |
|---|---|---|
| A | 删除，方案只存 profile | 失去「一次渲染 12 个方案」的能力，采纳前无法比较 |
| B | 保留为独立来源，加转换器 | 两处存储，需要一致性检查 |
| **C** | **对照页改为读 `profiles/theme/*.yaml`**，探索 YAML 只做未采纳草稿 | **推荐**：采纳的方案只有一个来源 |

**C 的具体做法**：`build_color_schemes.py` 的 `load_schemes()` 合并两处 ——

- `references/profiles/theme/*.yaml` 里的 profile（**已采纳**，页面上标记）
- `references/exploration/color-schemes.yaml` 里的草稿（**候选**，页面上标记）

两者用同一个渲染管线，页面上区分状态。采纳一个草稿 = 把它写进 profile 并从草稿文件删掉。

这样单一事实来源成立：**已采纳的色系只在 profile 里存在**。

---

## 五、扩展一个新色系：完整流程

```bash
# 1. 起草（可选）：加进探索 YAML，渲染对照页看看
#    references/exploration/color-schemes.yaml
python3 scripts/build_color_schemes.py

# 2. 采纳：复制最近的 profile，改名字与值
cp references/profiles/theme/folio-classic-v1.yaml \
   references/profiles/theme/folio-warm-blue-v1.yaml
#    改 profile 名、去掉 genre（非默认）、补全 data 或省略继承

# 3. 形状与语义
python3 scripts/profile_check.py          # schema + 语义（修好 B1 后覆盖所有文件）

# 4. 不变量（修复计划 Phase 3）
#    暖色 / 禁冷灰 / 强调色数量 / 文档侧对比度

# 5. 与图表主题的一致性
python3 scripts/color_sources.py check

# 6. 渲染验证
FOLIO_THEME=folio-warm-blue-v1 python3 scripts/build.py
python3 scripts/document_baseline.py compare    # 会报预览变化，需带理由重采样

# 7. 对照页
python3 scripts/build_color_schemes.py
```

**第 6 步是必须的**：换主题会改变所有文档的渲染结果，`document_baseline` 会报出来，需要走带理由的审批 —— 这个流程已经存在。

---

## 六、扩展时不该做的事

| 反模式 | 为什么 |
|---|---|
| 为色系新建一套 YAML 格式 | 已经有 profile + schema + 解析器，新建等于第二个事实来源 |
| 把候选放进 `references/profiles/` | 每个子目录会被当成一个 profile kind |
| 靠 `genre` 区分多个色系 | genre 表达的是「文档类型」，不是「配色方案」。用它选色系会让 genre 承担两个含义 |
| 在模板里写色系名 | 模板读变量，不读主题名 |
| 让色系文件互相 `extends` | 会形成难以追踪的链；需要共享时用「省略即继承默认」 |

---

## 七、待你决定

| # | 问题 | 选项 |
|---|---|---|
| 1 | 默认主题怎么声明 | 唯一 `default: true` / 保留 `genre: shared` / 显式 `FOLIO_THEME` 必填 |
| 2 | `data` 是否属于色系 | 每个色系都定义 / **允许省略并继承**（推荐） |
| 3 | `rule-warm` 归谁 | 收进主题 `colors.rule_warm`（推荐）/ 留在模板 |
| 4 | 图表主题是否跟随文档主题 | 跟随 / 独立（现在是独立，12 令牌约束） |
| 5 | 探索 YAML 保留还是删除 | 保留为草稿（推荐）/ 删除 |
| 6 | 色系数量上限 | 建议同时存在的采纳色系 ≤ 4–6，多了会退化成「选择困难」 |

**第 6 项值得想一下**：Carbon 有 4 套，是因为每套对应一个明确场景（白/浅灰/深灰/黑）。色系如果只是观感不同而没有场景归属，数量本身就是成本。

---

## 八、与修复计划的关系

本设计**依赖**修复计划的两项：

| 依赖 | 原因 |
|---|---|
| Phase 1（颜色进投影） | 不修的话，存了 profile 也不影响页面 —— 现在改主题色 PDF 字节不变 |
| Phase 2（主题选择入口） | 不修的话，`FOLIO_THEME` 不存在，多存的色系无法被选中 |

**建议顺序**：

```
修复计划 Phase 1 + 2   →  本设计的 B1/B3 修法  →  采纳色系  →  色系扩展成为日常操作
```

先做 Phase 1/2，色系存储才有意义；先修 B1，扩展开头才不会绕过校验。

---

## 九、复核命令

```bash
# B1：新文件是否绕过 schema
cp references/profiles/theme/folio-classic-v1.yaml /tmp/p.yaml
sed 's/folio-classic-v1/folio-probe-v1/; s/      paper: "#F6F0EA"/      paper: "#F6F0EA"\n      bogus: 1/' /tmp/p.yaml \
  > references/profiles/theme/folio-probe-v1.yaml
python3 scripts/profile_check.py      # 今天会通过 —— 这就是问题
rm references/profiles/theme/folio-probe-v1.yaml

# B2：未知主题名的报错
python3 -c "
import sys; sys.path.insert(0,'scripts')
import style_resolver as sr
sr.resolve(genre='one-pager', names={'theme':'nope'})
"

# B3：多主题并存的默认选择
# 复制成第二个 profile 文件后，resolve() 不给定名字，看它选谁

# B4：令牌覆盖
python3 -c "
import yaml
from pathlib import Path
t = yaml.safe_load(Path('references/profiles/theme/folio-classic-v1.yaml').read_text())['profiles']['folio-classic-v1']
s = yaml.safe_load(Path('references/exploration/color-schemes.yaml').read_text())['schemes'][0]['tokens']
print('theme 域:', {k: len(v) for k, v in t.items() if isinstance(v, dict)})
print('scheme 令牌:', len(s))
"

# 候选不能在 profiles 下：profile_check 会把子目录当成 kind
grep -n "PROFILES.iterdir" scripts/profile_check.py
```
