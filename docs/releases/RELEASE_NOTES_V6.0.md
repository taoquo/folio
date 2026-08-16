<p align="center">
  <img src="assets/images/folio-mark.svg" width="96" alt="Folio">
</p>

<h1 align="center">Folio Drawing DSL V6</h1>

<p align="center">Twenty-two generator-backed diagram types close the Drawing DSL program.</p>

### Changelog

1. Completed the twenty-two-type generator catalog by adding Pyramid, Org Chart, Loop Flywheel, Scatter, and Gantt to the shared compiler, schema, CLI, catalog, and artifact pipeline.
2. Added a deterministic semantic routing layer with eight patterns that turns a plain-language brief into a diagram kind, a confidence band, a full score table, in-pattern alternatives, and a readable trace.
3. Added three theme profiles, folio, dark, and terminal, resolved at render time from semantic roles and gated by contrast checks instead of literal colors in payloads.
4. Added render-layer output knobs for size, detail, audience, and variant so export width, annotation density, type ramp, and stroke treatment change without touching compiler-owned geometry.
5. Added Mermaid and draw.io import plus CSV and TSV chart normalization, each producing typed diagram JSON with a fidelity ledger of what was preserved and what was dropped.
6. Rewrote Tree sibling routing onto a shared horizontal bus per parent, matching Org Chart, and restored edge and bend metrics from the primitive channel so all geometry gates still apply.
7. Fixed the showcase visual pass defects: swimlane label obstacles, along-segment label sliding, duplicated donut legend shares, crossing sibling connectors, and bar-chart value labels colliding with reference lines.
8. Recorded the closing program audit with reference-principle conformance, a twenty-two-fixture showcase review, measured canvas utilization per kind, and the one remaining bounded compromise.

### 更新日志

1. 新增金字塔、组织架构、飞轮循环、散点图和甘特图，将生成器目录补齐到二十二种，全部接入共享编译器、Schema、CLI、目录和 artifact 管线。
2. 新增确定性语义路由层，用八个模式把自然语言描述解析为图表类型，并返回置信区间、完整分数表、同模式备选项和可读推理轨迹。
3. 新增 folio、dark、terminal 三套主题 profile，在渲染时依据语义角色解析配色并通过对比度校验，payload 中不再出现字面颜色。
4. 新增渲染层输出拨杆 size、detail、audience 和 variant，导出宽度、标注密度、字号阶梯和描边风格均可调整，且不触碰编译器持有的几何。
5. 新增 Mermaid 与 draw.io 导入以及 CSV、TSV 图表数据规范化，统一产出类型化图表 JSON，并附保真度台账记录保留项与丢弃项。
6. 重写树图兄弟连线，改为每个父节点一条共享横向主干，与组织架构一致，并从图元通道还原边数与折点指标，几何门禁全部继续生效。
7. 修复展示评审中发现的视觉缺陷：泳道标签避障、标签沿线滑动、环形图图例份额重复、兄弟连线交叉，以及柱状图数值标签与参考线重叠。
8. 记录收尾审计，覆盖参考原则符合度、二十二个展示样例的逐个复核、每种类型的画布利用率实测，以及唯一剩余的有界折衷。

> Folio is an editorial document and diagram design system for durable professional artifacts. https://github.com/taoquo/folio

