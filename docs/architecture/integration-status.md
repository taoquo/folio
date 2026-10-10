# 接入状态

> 每个模块**是否在生产路径中被使用**，以及它接入的方式。
>
> 建成不等于接入。一个只被测试引用的模块不产生任何作用，这份文档的存在是为了让那种状态可见。

**分支**：`dev/document-engine`
**复核方式**：文中每条判定都可用附带的命令复现

---

## 一、接入判定

| 模块 | 生产接入 | 接入方式 |
|---|---|---|
| `document_ir/` | ✅ | `document_build.py` 构建 IR 并渲染 |
| `projection.py` | ✅ | `document_build.py` 注入样式与策略 |
| `style_resolver.py` | ✅ | 被 `projection.py` 调用 |
| `layout_policy.py` | ✅ | 被 `projection.py` 调用（默认关闭） |
| `build_manifest.py` | ✅ | `document_build.py` 写出 manifest |
| `fidelity.py` | ✅ | 度量工具，对比两条路径 |
| `pipeline.py` | ✅ | `document_build.py` 读取路径选择 |
| `spacing.py` | ⚠️ **诊断** | 被 `spacing_probe.py` 用于对比，**不改写渲染** |
| `spacing_probe.py` | ⚠️ **诊断** | 读产物、比对规则，**不参与渲染** |
| `assets.py` | ❌ 仅 CLI | 未进构建流程 |
| `diagnostics.py` | ❌ 仅 CLI | 注册表未被 CI 引用 |
| `language_support.py` | ❌ 仅 CLI | 支持报告未被消费 |
| `corpus_matrix.py` | ❌ 仅 CLI | 覆盖检查未被消费 |
| `layout_experiment.py` | ❌ 仅 CLI | 一次性实验工具 |
| `migration.py` | ❌ 仅 CLI | 矩阵未接入构建决策 |

复核：

```bash
grep -rlE "from (document_ir\.)?projection import|import projection" scripts/document_build.py
grep -rl "import spacing" scripts/document_build.py scripts/projection.py
```

---

## 二、为什么 `spacing.py` 是诊断而非改写

原计划要求 HTML writer 只投影已解析的 `ResolvedGap`。实测后改为诊断，理由有三：

| 发现 | 证据 |
|---|---|
| 模板无实质 margin collapsing | `margin-top` 仅 2–8 处且有语义 |
| margin 与 padding 不等价 | 替换一处后 SSIM **0.90348** |
| 全面替换风险高 | 505 处声明，任一语义变化即改分页 |

**因此 `spacing.py` 的价值是「表达与验证」**：

```bash
python3 scripts/spacing_probe.py compare --genre one-pager
# 9/14 rule(s) match a gap on the page
```

一个规则若不再匹配模板，会**显示出来**，而不是被静默套用。

---

## 三、开关与默认值

| 开关 | 默认 | 作用 | 回滚验证 |
|---|---|---|---|
| `FOLIO_PIPELINE` | `ir` | 选择构建路径 | `=legacy` |
| `FOLIO_STYLE_PROJECTION` | **on** | 投影解析后的样式 | `=off` |
| `FOLIO_LAYOUT_POLICY` | **off** | 投影 keep/break 规则 | `=off`（默认即关） |
| `FOLIO_BUILD_MANIFEST` | **on** | 写出构建 manifest | `=off` |

复核：

```bash
FOLIO_STYLE_PROJECTION=off python3 scripts/document_build.py build --genre one-pager --lang zh --out /tmp/off
python3 scripts/document_build.py build --genre one-pager --lang zh --out /tmp/on
python3 scripts/visual_diff.py /tmp/off/*.pdf /tmp/on/*.pdf   # SSIM 1.00000
```

---

## 四、验证证据

| 项 | 结果 | 命令 |
|---|---|---|
| 测试 | 847 通过 | `python3 -m unittest discover -s tests --buffer` |
| 保真度 | 7/7，SSIM 1.0000 | `python3 scripts/fidelity.py measure` |
| 投影 | SSIM 1.00000，页数一致 | 见上 |
| 灰度 | 7/7 PASS | `FOLIO_LAYOUT_POLICY=on` 逐类构建 |

---

## 五、已知缺口

| 缺口 | 状态 | 影响 |
|---|---|---|
| PDF/UA 合规检查 | 未实现 | 无法声称 PDF/UA 符合 |
| Tagged PDF 验证 | 未实现 | 同上 |
| slides 迁移 | `not-started` | PPTX 无模板对照路径 |
| 语料规模 | 150（目标 150–220） | 达下限 |
| `assets.py` 未进构建 | 仅 CLI | 资产哈希未在构建时校验 |

---

## 六、这份文档如何保持准确

接入状态**会随代码变化**。判定方法固定为一条命令：

```bash
# 某模块是否被生产路径引用
grep -rl "<module>" scripts/document_build.py scripts/projection.py scripts/document_ir/ scripts/build.py
```

新增模块时，应同时更新本表；否则本表会变成一份过时的声明，而它存在的意义正是不让「建成但未接入」被忽略。
