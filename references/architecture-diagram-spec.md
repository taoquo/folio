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

Node kinds:

- `external`
- `service`
- `store`
- `cloud`

Edge kinds:

- `primary`
- `secondary`
- `async`
