# Architecture Diagram Spec

This JSON shape is the compatibility facade for existing callers. Internally, Folio converts it to `SemanticDiagram`, plans a `DrawingPlan`, compiles layout constraints, resolves a `ResolvedScene`, and renders that scene. New visual behavior belongs in the executable Drawing Grammar rather than new pixel-level JSON fields.

See `drawing-dsl.md` and `drawing-architecture.md` for the V1 compiler contract.

Use `kind: "architecture"` with one of:

- `horizontal-layers`
- `vertical-stack`
- `hub-and-spoke`

Required fields:

- `title`
- `layout`
- `nodes`
- `edges`

Optional semantic planning fields:

- `focus_path`
- `focus_reason`
- `groups`
- `legend`

Optional layout policy fields:

- `layers[].row_policy`
- `groups[].layout_policy`

Node kinds:

- `external`
- `service`
- `store`
- `cloud`

Edge kinds:

- `primary`
- `secondary`
- `async`

Node semantic fields:

- `role`
- `group`
- `description`
- `importance`
- `state_owner`
- `lifecycle_phase`

Recommended role values:

- `entry`
- `scheduler`
- `orchestrator`
- `executor`
- `world`
- `system`
- `query-engine`
- `cache`
- `resource-loader`
- `storage`
- `event-bus`
- `renderer`
- `tool-runtime`

Recommended row policy values:

- `centered`
- `pipeline`
- `attachments-right`

Recommended group layout policy values:

- `center-band`
- `pipeline`
- `sidecar`
- `stack`

Edge semantic fields:

- `flow`
- `interaction`
- `priority`
- `dashed`
- `source_port`
- `target_port`
- `route_hint`
- `phase`

Recommended flow values:

- `control`
- `read`
- `write`
- `query`
- `event`
- `stream`
- `sync`
- `async`
