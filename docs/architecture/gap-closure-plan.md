# 缺失项实施计划

> 目的：完成接入层剩余的缺口，使已建成的模块真正产生作用，并补齐方案要求但未实现的检查。
>
> 本计划基于实测数据制定。每项都先验证可行性，再实施，再验证。

**前置状态**：`a58e2e4` + 9 个未提交文件（接入层 I-1 至 I-5 部分完成）
**分支**：`dev/document-engine`

---

## 一、缺口清单（实测）

### 模块接入状态

| 模块 | 生产接入 | 缺口 |
|---|---|---|
| `projection.py` | ✅ | — |
| `style_resolver.py` | ✅ | — |
| `build_manifest.py` | ✅ | — |
| `layout_policy.py` | ✅ | 已接入但默认关闭 |
| **`spacing.py`** | ❌ **孤立** | **P4 核心要求未满足** |
| `assets.py` | ❌ 孤立 | 哈希校验未进构建流程 |
| `diagnostics.py` | ❌ 孤立 | 注册表未在 CI 引用 |
| `language_support.py` | ❌ 孤立 | 支持报告仅 CLI |
| `corpus_matrix.py` | ❌ 孤立 | 覆盖检查仅 CLI |
| `migration.py` | ❌ 孤立 | 矩阵未接入构建决策 |

**11 个模块：4 接入、7 孤立。**

### 开关状态

| 开关 | 默认 | 状态 |
|---|---|---|
| `FOLIO_STYLE_PROJECTION` | `True` | ✅ 已切换 |
| `FOLIO_BUILD_MANIFEST` | `True` | ✅ 已切换 |
| **`FOLIO_LAYOUT_POLICY`** | **`False`** | ❌ 未切换 |

### 方案要求但未实现

| 项 | 方案出处 | 状态 |
|---|---|---|
| PDF/UA 合规检查 | §12.4 | ❌ 未实现 |
| Tagged PDF 验证 | §18 | ❌ 未实现 |
| slides 迁移 | §13 | ❌ `not-started` |
| 语料规模 | §11.1 | 150（目标 150–220） |

### 文档同步缺口

| 文档 | 缺什么 |
|---|---|
| `AGENTS.md` | 未提及 `projection.py`、`FOLIO_STYLE_PROJECTION` |
| `api-stability.md` | 未列入 `projection.py` |
| `integration-plan.md` | 未记录 POLICY 默认未切换 |

---

## 二、实测可行性验证

### V1：间距诊断是否可行 ✅

**方法**：从 PDF 提取行几何，用 `y` 坐标差分析间距。

**实测**（one-pager 第 1 页，23 行）：

```
间距升序: [10.2, 10.5, 10.7, 11.7, 13.0, 13.1, 15.4, 16.1, 17.8,
          18.5, 18.5, 20.5, 25.7, 27.2, 27.6, 28.4, 28.5, 30.9,
          35.0, 35.3, 37.3, 42.9]
基线行距: 18.5pt（最常见）
块间距:   >27pt（1.5x 基线阈值）
```

**结论**：基线行距与块间距**可清晰区分**，诊断方案可行。

### V2：CSS 变量注入是否安全 ✅

**方法**：注入变量层后对比 SSIM。

**实测**：SSIM = **1.00000**（值来自模板，属等价替换）。

### V3：margin→padding 是否等价 ❌

**实测**：SSIM = **0.90348**。

**结论**：**不做存量间距替换**。间距诊断应走「验证」而非「改写」路径。

---

## 三、实施顺序

按「零风险 → 低风险 → 需决策」排列。

### 阶段 A：间距诊断接入（零渲染风险）

**目标**：让 `spacing.py` 脱离孤立状态，作为**诊断依据**而非渲染改写。

| 步骤 | 内容 | 产物 |
|---|---|---|
| A-1 | `spacing_probe.py`：从 PDF 提取块间距 | 新脚本 |
| A-2 | 对比模板实际 gap 与 `spacing.py` 规则 | 差异报告 |
| A-3 | 接入 CI（报告 + 阈值告警） | 门禁 |
| A-4 | 测试 | 单测 ≥ 12 项 |

**为什么零风险**：**只读取产物，不修改渲染**。

**验收标准**：

| 项 | 阈值 |
|---|---|
| 能提取块间距 | 至少 3 类文档可提取 |
| 与规则可比 | 输出 declared vs observed |
| 不改变渲染 | 现有 SSIM 保持 1.0000 |
| 测试覆盖 | ≥ 12 项 |

**回滚**：纯新增文件，无回滚需求。

---

### 阶段 B：文档同步（零代码风险）

| 步骤 | 内容 |
|---|---|
| B-1 | `AGENTS.md` 补充 `projection.py`、两个开关、`document_build.py` |
| B-2 | `api-stability.md` 列入 `projection.py`（Public stable） |
| B-3 | `integration-plan.md` 记录 POLICY 默认状态与理由 |
| B-4 | 新增 `docs/architecture/integration-status.md` 汇总接入状态 |

**验收**：文档中的每条声明都能用命令复现。

---

### 阶段 C：孤立模块接入 CI（低风险）

| 步骤 | 模块 | 门禁 |
|---|---|---|
| C-1 | `assets.py check` | 资产哈希有效 |
| C-2 | `corpus_matrix.py gaps` | 无覆盖盲区 |
| C-3 | `language_support.py report` | 输出可读 |
| C-4 | `migration.py matrix` | 已在 CI |

**验收**：CI 步骤数增加，且本地可复现。

---

### 阶段 D：`FOLIO_LAYOUT_POLICY` 默认切换（需决策）

**当前**：`default=False`，但灰度验证 7/7 PASS。

| 步骤 | 内容 | 验证 |
|---|---|---|
| D-1 | 改为 `default=True` | — |
| D-2 | 重跑 7 类灰度 | SSIM ≥ 0.999 |
| D-3 | 验证回滚 | `=off` 有效 |

**依据**：`break-after: avoid` / `break-inside: avoid` 是**保守规则**，且已验证不退步。

**风险**：低。但**需你确认**是否切换。

---

### 阶段 E：PDF/UA 检查（独立工作量）

**前提**：需要外部验证器。先探测可用性。

| 步骤 | 内容 |
|---|---|
| E-1 | 探测 `veraPDF` / `pdfua` 工具可用性 |
| E-2 | 若可用：接入 `quality_vector` 的新维度 |
| E-3 | 若不可用：在 `quality_vector` 标注 `not_measured` 并说明原因 |
| E-4 | 报告 PDF 结构事实（bookmarks、tags、lang） |

**诚实处理**：无法验证时**明确标注**，而非默认通过。

---

### 阶段 F：语料扩容（可选）

**当前** 150（目标 150–220）。

| 步骤 | 内容 |
|---|---|
| F-1 | 按矩阵补至 180+ |
| F-2 | 优先补 `below-target` 类 |

**优先级最低** —— 当前每类已有 fixture，扩容是边际改善。

---

## 四、验证体系

### 每阶段的四层验证

| 层 | 方法 | 阈值 |
|---|---|---|
| L1 结构 | 页数 + 字体 | 精确 |
| L2 视觉 | SSIM | ≥ 0.999 |
| L3 语义 | 文本提取 | 无丢失 |
| L4 门禁 | 全量门禁 | 全绿 |

### 每阶段必跑命令

```bash
python3 -m unittest discover -s tests --buffer
ruff check .
python3 scripts/corpus.py validate
python3 scripts/document_baseline.py compare
python3 scripts/assets.py check
python3 scripts/projection.py check
python3 scripts/diagnostics.py check
python3 scripts/fidelity.py measure          # 7/7 SSIM 1.0000
```

### 新增验证（本计划）

| 验证 | 阶段 | 方法 |
|---|---|---|
| 间距提取准确 | A | 对比已知模板值 |
| 文档声明可复现 | B | 逐条运行文档中的命令 |
| CI 步骤可本地跑 | C | 每个门禁单独执行 |
| 策略切换不退步 | D | 7 类灰度 |
| PDF/UA 状态诚实 | E | 工具不可用则标 `not_measured` |

---

## 五、风险矩阵

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| 间距诊断误报 | **中** | 低 | 只报告不阻断 |
| 文档与代码不一致 | 中 | 中 | 每条声明附命令 |
| CI 步骤失败 | 低 | 中 | 本地先验证 |
| 策略切换退化 | **低** | 高 | 7 类灰度 + 回滚 |
| PDF/UA 工具不可用 | **高** | 低 | 标注 `not_measured` |
| 语料扩容引入无效 fixture | 中 | 低 | `corpus.py validate` |

---

## 六、交付里程碑

| 里程碑 | 完成标志 | 验证 |
|---|---|---|
| **M-A** | 间距诊断可用 | 能提取并对比 gap，渲染不变 |
| **M-B** | 文档同步 | 声明可复现 |
| **M-C** | CI 覆盖孤立模块 | 步骤数增加且本地可跑 |
| **M-D** | POLICY 默认切换 | 7/7 灰度通过 |
| **M-E** | PDF/UA 状态明确 | 要么检查，要么明确标注 |
| **M-F** | 语料扩容（可选） | ≥ 180 |

---

## 七、执行原则

1. **先验证可行性，再实施** —— 每阶段开始前用命令确认前提
2. **每阶段独立可回滚** —— 或纯新增（无回滚需求）
3. **不伪造能力** —— 无法验证的标 `not_measured`
4. **文档与代码同步** —— 改代码必须改文档
5. **每阶段完成后跑全量门禁**
