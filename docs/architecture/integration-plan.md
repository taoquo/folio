# 接入层实施计划

> 目的：把已完成但**未接入渲染**的模型（`style_resolver.py`、`spacing.py`、`build_manifest.py`、
> `layout_policy.py`）接入 `document_build.py` 与 writer，使这些能力产生实际作用。
>
> 本计划基于《间距差分实验报告》的实测结论制定，不采用方案中未经证实的假设。

**前置状态**：`a58e2e4`（模型层完成，815 测试通过，全门禁绿）

---

## 一、为什么必须做接入

当前 10 个模块**零生产路径接入**，只被测试与 CLI 引用：

| 模块 | 能力 | 未接入的后果 |
|---|---|---|
| `style_resolver.py` | 74 个值 + 来源溯源 | 「为什么是这个字号」能回答，但与渲染无关 |
| `spacing.py` | 14 条间距规则 | 间距仍由 CSS 决定 |
| `layout_policy.py` | keep/break/float 策略 | 0 引用，完全孤立 |
| `build_manifest.py` | 构建条件指纹 | 产物不携带 provenance |

**模型层不接入，能力等于零。**

---

## 二、实测得出的三条约束

来自《间距差分实验报告》：

| # | 约束 | 证据 |
|---|---|---|
| C1 | **CSS 变量注入安全** | 注入后 SSIM = **1.00000** |
| C2 | **margin 与 padding 不等价** | 替换后 SSIM = **0.90348** |
| C3 | **模板无实质 margin collapsing** | `margin-top` 仅 2-8 处且有语义 |

**推论**：
- C1 允许**注入式**接入（不修改模板）
- C2 禁止**盲目替换**全部 505 处间距
- C3 说明间距已是显式的，接入目标应是**统一表达**而非修复折叠

---

## 三、接入策略

### 核心原则

> **注入覆盖层，不修改模板；增量接入，每步可回滚。**

```
模板 CSS（不动）
    ↓
+ 注入的变量层（resolver 提供值）
    ↓
+ 注入的策略层（layout_policy 提供 keep/break）
    ↓
渲染
```

### 与方案原文的差异（及理由）

| 方案原文 | 本计划 | 理由 |
|---|---|---|
| 「HTML writer 只投影已解析的 gap」 | **新路径生成 + 存量保留 CSS** | 实测：全面替换 SSIM 0.90，风险高 |
| 「避免 margin collapsing」 | 降级为风格约定 | 实测：模板无实质 collapsing |
| 一次性迁移 | **逐类型灰度** | 方案 §13 本身要求 |

---

## 四、阶段划分

### Phase I-1：投影基础设施（无行为变更）

**目标**：建立注入机制，注入空内容时渲染结果不变。

| 步骤 | 产物 | 验证 |
|---|---|---|
| I-1.1 | `projection.py`：resolver 值 → CSS 变量块 | 单测：74 值 → 合法 CSS |
| I-1.2 | `projection.py`：layout_policy → 覆盖规则 | 单测：策略 → 有效选择器 |
| I-1.3 | `skeleton.py` 增加 `inject_css: str = ""` 参数 | 默认空 |
| I-1.4 | `document_build.py` 增加 `FOLIO_STYLE_PROJECTION` 开关 | 默认 `off` |

**验收标准**：

```bash
# 注入空块，SSIM 必须为 1.0
FOLIO_STYLE_PROJECTION=off python3 scripts/document_build.py build --genre one-pager
# 对比注入前后的 PDF
python3 scripts/visual_diff.py before.pdf after.pdf
# 断言: SSIM == 1.00000
```

**回滚**：无需（默认关闭）

---

### Phase I-2：样式值与 provenance 接入

**目标**：让 `style_resolver` 的值**真实影响渲染**，且产物携带构建条件。

| 步骤 | 内容 | 验证 |
|---|---|---|
| I-2.1 | 注入字号/行高变量（`--body-size`、`--body-leading`） | SSIM ≥ 0.999 |
| I-2.2 | 注入字族变量（`--serif` 等已有变量，复用） | SSIM = 1.0（值相同） |
| I-2.3 | 产物写出 `build-manifest.json` | 文件存在且字段完整 |
| I-2.4 | parity 检查 | 页数一致 |

**验收标准**：

| 项 | 阈值 |
|---|---|
| SSIM（对比未注入） | ≥ 0.999 |
| 页数 | 完全一致 |
| 文本提取 | 无丢失 |
| manifest | 含 commit / renderer / fonts / fingerprint |

**回滚**：`FOLIO_STYLE_PROJECTION=off`

**为什么安全**：resolver 的值**提取自模板**（`body.size_pt = 10` 对应 `font-size: 10pt`），注入是等价替换 → 已实测 SSIM 1.0。

---

### Phase I-3：布局策略接入（限定范围）

**目标**：让 `layout_policy` 的 keep/break 策略生效。

**范围限制**（基于实验结论）：

| 接入 | 不接入 |
|---|---|
| ✅ `keep-with-next`（标题不与正文分离） | ❌ 间距替换（505 处，风险高） |
| ✅ `break-inside: avoid`（图表/表格不切分） | ❌ margin-top/bottom 改写 |
| ✅ 分页语义（章节起始） | ❌ padding 调整 |

| 步骤 | 内容 | 验证 |
|---|---|---|
| I-3.1 | 注入 `h1,h2,h3 { break-after: avoid }` | SSIM 记录，不设阈值 |
| I-3.2 | 注入 `figure, table { break-inside: avoid }` | 同上 |
| I-3.3 | 与模板既有规则去重 | 无冲突声明 |
| I-3.4 | 分页缺陷对比（`layout_experiment`） | 缺陷数不增加 |

**验收标准**：

- 页数**不减少**（避免内容被挤出）
- `layout_experiment` 的可靠缺陷类**不增加**
- 每步独立记录 SSIM

**回滚**：`FOLIO_LAYOUT_POLICY=off`

---

### Phase I-4：逐类型灰度

**顺序**（由简到繁）：

```
1. changelog    （2 页，结构简单）
2. one-pager    （1 页，无分页）
3. letter       （1 页）
4. portfolio    （6 页）
5. equity-report（5 页）
6. long-doc     （7 页，最复杂）
7. resume       （4 页，硬页数合同）
```

**每类流程**：

```bash
# 1. 记录基线
python3 scripts/migration.py check-parity <type>

# 2. 启用投影
FOLIO_STYLE_PROJECTION=on FOLIO_LAYOUT_POLICY=on \
  python3 scripts/document_build.py build --genre <type>

# 3. 三重验证
python3 scripts/visual_diff.py <before> <after>   # SSIM
python3 scripts/fidelity.py measure --genre <type> # 与模板对比
python3 scripts/migration.py check-parity <type> --record

# 4. 通过则记录，否则回滚
```

**resume 特殊处理**：硬 2 页合同，任何分页变化**必须阻断**。

---

## 五、验证体系

### 每步必过的四层验证

| 层 | 方法 | 阈值 | 命令 |
|---|---|---|---|
| **L1 结构** | 页数 + 字体 | 精确 | `migration.py check-parity` |
| **L2 视觉** | SSIM | ≥ 0.999 | `visual_diff.py` |
| **L3 语义** | 文本提取 | 无丢失 | `fidelity.py` |
| **L4 门禁** | 全量门禁 | 全绿 | 见下 |

### 完整门禁清单

```bash
python3 -m unittest discover -s tests --buffer   # 815+ 测试
ruff check .                                      # lint
python3 scripts/corpus.py validate                # 150 fixture
python3 scripts/document_baseline.py compare      # 基线
python3 scripts/assets.py check                   # 资产
python3 scripts/diagnostics.py check              # 错误码
python3 scripts/corpus_matrix.py gaps             # 覆盖
python3 scripts/build.py --verify                 # 只读验证
```

### 新增门禁（本计划要求）

| 门禁 | 作用 | 实现 |
|---|---|---|
| `projection_check.py` | 注入的 CSS 合法且值来自 resolver | I-1 |
| SSIM 断言 | 每步视觉不退化 | I-2 起 |
| manifest 存在性 | 产物携带 provenance | I-2 |

---

## 六、风险矩阵

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| 变量注入改变渲染 | **低** | 高 | 已实测 SSIM 1.0 |
| 间距替换语义错误 | **高** | 高 | **不做存量替换**（已验证 0.90） |
| 分页变化破坏硬合同 | 中 | 高 | resume 单独阻断式验证 |
| 模板改动导致漂移 | 中 | 中 | `fidelity` 检测 |
| 灰度遗漏 | 低 | 中 | feature flag + 逐类记录 |
| 注入 CSS 与模板冲突 | 中 | 中 | `projection_check.py` 检测冲突 |

---

## 七、可回滚性设计

每个阶段有独立开关：

| 开关 | 默认 | 作用 |
|---|---|---|
| `FOLIO_STYLE_PROJECTION` | `off` | 样式值注入 |
| `FOLIO_LAYOUT_POLICY` | `off` | 布局策略注入 |
| `FOLIO_PIPELINE` | `ir` | 路径选择（已有） |

**回滚验证**：每个开关都需有测试证明关闭后渲染回到基线。

---

## 八、交付里程碑

| 里程碑 | 完成标志 | 验证 |
|---|---|---|
| **M-I1** | 注入基础设施可用 | 注入空块 SSIM = 1.0 |
| **M-I2** | 样式值与 manifest 接入 | SSIM ≥ 0.999 + manifest 存在 |
| **M-I3** | 布局策略接入 | 缺陷数不增加 |
| **M-I4** | 7 类灰度完成 | 7/7 parity + 全门禁绿 |
| **M-I5** | 默认切换 | `FOLIO_STYLE_PROJECTION=on` 为默认 |

---

## 九、执行顺序

```
I-1 (基础设施)
  → I-2 (样式 + manifest)
    → I-3 (布局策略)
      → I-4 (逐类型灰度)
        → I-5 (默认切换)
```

**每个 I-x 完成后**：
1. 运行完整门禁
2. 记录验证证据
3. 汇报后再进入下一步

**任一阶段失败**：回滚该阶段开关，记录原因，不推进。
