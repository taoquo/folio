# Web Checklist

Use this checklist before and after Web design work with Folio.

## 1. Choose The Mode

Pick one primary mode:

- Reading / Publication: the user reads, evaluates, cites, or shares content.
- Workspace / Product UI: the user inspects state, edits, reviews, monitors, or acts repeatedly.
- Mixed: separate reading regions from workspace regions; do not blend article hierarchy and app controls into one ambiguous surface.

## 2. Before Design

Confirm:

- page goal
- archetype: Reading, Workspace, or Hybrid
- primary object or argument for the first viewport
- orientation mechanism: contents, progress, nav, selected item, or status band
- content plan: required content regions, evidence, actions, and feedback in page order
- primary audience
- primary content or data
- required user actions
- required states
- source or material requirements
- mobile behavior
- motion thesis: 2-3 movements using the Motion Thesis Template; mark omitted layers with `Not used because ...`
- whether this is guidance, mockup, or implementation code

## 3. During Design

Check:

- the first viewport explains the page job
- the primary object or argument appears early
- one focal path is visible per viewport
- parchment or warm base is present where Folio identity matters
- cinnabar-coral has one clear job
- warm neutrals are used instead of cool grays
- cards are used only for real repeated or selectable objects
- headings summarize the page or section
- motion maps to page, region, object, or control semantics
- each motion can be written as `This motion means ...`
- at least one motion is normally page, region, or object level, not only hover, active, or focus
- mobile layout is not an afterthought
- focus, hover, active, selected, disabled, loading, empty, and error states are considered when relevant
- dense workspace regions use functional alignment, tables, rows, and labels rather than document cover styling

## 4. Reading Page Review

Pass standard:

- The title block establishes topic and context.
- The section headings summarize the argument.
- Long pages provide orientation through contents, progress, or visible section structure.
- Figures include insight captions.
- Sources or footnotes are findable.
- Motion does not interrupt reading.
- The reading measure stays comfortable on desktop and mobile.
- Decorative imagery does not replace evidence or source treatment.

## 5. Workspace Review

Pass standard:

- The user can tell where they are, what is selected, and what action is available.
- The primary work area is visually dominant.
- Secondary context is useful but not louder than the work.
- Loading, empty, error, disabled, selected, and success states exist where needed.
- Metrics and tables support decisions.
- Copy sounds like product UI, not a landing page.
- Tables, queues, filters, editors, and logs use functional density instead of editorial whitespace when needed.
- Inspectors, drawers, or detail panels preserve the selected object's context.

## 6. Output Contract

Before finalizing design guidance or implementation, ensure the answer or internal design includes:

- visual thesis
- page job
- archetype
- content plan
- primary object
- page skeleton
- interaction thesis using the Motion Thesis Template
- state coverage
- mobile collapse plan
- final quality gate

## 7. Final Gate

Reject the design if:

- it looks like a generic SaaS card grid
- it depends on a second accent color
- it uses cool gray defaults
- it hides core content behind hover or motion
- it overpromises Web output as part of Folio's static build system
- it cannot explain its motion choices in one sentence
- all motion choices are only hover, active, or focus states
- it starts from components instead of page job
- it forces document-cover styling into dense operational UI
- it cannot be understood by scanning headings, labels, and numbers
- it depends on hover for mobile-critical actions
- it has more than one primary focal path in the same viewport
