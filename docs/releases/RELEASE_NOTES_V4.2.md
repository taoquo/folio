<p align="center">
  <img src="assets/images/folio-mark.svg" width="96" alt="Folio">
</p>

<h1 align="center">Folio Drawing DSL V4.2</h1>

<p align="center">Safe tabular authoring and bounded semantic detail for production data visualizations.</p>

### Changelog

1. Added deterministic local CSV and TSV import with explicit encoding, delimiter, header, mapping, missing, locale, and coercion contracts.
2. Added fail-closed protection against remote resources, formula-like cells, ambiguous values, duplicate headers, malformed rows, and oversized inputs.
3. Added grouped or stacked Bar modes with separate positive and negative accumulation, stable segment ids, and accurate endpoint totals.
4. Added bounded reference lines for Bar and Line plus semantic mark annotations for Bar, Line, and Candlestick.
5. Added arithmetically verified Waterfall subtotal steps that preserve exact accessible running totals.
6. Added explicit locale, precision, compact, grouping, and unit-position formatting without changing serialized semantic values.
7. Fixed Line axis-label alignment and stable point identity, negative Bar label placement, chart canvas contract drift, and plan/table reduction mismatches.
8. Added four feature fixtures, thirty-six profile/format artifacts, numerical property coverage, classified visual approval, and complete release gates.

### 更新日志

1. 新增确定性的本地 CSV 与 TSV 导入，强制声明编码、分隔符、表头、映射、缺失值、地区和类型转换规则。
2. 新增失败闭合防护，拒绝远程资源、公式型单元格、歧义数值、重复表头、畸形行和超限输入。
3. 为柱状图新增分组与堆叠模式，分别累计正负值，保持分段 ID 稳定并正确显示端点总量。
4. 为柱状图和折线图新增有界基准线，并为柱状图、折线图和 K 线图新增语义标记注释。
5. 为瀑布图新增经过算术校验的小计步骤，并保持可访问运行总计精确一致。
6. 新增明确的地区、精度、紧凑显示、分组和单位位置格式规则，不改写序列化语义数值。
7. 修复折线轴标签对齐与稳定点身份、负柱标签位置、画布契约漂移以及计划与回退表之间的缺失值不一致。
8. 新增四个功能样例、三十六个 Profile/格式产物、数值性质测试、分类视觉批准和完整发布门禁。

> Folio is an editorial document and diagram design system for durable professional artifacts. https://github.com/taoquo/folio
