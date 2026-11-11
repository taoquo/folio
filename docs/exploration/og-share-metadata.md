# 分享元数据与分享图：缺口分析与实施方案

> 状态：已实施（P0–P3，本地，未提交）。实施结果、与计划的偏差、遗留见 §11；§1–§10 保留决策时的原始证据，不追改。
> 调研时间：2026-11-10；实施 2026-11-11。分支：`Enhanced`。
> 相关：`docs/exploration/kami-six-months.md`（Kami 的 Social Card 是本文的触发点，但它解决的是"发图"，本文解决的是"链接被分享时是什么样"）。

---

## 1. 一句话结论

我们不是"少一个 Social Card 模板"，是**页面的 head 从来没长齐**：标题有，描述只有自家首页有，`og:` / `twitter:` 一条没有，`canonical` 是相对路径，`theme-color` 没有，检查器里没有任何一条规则管 head。

而卡片需要的文字，`series.json` 里**已经全部存在**（`title` / `kicker` / `lead` / `summary`），构建时被丢掉了。

技术上也已经验证：用现有引擎（WeasyPrint + `SOURCE_DATE_EPOCH` + `pdftoppm`）可以稳定产出 1200×630、37 KB、**两次构建字节一致**的分享图，不需要浏览器、不需要新依赖。

---

## 2. 现状盘点（实测）

| 页面 | `<title>` | `description` | `og:` | `twitter:` | `canonical` | `theme-color` |
|---|---|---|---|---|---|---|
| `index.html`（EN 首页） | 有 | 有 | 无 | 无 | 无 | 无 |
| `index-zh.html`（中文首页） | 有 | 有 | 无 | 无 | 无 | 无 |
| `index-en.html`（跳转页） | 有 | 无 | 无 | 无 | 相对路径 | 无 |
| `dist/web/<series>/index.html`（系列首页） | 有 | 无 | 无 | 无 | 无 | 无 |
| `dist/web/<series>/<module>/index.html`（阅读页） | 有 | 无 | 无 | 无 | 无 | 无 |
| `assets/demos/*.html` | 有 | 无 | 无 | 无 | 无 | 无 |

两个模板的 head 一共三行：

```html
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{PAGE_TITLE}}</title>
```

`scripts/check_web.py` 的 51 条 `W-*` 里，没有一条读 `<head>`：不查 title 长度，不查 description 是否存在，不查 og。也就是说这不是"某处漏了"，是**契约里没有这一层**。

### 2.1 数据其实已经在了

`references/fixtures/web/attention/series.json`：

```json
{"series": "attention", "kind": "case", "language": "zh-Hans-CN",
 "kicker": "TRANSFORMER · PAPER READING",
 "title": "Attention Is All You Need",
 "lead": "一次把循环与卷积移出序列建模的架构说明：它做了什么、为什么成立、代价在哪里。"}
```

每个模块还有 `name` / `summary` / `lead` / `kicker` / `num` / `source`。**一份分享图需要的四段文字全都有**，缺的是把它们写到 `<head>` 和一张图上。

### 2.2 后果

- 链接发到 Slack / X / iMessage / 飞书，**没有图、没有摘要**，只有一行标题。
- `dist/web` 的阅读页没有 `description`，搜索引擎抓到的也是裸标题。
- 手机浏览器的地址栏是白色，页面是暖纸色，切换时闪一下。
- `index-en.html` 的 `canonical` 是 `./index.html`，相对路径；跨域引用时会被解析到错误的位置。

---

## 3. 生成路径比较（含实测）

分享图需要：1200×630、文字排版、主题色、中文字体、可复现。四条路：

| 路线 | 依赖 | 可复现 | 文字排版 | 判断 |
|---|---|---|---|---|
| 浏览器截图（Playwright） | Chromium | 需锁版本与设备像素比 | 最好，等于页面本身 | 只有 nightly 装了浏览器，快速门禁跑不了 |
| **WeasyPrint → pdftoppm** | 已有（渲染器 + poppler） | **实测字节一致** | 好，flex 足够 | **推荐** |
| SVG → rsvg-convert | 已有 | 好 | 差：SVG 不会自动折行 | 标题一长就得自己断行 |
| 手绘 PNG | 无 | 好 | 不适用 | 每加一种语言、一个系列都要手画 |

实测（本机）：

```text
$ SOURCE_DATE_EPOCH=0 weasyprint card.html card1.pdf   # 1200px x 630px @page
$ SOURCE_DATE_EPOCH=0 weasyprint card.html card2.pdf
0090712f...  card1.pdf
0090712f...  card2.pdf          # 字节一致

$ pdftoppm -r 96 -png -singlefile card1.pdf card1
$ pdftoppm -r 96 -png -singlefile card2.pdf card2
00e1c677...  card1.png
00e1c677...  card2.png          # 字节一致
png size (1200, 630)            # 尺寸精确
37K                             # 体积
```

同一份卡片用的就是站点字体（Source Serif 4 + LXGW WenKai），`@page { size: 1200px 630px; margin: 0 }`，`pdftoppm -r 96` 把 1 CSS px 映成 1 像素。渲染一次约两秒。

这和我们已有的确定性机制是同一套：`diagram_catalog.reproducible_pdf()` 已经在设 `SOURCE_DATE_EPOCH`，`determinism.py` 已经在比对栅格摘要。

---

## 4. 分享图的设计约束

### 4.1 尺寸

一个尺寸就够：**1200×630（1.91:1）**。Facebook / LinkedIn / Slack / iMessage / 飞书通用；X 的文档写 1200×628，差 2px 看不出来。微信和小红书不读 Open Graph，它们要的是上传图片，不在本方案范围内。

### 4.2 安全区

不同客户端会裁成不同比例（时间线 1.91:1，部分客户端方形）。规则：

- 画布 1200×630；**文字安全区 x∈[300, 900]、y∈[80, 550]**（居中 600×470），方形裁剪也不切字。
- 标题最多 3 行，导语最多 2 行；超了降一档字号，到地板仍放不下就**截断导语，永不截断标题**。
- 这是 `compose_for_band()` 的同一条思路：**取"能满足下限的最大一档"**，而不是写死一个字号。卡片的档位与选择结果要记录进清单，检查器重算，不信任样式表。

### 4.3 内容

| 来源 | 标题 | 描述 | 眉标 |
|---|---|---|---|
| 系列首页 | `series.title` | `series.lead` | `series.kicker` |
| 阅读页 | `module.title` | `module.summary` | `series.kicker` + `module.num` |
| 自家首页 | 手写 | 手写 | 手写 |

### 4.4 两种构图

- **A 文字卡**（默认）：眉标 / 标题 / 导语 / 一条强调色横线 / 系列名。空、稳、和文档同一套字体。
- **B 文字 + 图版**：右侧放该页的主图（我们已经有 SVG 和确定的构图）。视觉更强，但引入"图在 1200×630 里怎么裁"的新问题，一期不做。

同一套图只用一种构图、一套字阶：这和文档侧的克制一致。

---

## 5. 一个架构决定：origin 是构建输入

`og:url` 和 `og:image` **必须是绝对 URL**，抓取器不会解析相对路径。而构建时输出的是文件树，构建器不知道它将被部署到哪个域名。

所以，和 ADR 0009「stage 由宿主给，不由 payload 写」同构：

> **origin 由系列声明，构建器不自造。**

- `series.json` 增加可选 `"origin": "https://example.com/attention"`；也可用 `--base-url` 覆盖。
- 有 origin：输出 `og:url` / `og:image` / `canonical` 为绝对地址。
- 无 origin：**不输出这三个标签**，并在构建输出里说明原因（`WARN: no origin; share tags omitted`）。宁可没有，不要发一个错的绝对地址。
- 建议落成 `references/decisions/0010-the-origin-is-a-build-input.md`。

这一条同时解决 `index-en.html` 那个相对的 `canonical`：自家首页的 origin 是已知常量。

---

## 6. 检查与门禁

新增两类，沿用现有编号体系：

**静态（`W-META-*`，进 `check_web.py`）**

| 编号 | 判据 |
|---|---|
| W-META-01 | 每页有非空 `<meta name="description">`，长度 40–160 字符（中文按 2 计） |
| W-META-02 | `og:title` / `og:description` / `og:type` / `og:locale` 齐全，且 `og:title` 与 `<title>` 同源 |
| W-META-03 | 有 origin 时 `og:url` / `og:image` / `canonical` 是绝对地址；无 origin 时三者都不存在 |
| W-META-04 | `og:image` 指向的文件真实存在，且清单记录宽高与摘要 |
| W-META-05 | `<meta name="theme-color">` 等于主题的 surface 值 |

**实测（`V-META-01`，进 `web_measure.py`）**

- PNG 恰好 1200×630，字节数在预算内（例如 < 300 KB）。
- 非背景像素的包围盒落在安全区内，容差 4px。方法已在本机验证：PIL 取背景色做差、阈值 8、`getbbox()`，实测 `ink bbox (80,112)-(742,550)`。
- 两次构建的 PNG SHA-256 相同。

**失败模式要能被抓到**：长中文标题撑破安全区、字体没加载导致回退、主题色改了卡片没重建。前两条由 V-META-01 抓，第三条由摘要进 `determinism.py`／基线抓。

---

## 7. 产物

```text
dist/web/<series>/
  index.html            <meta ... og:image="<origin>/share.png">
  share.png             系列分享图
  share.manifest.json   {page, title, description, image, width, height, sha256, rung, source}
  <module>/
    index.html          og:image="<origin>/<module>/share.png"
    share.png
```

- 图片与页面同目录，相对路径天然正确；标签里写绝对地址，靠 origin 拼。
- URL 带内容摘要（`share.png?v=<sha8>`）以绕开平台缓存：卡片变了，URL 也变。
- 生成物进 `.gitignore` 的 `dist/`，与现有约定一致；自家首页的两张图是例外，进 `assets/images/`，因为它们服务于被跟踪的 `index.html` / `index-zh.html`。

---

## 8. 分阶段

| 阶段 | 内容 | 验收 | 量级 |
|---|---|---|---|
| **P0 自家首页** | 生成 `assets/images/share-en.png`、`share-zh.png`；两个首页补 `og:` / `twitter:` / `theme-color`；`index-en.html` 的 canonical 改绝对 | 三个首页的标签齐全；两张图字节可复现 | 半天 |
| **P1 系列与阅读页** | `build_web` 生成每页分享图与 `share.manifest.json`；`series.json` 加 `origin`；模板补 head | 有 origin 时标签齐全，无 origin 时明确省略 | 2–3 天 |
| **P2 门禁** | `W-META-01..05`、`V-META-01`；PNG 摘要进确定性检查 | 故意改坏一处，门禁必须红 | 1–2 天 |
| **P3 可选** | 构图 B（文字 + 图版）；阅读页按章节出图 | 只在 P1 稳定后再谈 | — |

先做 P0 的理由：它不依赖新架构，当天就能让**我们现在真正会被分享的页面**有预览图；同时把"卡片长什么样"这件事用两张真图定下来，P1 只是把它参数化。

---

## 9. 明确不做

- 不做 Kami 那样的 8 种纸色卡片族：那是一套内容产品，不是我们缺的东西。
- 不做多平台尺寸矩阵（1600×900 / 1242×1660 / 1080×1440）：那是投放，会一直加尺寸。
- 不做逐图分享卡。
- 不用浏览器截图做卡片：主路径必须能在快速门禁里跑。

---

## 10. 决策点

1. **origin 从哪来**：`series.json` 字段，还是 `--base-url` + 环境变量？我倾向 `series.json`（声明式，跟着内容走），CLI 只做覆盖。
2. **无 origin 时**：省略标签并 WARN（本文推荐），还是用相对路径硬发？
3. **P0 的两张首页图**：进版本库（`assets/images/`），还是每次构建生成到 `dist/`？我倾向进版本库——首页是手写 HTML，图应当和它一起被评审。

---

## 11. 实施记录（as-built）

> 2026-11-11，分支 `Enhanced`，本地实施，未提交。P0–P3 全部落地，`docs/` 与 `AGENTS.md` 同步。
> 复现命令与实测输出见 §11.6。

### 11.1 先说与计划的偏离

1. **4.2 的"安全区"被换成了页面自己的栅格。** 第一版严格照 x∈[300,900] 做：600px 居中栏、72px 标题。渲染出来卡片**不像它所链接的那一页**——1200 宽的画布上文字只占中间一半，右侧全空，眉标与落款挤在左三分之一。第二版改为照抄首页 hero：左右 72px 边距、1056 内容宽、标题 120px/1.05、导语 26px/1.35、眉标用衬线大写（首页 `.eyebrow` 本身就是衬线）、导语用 `--color-text-secondary` 而不是 muted。
2. **方形裁剪是有代价的，这次选择接受。** 卡片按 1.91:1 构图：X 的 2:1、Facebook / LinkedIn / Slack 的 1.91:1 都是整幅显示；iMessage 这类 1:1 缩略图会裁掉左右各约 190px，导语右端会被切。取舍的理由写在代码注释里：先让卡片读起来是那一页，再谈极少数客户端的降级。标题控制在 3 行以内，裁剪时至少保住开头的词。
3. **卡片只使用随仓字体。** 页面字体栈可能把系统字体排在前面（EN 阅读页是 `Charter` 在前）。`embedded_stack()` 把随仓的三款字面提到最前，于是同一份输入在任何机器上产出同一份字节。页面本身是否嵌入该字面是另一个问题，见 11.5。
4. **首页的 `description` 不重复。** 首页已有 `<meta name="description">`；注入块只补 og / twitter / canonical / theme-color，`schema` 里由页面自己持有描述。阅读页的描述由 `series.json` 生成，块内自带。
5. **没有 origin 时仍然渲染图片，只是不发绝对标签。** 图片可以人工取用；标签一旦相对就比没有更糟。

### 11.2 P0：两个首页

- `references/site/share.json`：站点 origin、每页的卡片文字与输出路径、跳转页与目标。
- `scripts/share_card.py --site`：渲染 `assets/images/share-en.png`、`share-zh.png`，把 head 块写进 `index.html` / `index-zh.html` 的 `<!-- folio-meta:start/end -->` 区，并把 `index-en.html` 的 canonical 改成绝对地址。
- 颜色与字族从 `styles.css` 读（`--color-surface-page` 等），不在这份 JSON 里写第二份。
- 卡片的组合由测量决定：标题挑字号档（120/104/88/74），导语在块底之上 40px 处收住，末尾行不足 30% 时把行宽 40px 一档收窄到不再出现孤字。选择结果记入清单。
- `og:image` 与 `twitter:image` 都带 `?v=<sha8>`，与 §7 的系列页一致：卡片换了，地址也换，平台缓存才会重新抓。
- `assets/images/share.manifest.json` 记录每张卡的输入文字、选中档位与摘要；`--check-heads` 用它判断"文字改了但卡没重画"，不需要重新渲染。

### 11.3 P1：系列页与阅读页

- `series.json` 新增可选 `origin`；没有它则构建照常、绝对标签全部省略（`og:url` / `canonical` / `og:image*` / `twitter:image`）。
- `build_web.py` 为每个页面写 `share.png` + `share.manifest.json`（尺寸、摘要、选中的字号与行宽、是否截断），并把 head 块注入两个模板的 `{{HEAD_META}}`。
- `og:image` 带内容摘要 `share.png?v=<sha8>`：卡片变了 URL 就变，绕过平台缓存。
- 构图 B：模块页取该页第一张图，用**窄档**（为最小视口构图的那一版）整幅放进右侧 368×444 的框里，不裁切；没有图或图不是窄档可组合的家族时退回构图 A。整幅而不是裁切，理由是切穿方框的图读者读不完。

### 11.4 P2：门禁

- `check_web.py` 新增 `W-META-01..05`（L1，静态）：描述长度、og 四件套与 `<title>` 同源、绝对地址完整且同源、图片存在且清单摘要一致、`theme-color` 等于主题 surface。
- `web_verify.py` 新增 `V-META-01`（L3，实测）：PNG 恰好 1200×630、摘要与清单一致、墨迹包围盒在画布边距以内（左 64 / 右 1136 / 上 32 / 下 606）。
- 反转验证：删掉 `og:image`、改 `theme-color`、改清单摘要、写坏 PNG，四条规则分别变红（§11.6）。
- 首页的两张卡不在 `build_web` 的产物里，由 `share_card.py --site` 两个档位看守：`--check` 重渲染比字节（在生成卡片的机器上跑），`--check-heads` 只比 `?v=` 摘要与 PNG 尺寸（不渲染，进快速门禁）。后者进 `.github/workflows/drawing-dsl.yml`：PDF 转 PNG 的栅格器在不同平台上不保证逐字节一致，字节比对放在作者机器上，摘要比对放在所有机器上。

### 11.5 已知遗留（不在本次改动内）

- **EN 阅读页没有嵌入任何衬线字面。** `folio-web-en-v1` 的 `font` 块没有 `latin_face`，所以 `web_font_faces("en")` 只返回 mono；页面在 macOS 上落到系统 Charter，在 Linux 上落到别的。卡片因为只认随仓字面反而不受影响。要修就得改 profile（`latin_face: Source Serif 4` 并把字面排到栈首），那会改变所有英文阅读页的字体，属于需要单独决定的设计变更。
- **`index-zh.html` 的 `<title>` 仍是 `Folio · Design System`**，中文页给了英文标题。这是内容决定，未改。
- **origin 是占位值**：`https://taoquo.github.io/folio`、`.../web/attention`、`.../web/reading-demo`。仓库是 `taoquo/folio`，Pages 的地址需要确认后改这一处（`references/site/share.json` 与两份 `series.json`）。
- 章节级分享图不做：OG 是文档级元数据，不是锚点级；一个页面只有一个 `og:image`。

### 11.6 复现与实测

```bash
python3 scripts/share_card.py --site                 # 两张首页卡 + head 块
python3 scripts/share_card.py --site --check         # 字节与 head 块漂移
python3 scripts/share_card.py --site --check-heads   # head 的 v= 摘要与 PNG 尺寸
python3 scripts/build_web.py --series references/fixtures/web/attention --out /tmp/webout
python3 scripts/check_web.py <page> --level 3 --series-dir <series>
python3 scripts/web_measure.py --series attention && python3 scripts/web_verify.py --series attention
python3 -m unittest tests.test_share_card tests.test_web_checks tests.test_web_verify
```
