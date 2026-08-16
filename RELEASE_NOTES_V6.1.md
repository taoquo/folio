<p align="center">
  <img src="assets/images/folio-mark.svg" width="96" alt="Folio">
</p>

<h1 align="center">Folio Drawing DSL V6.1</h1>

<p align="center">Twenty-three generator-backed diagram types on a bounded, schema-enforced canvas.</p>

### Changelog

1. Added Heatmap as the twenty-third generator-backed diagram type, grading one measure with a single warm ramp, at most one focal row, and values carried by the legend and the accessible description instead of cell text.
2. Turned the diagram canvas height into a bounded knob: data charts accept 400-720 and notation diagrams accept 480-800, both in steps of 4, replacing the exact-canvas assertions that made the documented knob unusable on eleven kinds.
3. Derived plot bands, donut geometry, notation grid rows, and source captions from the canvas height, so the same JSON renders identically at the default and scales correctly at every accepted height.
4. Aligned the JSON contracts with the compiler so schema validation and compilation reject the same out-of-range canvas, and `validate-drawing-schema` now checks every registered contract instead of a hand-listed subset.
5. Added an orphan-text gate backed by paragraph reconstruction from the PDF text matrix, plus a homepage miniature parity gate, both wired into the build checks and CI.
6. Threaded theme and variant through the host and review paths with a schema 1.1 manifest, drift rejection on verify, and motion rejected for PPTX slots.
7. Retired dead legacy layout code, clarified the compiler facade boundaries, and converted the illustration set to WebP, cutting 9.2MB to 1.5MB.
8. Remeasured the closing audit on the full twenty-three-fixture showcase corpus and recorded what the height knob actually changes per kind, separating framing control from utilization mitigation.

### 更新日志

1. 新增热力图作为第二十三种生成器类型，用单一暖色渐变表达一个度量，最多允许一个焦点行，数值由图例和无障碍描述承载而非写入单元格。
2. 将画布高度改为有界旋钮：数据图接受 400 至 720，记号图接受 480 至 800，步进均为 4，替换掉使十一种类型无法使用该旋钮的精确画布断言。
3. 绘图带、环形图几何、记号图网格行和数据来源标注均改为从画布高度派生，同一份 JSON 在默认高度渲染结果不变，在任意合法高度下正确缩放。
4. 令 JSON 契约与编译器一致，Schema 校验与编译对越界画布给出相同拒绝结果，`validate-drawing-schema` 改为校验全部注册契约而非手工列举的子集。
5. 新增孤字门禁，基于 PDF 文本矩阵重建段落进行检测，并新增首页缩略图对等门禁，两者均接入构建检查与 CI。
6. 将主题与变体贯通宿主与评审链路，宿主清单升级到 schema 1.1，校验时拒绝变体漂移，PPTX 插槽拒绝动效。
7. 清理失效的历史布局代码，明确编译器门面边界，并将插图集转为 WebP，体积从 9.2MB 降至 1.5MB。
8. 在完整的二十三个展示样例上重测收尾审计，逐类型记录高度旋钮的实际作用，区分取景控制与利用率改善。

> Folio is an editorial document and diagram design system for durable professional artifacts. https://github.com/taoquo/folio

