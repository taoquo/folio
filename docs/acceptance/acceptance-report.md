# 验收报告（临时）

> 目的：让「改动效果」可以被感性判断，而不只是数字。
>
> 左栏**现状**：模板字符串替换（`FOLIO_PIPELINE=legacy`）
> 右栏**新引擎**：Document IR + skeleton writer（`FOLIO_PIPELINE=ir`）

**生成时间**：2026-10-09
**分支**：`dev/document-engine`

## 交付物

| 文件 | 内容 |
|---|---|
| **`docs/acceptance/comparison.html`** | **逐类逐页对照页**，52 张内嵌图，可直接打开 |
| `assets/demos/acceptance-side-by-side.png` | 单页总览图 |
| `scripts/build_acceptance_page.py` | 页面生成器，可复现 |

**重新生成**：

```bash
python3 scripts/build_acceptance_page.py
```

页面在 `docs/acceptance/assets/` 下缓存了每页 PNG，图已内嵌为 base64，**不需要服务器即可打开**。

---

## 一、结论先说

**7 类文档的页数与视觉完全一致（SSIM 1.00000）。**

这不是"效果好"，而是「**改引擎没有改变外观**」。

| 类别 | 页数 legacy/ir | SSIM | 像素差异 |
|---|---|---|---|
| one-pager | 1 / 1 | 1.00000 | 0.00% |
| letter | 1 / 1 | 1.00000 | 0.00% |
| resume | 4 / 4 | 1.00000 | 0.00% |
| changelog | 2 / 2 | 1.00000 | 0.00% |
| long-doc | 7 / 7 | 1.00000 | 0.00% |
| portfolio | 6 / 6 | 1.00000 | 0.00% |
| equity-report | 5 / 5 | 1.00000 | 0.00% |

**复核命令**：

```bash
python3 scripts/document_build.py compare --genre one-pager --lang zh --keep /tmp/c
```

---

## 二、这意味着什么

### 好的方面

| 含义 | 说明 |
|---|---|
| **迁移无风险** | 换引擎不动视觉效果，用户无感 |
| **可回滚** | `FOLIO_PIPELINE=legacy` 随时切回 |
| **语义已就位** | IR 结构已建立，只是渲染结果与旧路径相同 |

### 需要说清的方面

| 问题 | 回答 |
|---|---|
| 那改了什么？ | **内容的组织方式**，不是外观 |
| 用户能看出区别吗？ | **不能** —— 这正是目的 |
| 有什么实际收益？ | 见第三节 |

---

## 三、实际收益（不在视觉上，在结构上）

| 能力 | 现状（legacy） | 新引擎（IR） |
|---|---|---|
| 内容模型 | HTML 字符串 | **语义节点树** |
| 可校验性 | 无 | **fail-closed validator** |
| 出处追踪 | 无 | **每节点带 source locator** |
| 产物溯源 | 无 | **build manifest** |
| 可解释性 | 无 | **style resolver 能答"为什么是这个字号"** |
| 渲染器可替换 | 否 | **是**（PPTX writer 已证明） |

**复核命令**：

```bash
python3 scripts/document_build.py build --genre one-pager --lang zh --out /tmp/x
cat /tmp/x/*.manifest.json      # 引擎、字体、提交、构建选项
```

---

## 四、验收中发现的真实问题

### 问题 1：fixture 选择器不一致（已修）

| 项 | 内容 |
|---|---|
| 现象 | `document_build` 与 `fidelity` 为同一 genre **选中不同 fixture** |
| 后果 | 对比的是**不同文档**，SSIM 显示 0.966，像是引擎差异 |
| 修复 | `document_build` 改为调用 `fidelity._fixture_for` |
| 修复后 | SSIM 恢复 **1.00000** |

**这是验收报告的价值** —— 它暴露了一个被数字掩盖的测量错误。

### 问题 2：部分 fixture 有未填充槽位

| 类别 | 未填充 | 原因 |
|---|---|---|
| letter | 3 | 中文内容渲染英文模板（无中文问候语源） |
| long-doc | 3 | 同上 |
| portfolio | 1 | 同上 |
| 其余 4 类 | 0 | — |

**这不是引擎缺陷**，而是 fixture 的语言组合问题。渲染结果仍与 legacy 一致（因为 legacy 也用同一 fixture）。

---

## 五、如何看对照图

`assets/demos/acceptance-side-by-side.png` 的每一行是一类文档：

```
[左：legacy 第 1 页]  [右：IR 第 1 页]     类别
                                          页数 legacy/ir
                                          SSIM
                                          像素差异
```

**观察方式**：

1. 两栏**看起来相同** → 符合预期
2. 数字区显示 `完全一致` → SSIM ≥ 0.999
3. 若出现 `存在差异` → 需要按 `review-protocol.md` 人工判断

---

## 六、本次验收未覆盖的内容

| 项 | 状态 |
|---|---|
| 多页文档的第 2 页及之后 | 照片只取第 1 页；页数已验证 |
| 真实用户文档（非 fixture） | 未测 |
| PDF/UA 合规 | 无验证器，`NOT_MEASURED` |
| 分页缺陷改善 | 布局策略是否**改善**缺陷，未证明（只证明不退化） |

---

## 七、一句话总结

> **新引擎没有改变文档的外观，改变的是文档的组织方式。**
>
> 视觉上 7/7 完全一致 —— 这既是「迁移安全」的证据，也说明**收益在结构层而非表现层**。
>
> 如果你期待看到「排版变好了」，本次验收**没有这个结果**，因为改动目标是架构而非视觉。

---

## 附：复核清单

```bash
# 1. 页数与保真度
python3 scripts/fidelity.py measure          # 7/7, SSIM 1.0000

# 2. 两路径对比
python3 scripts/document_build.py compare --genre resume --lang zh

# 3. 产物溯源
python3 scripts/document_build.py build --genre changelog --lang zh --out /tmp/c
cat /tmp/c/*.manifest.json

# 4. 回滚
FOLIO_PIPELINE=legacy python3 scripts/document_build.py build --genre one-pager --lang zh --out /tmp/legacy
```
