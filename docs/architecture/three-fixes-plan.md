# 三项重点修复计划

> 目的：修复评估中识别出的三个最值得投入的问题。每项都先做根因诊断，再做修复，再验证。

**分支**：`dev/document-engine`
**起点**：`ca5cc46`（855 测试通过，census 49/50）

---

## 一、诊断结果（实测，非推测）

### A1：`style_resolver` 默认选错语言 🔴

**现象**

```
python3 scripts/style_resolver.py resolve --genre one-pager
  → typography  folio-one-pager-en-v1     ← 错，模板默认中文
```

**根因**

`_best_match` 打分后按**名称字母序**打破平局：

```
实测排序:
  4  folio-one-pager-en-v1    ← 胜出（'e' < 'z'）
  4  folio-one-pager-zh-v1
```

`-en` 与 `-zh` 同分（genre 匹配各 +4），平局由字母序决定。

**危害等级**：最高。其他缺口是「能力不足」，这个是「**给出错误答案**」—— 不显式传语言时，解析出英文排版参数并注入渲染。

---

### A2：间距只能事后验证 🟠

**现象**

| 事实 | 值 |
|---|---|
| `spacing.py` 被引用者 | `census.py`、`spacing_probe.py`（**仅诊断**） |
| `projection.py` 投影 gap | **0 处** |
| 渲染时使用 | **否** —— 仍由模板 CSS 决定 |

**根因**

上一轮的差分实验发现：`margin-top` → `padding-top` 会使 SSIM 降到 **0.90348**。因此**主动放弃**了替换。

**但结论过度保守**：实验证明的是「**不能盲目替换存量**」，不是「间距模型无用」。

---

### A3：分页缺陷检测不可靠 🟠

**现象**

`layout_experiment` 的 6 类检测中 **5 类被判不可靠**：

| 检测 | 比率 | 问题 |
|---|---|---|
| short-last-line | 100% | 短末行是正常排版 |
| heading-at-page-bottom | 64.3% | 在 long-doc 上 **6/7 页**触发 |
| widow | 50% | long-doc 上 **6/6 跨页段落**全中 |
| orphan | 50% | 同 widow |
| thin-page | 21.4% | 收尾页不是缺陷 |

**根因**

`artifact_inspector` 从 PDF 反推段落边界：PDF 不含源 id，只能按**行几何**猜测。猜测在 long-doc 上**饱和**（每个跨页段落都被判为 widow）。

**关键技术前提（本轮实测突破）**

WeasyPrint 的 `render()` 返回 `Document`，其 `pages[n]._page_box` 是**完整 box tree**：

```
PageBox
  BlockBox <html>
    BlockBox <body>
      BlockBox <p>          ← 段落边界，精确
        LineBox <p>         ← 行框，可数
          TextBox <p> '...'
```

**这意味着不必从 PDF 猜测** —— 行数与段落归属可直接读取。

---

## 二、修复方案

### A1 修复：从模板推断语言

| 步骤 | 内容 |
|---|---|
| A1-1 | `_best_match` 接受 `prefer_language` 参数 |
| A1-2 | 无显式语言时，从模板的 `lang` 属性推断 |
| A1-3 | 仍无提示时，**报告歧义**而非静默选择 |
| A1-4 | 测试：无语言时选 zh；有 en 时选 en；两者皆无时报歧义 |

**为什么从模板推断**：模板决定文档语言，profile 应跟随它，而非按名称排序。

**验收**：

```bash
python3 scripts/style_resolver.py resolve --genre one-pager   # 应为 zh
python3 scripts/style_resolver.py resolve --genre one-pager --lang en-US   # 应为 en
```

---

### A2 修复：让间距成为「约束」而非「观察」

**核心判断**：不替换存量 CSS，而是让模型在**两条路径**上产生作用。

| 路径 | 作用 |
|---|---|
| **新文档** | 从规则**生成** gap（已验证变量注入 SSIM 1.0） |
| **存量文档** | 用 probe **验证** 模板是否符合规则 |

| 步骤 | 内容 |
|---|---|
| A2-1 | `projection.py` 增加 `gap_projection()`：把 `ResolvedGap` 转为 CSS 变量 |
| A2-2 | 注入**条件**：仅当模板未声明该 gap 时注入（避免覆盖） |
| A2-3 | `spacing_probe.py` 增加 `audit` 模式：规则 vs 实测的差异报告 |
| A2-4 | 测试：注入后退回原始值，SSIM 保持 1.0 |

**关键约束**：**默认关闭**。开启时只补模板未声明的部分。

**验收**：

| 项 | 阈值 |
|---|---|
| 默认关闭时 SSIM | 1.00000 |
| 开启时 SSIM | ≥ 0.999 |
| 与 probe 的规则匹配数 | 不下降（当前 9/14） |

---

### A3 修复：从 box tree 精确测量分页缺陷

| 步骤 | 内容 |
|---|---|
| A3-1 | `box_inspector.py`：从 WeasyPrint box tree 提取段落与行 |
| A3-2 | 精确计算：每段行数、跨页段落、widow、orphan、标题孤立 |
| A3-3 | 与 `artifact_inspector` 的启发式结果**对比**，量化误报率 |
| A3-4 | `layout_experiment` 改用精确测量 |
| A3-5 | 测试：构造已知缺陷文档，验证精确检出 |

**为什么这是突破**：box tree 给出**带源 id 的段落**，不再需要几何猜测。

**验收**：

| 项 | 阈值 |
|---|---|
| 段落边界准确率 | 100%（有源 id） |
| 与启发式对比 | 量化差异并记录 |
| 已知缺陷检出 | 构造用例全部检出 |

---

## 三、实施顺序与依赖

```
A1（独立，最高优先级）
  ↓
A3（独立，技术突破已验证）
  ↓
A2（依赖 A3 的精确测量来验证）
```

**为什么 A2 最后**：间距是否「正确」需要精确的分页测量来判断，A3 提供这个能力。

---

## 四、验证体系

### 每项的验收层次

| 层 | 方法 | 阈值 |
|---|---|---|
| L1 功能 | 单元测试 | 全部通过 |
| L2 不退化 | `fidelity.py measure` | 7/7 SSIM 1.0000 |
| L3 不回归 | `unittest discover` | 855+ 通过 |
| L4 门禁 | 8 项门禁 | 全绿 |
| L5 普查 | `census.py` | 不下降 |

### 每项完成后必跑

```bash
python3 -m unittest discover -s tests --buffer
ruff check .
python3 scripts/fidelity.py measure
python3 scripts/census.py
python3 scripts/document_baseline.py compare
```

---

## 五、风险矩阵

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| A1 改动影响现有解析 | 中 | 高 | 保留 `--lang` 显式路径；测试全覆盖 |
| A2 注入改变渲染 | **中** | 高 | **默认关闭**；开启时逐类验证 |
| A3 box tree API 变动 | 中 | 中 | 版本探测 + 降级到启发式 |
| A3 性能开销 | 中 | 中 | 只在需要时渲染 box tree |

---

## 六、交付里程碑

| 里程碑 | 完成标志 | 验证 |
|---|---|---|
| **M-A1** | 无语言时选 zh | 命令输出 zh profile |
| **M-A2** | 间距双路径生效 | 默认关 SSIM 1.0，开启 ≥0.999 |
| **M-A3** | 精确测量分页 | 段落边界 100% 准确 |
| **M-ALL** | 全量通过 | 855+ 测试、8 门禁、census ≥49 |

---

## 七、预期收益

| 项 | 修复前 | 修复后 |
|---|---|---|
| A1 | 静默给错答案 | 从模板推断，歧义时报错 |
| A2 | `spacing.py` 是死代码 | 新文档生成器 + 存量校验器 |
| A3 | 6 类检测 5 类不可靠 | 精确测量，可支撑自研决策 |
| **综合** | 能力声明未闭环 | **三项闭环，census 50/50** |
