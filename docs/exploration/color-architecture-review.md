# 颜色架构整体梳理

> 你的判断是对的：**同一个色值要在十个地方各写一遍，说明这套「语义色彩体系」还不成立。**
>
> 本文是全仓颜色的完整地图、目标架构、以及落地顺序。所有数字来自实测。

**分支**：`dev/document-engine`
**日期**：2026-10-11

---

## 一、结论

| 问题 | 实测答案 |
|---|---|
| 全项目有多少个色值？ | **47 个**（10 个手工维护的源） |
| 有多少个独立声明点？ | **10 个** |
| 有多少色值跨源重复？ | **23 个**（49%） |
| 有多少色值出现在 **5 个以上源**？ | **9 个** |
| 有没有已经漂移的？ | **有 —— PPTX 的墨色与分隔线在别处根本不存在** |
| 现在是「配置好就到处生效」吗？ | **不是。是 10 份各自的副本，其中 1 份已经漂了** |

**`references/tokens.json` 名义上是规范源，但它只有 8 个值，而且没有任何渲染器读它 —— 它只被用来「对比」。**

---

## 二、完整地图：10 个声明点

| # | 源 | 值数 | 谁真正读它 | 性质 |
|---|---|---:|---|---|
| 1 | `references/profiles/theme/*.yaml` | 24 | **无**（解析后不投影） | 数据 |
| 2 | `references/tokens.json` | 8 | 无（只被 `build.py --sync` 对比） | 数据 |
| 3 | `assets/templates/*.html` `:root` | 18 | **WeasyPrint（权威）** | 手写 |
| 4 | `assets/diagrams/*.html` | 14 | **WeasyPrint（权威）** | 手写 |
| 5 | `index.html` / `index-zh.html` 内联 SVG | 18 | 浏览器直接打开 | **手写** |
| 6 | `assets/demos/*.html` | 20 | 浏览器直接打开 | 手写 + 部分生成 |
| 7 | `references/fixtures/hosting/*.html` | 8 | WeasyPrint | 手写 |
| 8 | `scripts/drawing/theme/folio.py` | 37 | **图表编译器** | 手写 |
| 9 | `scripts/document_ir/writers/pptx.py` `PALETTE` | 5 | **PPTX writer** | 手写 |
| 10 | `scripts/drawing/hosting.py` 内联 `RGBColor` | 1 | PPTX 图注 | 手写 |

**跨源共享**（改一处不够）：

```
#F6F0EA  8 源    #191514  8 源    #85776F  8 源
#5A4A43  7 源    #B83D2E  7 源    #FBF7F3  7 源
#E9DED4  6 源    #F7E6E1  6 源    #3A312D  5 源
```

**品牌色 `#B83D2E` 在 62 个文件里出现 169 次。**

---

## 三、一处已经发生的漂移

`scripts/document_ir/writers/pptx.py`：

```python
# The parchment palette, kept in one place. A theme profile supplies colours in
# the IR; these are the defaults when it does not.
PALETTE = {
    "canvas": "F6F0EA",
    "ink":    "24211D",      # ← 别处是 #191514
    "muted":  "85776F",
    "accent": "B83D2E",
    "rule":   "E5D9CE",      # ← 别处是 #E9DED4
}
```

实测这两个值在**其它任何源里都是 0 处**：

```
#24211D (pptx ink):  0 处
#E5D9CE (pptx rule): 0 处
```

注释说「kept in one place」—— **它确实在一处，但那是它自己的一处，与别处不同。**

**后果**：同一份内容导出 PPTX 与 PDF，墨色和分隔线颜色不一样。这正是「体系不完备」的具体形态。

---

## 四、为什么不能简单合并

我测了各源 `:root` 块的一致性：

| 类别 | 文件数 | 不同的 `:root` 变体 |
|---|---:|---:|
| 图表模板 | 14 | **6 种** |
| demo 源 | 14 | **9 种** |
| 文档模板 | 14 | **11 种** |

**不是复制粘贴。** 每个模板声明的是**自己需要的子集**，还有各自的补充。

所以正确做法不是「生成一段相同的块写进每个文件」，而是**在渲染时注入规范变量，模板只保留自己额外的东西**。

（这也解释了为什么早期把 `--sans`、`--sand` 判定为死变量是错的 —— 各模板的子集不同。）

### 三类消费者，需要两种机制

| 类别 | 例子 | 能否运行时读规范源 |
|---|---|---|
| **A. 渲染时** | 文档、图表、宿主 | ✅ 可以由 projection 注入 CSS 变量 |
| **B. 构建时** | 图表 SVG、PPTX、tokens.json | ✅ 可以在构建时读取 |
| **C. 静态发布物** | `index.html`、`demo-*.html` | ❌ **浏览器直接打开，运行时读不到 YAML** |

**C 类必须构建时生成。** 这也是 `AGENTS.md` 痛点 #8 存在的原因：图表模板改了要手工同步到首页两处 SVG，`--check-index` 只能校验两个首页之间一致，**校验不了它们与真实来源一致**。

---

## 五、目标架构

```
references/theme/<scheme>.yaml        ← 唯一事实来源
  palette:  原始色板（只被 color 层引用）
  color:    语义角色（模板只读这一层）
        │
        │  构建时生成 / 渲染时注入
        │
        ├─► 文档模板        projection 注入 CSS 变量          [A 运行时]
        ├─► 图表模板        projection 注入 CSS 变量          [A 运行时]
        ├─► 宿主模板        同上                              [A 运行时]
        ├─► Drawing 主题    由 palette/color 解析或生成        [B 构建时]
        ├─► 图表 SVG        由 Drawing 主题渲染                [B 构建时]
        ├─► PPTX PALETTE    由 color 生成（消除已发生的漂移）  [B 构建时]
        ├─► index.html      生成内联 SVG 的颜色                [C 生成]
        ├─► demo HTML       生成                               [C 生成]
        └─► tokens.json     由 palette 生成，或退休            [B 构建时]
```

**单一事实来源的定义**：不是「所有消费者运行时都读它」，而是**所有消费者的值都由它产生，且没有任何一处手工副本**。

---

## 六、逐个源的处理方案

| # | 源 | 目标机制 | 阶段 | 规模 |
|---|---|---|---|---|
| 9 | PPTX `PALETTE` | 由 theme 的 `color` 生成 | **1** | 小 |
| 10 | `hosting.py` 内联 | 读 Drawing 主题的 `olive` | **1** | 小 |
| 2 | `tokens.json` | 退休，或改为由 `palette` 生成 | 2 | 小 |
| 4 | 图表模板 | projection 注入（Phase 1 落地后） | 3 | 中 |
| 3 | 文档模板 | projection 注入（Phase 1 落地后） | 3 | 中 |
| 8 | Drawing 主题 | 从 palette 派生 12 令牌 | 4 | 中 |
| 7 | 宿主模板 | projection 注入 | 4 | 小 |
| 5 | `index.html` ×2 | **生成**，消除手工同步 | 5 | 中 |
| 6 | demo HTML | **生成** | 5 | 中 |
| 1 | theme profile | 升为两层结构（见令牌结构设计） | 6 | 中 |

**阶段 1 为什么最先做**：它已经是错的（漂移已发生），改动最小，收益立刻可见（PDF 与 PPTX 一致）。

**阶段 3 依赖修复计划 Phase 1**（颜色进投影），否则注入的变量无人读。

---

## 七、验收：一条「改一次，全部变」的测试

这是这套体系是否成立的唯一判据：

```bash
# 改 palette 里的品牌色一个值
python3 - <<'PY'
from pathlib import Path
p = Path("references/theme/folio-classic-v1.yaml")
p.write_text(p.read_text().replace('cinnabar:      "#B83D2E"', 'cinnabar:      "#1F5FEB"'))
PY

# 重建全部
python3 scripts/build.py
python3 scripts/folio.py diagram-catalog
python3 scripts/build_color_schemes.py

# 期望：以下每一处都出现新色，且没有手工步骤
#   文档 PDF        pdffonts/text 不变，页面颜色变
#   图表 PDF/SVG    颜色变
#   PPTX            颜色变
#   index.html      内联 SVG 颜色变
#   demo HTML       颜色变
#   对比页          颜色变

# 反向检查：旧色不应残留
grep -c "B83D2E" assets/**/*.pdf 2>/dev/null    # 应为 0
```

**今天这条测试会失败**：改 theme profile，PDF 字节不变（审计实验 1）。

---

## 八、这暴露的更深问题

不只是颜色。同样的形态在别处也有：

| 领域 | 症状 |
|---|---|
| 字体 | 已统一（57 个产物无系统字体依赖），但**字体栈仍写在 32 处模板字面值里** |
| 页数契约 | ✅ 已单一来源（`page_contracts.py`） |
| 图表几何 | `index.html` 与 `assets/diagrams/*.html` 手工同步（痛点 #8） |
| 排版度量 | profile 解析后不投影（审计） |

**共同模式**：**「值」写在多个地方，「意图」只在 профиль 里，两者之间没有生成关系。**

而仓库里已经有一个做对了的例子：`page_contracts.py` 是单一来源，被 `build.py` 与 `stabilize.py` 共同消费 —— 所以页数契约不会漂移。

**目标就是把颜色变成第二个 `page_contracts.py`。**

---

## 九、与前面四份设计的关系

这五份文档是同一件事的不同层次：

| 文档 | 回答 | 层次 |
|---|---|---|
| `color-font-support-audit.md` | 现在为什么不生效 | 诊断 |
| **`color-architecture-review.md`（本文）** | **整体是什么状态、目标是什么** | **全景** |
| `color-scheme-storage-design.md` | 色系存哪里、怎么扩展 | 存储 |
| `color-token-structure-design.md` | 令牌怎么分层、怎么命名 | 结构 |
| `color-font-remediation-plan.md` | 怎么让它真正到达页面 | 执行 |

**本文是其余四份的框架。** 之前四份各自正确，但缺一张全景图说明它们如何拼在一起。

---

## 十、待你决定

| # | 问题 | 选项 | 倾向 |
|---|---|---|---|
| 1 | 规范源放哪 | 现有 `references/profiles/theme/` / 新建 `references/theme/` | **现有位置**，不新建目录 |
| 2 | `tokens.json` 去留 | 退休 / 改为生成物 | **改为生成物**：它已是 `--sync` 的基准，保住这个检查 |
| 3 | `index.html` 生成方式 | 整页生成 / 只生成 SVG 颜色段 | **只生成颜色段**：页面结构是手工设计的 |
| 4 | PPTX 是否跟随文档主题 | 跟随 / 独立 | **跟随**：漂移已经发生 |
| 5 | Drawing 主题是否由 palette 派生 | 派生 / 独立维护 | **派生**：12 令牌是固定交换单元，值可以从 palette 取 |
| 6 | 阶段顺序 | 按本文 / 按修复计划 | **先修已漂移的（阶段 1）**，再打通投影 |

---

## 十一、复核命令

```bash
# 全仓色值分布（排除构建产物）
python3 - <<'PY'
import re
from collections import defaultdict
from pathlib import Path
ROOT = Path(".")
HEX = re.compile(r"#[0-9A-Fa-f]{6}\b")
SOURCES = {
 "模板": ["assets/templates"], "图表模板": ["assets/diagrams"],
 "Drawing": ["scripts/drawing/theme/folio.py"], "Theme": ["references/profiles/theme"],
 "tokens.json": ["references/tokens.json"], "首页SVG": ["index.html","index-zh.html"],
 "demo": ["assets/demos"], "宿主": ["references/fixtures/hosting"],
 "PPTX": ["scripts/document_ir/writers/pptx.py"],
}
owner = defaultdict(set)
for label, targets in SOURCES.items():
    for t in targets:
        p = ROOT / t
        for path in ([p] if p.is_file() else [q for q in p.rglob("*") if q.is_file()]):
            if any(x in {"__pycache__","generated"} for x in path.parts): continue
            if path.suffix.lower() not in {".html",".py",".json",".yaml",".svg"}: continue
            for h in HEX.findall(path.read_text(encoding="utf-8", errors="ignore")):
                owner[h.upper()].add(label)
shared = {v:s for v,s in owner.items() if len(s)>1}
print(f"{len(owner)} 个色值, {len(shared)} 个跨源, {len([1 for v,s in owner.items() if len(s)>=5])} 个在 5+ 源")
PY

# PPTX 是否漂移
grep -n "PALETTE" -A7 scripts/document_ir/writers/pptx.py
grep -rc "24211D\|E5D9CE" assets/templates assets/diagrams references index.html 2>/dev/null | grep -v ":0"

# :root 变体数量（说明不能靠复制一段块解决）
python3 - <<'PY'
import re, hashlib
from collections import defaultdict
from pathlib import Path
for label, pat in (("图表模板","assets/diagrams/*.html"),("demo","assets/demos/*.html"),("文档模板","assets/templates/*.html")):
    g = defaultdict(int)
    for p in sorted(Path(".").glob(pat)):
        t = p.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r":root\s*\{", t)
        if not m: continue
        end = t.index("}", m.end())
        pairs = tuple(sorted(re.findall(r"--([a-z0-9-]+)\s*:\s*([^;]+);", t[m.end():end])))
        g[hashlib.sha256(str(pairs).encode()).hexdigest()[:8]] += 1
    print(label, len(g), "种变体")
PY

# 一条「改一次全部变」的测试
# 见第七节
```
