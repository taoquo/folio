# 方案 B：示例统一走 IR

> 把 `assets/examples/` 的文档示例改为 IR 渲染的成品，**取消双轨**。
>
> 目标：用户看到的示例与引擎的实际能力一致。

**分支**：`dev/document-engine`
**起点**：`5fdf819`
**决策**：用户选择方案 B（统一），而非双轨

---

## 一、影响面测绘（已完成）

### 谁引用 `assets/examples/`

| 引用者 | 用途 | 影响 |
|---|---|---|
| `references/production.md` | 运行手册提到路径 | 需更新说明 |
| `tests/test_build.py` | 断言示例存在与页数 | 需更新期望 |
| `.github/workflows/drawing-dsl.yml` | 构建与校验 | 可能需调整 |
| **README.md / README.zh-CN.md** | **不引用** | **无影响** |
| `assets/demos/demo-*.png` | **独立来源** | **无影响** |

**关键发现**：README 与 demo 图**都不依赖** `assets/examples/`。

**这使方案 B 的风险远低于最初估计。**

### 15 个文档示例的当前状态

| 示例 | 占位符数 | 说明 |
|---|---|---|
| one-pager | 36 | 模板示例 |
| letter | 18 | 同 |
| resume | 120 | 同 |
| portfolio | 50 | 同 |
| long-doc | 53 | 同 |
| equity-report | 71 | 同 |
| changelog | 22 | 同 |
| 英文 7 个 | 15–117 | 同 |

**全部是模板示例（保留占位符）。**

---

## 二、目标状态

| 目标 | 现在 | 改后 |
|---|---|---|
| `assets/examples/one-pager.pdf` | 模板 + 占位符 | **IR 成品** |
| `assets/examples/one-pager-en.pdf` | 同 | **IR 成品** |
| 图表/PPTX 示例 | 不变 | 不变 |

**每个文档示例都有真实内容，与 `document_build` 的产出逻辑一致。**

---

## 三、内容从哪来

### 问题

示例需要**真实内容**，而 `references/fixtures/document/canonical/` 的 fixture 是给测试用的通用文本（如 `balanced-digits-letter-04`）。

### 方案：专用展示 fixture

新建 `references/fixtures/document/showcase/`，每个文档类型一个 fixture，内容是**为展示编写**的。

| 类型 | fixture | 内容 |
|---|---|---|
| one-pager | `showcase-one-pager-zh.yaml` | 中文产品方案 |
| one-pager-en | `showcase-one-pager-en.yaml` | 英文产品提案 |
| letter | `showcase-letter-zh.yaml` | 中文商务信函 |
| ... | ... | ... |

**为什么不用 canonical**：canonical fixture 的文本是为覆盖边界（数字、标点、混排）而设计，读起来像测试数据，不适合作为展示。

---

## 四、实施步骤

### 阶段 1：建立展示内容

| 步骤 | 内容 | 验证 |
|---|---|---|
| 1.1 | 新建 `showcase/` 目录 | 目录存在 |
| 1.2 | 编写 15 个 fixture（14 文档 + 1 备用） | `corpus.py validate` 通过 |
| 1.3 | 每个 fixture 通过 IR 校验 | `validate.py` 0 error |

**样本量考虑**：15 个 fixture 内容需手工编写，这是本方案**主要工作量**。

### 阶段 2：改造 `build.py`

| 步骤 | 内容 | 验证 |
|---|---|---|
| 2.1 | `build_html` 对**文档类型**改调 `document_build` | 单类型产出正确 |
| 2.2 | 图表类型保持模板路径 | 图表产出不变 |
| 2.3 | 顶层 import `document_build` | 架构检查通过 |
| 2.4 | `build_all()` 全量可跑 | 无失败 |

**关键区分**：

```python
# 文档类型 -> IR
if name in HTML_TARGETS:
    outcome = document_build.build(fixture, output)

# 图表 -> 模板（不变）
else:
    render_html_to_pdf(source, base, out)
```

### 阶段 3：更新引用

| 步骤 | 内容 |
|---|---|
| 3.1 | `references/production.md` 说明示例由 IR 生成 |
| 3.2 | `tests/test_build.py` 更新期望 |
| 3.3 | `AGENTS.md` 记录示例生成方式 |

### 阶段 4：验证与门禁

| 步骤 | 内容 |
|---|---|
| 4.1 | `architecture.py` 检查 `build.py` 走 IR |
| 4.2 | CI 更新 |
| 4.3 | `census.py` 增加检查项 |

---

## 五、验证设计

### ⚠️ 与方案 A 的关键差异

**方案 A 的硬约束「模板示例不变」在方案 B 中不成立** —— 示例**必须改变**（占位符 → 真实内容）。

**替代的验证**：

| 层 | 对象 | 方法 | 阈值 |
|---|---|---|---|
| **L1 契约** | 页数 | `page_contracts` | 精确匹配 |
| **L2 语义** | IR 校验 | `validate.py` | 0 error |
| **L3 完整性** | 占位符残留 | `--check-placeholders` | **0 个** |
| **L4 字体** | 声明字体 | `--verify` | 无未授权字体 |
| **L5 图表不变** | 图表示例 | SSIM vs 改前 | 1.00000 |

**L3 是最重要的新验证** —— 成品示例**不应含任何 `{{}}`**。

### 新增测试

| 测试 | 内容 |
|---|---|
| `test_examples_are_ir_built` | 示例由 `document_build` 产出 |
| `test_examples_have_no_placeholders` | 无 `{{}}` 残留 |
| `test_examples_match_page_contracts` | 页数符合契约 |
| `test_diagrams_unchanged` | 图表示例未变 |
| `test_build_reaches_ir` | 架构检查 |

---

## 六、风险

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| **页数契约不满足** | **高** | **高** | 先构建后对比，必要时调整 fixture 内容长度 |
| 展示内容编写工作量大 | **高** | 中 | 15 个 fixture，可分批 |
| 字体回退 | 中 | 中 | `--verify` 检测 |
| 图表受影响 | 低 | 高 | 路径严格区分 |
| CI 时间增加 | 中 | 低 | 示例构建本就在 CI 中 |

**最高风险是页数契约**：

| 类型 | 契约 | 风险 |
|---|---|---|
| resume | **2 页（严格）** | 内容长度需精确控制 |
| one-pager | 1 页 | 需精简 |
| letter | 1 页 | 同 |
| long-doc | 5–9 页 | 较宽松 |
| portfolio | 4–8 页 | 较宽松 |

**resume 的 2 页硬约束**是最难的部分。

---

## 七、实施顺序

```
1. 展示 fixture（15 个）        ← 主要工作量
   ↓
2. build.py 改造（路径分离）
   ↓
3. 逐类型验证页数契约
   ↓
4. 更新引用与文档
   ↓
5. 全量验证
```

**建议按类型逐个推进**，每完成一个类型验证一次：

```
changelog (1-2 页，简单)
  → one-pager (1 页)
    → letter (1 页)
      → equity-report (2-3 页)
        → portfolio (4-8 页)
          → long-doc (5-9 页)
            → resume (2 页严格，最难)
```

---

## 八、回滚

| 层级 | 方式 |
|---|---|
| 单类型 | 从 `IR_TARGETS` 移除，恢复模板路径 |
| 全部 | `git revert` 该 commit |
| 内容 | fixture 独立，删除即可 |

**注意**：方案 B **没有双轨的天然隔离**，回滚依赖 git。因此实施应在**独立 commit** 中完成。

---

## 九、明确的「不做」

| 不做 | 理由 |
|---|---|
| 保留模板示例 | 用户明确要求统一 |
| 双轨产出 | 同上 |
| 改动图表示例 | 图表不属于文档引擎 |
| 用 canonical fixture 作展示 | 文本为测试设计，不像真实文档 |

---

## 十、里程碑

| 里程碑 | 完成标志 | 验证 |
|---|---|---|
| **M-1** | 15 个展示 fixture | `corpus.py validate` 通过 |
| **M-2** | `build.py` 文档类型走 IR | 架构检查通过 |
| **M-3** | 页数契约全部满足 | `--verify` 通过 |
| **M-4** | 无占位符残留 | `--check-placeholders` 通过 |
| **M-5** | 图表不变 | SSIM 1.00000 |
| **M-6** | 全量绿 | 906+ 测试、8 门禁 |

---

## 十一、工作量估计

| 阶段 | 工作量 | 说明 |
|---|---|---|
| 展示 fixture | **最大** | 15 个 × 真实内容 |
| `build.py` 改造 | 小 | 路径分离 |
| 页数调优 | **中** | 尤其 resume |
| 引用更新 | 小 | 3 处 |
| 验证 | 小 | 复用现有工具 |
