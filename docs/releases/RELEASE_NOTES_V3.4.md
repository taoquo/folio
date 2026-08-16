<p align="center">
  <img src="assets/images/folio-mark.svg" width="96" alt="Folio">
</p>

<h1 align="center">Folio Drawing DSL V3.4</h1>

<p align="center">A deterministic, audited, and release-gated baseline for the fourteen-type drawing platform.</p>

### Changelog

1. Added fast and full GitHub CI gates for tests, catalog validation, visual comparison, complete builds, and release packaging.
2. Added an approved fourteen-type visual baseline that locks semantic reading order, dimensions, content bounds, source digests, and classified pixel differences.
3. Fixed dependency diagnosis so the project WeasyPrint fallback is recognized and the required page-preview rasterizer is checked.
4. Made ZIP size validation portable across macOS and Linux and bundled all approved visual-baseline evidence below the 5 MB limit.
5. Derived V3 catalog coverage from the compiler registry and expanded compatibility tests across migration, validation, bundling, rendering, and review commands.
6. Closed the V3.4 audit with 145 passing tests, zero catalog diagnostics, deterministic replay, and all document, diagram, artifact, and slide targets verified.

### 更新日志

1. 新增快速与完整两级 GitHub CI 门禁，覆盖测试、目录校验、视觉比较、完整构建和发布打包。
2. 新增十四类已批准视觉基线，锁定语义阅读顺序、尺寸、内容边界、源摘要和经过分类的像素差异。
3. 修复依赖诊断，使项目内 WeasyPrint 回退环境可以被正确识别，并检查页面预览真正需要的栅格化工具。
4. 让 ZIP 大小校验同时兼容 macOS 与 Linux，并在 5 MB 限制内打包全部已批准视觉基线证据。
5. 让 V3 目录覆盖范围直接来源于编译器注册表，并补全迁移、校验、分包、渲染和审阅命令的兼容测试。
6. 完成 V3.4 审计：145 项测试通过、目录诊断为零、确定性重放通过，全部文档、图表、产物和幻灯片目标验证成功。

> Folio is a document design system with eight document templates and a deterministic editorial drawing platform. https://github.com/taoquo/folio
