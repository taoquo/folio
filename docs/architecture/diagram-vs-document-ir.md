# Diagram 与 Document IR 的架构关系分析

> 本文用于向外部评审者说明一个架构判断：DSL 驱动的 diagram 系统与本轮新建的 document IR 系统之间的关系。
> 文中所有数字与结论均可在仓库内复核，复核命令附在每节末尾。

**状态**：待外部评审
**分析对象**：`scripts/drawing/`（77 个 .py）与 `scripts/document_ir/`（9 个顶层项）
**结论摘要**：两套系统当前并列、零共享；本轮工作**未触碰** diagram 系统。

---

## 一、问题的由来

本轮工作为 Folio 的**文档侧**建立了一套语义中间表示（Document IR），并让它接管生产渲染路径。工作完成后，评审者指出：

> 「文档类型里面好像没有包含 Diagram 吧？尤其是 DSL 驱动的 diagram」

这个质疑成立。本轮建立的文档类型覆盖是：

| 类别 | 数量 | 产出管线 |
|---|---|---|
| 文档模板 | 7 类 × 2 语言 = 14 target | `assets/templates/` → `document_ir/` → WeasyPrint |
| **图表（diagram）** | **23 种**（catalog 实测） | `assets/diagrams/` → `scripts/drawing/` → SVG/PNG/PDF |

**Diagram 不在本轮范围内，且本轮 diff 未改动任何 drawing 代码。**

---

## 二、根本原因：两套系统是并列关系，不是同一系统的两个部分

### 2.1 它们各自独立成熟

| 维度 | drawing 侧 | document 侧（本轮新建） |
|---|---|---|
| 模块数 | **77 个 .py**（25 个顶层 + 子包） | 9 个顶层项 |
| IR 管线 | `SemanticDiagram → DrawingPlan → ResolvedScene` | `Document → Block[]` |
| 渲染器 | SVG / PNG / PDF 适配器 | HTML（skeleton writer）/ PPTX |
| 诊断 | `drawing/validation/` 14 模块，带错误码与修复提示 | `document_ir/validate.py`（对标中） |
| 指标 | 11 字段指标体系 | 5 维质量向量 |
| 基线 | `catalog-baseline-v3.json`，强制批准理由 | `document-v1/baseline.json`，强制批准理由 |
| 测试文件 | 24 | 13 |
| CI | `drawing-dsl.yml`（fast + release gate） | `document-engine-nightly.yml`（新增） |
| 共享代码 | **0** | **0** |

复核命令：

```bash
find scripts/drawing -name '*.py' | wc -l   # 77
ls scripts/document_ir/                      # 9 个顶层项
grep -rn "from.*document_ir import" scripts/drawing/   # 无输出
grep -rn "from.*drawing import" scripts/document_ir/   # 无输出
```

### 2.2 蓝图明确定位为「对标」，而非「统一」

原蓝图（`Folio 文档排版引擎落地实施蓝图.md`）的关键表述：

| 行 | 原文 | 含义 |
|---|---|---|
| 15 | 图形侧**已具备完整的编译纪律**（`SemanticDiagram → DrawingPlan → ResolvedScene`）…**成熟** | drawing 是已完成的一方 |
| 62 | 图形侧三阶段 IR — **成熟** | 状态评估 |
| 113 | 文档侧诊断模型**照此设计**（补上 severity/code/hint） | 借鉴关系 |
| 116 | 文档视觉回归**沿用**「不缩放」原则 | 借鉴关系 |

**即：蓝图把 drawing 侧当作成熟先例，要求文档侧向它学习，而不是把两者合并。**

### 2.3 为什么不应合并（技术判断）

| 理由 | 说明 |
|---|---|
| 抽象层次不同 | diagram 的 IR 解决「图形如何被结构化描述与布局」；document 的 IR 解决「文本内容如何与呈现分离」 |
| 生命周期不同 | drawing 已稳定并有独立基线；document 仍在建立期 |
| 失败模式不同 | 图形失败是几何/布局错误；文档失败是分页/字体/语义错误 |
| 合并代价 | 需重新校准两套基线、指标与诊断码，收益不明确 |

---

## 三、本轮实际做了什么（以及没做什么）

### 3.1 已做：document 侧对标 drawing 侧

| drawing 的先例 | document 侧的落实 | 复核 |
|---|---|---|
| 诊断带错误码与修复提示 | `validate.py` 含 code/severity/hint | `grep -c "code\|severity\|hint" scripts/document_ir/validate.py` → 26 |
| 视觉比对「不缩放」 | `visual_diff.py` 明确 pad 而非 resize | `scripts/visual_diff.py:241` 注释 `Padding rather than resizing` |
| 基线强制批准理由 | `document_baseline.py` 要求非空理由 | `grep -c approval scripts/document_baseline.py` → 11 |
| 确定性摘要快照 | `determinism.py` 用 sha256 摘要 | `grep -c sha256 scripts/determinism.py` → 5 |
| 三阶段 IR 思路 | `Document → Block[] → 渲染器` | `scripts/document_ir/model.py` |

### 3.2 未做：diagram 系统零改动

```bash
git diff --cached --name-only | grep -c "scripts/drawing"   # 0
```

**diagram 系统保持原样，其能力、基线、CI 均未受影响。**

### 3.3 一处需要说明的副作用

`build.py --verify` 会重写 `assets/diagrams/generated/png/` 下的图表产物（5 个 PNG）。这是**既有的构建行为**，本轮分析中已发现并恢复，未进入提交。

---

## 四、当前现状

### 4.1 两套系统的边界

```
                    ┌─────────────────────────────────┐
                    │         Folio 仓库              │
                    └─────────────────────────────────┘
                                   │
          ┌────────────────────────┴────────────────────────┐
          │                                                 │
   ┌──────▼──────┐                                  ┌───────▼───────┐
   │  drawing 侧  │                                  │  document 侧  │
   │ (77 个 .py)  │                                  │ (9 个顶层项)  │
   │   成熟稳定   │                                  │   本轮新建    │
   └──────┬──────┘                                  └───────┬───────┘
          │                                                 │
   SemanticDiagram                                   Document
          ↓                                                 ↓
   DrawingPlan                                       Block[]
          ↓                                                 ↓
   ResolvedScene                            ┌────────────────┴────────────────┐
          ↓                                 │                                 │
   SVG / PNG / PDF                    skeleton writer                    pptx writer
                                            ↓                                 ↓
                                      HTML → WeasyPrint              python-pptx
                                            ↓                                 ↓
                                           PDF                              PPTX

   ┌──────────────────┐                      ┌──────────────────┐
   │ catalog-baseline │                      │ document-v1      │
   │ drawing-dsl.yml  │                      │ baseline         │
   │ 24 测试文件       │                      │ nightly.yml      │
   └──────────────────┘                      │ 13 测试文件       │
                                             └──────────────────┘
        零共享代码            零共享代码            零共享代码
```

### 4.2 质量度量的覆盖范围

`scripts/fidelity.py measure` 当前**只覆盖 document 侧**：

| 覆盖 | 未覆盖 |
|---|---|
| 7 类文档 × 2 语言 = 14 target | **23 种 diagram** |
| 指标：SSIM、改变像素比、填充完整度 | diagram 有自己的指标（11 字段） |

复核：

```bash
python3 scripts/fidelity.py measure
# renders identically  7/7
# average SSIM         1.0000
```

**注意**：这里的 "7/7" 指 **7 类文档模板**，不含 diagram。这一措辞曾造成误解，本文予以澄清。

### 4.3 本轮达成的指标（document 侧）

| 项 | 结果 |
|---|---|
| 文档类型保真度 | 7/7 与模板路径 SSIM 1.0000 |
| 测试 | 729 项通过 |
| 语料 | 128 fixture（四种书写系统各 32） |
| IR fixture | 14 |
| Profile | 36 个，5 个 JSON Schema |
| 迁移就绪 | 7/8 类型（slides 无模板对照） |
| 生产路径 | `FOLIO_PIPELINE=ir`（默认），`legacy` 可回滚 |

---

## 五、待评审的问题

请评审者就以下问题给出判断：

### Q1：两套 IR 是否应当统一？

- **方案 A（当前）**：保持并列，各自独立演进
  - 依据：蓝图定位为「对标」；抽象层次、生命周期、失败模式均不同
  - 代价：两套基础设施、两套基线、两套 CI
- **方案 B**：统一为一套通用 IR
  - 收益：单一心智模型、共享诊断与基线设施
  - 代价：需重新校准全部基线与指标，drawing 侧已稳定，改动风险高
- **方案 C**：部分统一（共享诊断码、基线工具、视觉比对库）
  - 收益：消除重复实现，不触碰各自的 IR 模型
  - 代价：需引入共享层，边界需谨慎设计

### Q2：diagram 是否应纳入 fidelity 度量？

- **纳入**：统一质量视图，但 diagram 已有自己的指标与基线，可能重复
- **不纳入**：保持边界清晰，但缺少跨系统的整体质量报告

### Q3：`--verify` 重写 diagram 产物是否合理？

现状：`build.py --verify` 会重写 `assets/diagrams/generated/png/` 下 5 个 PNG，导致工作区出现**非预期改动**。

- **保持**：构建行为一致
- **修正**：让校验类操作不产生写入副作用

### Q4：文档与图表的交叉场景如何处理？

当前存在 `assets/diagrams/*.html` 作为**文档模板的图表宿主**（`drawing-hosts`），说明两者在产出层有交叉。

- 这种交叉是否需要在 IR 层表达？
- 还是保持「文档 IR 引用图表产物」的松耦合？

---

## 六、附：关键证据索引

| 结论 | 证据位置 |
|---|---|
| drawing 侧 35 模块 | `scripts/drawing/` |
| drawing 三阶段 IR | `scripts/drawing/adapters.py`、`bounds.py` |
| 两套系统零共享 | `grep -rn "from.*document_ir" scripts/drawing/` 无输出 |
| 蓝图定位为对标 | 蓝图第 15/62/113/116 行 |
| 本轮未动 drawing | `git diff --cached --name-only \| grep scripts/drawing` → 0 |
| document 侧对标落实 | `validate.py`、`visual_diff.py:241`、`document_baseline.py`、`determinism.py` |
| fidelity 覆盖范围 | `scripts/fidelity.py` 的 `GENRES` 常量 |

---

**文档位置**：`docs/architecture/diagram-vs-document-ir.md`
**生成时间**：本轮工作完成后
**复核方式**：文中每条命令均可在仓库根目录执行
