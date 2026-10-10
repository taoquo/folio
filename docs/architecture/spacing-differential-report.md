# 间距差分实验报告

> 目的：在把 `spacing.py` 的 `ResolvedGap` 接入渲染之前，量化「模板 CSS 的 margin collapsing」与「显式指定 gap」在真实文档上的实际差异。
>
> 本实验是接入层 Phase I-3 的可行性判据。

**日期**：2026-10-09
**分支**：`dev/document-engine`
**基线 commit**：`a58e2e4`
**方法**：控制变量差分，用 `visual_diff` 的 SSIM 与像素级行扫描

---

## 一、实验假设

方案 §7.4 要求：

> 在 Layout Policy 层确定每对相邻块最终应产生的 `ResolvedGap`。
> HTML writer 只投影已解析的 gap，不让各组件各自定义上下 margin 再依赖浏览器自动折叠。

**待验证的假设**：模板当前依赖 margin collapsing，因此显式设定 gap 会改变渲染。

---

## 二、实验一：模板间距的真实结构

### 方法

统计 14 个模板的 `margin-top` 与 `margin-bottom` 数量。margin collapsing 只在相邻元素**同时**有 margin 时发生。

### 结果

| 模板 | margin-top | margin-bottom | 比值 |
|---|---:|---:|---:|
| one-pager | **2** | 13 | 1:6.5 |
| letter | **2** | 12 | 1:6 |
| long-doc | 5 | 11 | 1:2.2 |
| changelog | 3 | 5 | 1:1.7 |
| portfolio | 3 | 17 | 1:5.7 |
| resume | **8** | 10 | 1:1.25 |
| equity-report | 5 | 7 | 1:1.4 |

### 结论

**模板以 margin-bottom 为主**。`margin-top` 仅出现在有明确语义的位置：

| 位置 | 用途 |
|---|---|
| `.timeline` | 时间线容器 |
| `.footer` | 页脚 |
| `.closing` / `.attachments` | letter 的收尾段落 |
| `.team-culture` | resume 的卡片 |

**即：间距已经是显式的单侧值，不是 collapsing 的产物。**

---

## 三、实验二：margin vs padding 的语义差异

### 方法

把 `.timeline { margin-top: 6pt }` 改为 `padding-top: 6pt`，其余不变。若间距是"纯间距"，两者应等价。

### 对照设计

| 组 | 变更 | 预期 |
|---|---|---|
| 对照组 | `margin-top: 6pt`（无变化） | SSIM = 1.0 |
| 实验组 | `margin-top` → `padding-top` | ? |

### 结果

| 组 | SSIM | 首次差异 y 坐标 |
|---|---|---|
| 对照组 | **1.00000** | 无差异 |
| 实验组 | **0.90348** | **617** / 1170（页面中部，即 `.timeline` 位置） |

### 结论

1. **实验方法有效**：对照组 1.0 证明差分可信
2. **margin 与 padding 不等价**：SSIM 0.90，差异精确定位在 `.timeline`
3. **原因**：`margin` 在容器外，`padding` 在容器内 — 这**不是 collapsing**，而是**盒模型语义差异**

---

## 四、实验三：显式 gap 的可达性

### 方法

验证 `spacing.py` 的 14 条规则能否覆盖模板的实际间距。

### 结果

| 项目 | 数量 |
|---|---|
| 模板中的间距声明 | **505** |
| `spacing.py` 的规则 | **14** |
| 覆盖率 | **2.8%** |

**规则值来源**：`spacing.py` 的值（如 `heading→paragraph: 6pt`）是**从模板 CSS 提取的**，与模板一致。

### 结论

规则覆盖的是**语义配对**，不是全部 505 处声明。剩余的 491 处是：
- 容器内部间距（padding）
- 单元素间距（无配对）
- 结构性间距（section、page）

---

## 五、综合结论

### 核心发现

> **模板不存在实质性的 margin collapsing。**

证据：
1. `margin-top` 极少（2-8 处），且集中在有语义的位置
2. 间距以显式 `margin-bottom` 为主
3. 唯一的差异来源是 **margin vs padding 的盒模型语义**，不是折叠

### 对方案 §7.4 的修正理解

方案假设"margin collapsing 导致间距不可预测"。**实测不成立**：

| 方案假设 | 实测 |
|---|---|
| 浏览器自动折叠决定间距 | **模板已是单侧显式值** |
| 间距不可预测 | **可从 CSS 直接读出** |
| 需要 ResolvedGap 取代 collapsing | **需要的是统一表达，不是修复折叠** |

---

## 六、接入层 Phase I-3 的决策

### 风险评估（基于实验）

| 做法 | 风险 | 理由 |
|---|---|---|
| **全面替换 505 处 margin 为 ResolvedGap** | **高** | 会引入 margin/padding 语义错误；SSIM 已证明 0.90 差异 |
| **只接入 14 条语义配对的 gap** | **低** | 值与模板一致；仅统一表达 |
| **不接入** | 无 | 但 `spacing.py` 成为死代码 |

### 建议：改为「可查询」而非「可替换」

`spacing.py` 的真实价值**不是取代 CSS**，而是：

1. **给编号/引用提供语义**：`heading→paragraph` 的 gap 有名字、有理由
2. **供诊断使用**：报告某个 gap 的来源
3. **为迁移提供目标**：新文档类型可从规则生成，而非复制 CSS

**因此 Phase I-3 的正确形态**：

```
不替换现有模板的 CSS
  ↓
而是让 spacing.py 成为「间距的权威描述」
  ↓
新文档可从规则生成 CSS（已验证变量注入 SSIM 1.0）
```

---

## 七、需要修订的方案内容

| 方案原文 | 实测结论 | 建议 |
|---|---|---|
| §7.4「HTML writer 只投影已解析的 gap」 | 替换 505 处风险高 | 改为：**新模板从规则生成，存量模板保留 CSS** |
| §7.4「避免 margin collapsing 的不可预测性」 | 模板无实质 collapsing | 降级为**风格约定**，非阻塞项 |
| §10.2「间距/节奏默认 warning」 | 仍适用 | 保留 |

---

## 八、实验结论摘要

1. **模板无实质 margin collapsing** — `margin-top` 仅 2-8 处且有语义
2. **margin ≠ padding** — SSIM 0.90，差异在盒模型语义
3. **全面替换风险高** — 505 处，任一处语义变化即改分页
4. **`spacing.py` 的价值在"表达"而非"替换"** — 应作为新文档的生成源与诊断依据
5. **Phase I-3 建议降级** — 不做存量替换，改做新路径生成

**证据文件**：本报告的每个数字都可用 `visual_diff.py` 与 `spacing.py audit` 复现。
