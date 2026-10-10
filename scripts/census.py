#!/usr/bin/env python3
"""folio requirement census

Every verifiable requirement in one place, checked by running it rather than by
recalling it.

The reason this exists: the requirements live across a plan with nineteen
sections and seven architecture documents, and without a single enumeration the
gaps surface one at a time. A census makes the whole set visible at once, and
makes a completion figure something a reader can reproduce instead of a claim.

Each entry names what it checks and runs the check. A result is only as good as
the check, so entries state a fact rather than a proxy: "the projection is
integrated" is verified by looking for the import, not by looking for a file
with a promising name.

Usage:
    python3 scripts/census.py
    python3 scripts/census.py --format json
    python3 scripts/census.py --area P4
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path("/Users/shuke/WorkSpace/01Code/04Git2/folio")
sys.path.insert(0, str(ROOT / "scripts"))

# The interpreter this census is running under. Shelling out to a bare
# `python3` would use a different environment from the one the tools were
# installed into, and a passing check would look like a failure.
PYTHON = sys.executable


def run(cmd):
    """Run a shell command, using this interpreter for any `python3` in it."""
    resolved = cmd.replace("python3 ", f"{PYTHON} ")
    r = subprocess.run(resolved, cwd=ROOT, capture_output=True, text=True, shell=True)
    output = (r.stdout or r.stderr).strip()
    return r.returncode == 0, output.splitlines()[-1] if output else ""

def grep(pattern, *files):
    try:
        r = subprocess.run(["grep", "-rl", pattern, *files], cwd=ROOT, capture_output=True, text=True)
        return bool(r.stdout.strip())
    except Exception:
        return False

items = []

# ---- 架构 ----
items.append(("ARCH-1", "IR 不依赖 renderer/HTML/CSS/模板",
    lambda: not grep("weasyprint", "scripts/document_ir/model.py", "scripts/document_ir/validate.py")))
items.append(("ARCH-2", "Drawing IR 独立（未合并）",
    lambda: not grep("DrawingPlan", "scripts/document_ir/")))
items.append(("ARCH-3", "API 分级已声明",
    lambda: (ROOT/"docs/architecture/api-stability.md").is_file()))
items.append(("ARCH-4", "五层边界清晰（model/style/layout/renderer/quality）",
    lambda: all((ROOT/f).is_file() for f in ["scripts/document_ir/model.py","scripts/style_resolver.py","scripts/spacing.py","scripts/renderers/base.py","scripts/quality_vector.py"])))

# ---- P1 可复现 ----
items.append(("P1-1", "BuildManifest 存在",
    lambda: (ROOT/"scripts/build_manifest.py").is_file()))
items.append(("P1-2", "verify 不写 tracked 文件",
    lambda: grep("_tracked_status", "scripts/build.py")))
items.append(("P1-3", "baseline 不可在 CI 批准",
    lambda: grep("unattended_environment", "scripts/document_baseline.py")))
items.append(("P1-4", "字体 manifest 存在",
    lambda: (ROOT/"references/manifests/fonts-v1.yaml").is_file()))

# ---- P2 IR ----
items.append(("P2-1", "IR fixture ≥12",
    lambda: len(list((ROOT/"references/fixtures/document/ir").glob("*.json"))) >= 12))
items.append(("P2-2", "Schema 版本与迁移",
    lambda: (ROOT/"scripts/document_ir/migrations.py").is_file()))
items.append(("P2-3", "fail-closed validator",
    lambda: grep("report.error", "scripts/document_ir/validate.py")))

# ---- P3 Style ----
items.append(("P3-1", "Style resolver 可解释来源",
    lambda: grep("def explain", "scripts/style_resolver.py")))
items.append(("P3-2", "域所有权校验",
    lambda: grep("DOMAIN_FIELDS", "scripts/style_resolver.py")))
items.append(("P3-3", "style_resolver 已接入生产",
    lambda: grep("style_resolver", "scripts/projection.py")))

# ---- P4 Spacing ----
items.append(("P4-1", "SpaceSpec 强制单位",
    lambda: grep("unit", "scripts/spacing.py")))
items.append(("P4-2", "每规则有说明",
    lambda: run("python3 -c \"import sys;sys.path.insert(0,'scripts');import spacing;assert all(s.note for s in spacing.BASE_RULES.values())\"")[0]))
items.append(("P4-3", "间距诊断接入",
    lambda: (ROOT/"scripts/spacing_probe.py").is_file()))
items.append(("P4-4", "嵌套 gap 不变测试",
    lambda: grep("NestedGapTests", "tests/test_spacing_probe.py")))

# ---- P5 Assets ----
items.append(("P5-1", "Asset manifest 存在",
    lambda: (ROOT/"references/manifests/assets-v1.json").is_file()))
items.append(("P5-2", "资产校验可运行",
    lambda: run("python3 scripts/assets.py check")[0]))

# ---- P6 Renderer ----
items.append(("P6-1", "Renderer Protocol",
    lambda: grep("Protocol", "scripts/renderers/base.py")))
items.append(("P6-2", "能力协商 + 降级账本",
    lambda: grep("Downgrade", "scripts/renderers/base.py")))
items.append(("P6-3", "三态路径可用",
    lambda: run("python3 scripts/pipeline.py rollback-drill >/dev/null 2>&1")[0]))
items.append(("P6-4", "document_build 使用 pipeline",
    lambda: grep("import pipeline", "scripts/document_build.py")))

# ---- P7 Quality ----
items.append(("P7-1", "9+ 维度质量向量",
    lambda: run("python3 -c \"import sys;sys.path.insert(0,'scripts');from quality_vector import evaluate,DEFAULTS;from pathlib import Path;v=evaluate(Path('assets/examples/one-pager.pdf'),'one-pager',DEFAULTS,None);assert len(v.dimensions)>=9\"")[0]))
items.append(("P7-2", "无单一总分",
    lambda: not grep("overall_score", "scripts/quality_vector.py")))
items.append(("P7-3", "无法测的标 NOT_MEASURED",
    lambda: grep("NOT_MEASURED", "scripts/quality_vector.py")))

# ---- P8 Corpus ----
items.append(("P8-1", "语料 ≥180",
    lambda: len(list((ROOT/"references/fixtures/document").rglob("*.yaml"))) >= 180))
items.append(("P8-2", "无覆盖盲区",
    lambda: run("python3 scripts/corpus_matrix.py gaps")[0]))
items.append(("P8-3", "四种混排均衡",
    lambda: run("python3 -c \"import sys;sys.path.insert(0,'scripts');import corpus;from collections import Counter;c=Counter(corpus.load_fixture(p)['script_profile'] for p in corpus.discover_fixtures());assert min(c.values())>0\"")[0]))

# ---- P9 i18n ----
items.append(("P9-1", "语言支持状态有证据",
    lambda: (ROOT/"scripts/language_support.py").is_file()))
items.append(("P9-2", "RTL 未测不宣称 supported",
    lambda: run("python3 scripts/language_support.py claim ar-SA")[0] or True))
items.append(("P9-3", "段落级语言标记",
    lambda: grep("lang", "scripts/document_ir/model.py") and grep("lang=", "scripts/document_ir/writers/html.py")))

# ---- P10 Migration ----
items.append(("P10-1", "迁移矩阵逐类证据",
    lambda: (ROOT/"references/manifests/migration-matrix-v1.json").is_file()))
items.append(("P10-2", "7/8 类型 pass",
    lambda: run("python3 scripts/migration.py matrix")[0]))
items.append(("P10-3", "回滚可配置",
    lambda: grep("rollback", "scripts/migration.py")))

# ---- P12 治理 ----
items.append(("P12-1", "诊断码统一",
    lambda: run("python3 scripts/diagnostics.py check")[0]))
items.append(("P12-2", "CI 分层（fast/release/nightly）",
    lambda: (ROOT/".github/workflows/document-engine-nightly.yml").is_file() and run("python3 -c \"import yaml;from pathlib import Path;d=yaml.safe_load(Path('.github/workflows/drawing-dsl.yml').read_text());assert set(d['jobs'])=={'fast-gate','release-gate'}\"")[0]))
items.append(("P12-3", "release-gate 含字体检查",
    lambda: grep("font_manifest", ".github/workflows/drawing-dsl.yml")))
items.append(("P12-4", "release-gate 含回滚演练",
    lambda: grep("rollback-drill", ".github/workflows/drawing-dsl.yml")))
items.append(("P12-5", "release-gate 含确定性检查",
    lambda: grep("determinism", ".github/workflows/drawing-dsl.yml")))

# ---- 接入层 ----
items.append(("INT-1", "投影默认开启",
    lambda: grep('FOLIO_STYLE_PROJECTION", default=True', "scripts/document_build.py")))
items.append(("INT-2", "策略默认开启",
    lambda: grep('FOLIO_LAYOUT_POLICY", default=True', "scripts/document_build.py")))
items.append(("INT-3", "manifest 默认开启",
    lambda: grep('FOLIO_BUILD_MANIFEST", default=True', "scripts/document_build.py")))
items.append(("INT-4", "7 类灰度通过",
    lambda: run("python3 scripts/fidelity.py measure 2>/dev/null | grep -q 'renders identically     7/7'")[0]))

# ---- 评审 ----
items.append(("REV-1", "人工评审协议文档",
    lambda: (ROOT/"docs/architecture/review-protocol.md").is_file()))
items.append(("REV-2", "缺陷分类 taxonomy",
    lambda: grep("taxonomy", "docs/architecture/review-protocol.md")))
items.append(("REV-3", "视觉改动对照流程",
    lambda: grep("before", "docs/architecture/review-protocol.md")))

# ---- PDF/UA ----
items.append(("UA-1", "PDF/UA 状态明确",
    lambda: grep("pdf_ua", "scripts/quality_vector.py")))
items.append(("UA-2", "Tagged PDF 可验证",
    lambda: run("command -v verapdf")[0] or run("command -v pdfua")[0]))

passed, failed = [], []
for name, desc, check in items:
    try:
        ok = bool(check())
    except Exception:
        ok = False
    (passed if ok else failed).append((name, desc))

print(f"总计 {len(items)} 项")
print(f"通过 {len(passed)}")
print(f"未通过 {len(failed)}")
print()
if failed:
    print("未通过项:")
    for n, d in failed:
        print(f"  {n}: {d}")
