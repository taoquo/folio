# 设计探索索引

这里保存设计与取舍的历史记录，不是现行规范。一个行为现在是什么样，以
`AGENTS.md` 和 `references/` 下的正文为准；这些文件回答的是「当时为什么这样定」。

保留它们的理由：色板分层、字体落地、图表系列色桥接、分享元数据、Web 阅读页
这几个决定都有被否决的方案和实测数据，删掉后只能靠回忆重建。

## 状态说明

| 状态 | 含义 |
|---|---|
| 已采纳 | 结论已进入代码或现行文档，正文仍可查到当时的证据 |
| 已实施 | 记录的是已完成的改动，包含实施结果和被否决的方案 |
| 已被取代 | 结论被后续文档推翻或替换，保留作为决策链的一环 |
| 历史记录 | 调研、盘点或审计，结论已并入其他文档，本身不再单独生效 |

## 清单

| 文件 | 主题 | 日期 | 状态 | 发布 | 落点 |
|---|---|---|---|---|---|
| `color-architecture-review.md` | 颜色架构的整体梳理：同一色值重复十处的问题 | 2026-10-11 | 已采纳 | 本地 | theme profile 的 `palette` / `color` 两层与 `scripts/style_resolver.py` |
| [color-scheme-storage-design.md](color-scheme-storage-design.md) | 色系存在哪里、如何扩展 | 2026-10-11 | 已采纳 | 随仓库 | `references/profiles/theme/*.yaml` |
| [color-token-structure-design.md](color-token-structure-design.md) | 令牌如何分层、命名、扩展 | 2026-10-11 | 已采纳 | 随仓库 | `color.*` 角色路径与投影出的 CSS 变量 |
| `color-font-current-state.md` | 语义色与自定义字体的现状盘点（E0） | 2026-10-11 | 历史记录 | 本地 | 后续四篇的起点 |
| `color-font-research.md` | 四项前置调研 | 2026-10-11 | 历史记录 | 本地 | `color-font-remediation-plan.md` |
| `color-font-support-audit.md` | 换色系、丰富配色、字体语义化的支持度实验 | 2026-10-11 | 历史记录 | 本地 | `color-font-remediation-plan.md` |
| `color-font-remediation-plan.md` | 让色彩与字体真正到达页面的修复计划 | 2026-10-11 | 已实施 | 本地 | 模板 `:root` 与投影链路 |
| `color-font-prototype-report.md` | 上一项的实施结果与被否决方案 | 2026-10-11 | 已实施 | 本地 | 同上 |
| [drawing-series-bridge.md](drawing-series-bridge.md) | 图表系列色能否跟随文档配色 | 2026-10-12 | 已被取代 | 随仓库 | 其“暂不实施”的结论被下一项的实测推翻 |
| `drawing-series-bridge-plan.md` | 系列色桥接的实施计划与结果 | 2026-10-12 | 已实施 | 本地 | `scripts/drawing/theme/folio.py` 的 `color.series.1..6` |
| [kami-six-months.md](kami-six-months.md) | tw93/kami 六个月观察：哪些改进值得借 | 2026-11-10 | 历史记录 | 随仓库 | 触发了分享元数据与“单一出口”的讨论 |
| [og-share-metadata.md](og-share-metadata.md) | 分享元数据与分享图的缺口与实施方案 | 2026-11-11 | 已实施 | 随仓库 | `scripts/share_card.py`、`share.manifest.json`、head 规则 |
| [web-scenario-repositioning.md](web-scenario-repositioning.md) | Web 场景的重新定位（假说与选项） | 2026-10-24 | 已被取代 | 随仓库 | 由下一项收束为具体方案 |
| [web-reading-scenario-design.md](web-reading-scenario-design.md) | Web 阅读页场景的重设方案 | 2026-10-24 | 已采纳 | 随仓库 | `references/web/`、`scripts/build_web.py`、`W-*` / `V-*` 规则 |

标为「本地」的七篇是工作笔记，按 `.gitignore` 留在本机、不随仓库发布。它们在
表内只写文件名，因为链接在克隆下来的仓库里会失效；读正文请用本机的工作目录。

## 维护规则

- 新增一篇探索文档时，在上表补一行；状态只有上面四种。
- 只有随仓库发布的笔记写成链接；本地笔记用代码字体写文件名，发布列写「本地」。
- 结论被采纳后不改写原文，只在“落点”列写清去向；原文里的数字是当时的实测值。
- 现行行为与本文冲突时，改现行文档，不改历史记录。
