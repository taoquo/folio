# API stability levels

The plan asks every public surface to declare what it promises. Without that,
a caller cannot tell whether a function is a contract or an implementation
detail, and a change that is safe in one case is a breaking change in the other.

Three levels, and what each one means:

| Level | Promise |
|---|---|
| **Public stable** | Changing this needs a version bump and a migration note. Callers may depend on it. |
| **Internal** | May change without notice. Reaching into it couples you to this release. |
| **Experimental** | Actively being shaped. Useful to try; not something to build on. |

## Public stable

### Document IR

| Surface | Module |
|---|---|
| `Document`, `Block`, `Metadata`, `ProfileRefs` | `document_ir/model.py` |
| `Text`, `Emphasis`, `Strong`, `Link`, `Citation`, `CrossRef` | `document_ir/model.py` |
| `ListItem`, `TableColumn`, `TableRow`, `BibliographyEntry` | `document_ir/model.py` |
| `read`, `document_from_data` | `document_ir/readers/structured.py` |
| `validate`, `ValidationReport`, `Diagnostic` | `document_ir/validate.py` |
| `bridge_template`, `default_map_for`, `BridgeMap` | `document_ir/bridge.py` |
| `supported_versions`, `migrate` | `document_ir/migrations.py` |

The IR schema version is independent of the Folio release version. Only a
breaking semantic change raises it, and `migrations.py` is where that is
recorded.

### Rendering

| Surface | Module |
|---|---|
| `Renderer`, `RenderRequest`, `ArtifactSet` | `renderers/base.py` |
| `RendererInfo`, `CapabilityReport`, `Downgrade` | `renderers/base.py` |
| `negotiate` | `renderers/base.py` |
| `FOLIO_PIPELINE` and its three values | `pipeline.py` |
| `BuildManifest`, `capture` | `build_manifest.py` |

### Projection

| Surface | Module |
|---|---|
| `FOLIO_STYLE_PROJECTION`, `FOLIO_LAYOUT_POLICY`, `FOLIO_BUILD_MANIFEST` | `document_build.py` |
| `projection.check`, `projection.inject` | `projection.py` |
| `BuildOutcome` | `document_build.py` |
| `spacing_probe.measure`, `spacing_probe.compare` | `spacing_probe.py` |

The switch names and their meaning are stable. The CSS a projection generates is
not: it is an implementation of the style model, and it changes when the model
does. A caller depends on `FOLIO_STYLE_PROJECTION=off` restoring the previous
rendering, not on the text of the injected block.

### Command line

| Command | Promise |
|---|---|
| `build.py` | Builds artifacts. Writes to the workspace. |
| `build.py --verify` | **Reads only.** A write is a failure of the check. |
| `document_baseline.py compare` | Reads. |
| `document_baseline.py capture --approval-reason` | Writes, and requires a reason. |
| `fidelity.py measure` | Reads. |
| `quality_vector.py` | Reads. |

The four diagnostic commands — `pipeline.py status`, `migration.py matrix`,
`language_support.py report`, `corpus_matrix.py report` — report state and do
not change it.

## Internal

| Surface | Why it is not public |
|---|---|
| `document_ir/writers/skeleton.py` | Fills a specific template. A template change alters it. |
| `document_ir/writers/html.py` | Class names and element choices are a template's business. |
| `document_ir/containers.py` | Records the structure of today's templates. |
| `shadow.py` | A comparison harness, not a product surface. |
| `visual_diff.py` internals | The SSIM implementation may change; the thresholds are the contract. |
| `projection.py` internals | The generated CSS follows the model; the switches are the contract. |
| `spacing_probe.py` thresholds | The block-gap factor is a measurement heuristic and may be recalibrated. |
| `stabilize.py` | Being retired into the layout policy. |

## Experimental

| Surface | Status |
|---|---|
| `document_ir/layout_policy.py` | The model exists; nothing renders from it yet. |
| `spacing.py` | Declares gaps; the templates still decide them. |
| `document_ir/writers/pptx.py` | Produces decks; has no template path to compare against. |
| `layout_experiment.py` | A measurement harness for a decision not yet taken. |
| `spacing.py` | Declares gaps; `spacing_probe.py` compares them with a page but nothing renders from them. |

Experimental surfaces do not enter a stable schema. An experimental field that
grows a consumer is promoted by moving it into this document, not by leaving it
marked and hoping.

## What is deliberately not promised

- The shape of a rendered page. Fidelity is measured against the template path;
  the page itself is not an API.
- The set of CSS classes a writer emits. That belongs to the template.
- Asset file hashes. They change when a diagram is rebuilt, which is normal.
