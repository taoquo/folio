# 主路径接入计划

> 处理最后一项架构问题：`assets/examples/` 由 `build.py` 的模板路径生成，**不经过 IR**。
>
> 本计划有前置测绘、边界定义、分步实施、验证与回滚。

**分支**：`dev/document-engine`
**起点**：`5fdf819`（906 测试通过，架构检查 0 error）

---

## 一、问题陈述

| 路径 | 引用 IR | 引用 renderer | 产出 |
|---|---|---|---|
| `build.py` | ❌ **0** | ✅ | `assets/examples/`、图表、PPTX |
| `document_build.py` | ✅ 17 | ✅（本轮接入） | 成品文档 |

**后果**：用户看到的示例（README、demo 截图）走的是**不经过语义模型**的路径。

---

## 二、前置测绘（已完成）

### build.py 的职责

| 职责 | 目标数 | 是否属于文档引擎 |
|---|---|---|
| **文档模板渲染** | **14** | ✅ 是 |
| 图表模板渲染 | ~20 | ❌ 否（图表 DSL） |
| 图表产物 | ~20 | ❌ 否 |
| PPTX 幻灯片 | 若干 | ⚠️ 部分（IR 有 pptx writer） |
| 首页集成 | 若干 | ❌ 否 |

**文档模板清单**（`page_contracts.HTML_TARGETS`）：

```
zh: one-pager, letter, long-doc, portfolio, resume
en: one-pager-en, letter-en, long-doc-en, portfolio-en, resume-en
    equity-report, equity-report-en, changelog, changelog-en
```

### 当前示例的状态

| 示例 | 未填充占位符 |
|---|---|
| one-pager | **36** |
| resume | **120** |
| long-doc | **53** |

**这是关键事实**：现有示例**保留占位符**（模板自身可渲染，用于展示结构）。

---

## 三、核心矛盾

### 两种「示例」的定义不同

| 定义 | 当前做法 | IR 做法 |
|---|---|---|
| **模板示例** | 模板原样渲染，占位符可见 | 不适用 |
| **成品示例** | 不产出 | 填充内容后渲染 |

**如果直接把 `build.py` 改成走 IR**：

- 示例外观**改变**（占位符消失、内容出现）
- README 与 demo 截图**全部失效**
- `--verify` 的页数契约**可能改变**

### 因此不能简单替换

---

## 四、方案：双轨产出

### 设计

| 目标 | 现在 | 改后 |
|---|---|---|
| `assets/examples/*.pdf` | 模板渲染（保留占位符） | **不变** |
| `assets/examples/structured/*.pdf` | — | **新增**：IR 渲染的成品 |

**理由**：

1. 模板示例有**独立价值** —— 它展示结构、供设计参考、可单独渲染
2. 成品示例是**新增能力** —— 它证明引擎端到端可用
3. 两者不冲突，各有用途

### 具体做法

| 步骤 | 内容 |
|---|---|
| 1 | `build.py` 增加 `IR_TARGETS`，指向文档类型 |
| 2 | 新增 `build_structured(name)`：调用 `document_build.build` |
| 3 | `build_all()` 同时产出两轨 |
| 4 | `build.py` 顶层 import `document_build` —— **满足可达性检查** |
| 5 | `--verify` 校验两轨的页数契约 |

---

## 五、实施步骤

### 阶段 1：建立调用（最小改动）

| 步骤 | 内容 | 验证 |
|---|---|---|
| 1.1 | `build.py` import `document_build` | import 成功 |
| 1.2 | 新增 `build_structured(name)` | 单类型可构建 |
| 1.3 | 输出到 `assets/examples/structured/` | 文件存在 |
| 1.4 | 加入 `build_all()` | `build.py` 全量可跑 |

**验收**：`build.py` 产出 14 个成品示例，页数符合契约。

### 阶段 2：架构检查覆盖

| 步骤 | 内容 | 验证 |
|---|---|---|
| 2.1 | `architecture.py` 的 `REQUIRED_CALLS["scripts/build.py"]` 加 `document_ir` | 检查通过 |
| 2.2 | 加测试断言 | 测试通过 |

**验收**：`architecture.py check` 0 error，且新增检查项。

### 阶段 3：验证体系

| 步骤 | 内容 | 验证 |
|---|---|---|
| 3.1 | 两轨页数契约分别校验 | `--verify` 通过 |
| 3.2 | 成品示例的 IR 校验 | validator 无 error |
| 3.3 | 模板示例**不变** | SSIM 1.00000 |

**验收**：
- 模板示例：与改前**完全一致**（SSIM 1.00000）
- 成品示例：页数符合契约，validator 通过

### 阶段 4：文档与 CI

| 步骤 | 内容 |
|---|---|
| 4.1 | `AGENTS.md` 说明两轨的区别 |
| 4.2 | CI 增加成品示例的构建 |
| 4.3 | `census.py` 增加检查项 |

---

## 六、验证设计

### 三层验证

| 层 | 对象 | 方法 | 阈值 |
|---|---|---|---|
| **L1 不退化** | 模板示例 | SSIM vs 改前 | **1.00000** |
| **L2 正确性** | 成品示例 | 页数契约 | 精确 |
| **L3 语义** | 成品示例 | validator | 0 error |

### 关键验证：模板示例必须完全不变

**这是硬约束**。改动只应**新增**产物，不应修改已有产物。

```bash
# 改前
cp -r assets/examples /tmp/before
# 改后
python3 scripts/build.py
python3 scripts/visual_diff.py /tmp/before/one-pager.pdf assets/examples/one-pager.pdf
# 断言 SSIM 1.00000
```

### 新增测试

| 测试 | 内容 |
|---|---|
| `test_build_structured` | 成品示例可构建，页数正确 |
| `test_templates_unchanged` | 模板示例与基线一致 |
| `test_architecture_reachability` | `build.py` 引用 `document_ir` |
| `test_ir_input` | `--ir` 路径可用（已有） |

---

## 七、风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| 模板示例外观改变 | **中** | **高** | 双轨产出，不动原路径 |
| 构建时间增加 | 高 | 低 | 成品示例可并行或按需 |
| 页数契约冲突 | 中 | 中 | 两轨各自校验 |
| `build.py` 复杂度上升 | 中 | 中 | 新逻辑独立函数 |
| CI 时间超限 | 中 | 中 | 成品示例放 nightly |

---

## 八、回滚

| 层级 | 方式 |
|---|---|
| 单类型 | 从 `IR_TARGETS` 移除 |
| 全部 | 删除 `assets/examples/structured/` |
| 代码 | `build_structured` 独立，删除即可 |

**模板路径完全不受影响** —— 这是双轨设计的核心价值。

---

## 九、明确的「不做」

| 不做 | 理由 |
|---|---|
| 替换模板示例为 IR | 会改变 README、demo、页数契约 |
| 强制 `build.py` 只走 IR | 图表、PPTX、首页集成不属于文档引擎 |
| 改动现有 `assets/examples/*.pdf` | 硬约束：只新增，不修改 |

---

## 十、里程碑

| 里程碑 | 完成标志 | 验证 |
|---|---|---|
| **M-1** | `build.py` 调用 `document_build` | 架构检查通过 |
| **M-2** | 14 个成品示例产出 | 文件存在且页数正确 |
| **M-3** | 模板示例不变 | SSIM 1.00000 |
| **M-4** | 检查覆盖 | `census` 通过率不降 |
| **M-5** | 全量绿 | 906+ 测试、8 门禁 |
