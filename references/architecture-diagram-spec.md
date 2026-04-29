# Architecture Diagram Spec

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
