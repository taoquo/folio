<div align="center">
  <img src="assets/images/folio-mark.svg" width="120" />
  <h1>Folio</h1>
  <p><b>值得留存的文档版式。</b></p>
  <p><sub><a href="README.md">English</a></sub></p>
  <p><sub>Folio fork 自 <a href="https://github.com/tw93/Kami">Kami</a>，并在此基础上扩展成一套面向 agent 生成交付物的文档设计系统。</sub></p>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg?style=flat-square" alt="License"></a>
</div>

## Folio 是什么

Folio 是一套面向 AI 时代的文档设计系统：覆盖 8 种文档类型、14 种内联 SVG 图表类型，并同时提供中英文两条生成路径，专门服务于 agent 驱动的文档交付。

它追求的不是视觉花样，而是稳定、清晰、专业、可重复的输出结果。

## 快速开始

**Claude Desktop**

构建或直接使用 `dist/folio.zip`，打开 Customize > Skills > "+" > Create skill，然后直接上传 ZIP。

**通用 agent 环境**（Codex、OpenCode、Pi，以及其他读取 `~/.agents/` 的工具）

可以先用打包好的 ZIP 本地安装；如果后续要发布，再把仓库放到你自己的命名空间下。

Folio 会根据自然语言请求自动触发。你只需要尽量把下面这些信息讲清楚：

- 想要的文档类型
- 使用的语言
- 原始内容、笔记、草稿或素材
- 必须保留的事实、数字或来源链接
- 相关品牌素材：logo、截图、产品图、品牌色
- 会影响输出的额外要求：PDF、PPTX、PNG、对外稿、内部备忘录

示例提示词：

- `帮我做一份一页纸`
- `帮我排版一份长文档`
- `帮我写一封正式信件`
- `帮我做一份作品集`
- `帮我做一份简历`
- `帮我做一套演讲幻灯片`
- `帮我写一份英伟达个股研报`
- `帮我整理更新日志`

可选：创建 `~/.config/folio/brand.md`，持久保存身份信息、文档默认设置和写作习惯。可从 [brand.example.md](references/brand.example.md) 开始。当前请求存在歧义时，Folio 会把它作为 fallback 上下文使用。

## 文档类型

| 类型          | 适合场景                          | 案例                                                               |
| ------------- | --------------------------------- | ------------------------------------------------------------------ |
| One-Pager     | 上线简介、提案、执行摘要          | [青岚旅图上线一页纸](assets/demos/demo-qinglan-onepager-zh.pdf)    |
| Long Doc      | 白皮书、复盘、技术报告            | [智能体运维半年复盘](assets/demos/demo-agent-ops-longdoc-zh.pdf)   |
| Letter        | 正式信件、备忘录、声明            | [模型变更评审建议函](assets/demos/demo-model-review-letter-zh.pdf) |
| Portfolio     | 作品集、案例集、精选项目          | [陈渡作品集](assets/demos/demo-chendu-portfolio-zh.pdf)            |
| Resume        | 简历、职业履历                    | [周叙简历](assets/demos/demo-zhouxu-resume-zh.pdf)                 |
| Slides        | 演讲稿、Keynote、内部汇报         | [中文智能体演示 deck](assets/demos/demo-agent-slides-zh.pdf)       |
| Equity Report | 投资备忘录、财报快报、个股研报    | [特斯拉 Q1 2026 投资分析](assets/demos/demo-tesla.pdf)             |
| Changelog     | 更新日志、版本说明、Release Notes | [Folio v1.2.0 更新日志](assets/demos/demo-folio-changelog-zh.pdf)  |

模板位于 `assets/templates/`。`assets/demos/` 现在只保留渲染后的 `PDF + PNG` 展示资产，上表也统一改为按 README 语种分别链接对应 PDF 案例。

## 核心能力

### 类型路由

Folio 会在 8 种文档类型和 2 条语言路径之间自动路由。

- 中文请求路由到 `*.html` 或 `slides.py`
- 英文请求路由到 `*-en.html` 或 `slides-en.py`
- Slides 的源模板是 Python，不是 HTML

### 内容蒸馏

Folio 不要求输入必须先整理成干净提纲，也能把原始材料收束成成型文档。

- 会议笔记、信息 dump、聊天记录、散乱 bullet 都可以蒸馏成适配模板的结构
- 简历和作品集会被收紧到更强调可量化结果的写法
- 研报和更新日志会被推向证据优先的写法，而不是泛泛总结

### 来源与素材检查

Folio 把“当前事实”和“品牌素材”当作一等输入，而不是补充信息。

- 涉及当前事实时，默认先看可靠来源再写
- 涉及品牌文档时，会检查 logo、截图、产品图和品牌色是否齐备
- 如果关键素材缺失，应明确标出缺口，而不是用泛化视觉凑数

### 输出生成

Folio 目前支持两条主输出路径：

- HTML 模板 -> PDF
- Python 幻灯片模板 -> PPTX

展示型 demo 通常会同时保留 `HTML + PDF + PNG`，这样首页和 README 才能持续反映真实状态。

### 基于 Cheatsheet 的快速编辑

Folio 不只是模板集合，还带了一份紧凑的操作参考：[CHEATSHEET.md](CHEATSHEET.md)。

- 需要最快路径时，看它拿 token、字号、间距、图表限制和常用 CSS 片段
- 需要完整视觉系统时，看 `references/design.md`
- 结构没问题但内容质量不够时，看 `references/writing.md`
- 构建、页数、渲染行为出问题时，看 `references/production.md`

## 排版规则

这些是最值得守住的最低规则集。

1. 页面底色固定为 parchment `#F6F0EA`，不要用纯白。
2. 全文只保留一个强调色：cinnabar-coral `#B83D2E`。
3. 默认一页一套 serif，除非模板本身已经定义了其他视觉语言。
4. Serif 正文保持 400，标题保持 500，避免 synthetic bold。
5. 中文印刷正文通常带少量字距，英文正文保持 0。
6. Tag 背景必须使用实色 hex，不要用 `rgba()`，否则 WeasyPrint 可能渲染出双层矩形。
7. 层次感来自 ring shadow、whisper shadow 或明暗切换，不用硬投影。
8. 必须守住各文档类型的页数契约，尤其是简历和一页纸。

## 设计参考

先看短参考，需要时再深入。

- [CHEATSHEET.md](CHEATSHEET.md)：快速参考
- [references/design.md](references/design.md)：视觉系统
- [references/writing.md](references/writing.md)：内容策略与质量标准
- [references/production.md](references/production.md)：构建、验证与排障
- [references/diagrams.md](references/diagrams.md)：内联 SVG 图表规则

## Travel / 图片提示词

Folio 也可以作为图片模型或绘图工具的风格 brief。把 `references/` 交给它们，并明确要求遵守 Folio 的暖纸底色、朱红克制、serif 层级和编辑式留白。

示例插图 brief：

- 高山夜行列车旅行图册：站点注释、时刻卡片、暖纸底和手工批注并存
  ![高山夜行列车旅行图册](assets/illustrations/travel-tesla-optimus.png)

- 海岸周末路线海报：潮汐时间窗、咖啡停靠点、步行段与换乘点清晰分层
  ![海岸周末路线海报](assets/illustrations/travel-spatialvla.png)

- 沙漠设计酒店旅行手账：到达地图、打包提示、物件特写与留白并置
  ![沙漠设计酒店旅行手账](assets/illustrations/travel-3d-representations.png)

## 支持

- 如果发现 bug、措辞漂移或版式回归，欢迎提 issue 或 PR。
- 代码和模板使用 MIT License。
- LXGW WenKai 为开源字体；Charter 依赖系统或开源可用性。
