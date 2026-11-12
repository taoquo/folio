# 0010. The origin is a build input

## Status

Accepted.

## Context

A share card is only useful if a crawler can fetch it. `og:url`, `og:image` and
`canonical` must be absolute, because a crawler resolves a relative value
against its own path, not against the page. But a template or a content payload
does not know where the page will be hosted: the same module is built locally,
staged, and published under a different host.

Three shortcuts were rejected. A hard-coded origin in a template makes a local
build advertise the author's host. A payload field would let content change an
address, which is delivery, not meaning. Emitting a relative `og:url` silently
produces a tag that looks valid and points nowhere.

## Decision

The origin is a declared build input, owned by the content that knows where it
will be published.

- A Web series declares `origin` in its `series.json`; the site's own pages
  declare it once in `references/site/share.json`.
- Templates and payloads never contain an origin. `scripts/share_card.py`
  composes absolute head tags; `scripts/build_web.py` passes the declared origin
  through.
- With an origin, the head carries absolute `og:url`, `og:image` and
  `canonical`. Without one, those tags are omitted and the build says why
  rather than emitting a relative address.
- The card URL carries the image's content digest (`share.png?v=<digest>`), so a
  changed card is a changed address and a platform cannot keep serving the old
  picture.

## Consequences

One series builds for any host without editing content, and a missing origin
degrades visibly instead of quietly producing a wrong URL.

The contract is held by the static rules `W-META-01..05` in
`scripts/check_web.py` and the measured rule `V-META-01` in
`scripts/web_verify.py`. The site's own redirect page has a known origin
constant, so its `canonical` is absolute as well.
