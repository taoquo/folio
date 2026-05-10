# Web Workspace

Use this guide for product workspaces and operational UI: dashboards, editors, review queues, admin tools, settings, monitors, and internal control surfaces.

Read `web-foundation.md` first.

## Core Job

A workspace page should help the user inspect state, make decisions, and take repeated action efficiently.

It should not sound like a landing page. Utility copy beats marketing copy.

## Standard Structure

1. Navigation: where the user is.
2. Primary work area: the thing being inspected or edited.
3. Secondary context: inspector, details, filters, history, or help.
4. Status and feedback: what happened, what is selected, what needs attention.

## Layout Patterns

### Two-Pane Editor

Use for document editors, configuration tools, and review flows.

- Left or center: editable document or primary artifact.
- Right: inspector, checks, metadata, or comments.
- Top: concise toolbar with current status.

### Three-Column Workspace

Use for queues and tools with navigation plus detail.

- Left: navigation or list.
- Center: selected item or main table.
- Right: inspector or contextual actions.
- Mobile: list and detail become separate stacked states.

### Dense Table With Filter Rail

Use for admin and monitoring surfaces.

- Filters sit in a rail or compact top band.
- Rows carry primary status, owner, date, and next action.
- Use dividers and alignment before card containers.

### Review Queue

Use for validation, moderation, or QA.

- Queue list.
- Selected item preview.
- Findings or checks.
- Clear accept, reject, rerun, or comment action.

### Operations Dashboard

Use when metrics support action.

- Metrics should connect to a decision or drill-down.
- Avoid identical KPI mosaics.
- Use tables, trend lines, and status rows when they scan better than cards.

## Required States

Workspace UI must account for:

- loading: skeletons matching the real layout
- empty: tells how to populate or start
- error: inline, specific, recoverable
- disabled: explains why action is unavailable when possible
- active/selected: clear without relying only on color
- success: visible but not theatrical

## Motion Patterns

Use:

- button active feedback
- selected-row transition
- inspector open/close
- inline status update
- toast or alert entrance when the user needs confirmation
- loading shimmer only when it matches actual layout blocks

Avoid:

- perpetual animation in dense workspaces
- decorative background motion
- moving tables or controls while the user is targeting them
- large page transitions after small actions

## Copy Rules

Use labels that help operation:

- Selected item
- Last sync
- Review status
- Source checks
- Open findings
- Run verification
- Apply changes

Avoid campaign language, vague promises, and hero-style value propositions inside the tool surface.

## Anti-Patterns

- dashboard made of disconnected cards
- every panel boxed with thick borders
- three equal cards as the default summary
- decorative gradients behind routine controls
- empty states that only say "No data"
- errors that do not say what to do next
- hidden actions that require hover on mobile
