"""Container structure that the templates lay their documents out with.

A template's appearance is not in its leaf elements. `.title-block` is styled
as a child of `.header`; `.metric` is a grid cell inside `.metrics`; the two
column layout is `.two-col` wrapping two `section`s. A writer that emits only
the leaves produces correct tags and no layout, which is what a visual
comparison found: SSIM 0.135 between the two paths on the same document.

This module states that structure once, so the bridge can group blocks and the
writer can emit the wrappers without either inventing names.

A container declares:
  id         stable identifier, used in the IR
  css        the class the template styles
  children   the block ids that belong inside, in order
  element    the tag to emit
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Container:
    """One wrapper the template expects."""

    id: str
    css: str
    element: str = "div"
    # Block ids that belong in this container, in document order. A block whose
    # id starts with one of these prefixes is drawn inside.
    members: tuple[str, ...] = ()
    # When true, every member is repeated (the template declares four metric
    # cards); the writer emits one child per block rather than per member.
    repeating: bool = False
    # The container this one nests inside, if any. Nesting is part of the
    # template's structure, not an implementation detail: `.header .title-block`
    # is a selector the template relies on.
    parent: str | None = None
    note: str = ""


# Ordered outermost first, so a block is placed in the most specific container
# that claims it and containers nest correctly.
CONTAINERS: tuple[Container, ...] = (
    Container(
        id="header",
        css="header",
        members=("p-eyebrow", "h-title", "p-subtitle", "p-meta"),
        note="Title block and document metadata sit together at the top.",
    ),
    Container(
        id="title-block",
        css="title-block",
        members=("p-eyebrow", "h-title", "p-subtitle"),
        parent="header",
        note="Nested inside header; the template styles the eyebrow through it.",
    ),
    Container(
        id="metrics",
        css="metrics",
        members=("p-metric", "c-metric"),
        repeating=True,
        note="A grid of metric cards; the template declares four.",
    ),
    Container(
        id="metric",
        css="metric",
        members=("p-metric-value", "p-metric-label"),
        parent="metrics",
        note="One card: a value above its label.",
    ),
    Container(
        id="decision-strip",
        css="decision-strip",
        members=("p-decision-label", "p-decision-text", "p-owner"),
        note="The decision bar under the lead.",
    ),
    Container(
        id="timeline",
        css="timeline",
        members=("p-tl-year", "p-stage"),
        repeating=True,
        note="The roadmap, one entry per stage; the template draws each as .tl-year.",
    ),
    Container(
        id="two-col",
        css="two-col",
        element="div",
        # Claims the body sections and their contents, so the two-column region
        # exists rather than the sections stacking in one column.
        members=("h-section", "p-body", "l-observations", "l-evidence", "l-notes",
                 "p-stage-1", "p-explain", "p-stage-2", "p-stage-3"),
        note="Two-column body region; the template lays its sections out here.",
    ),
    Container(
        id="footer",
        css="footer",
        element="div",
        members=("p-footer", "p-confidentiality", "p-page-contact"),
        note="The closing line: confidentiality marker and page reference.",
    ),
)


def container_for(block_id: str) -> Container | None:
    """The innermost container that claims a block.

    Innermost wins so a nested wrapper such as `title-block` takes precedence
    over the `header` that contains it.
    """
    best: Container | None = None
    for container in CONTAINERS:
        if any(block_id == m or block_id.startswith(f"{m}-") for m in container.members):
            if best is None or len(container.members) <= len(best.members):
                best = container
    return best


def containers_in_order(block_ids: list[str]) -> list[tuple[Container, list[str]]]:
    """Group block ids by container, preserving document order.

    Returns the containers that actually received a block, each with its
    members in the order they appear. A container with no members is omitted so
    an empty grid is not emitted.
    """
    grouped: dict[str, list[str]] = {}
    order: list[str] = []
    by_id = {c.id: c for c in CONTAINERS}

    for block_id in block_ids:
        container = container_for(block_id)
        if container is None:
            continue
        if container.id not in grouped:
            grouped[container.id] = []
            order.append(container.id)
        grouped[container.id].append(block_id)

    return [(by_id[cid], grouped[cid]) for cid in order]


def container_chain(container_id: str) -> list[str]:
    """A container and its ancestors, outermost first."""
    by_id = {c.id: c for c in CONTAINERS}
    chain: list[str] = []
    current: str | None = container_id
    guard = 0
    while current is not None:
        guard += 1
        if guard > 16:
            break
        chain.append(current)
        parent = by_id.get(current)
        current = parent.parent if parent else None
    return list(reversed(chain))


def build_tree(block_ids: list[str]) -> list[dict]:
    """Group blocks into the container tree the template lays out with.

    Two phases, deliberately: place every block into its innermost container,
    then create the containers that received something and attach each to its
    parent. A recursive walk was tried first and re-entered containers, because
    a nested wrapper and its ancestor both claim the same blocks.
    """
    by_id = {c.id: c for c in CONTAINERS}

    # Phase 1: which container holds each block, and in what order.
    held: dict[str, list[str]] = {}
    for block_id in block_ids:
        container = container_for(block_id)
        if container is None:
            continue
        held.setdefault(container.id, []).append(block_id)

    # Phase 2: which containers exist, including ancestors of occupied ones.
    present: set[str] = set()
    for container_id in held:
        present.update(container_chain(container_id))

    # Phase 3: attach each present container to its nearest present ancestor.
    children_of: dict[str | None, list[str]] = {}
    for container_id in present:
        container = by_id[container_id]
        parent = container.parent
        if parent is not None and parent not in present:
            parent = None
        children_of.setdefault(parent, []).append(container_id)

    # Where each container first appears, used to order the output.
    position: dict[str, int] = {}
    for index, block_id in enumerate(block_ids):
        container = container_for(block_id)
        if container is None:
            continue
        for ancestor in container_chain(container.id):
            position.setdefault(ancestor, index)

    def node_for(container_id: str) -> dict:
        container = by_id[container_id]
        nested = sorted(
            (node_for(child) for child in children_of.get(container_id, [])),
            key=lambda node: position.get(node["id"], 1 << 30),
        )
        # Blocks this container owns directly, meaning not claimed by a nested
        # container that sits inside it.
        direct: list[dict] = []
        nested_owners = {
            cid: by_id[cid]
            for cid in present
            if by_id[cid].parent == container_id
        }
        for block_id in held.get(container_id, []):
            if any(
                any(block_id == m or block_id.startswith(f"{m}-") for m in nested_container.members)
                for nested_container in nested_owners.values()
            ):
                continue
            direct.append({"kind": "block", "id": block_id})

        # Children in document order: a nested container is placed where its
        # own first block appears, so `title-block` stays above `meta` rather
        # than being sorted after every direct block.
        combined: list[tuple[int, dict]] = []
        for entry in direct:
            combined.append((position.get(container_id, 1 << 30), entry))
        for entry in nested:
            combined.append((position.get(entry["id"], 1 << 30), entry))
        # A stable tie-break keeps a nested container ahead of a sibling block
        # that shares its index, which is the template's arrangement.
        combined.sort(key=lambda pair: (pair[0], 0 if pair[1]["kind"] == "container" else 1))

        return {
            "kind": "container",
            "id": container.id,
            "css": container.css,
            "element": container.element,
            "repeating": container.repeating,
            "children": [entry for _, entry in combined],
        }

    # Interleave ungrouped blocks with the containers by document position, so
    # the lead paragraph stays under the metrics rather than moving to the end.
    entries: list[tuple[int, int, dict]] = []
    for cid in children_of.get(None, []):
        entries.append((position.get(cid, 1 << 30), 0, node_for(cid)))
    for index, block_id in enumerate(block_ids):
        if container_for(block_id) is None:
            entries.append((index, 1, {"kind": "block", "id": block_id}))

    entries.sort(key=lambda item: (item[0], item[1]))
    return [entry for _, _, entry in entries]



def ungrouped(block_ids: list[str]) -> list[str]:
    """Blocks that belong to no container and are emitted on their own."""
    return [b for b in block_ids if container_for(b) is None]
