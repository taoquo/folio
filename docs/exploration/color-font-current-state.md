# 语义化色彩与自定义字体：现状盘点

> 对应探索方案 E0。**本文只做盘点与调研，不做实施。**
>
> 目的：回答方案提出的问题之前，先弄清仓库里**已经有什么**，避免重造。

**盘点时间**：2026-10-11
**分支**：`dev/document-engine`
**方法**：全部数据来自实际命令，非推测

---

## 一、色彩现状

### 1.1 颜色的五个声明源

| 来源 | 文件 | 颜色数 |
|---|---|---|
| 模板 `:root` | `assets/templates/*.html` | 10–15（每个模板） |
| 颜色令牌表 | `references/tokens.json` | **8** |
| Theme profile | `references/profiles/theme/folio-classic-v1.yaml` | **12** |
| Drawing 主题 | `scripts/drawing/theme/folio.py` | **12** |
| 图表模板 | `assets/diagrams/*.html` | 10–14 |

**关键事实**：**同一个颜色值在 5 处独立声明**。

复核：

```bash
grep -o '#[0-9A-Fa-f]\{6\}' assets/templates/one-pager.html | sort -u | wc -l
```

### 1.2 值是一致的，但靠人工维护

| 令牌 | tokens.json | 模板 | 结果 |
|---|---|---|---|
| `--parchment` | `#F6F0EA` | `#F6F0EA` | 一致 |
| `--brand` | `#B83D2E` | `#B83D2E` | 一致 |
| `--near-black` | `#191514` | `#191514` | 一致 |

**它们目前一致**，但**没有任何机制保证一致** —— 靠人工同步。

### 1.3 已有 Theme Profile，设计意图正确

`references/profiles/theme/folio-classic-v1.yaml` 的文件头写着：

> Theme is appearance: the parchment canvas, the cinnabar accent, and the strokes that carry structure. It deliberately does NOT contain type sizes, leading, hyphenation or page rules.
>
> **This split is the point of the file.** Today the template `:root` block holds colours and the `--serif` stack side by side, so "change the theme" and "change the typography" are the same edit.

**这与方案 §3 的架构设想完全一致** —— 仓库已识别这个问题并建立了 profile 结构。

### 1.4 但 Theme Profile 的颜色值是空的 🔴

```python
style_resolver.resolve(genre='one-pager').values['colors.paper']
# ResolvedValue(path='colors.paper', value='', source='theme:folio-classic-v1')
```

**17 个颜色值全部解析为 `''`。**

**根因**：

```python
# scripts/profile_check.py:149
line = raw.split("#", 1)[0].rstrip()   # ← 粗暴剥离注释
```

自定义 YAML 解析器用 `split("#")` 去注释，**把引号内的 `#F6F0EA` 也切掉了**。

| 事实 | 值 |
|---|---|
| 被破坏的项 | **15**（全部在 `folio-classic-v1.yaml`） |
| 影响 | Theme 的所有颜色值 |
| 标准 YAML 行为 | `yaml.safe_load('a: "#F6F0EA"')` → `{'a': '#F6F0EA'}` ✅ |

**严重性**：这是一个**已定义但未生效**的能力 —— 恰好是方案 §1「不把新增 Schema 字段视为功能完成」警告的情况。

### 1.5 已有的颜色约束

| 约束 | 位置 | 作用 |
|---|---|---|
| 暖色板不变量 | theme profile `invariants.palette: warm` | 声明性 |
| 禁止冷灰 | `COOL_GRAY_BLOCKLIST`（`build.py --check`） | **硬门禁** |
| 单强调色 | `references/decisions/0006-*.md` | 设计决策 |
| 可覆盖令牌 | `overridable: [accent.brand, accent.tint, accent.tint_strong]` | 声明性 |

**结论**：约束机制**部分存在**，但只有「禁止冷灰」是真正执行的。

---

## 二、字体现状

### 2.1 字体资产

| 文件 | 大小 | 许可 | 用途 |
|---|---|---|---|
| `LXGWWenKai-Regular.ttf` | 24.3 MB | OFL-1.1 | 中文正文 400 |
| `LXGWWenKai-Medium.ttf` | 24.1 MB | OFL-1.1 | 中文 500 |
| `SourceSerif4Variable-Roman.ttf` | 1.1 MB | OFL-1.1 | 西文正文（可变 200–900） |
| `JetBrainsMono.woff2` | 0.1 MB | OFL-1.1 | 代码 |

**总计约 50 MB**，其中中文占 97%。

### 2.2 已有 Font Manifest ✅

`references/manifests/fonts-v1.yaml` **结构完整**：

| 字段 | 内容 |
|---|---|
| `fonts` | 5 个条目（body_zh_regular、body_zh_medium、mono、body_en、body_en_fallback） |
| `fallback_chains` | **4 条**（en_serif、zh_serif、mono、diagram_serif） |
| `fallback_policy` | 回退策略声明 |
| `ci` | CI 检查配置 |
| 许可 | 每条含 `license: OFL-1.1` 或系统字体说明 |

**这已经覆盖了方案 §5.3 提出的 FontManifest 核心字段。**

### 2.3 已有 Language Profile 与回退链 ✅

`references/profiles/language/folio-v1.yaml` 有 **3 个 profile**：

| Profile | tag | script | font_fallback |
|---|---|---|---|
| `en-us-v1` | en-US | Latn | `['Source Serif 4', 'Charter', 'Georgia', ...]` |
| `zh-hans-cn-v1` | zh-Hans-CN | Hans | `['LXGW WenKai', 'Source Han Serif SC', ...]` |
| `mixed-latin-cjk-v1` | und | Zyyy | Latin 走西文栈，CJK 走中文栈 |

**这已经实现了方案 §5.4 提出的「按语言配置回退」模型。**

### 2.4 字体角色：只有 3 个

`references/profiles/typography/folio-v1.yaml`：

```yaml
folio-editorial-zh-v1:
  body: [family, size_pt, leading, weight, alignment]
  roles: [heading_1, heading_2, caption]
```

**当前角色**：`body` + `heading_1` + `heading_2` + `caption`

方案 §5.2 提出三档（3 角色 / 6 角色 / preset）：

| 方案 | 当前状态 |
|---|---|
| A（body/heading/code） | **接近**，但 `code` 未定义为角色 |
| B（+data/caption/math） | 未实现 |
| C（genre preset + 覆盖） | 未实现 |

### 2.5 系统字体依赖已消除 ✅

**本轮已完成的工作**：

| 产物类别 | 无系统字体依赖 |
|---|---|
| 文档 demo | 21/21 |
| 图表产物 | 5/5 |
| 文档示例 | 31/31 |
| **总计** | **57/57** |

**这消除了方案 §5.5 关注的核心风险** —— 实际使用字体不再依赖运行环境。

### 2.6 后端能力差异

| 后端 | 字体处理 | 状态 |
|---|---|---|
| WeasyPrint | `@font-face` + Pango | ✅ 已验证（57 个产物） |
| PPTX writer | `run.font.name` | ⚠️ 见 `hosting.py:521` |
| SVG/PNG（图表） | SVG `font-family` | ✅ 已统一 |

**PPTX 未验证** —— 方案 §8.3 要求「记录 writer 是否能够设置所需字体」。

---

## 三、方案问题的初步回答

### 3.1 色彩

| 方案提问 | 现状回答 |
|---|---|
| 朱砂红是品牌色还是通用强调色？ | 设计决策文件 `0006` 明确为**单一强调色**；theme profile 有 `accents_per_document: 1` |
| 是否需要分「语义角色」与「具体颜色」？ | **已有** theme profile 的 `colors`/`accent` 分层，但**值是空的** |
| 不同文档类型是否需不同色彩密度？ | 当前**所有文档共用** `folio-classic-v1` |
| 如何避免语义色/图表色混用？ | **无机制** —— Drawing theme 与文档 theme 是两套独立声明 |

### 3.2 字体

| 方案提问 | 现状回答 |
|---|---|
| 「自定义字体」指哪些能力？ | 当前支持**项目内置字体**；系统字体为回退 |
| 字体设置是主题级/文档级/角色级？ | **语言级 + 角色级**（已有 language profile + roles） |
| 正文/标题/代码/数据是否需独立角色？ | 当前 4 个角色，`code` **未作为角色定义** |
| 各语言如何配置回退链？ | **已实现**（3 个 language profile + 4 条链） |
| 如何确认 PDF 实际使用了哪些字体？ | **已实现**（`pdffonts` 验证，本轮用于 57 个产物） |
| 字体变化对排版的影响？ | **已实现度量**（`fidelity.py`、页数契约、SSIM） |
| 字体许可如何记录？ | **已实现**（font manifest 含 license 字段） |
| 后端能否一致使用？ | WeasyPrint ✅ / SVG ✅ / **PPTX 未验证** |

---

## 四、关键发现

### 🔴 发现 1：Theme 颜色值是空的

**这是最重要的一项。**

| 项 | 状态 |
|---|---|
| Profile 定义 | ✅ 存在且设计正确 |
| 字段被消费 | ⚠️ 被读取，但值为 `''` |
| 影响产物 | ❌ **无** —— 模板用硬编码值渲染 |
| 根因 | YAML 解析器 `split("#")` 破坏十六进制色值 |
| 修复成本 | **低**（解析器识别引号） |

**这正是方案 §1 警告的情况**：「不把新增 Schema 字段视为功能完成；必须验证字段被真实消费并影响最终产物。」

### 🟠 发现 2：颜色有 5 个独立声明源

**无单一事实来源**。当前靠人工保持一致。

### 🟠 发现 3：文档 theme 与绘图 theme 是两套

| | 声明位置 |
|---|---|
| 文档颜色 | 模板 `:root` + theme profile |
| 图表颜色 | `scripts/drawing/theme/folio.py` |

**方案 §4.5 建议「共享色彩语义词汇，但不合并 IR」** —— 当前**连词汇都不共享**。

### 🟡 发现 4：字体系统比预期成熟

方案假设需要从零建立 FontManifest / LanguageProfile / fallback 链 —— **实际都已存在**。

**这意味着字体的探索重点应转向**：
1. 角色扩展（`code`、`data`、`math`）
2. 用户自定义字体的**来源类型**（内置/上传/系统）
3. PPTX 后端验证
4. 变量字体的实际能力边界

---

## 五、与方案的差异

| 方案假设 | 实际情况 |
|---|---|
| 需要建立 FontManifest | **已有** |
| 需要设计 fallback 与语言策略 | **已有**（3 profile + 4 链） |
| 需要区分 primitive/semantic token | **已有分层**，但值为空 |
| 需要建立 ResolvedStyle 来源追踪 | **已有**（`style_resolver` 记录 source） |
| 色彩需要「从零探索」 | **有基础骨架**，问题是「未生效」 |

**结论**：方案的**大部分架构设想仓库已经实现**，真正的问题是：

1. **已定义的未生效**（theme 颜色）
2. **生效的未统一**（5 个颜色源）
3. **未建的**（色彩语义、图表色板、PPTX 字体验证）

---

## 六、下一步建议（待你确认）

按「先验证已有、再扩展」的顺序：

| 优先级 | 事项 | 类型 |
|---|---|---|
| 1 | 修复 YAML 解析器，让 theme 颜色真正生效 | 调研 → 小修 |
| 2 | 统计 theme 生效后模板是否可去掉硬编码 | 调研 |
| 3 | 建立颜色源一致性检查 | 调研 |
| 4 | 探索色彩语义模型（方案 A/B/C） | 需要 PoC |
| 5 | 探索字体角色扩展 | 需要 PoC |
| 6 | PPTX 字体能力验证 | 需要实验 |

**第 1 项是前提** —— 当前 theme 是「声明了但没生效」，在此基础上讨论色彩模型会建立在错误的前提上。

---

## 七、复核命令

```bash
# 颜色的 5 个声明源
grep -o '#[0-9A-Fa-f]\{6\}' assets/templates/one-pager.html | sort -u | wc -l
python3 -c "import json;print(len(json.load(open('references/tokens.json'))))"

# theme 颜色为空
python3 -c "
import sys;sys.path.insert(0,'scripts')
import style_resolver as sr
print(sr.resolve(genre='one-pager').values['colors.paper'])
"

# 字体资产与清单
ls -la assets/fonts/
python3 -c "import yaml;d=yaml.safe_load(open('references/manifests/fonts-v1.yaml'));print(list(d['fonts']),list(d['fallback_chains']))"

# 系统字体依赖
python3 -c "
import subprocess,glob
n=sum(1 for f in glob.glob('assets/**/*.pdf',recursive=True) if 'Charter' in subprocess.run(['pdffonts',f],capture_output=True,text=True).stdout)
print(f'{n} 个残留')
"
```
