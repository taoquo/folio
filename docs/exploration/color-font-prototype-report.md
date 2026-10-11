# 语义化色彩与自定义字体：实施报告

> 本文记录本轮实施的结果、证据，以及**被否决的方案与原因**。
>
> 代码尚未提交，等待 review。

**分支**：`dev/document-engine`
**前置**：`color-font-current-state.md`（E0 盘点）、`color-font-research.md`（四项调研）

---

## 一、实施内容

| # | 事项 | 状态 |
|---|---|---|
| 1 | 修复 YAML 解析器破坏十六进制色值 | 已完成（已单独提交 `d9dedc2`） |
| 2 | Theme 补 `status` 与 `data` 两个域 | 已完成 |
| 3 | 域所有权与 Schema 同步 | 已完成 |
| 4 | 模板接入 status 令牌 | 已完成 |
| 5 | 内联色值提升为变量 | 27 → 14（剩余全部为 `@page` 背景） |
| 6 | 清理死变量 | 移除 12 个真正无用声明 |
| 7 | 颜色源一致性检查工具 | 已完成并接入 CI |
| 8 | `stone` 漂移 → 更名 `label` | 已完成 |
| 9 | 修复字体验证的误报 | 已完成 |
| 9b | 修复 demo HTML 生成器不声明字体 | 已完成 |
| 10 | 图表色板接入 data 域 | **已否决**（见第三节） |

---

## 二、逐项证据

### 2.1 Theme 新增两个域

`references/profiles/theme/folio-classic-v1.yaml`：

```yaml
status:
  positive: "#B83D2E"      # 品牌红，中文财经读红为涨
  caution: "#A8722C"
  negative: "#5A6B7A"
  informative: "#4A6B7A"
  # 四个 tint
data:
  category_1..6            # 分类色，无顺序含义
  sequential_1..5          # 顺序色阶
  diverging_negative|neutral|positive
```

**共 21 个新令牌，全部可解析**：

```
status.positive   #B83D2E
data.category_1   #B83D2E
data.sequential_5 #7E241C
```

**域所有权**：`DOMAIN_FIELDS` 的 `theme` 集合加入 `status`、`data`。这不是放松校验，而是声明「颜色由 theme 决定」。

**Schema**：`theme.schema.json` 同步允许两个域，`additionalProperties: false` 仍然生效。

### 2.2 模板接入

| 模板 | 变更 |
|---|---|
| `equity-report` / `-en` | `--positive`/`--negative` → `--status-*`，补齐 8 个状态令牌 |
| `changelog` / `-en` | breaking 标签改用 `status.caution` 与 `caution_tint` |
| 全部 14 个 | 字面色值改为变量 |

**自检**：`var(--name)` 未定义引用数为 **0**。

### 2.3 内联色值与死变量

| 项 | 前 | 后 |
|---|---:|---:|
| `:root` 之外的字面色值 | 27 | **14** |
| 声明但未读取的变量 | 18 | 0 |

**剩余 14 处全部是 `@page` 背景** —— 该渲染器中 `@page` 规则读不到自定义属性，这是技术必需，不是遗漏。

### 2.4 颜色源检查

新增 `scripts/color_sources.py`：

```bash
python3 scripts/color_sources.py check       # 四个源是否对一个名字给同一个值
python3 scripts/color_sources.py inventory   # 只出现在单一源的颜色
```

**设计判断**：检查的是**连接**而不是**值**。一个源可以拥有另一个源没有的颜色（图注与正文是不同职责）；不允许的是两个源对同一个名字给不同的值 —— 这正是 `stone` 曾经的情形。

已接入 CI `fast-gate`，并新增 13 个测试。

### 2.5 `stone` 漂移

| | 文档 | 图表 |
|---|---|---|
| 名字 | `colors.stone` | `label` |
| 值 | `#85776F` | `#74665F` |

**改为两个名字并说明理由**：图表标签在更小的尺寸下落在羊皮纸画布上，需要更深的灰。用同一个名字掩盖了一个真实差异。

连锁影响 18 处调用点、3 个对比色对、2 个关键字构造的主题、1 个测试。

### 2.6 字体验证误报

`build.py --verify` 在 HEAD 下已有 **14 个 ERROR**：`no recognizable font embedded`。

**根因**：「可识别字体」列表只有宿主字体（Charter、Georgia、Songti…）。字体统一后图表只嵌入 `Source Serif 4`，于是正确嵌入的字被报成缺失。

**修正**：仓库自带的字体也算可识别 —— 文件在仓库里，比系统字体是更强的保证。修复后 **0 ERROR**。

### 2.7 demo HTML 生成器不声明字体

`_showcase_demo_html` 在 `font-family` 里写了 `"Source Serif 4"`，却**不声明 `@font-face`**。

仓库里已提交的 demo HTML 有这个声明，因为它是**手工加上的** —— 重新生成一次就没了。这正是字体统一工作留下的隐患：全量构建或单目标重建都会静默丢掉字体声明。

**修正**：生成器输出声明，路径用相对的 `../fonts/...`（绝对 `file://` 在别的机器上不可用）。现在重新生成的 demo HTML 与提交版本只差声明的排版格式，`git diff` 里是等价的。

---

## 三、被否决的方案：图表色板接入 data 域

### 尝试

把三处图表色板 `(olive, label, neutral_mid)` 等替换为 `theme.categorical`。

### 结果

| 失败 | 现象 |
|---|---|
| donut 越界 | 色板从 6 个变 5 个，`palette[index]` 抛 `IndexError` |
| 对比度门禁 | `VQ106` 报 1.05:1、2.21:1 |
| 令牌数量测试 | `assertEqual(12, len(colors))` 失败 |

### 根因

**Drawing theme 是一个 12 令牌的固定交换单元**：

- 每个令牌在 dark / terminal 主题中都必须有对应；
- 有测试断言数量为 12；
- `theme_token_map` 做令牌对令牌替换，**新字段在两个深色主题中继承了浅色默认值**，于是深色画布上留下浅色 → 对比度门禁失败（正确地失败）。

文件里还有一段说明：`neutral_mid` 与 `neutral_light` 是**仅用于填充**的色阶，不用于文字或描边。

### 判断

**扩展 Drawing theme 是一个决策，不是重构。**

它意味着同时扩展三个主题、改动一个测试断言的约束，并且要决定图表色板是否属于主题交换单元。这超出本轮范围。

**图表色板恢复原状**，`theme.categorical/sequential/diverging` 不作为对现有图表的强制。

**这与仓库既有的原则一致**：AGENTS.md 记录过「不要用模型的间距替换模板的间距」—— 诊断可以指出差异，替换是另一回事。

---

## 四、过程中的三个自伤与修正

诚实记录，因为它们说明了检查的价值：

| # | 错误 | 如何被发现 | 修正 |
|---|---|---|---|
| 1 | 重建 `:root` 块时丢了开括号，14 个模板 CSS 失效 | 括号计数 | `git checkout` 后改为逐行编辑，不重建块 |
| 2 | 判定「未使用变量」用 `var(--name)` 精确匹配，**漏掉带回退值的 `var(--border-soft, #E8DED6)`**，删除了 3 个仍在使用的变量 | `document_baseline` 报 `long-doc-en: fonts, text_sha256` —— **文字变了** | 改用 `var(--name` 前缀匹配，并在脚本末尾加未定义引用自检 |
| 3 | resume 的 `#e3baa9` 被替换成主题 `--border`（不同值） | `document_baseline` 报 resume 预览变化 | 保留原值，声明为 `--rule-warm` |

**第 2 项最有价值**：文字哈希变化告诉我「一次声称只改颜色的重构改了文字」。这正是基线检查存在的意义。

---

## 五、验证结果

| 检查 | 结果 |
|---|---|
| 单元测试 | **934 通过** |
| ruff | **clean** |
| `corpus.py validate` | OK |
| `document_baseline.py compare` | OK |
| `assets.py check` | OK |
| `projection.py check` | OK |
| `diagnostics.py check` | OK |
| `corpus_matrix.py gaps` | OK |
| `pipeline.py rollback-drill` | OK |
| `architecture.py check` | OK |
| `profile_check.py` | OK（36 profiles） |
| `color_sources.py check` | OK |
| `build.py --check / --sync / --verify / --check-placeholders / --check-index / --check-rhythm` | 全部 OK |
| 保真度 | 7/7 渲染一致（平均 SSIM 0.9887，**与 HEAD 相同**） |

### 唯一一处有意的视觉变更

`document_baseline` 报 **changelog / changelog-en** 预览变化：

| | 前 | 后 |
|---|---|---|
| breaking 标签背景 | `#f0e0d8` | `#F6EBD9`（`status.caution_tint`） |
| breaking 标签文字 | `#8b4513` | `#A8722C`（`status.caution`） |

**这是把模板接到语义令牌上的目的** —— 一处决定「警告」长什么样。

基线已用带理由的方式重新采样，理由写入 `document_baseline.py capture --approval-reason`。

**其余 14 个文档渲染完全不变** —— 提升为变量的字面值与变量同值；唯一值不同的那一处（resume 的分隔线）保留了自己的名字。

---

## 六、未做

| 项 | 原因 |
|---|---|
| Drawing theme 扩展 data 域 | 需要同时扩展三个主题，是决策 |
| 图表实际使用新色板 | 同上 |
| `data` 字体角色接入排版 | 已在 2 个 profile 声明，未接入渲染 |
| PPTX 字体验证 | 用户指示稍后再分析 |
| 27 处中的 14 处 `@page` 背景 | 渲染器限制，无法变量化 |

---

## 七、复核命令

```bash
# 测试与门禁
python3 -m unittest discover -s tests
for c in corpus document_baseline assets projection diagnostics \
         corpus_matrix pipeline architecture profile_check color_sources; do
  python3 scripts/$c.py validate 2>/dev/null || python3 scripts/$c.py check 2>/dev/null || \
  python3 scripts/$c.py compare 2>/dev/null || python3 scripts/$c.py gaps 2>/dev/null || \
  python3 scripts/$c.py rollback-drill 2>/dev/null
done
python3 scripts/build.py --check && python3 scripts/build.py --verify

# 新域是否可解析
python3 -c "
import sys; sys.path.insert(0,'scripts')
import style_resolver as sr
s = sr.resolve(genre='one-pager')
print(len([k for k in s.values if k.startswith(('status.','data.'))]), 'status/data tokens')
print(s.values['status.positive'].value, s.values['data.category_1'].value)
"

# 未定义变量自检
python3 -c "
import re, glob
from pathlib import Path
for f in sorted(glob.glob('assets/templates/*.html')):
    t = Path(f).read_text(encoding='utf-8')
    m = re.search(r':root\s*\{', t)
    end = t.index('}', m.end())
    d = set(re.findall(r'--([a-z0-9-]+)\s*:', t[m.end():end]))
    u = set(re.findall(r'var\(\s*--([a-z0-9-]+)', t))
    if u - d: print(f, sorted(u - d))
"

# 图表色板容量
python3 -c "
import sys, dataclasses; sys.path.insert(0,'scripts')
from drawing.theme import DEFAULT_FOLIO_THEME as t
print(len([f for f in dataclasses.fields(t) if getattr(t, f.name).startswith('#')]), 'colour tokens')
"
```
