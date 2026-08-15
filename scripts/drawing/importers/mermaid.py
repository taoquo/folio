from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .ledger import ImportError_, Ledger, MAX_EDGES, MAX_NODES, _clean_label, _slug, local_source

HEADER_RE = re.compile(r"^(flowchart|graph|sequenceDiagram|stateDiagram(?:-v2)?|erDiagram|classDiagram)\b(.*)$")
COMMENT_RE = re.compile(r"^\s*%%")
DIRECTIVE_RE = re.compile(r"^\s*(?:%%\{|click |style |classDef |linkStyle |class )")

FLOW_SHAPES = (
    (re.compile(r"^(?P<id>[A-Za-z0-9_.-]+)\(\((?P<label>[^)]*)\)\)$"), "terminal"),
    (re.compile(r"^(?P<id>[A-Za-z0-9_.-]+)\{(?P<label>[^}]*)\}$"), "decision"),
    (re.compile(r"^(?P<id>[A-Za-z0-9_.-]+)\(\[(?P<label>[^\]]*)\]\)$"), "terminal"),
    (re.compile(r"^(?P<id>[A-Za-z0-9_.-]+)\[\[(?P<label>[^\]]*)\]\]$"), "subprocess"),
    (re.compile(r"^(?P<id>[A-Za-z0-9_.-]+)\[/(?P<label>[^/]*)/\]$"), "data"),
    (re.compile(r"^(?P<id>[A-Za-z0-9_.-]+)\((?P<label>[^)]*)\)$"), "terminal"),
    (re.compile(r"^(?P<id>[A-Za-z0-9_.-]+)\[(?P<label>[^\]]*)\]$"), "step"),
    (re.compile(r"^(?P<id>[A-Za-z0-9_.-]+)$"), "step"),
)
FLOW_EDGE_RE = re.compile(
    r"^(?P<source>.+?)\s*(?P<arrow>-{2,3}>|-{2,3}|={2,3}>|-\.->|-\.-)\s*(?:\|(?P<label>[^|]*)\|\s*)?(?P<target>.+?)$"
)


def load_mermaid_diagram(path: str | Path, *, base: Path | None = None) -> tuple[dict[str, Any], Ledger]:
    source = local_source(path, base=base or Path.cwd())
    text = source.read_text(encoding="utf-8")
    lines = _significant_lines(text)
    if not lines:
        raise ImportError_("mermaid source has no diagram statements")
    header = HEADER_RE.match(lines[0])
    if not header:
        raise ImportError_("mermaid source must start with a supported diagram header")
    keyword = header.group(1)
    body = lines[1:]
    if keyword in {"flowchart", "graph"}:
        return _flowchart(source, header.group(2).strip(), body)
    if keyword == "sequenceDiagram":
        return _sequence(source, body)
    if keyword.startswith("stateDiagram"):
        return _state_machine(source, body)
    if keyword == "erDiagram":
        return _er(source, body)
    return _class(source, body)


def _significant_lines(text: str) -> list[str]:
    result: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or COMMENT_RE.match(line):
            continue
        result.append(line)
    return result


def _title_from(source: Path, fallback: str) -> str:
    stem = source.stem.replace("-", " ").replace("_", " ").strip()
    return stem.title() if stem else fallback


def _register_flow_node(token: str, nodes: dict[str, dict[str, Any]], ids: dict[str, str], ledger: Ledger) -> str:
    token = token.strip()
    for pattern, role in FLOW_SHAPES:
        match = pattern.match(token)
        if not match:
            continue
        raw_id = match.group("id")
        node_id = _slug(raw_id, ids)
        label = _clean_label(match.groupdict().get("label") or raw_id) or raw_id
        existing = nodes.get(node_id)
        if existing is None:
            nodes[node_id] = {"id": node_id, "type": role, "label": label[:56]}
        elif match.groupdict().get("label"):
            existing["label"] = label[:56]
            existing["type"] = role
        return node_id
    raise ImportError_(f"unsupported mermaid node token: {token[:32]}")


def _flowchart(source: Path, direction: str, body: list[str]) -> tuple[dict[str, Any], Ledger]:
    ledger = Ledger(source.name, "mermaid", "flowchart")
    axis = "left-right" if direction.upper().startswith(("LR", "RL")) else "top-down"
    ledger.keep("direction", axis)
    nodes: dict[str, dict[str, Any]] = {}
    ids: dict[str, str] = {}
    edges: list[dict[str, Any]] = []
    for line in body:
        if DIRECTIVE_RE.match(line):
            ledger.drop("styling", line[:40])
            continue
        if line.startswith("subgraph") or line == "end":
            ledger.drop("subgraph", line[:40])
            continue
        match = FLOW_EDGE_RE.match(line)
        if match:
            source_id = _register_flow_node(match.group("source"), nodes, ids, ledger)
            target_id = _register_flow_node(match.group("target"), nodes, ids, ledger)
            label = _clean_label(match.group("label") or "")
            arrow = match.group("arrow")
            kind = "sequence-flow"
            if label:
                kind = "conditional-flow"
            if arrow.startswith("-."):
                kind = "exception-flow"
                ledger.downgrade("dotted edge", "mapped to exception-flow")
            if arrow.startswith("="):
                ledger.downgrade("thick edge", "mapped to sequence-flow")
            edge: dict[str, Any] = {"source": source_id, "target": target_id, "kind": kind}
            if label:
                edge["label"] = label[:24]
            edges.append(edge)
            continue
        _register_flow_node(line, nodes, ids, ledger)
    if not nodes:
        raise ImportError_("mermaid flowchart has no nodes")
    _bound(nodes, edges)
    ledger.keep("nodes", str(len(nodes)))
    ledger.keep("edges", str(len(edges)))
    payload = {
        "schema_version": "2.0",
        "kind": "flowchart",
        "title": _title_from(source, "Imported Flowchart"),
        "axis": axis,
        "nodes": list(nodes.values()),
        "edges": edges,
    }
    return payload, ledger


def _bound(nodes: dict[str, Any], edges: list[Any]) -> None:
    if len(nodes) > MAX_NODES:
        raise ImportError_(f"import exceeds {MAX_NODES} nodes; split the diagram before importing")
    if len(edges) > MAX_EDGES:
        raise ImportError_(f"import exceeds {MAX_EDGES} edges; split the diagram before importing")


SEQ_MESSAGE_RE = re.compile(
    r"^(?P<source>[A-Za-z0-9_.-]+)\s*(?P<arrow>-->>|--\)|-->|->>|->|-\))\s*"
    r"(?P<target>[A-Za-z0-9_.-]+)\s*:\s*(?P<label>.+)$"
)
SEQ_PARTICIPANT_RE = re.compile(r"^(participant|actor)\s+(?P<id>[A-Za-z0-9_.-]+)(?:\s+as\s+(?P<label>.+))?$")


def _sequence(source: Path, body: list[str]) -> tuple[dict[str, Any], Ledger]:
    ledger = Ledger(source.name, "mermaid", "sequence")
    participants: dict[str, dict[str, Any]] = {}
    ids: dict[str, str] = {}
    messages: list[dict[str, Any]] = []

    def participant(raw: str, kind: str = "system") -> str:
        pid = _slug(raw, ids)
        if pid not in participants:
            participants[pid] = {"id": pid, "label": _clean_label(raw)[:24], "kind": kind}
        return pid

    for line in body:
        declared = SEQ_PARTICIPANT_RE.match(line)
        if declared:
            pid = participant(declared.group("id"), "actor" if line.startswith("actor") else "system")
            if declared.group("label"):
                participants[pid]["label"] = _clean_label(declared.group("label"))[:24]
            continue
        if line.startswith(("note ", "Note ", "loop", "alt", "else", "opt", "par", "end", "activate", "deactivate", "rect", "autonumber")):
            ledger.drop("sequence block", line[:40])
            continue
        match = SEQ_MESSAGE_RE.match(line)
        if not match:
            ledger.drop("statement", line[:40])
            continue
        source_id = participant(match.group("source"))
        target_id = participant(match.group("target"))
        arrow = match.group("arrow")
        kind = "return" if arrow.startswith("--") else "async" if arrow.endswith(")") else "sync"
        label = _clean_label(match.group("label"))[:32]
        if source_id == target_id:
            ledger.drop("self message", label)
            continue
        messages.append({
            "id": f"m{len(messages) + 1}",
            "source": source_id,
            "target": target_id,
            "label": label,
            "kind": kind,
        })
    if len(participants) < 2 or not messages:
        raise ImportError_("mermaid sequence requires at least two participants and one message")
    _bound(participants, messages)
    ledger.keep("participants", str(len(participants)))
    ledger.keep("messages", str(len(messages)))
    payload = {
        "schema_version": "3.0",
        "kind": "sequence",
        "title": _title_from(source, "Imported Sequence"),
        "participants": list(participants.values()),
        "messages": messages,
    }
    return payload, ledger


STATE_EDGE_RE = re.compile(r"^(?P<source>\[\*\]|[A-Za-z0-9_.-]+)\s*-->\s*(?P<target>\[\*\]|[A-Za-z0-9_.-]+)\s*(?::\s*(?P<label>.+))?$")
STATE_ALIAS_RE = re.compile(r"^state\s+\"(?P<label>[^\"]+)\"\s+as\s+(?P<id>[A-Za-z0-9_.-]+)$")


def _state_machine(source: Path, body: list[str]) -> tuple[dict[str, Any], Ledger]:
    ledger = Ledger(source.name, "mermaid", "state-machine")
    ids: dict[str, str] = {}
    labels: dict[str, str] = {}
    order: list[str] = []
    transitions: list[dict[str, Any]] = []
    used_initial = False
    used_final = False

    def state(raw: str, position: str) -> str:
        nonlocal used_initial, used_final
        if raw == "[*]":
            if position == "source":
                used_initial = True
                if "initial" not in order:
                    order.insert(0, "initial")
                return "initial"
            used_final = True
            if "final" not in order:
                order.append("final")
            return "final"
        sid = _slug(raw, ids)
        if sid not in order:
            order.append(sid)
            labels.setdefault(sid, _clean_label(raw)[:24])
        return sid

    for line in body:
        alias = STATE_ALIAS_RE.match(line)
        if alias:
            sid = _slug(alias.group("id"), ids)
            labels[sid] = _clean_label(alias.group("label"))[:24]
            if sid not in order:
                order.append(sid)
            continue
        if line.startswith(("note", "state ", "direction", "classDef", "class ")):
            ledger.drop("state block", line[:40])
            continue
        match = STATE_EDGE_RE.match(line)
        if not match:
            ledger.drop("statement", line[:40])
            continue
        source_id = state(match.group("source"), "source")
        target_id = state(match.group("target"), "target")
        transition: dict[str, Any] = {
            "id": f"t{len(transitions) + 1}",
            "source": source_id,
            "target": target_id,
        }
        label = _clean_label(match.group("label") or "")
        if label:
            transition["event"] = label.split("/")[0].strip()[:20]
        transitions.append(transition)
    if not transitions:
        raise ImportError_("mermaid state diagram has no transitions")
    states: list[dict[str, Any]] = []
    for sid in order:
        if sid == "initial":
            states.append({"id": "initial", "type": "initial"})
        elif sid == "final":
            states.append({"id": "final", "type": "final"})
        else:
            states.append({"id": sid, "type": "state", "label": labels.get(sid, sid)})
    if not used_initial:
        raise ImportError_("mermaid state diagram requires one [*] entry transition")
    if not used_final:
        ledger.downgrade("terminal state", "no [*] exit found; imported as persistent")
    _bound({item["id"]: item for item in states}, transitions)
    ledger.keep("states", str(len(states)))
    ledger.keep("transitions", str(len(transitions)))
    payload: dict[str, Any] = {
        "schema_version": "3.0",
        "kind": "state-machine",
        "title": _title_from(source, "Imported State Machine"),
        "states": states,
        "transitions": transitions,
    }
    if not used_final:
        payload["persistent"] = True
    return payload, ledger


ER_BLOCK_RE = re.compile(r"^(?P<name>[A-Za-z0-9_.-]+)\s*\{$")
ER_FIELD_RE = re.compile(r"^(?P<type>[A-Za-z0-9_\[\]()]+)\s+(?P<name>[A-Za-z0-9_.-]+)(?P<rest>.*)$")
ER_REL_RE = re.compile(
    r"^(?P<source>[A-Za-z0-9_.-]+)\s+(?P<left>\|o|\|\||\}o|\}\|)(?P<line>--|\.\.)(?P<right>o\||\|\||o\{|\|\{)\s+(?P<target>[A-Za-z0-9_.-]+)\s*:\s*(?P<label>.+)$"
)
ER_CARDINALITY = {"|o": "zero-or-one", "||": "one", "}o": "many", "}|": "one-or-many",
                  "o|": "zero-or-one", "o{": "many", "|{": "one-or-many"}


def _er(source: Path, body: list[str]) -> tuple[dict[str, Any], Ledger]:
    ledger = Ledger(source.name, "mermaid", "er-diagram")
    ids: dict[str, str] = {}
    entities: dict[str, dict[str, Any]] = {}
    relationships: list[dict[str, Any]] = []
    current: str | None = None

    def entity(raw: str) -> str:
        eid = _slug(raw, ids)
        entities.setdefault(eid, {"id": eid, "name": _clean_label(raw)[:24], "fields": []})
        return eid

    for line in body:
        if current is not None:
            if line == "}":
                current = None
                continue
            field = ER_FIELD_RE.match(line)
            if not field:
                ledger.drop("field", line[:40])
                continue
            rest = field.group("rest")
            record: dict[str, Any] = {
                "id": field.group("name"),
                "name": field.group("name")[:20],
                "type": field.group("type")[:12],
            }
            if re.search(r"\bPK\b", rest):
                record["primary_key"] = True
            if re.search(r"\bFK\b", rest):
                record["foreign_key"] = True
            if re.search(r"\bUK\b", rest):
                ledger.downgrade("unique key", f"{field.group('name')} UK flag dropped")
            entities[current]["fields"].append(record)
            continue
        block = ER_BLOCK_RE.match(line)
        if block:
            current = entity(block.group("name"))
            continue
        match = ER_REL_RE.match(line)
        if not match:
            ledger.drop("statement", line[:40])
            continue
        source_id = entity(match.group("source"))
        target_id = entity(match.group("target"))
        if match.group("line") == "..":
            ledger.downgrade("non-identifying relationship", "rendered as a solid route")
        relationships.append({
            "id": f"r{len(relationships) + 1}",
            "source": source_id,
            "target": target_id,
            "label": _clean_label(match.group("label"))[:20],
            "source_cardinality": ER_CARDINALITY[match.group("left")],
            "target_cardinality": ER_CARDINALITY[match.group("right")],
        })
    if len(entities) < 2 or not relationships:
        raise ImportError_("mermaid ER diagram requires at least two entities and one relationship")
    for item in entities.values():
        if not item["fields"]:
            item["fields"] = [{"id": "id", "name": "id", "type": "text", "primary_key": True}]
            ledger.downgrade("entity fields", f"{item['id']} had no attribute block; added a synthetic key")
        elif not any(field.get("primary_key") for field in item["fields"]):
            item["fields"][0]["primary_key"] = True
            ledger.downgrade("primary key", f"{item['id']} first field promoted to PK")
        if len(item["fields"]) > 8:
            ledger.drop("fields", f"{item['id']} truncated to 8 fields")
            item["fields"] = item["fields"][:8]
    _bound(entities, relationships)
    ledger.keep("entities", str(len(entities)))
    ledger.keep("relationships", str(len(relationships)))
    payload = {
        "schema_version": "3.0",
        "kind": "er-diagram",
        "title": _title_from(source, "Imported ER Diagram"),
        "entities": list(entities.values()),
        "relationships": relationships,
    }
    return payload, ledger


CLASS_BLOCK_RE = re.compile(r"^class\s+(?P<name>[A-Za-z0-9_.-]+)\s*\{$")
CLASS_MEMBER_RE = re.compile(r"^(?P<visibility>[+\-#~])?\s*(?P<body>.+)$")
CLASS_REL_RE = re.compile(
    r"^(?P<source>[A-Za-z0-9_.-]+)\s+(?P<arrow><\|--|--\|>|\*--|--\*|o--|--o|-->|<--|--)\s+(?P<target>[A-Za-z0-9_.-]+)\s*(?::\s*(?P<label>.+))?$"
)
CLASS_KIND = {"<|--": "inheritance", "--|>": "inheritance", "*--": "composition", "--*": "composition",
              "o--": "aggregation", "--o": "aggregation", "-->": "association", "<--": "association", "--": "association"}


def _class(source: Path, body: list[str]) -> tuple[dict[str, Any], Ledger]:
    ledger = Ledger(source.name, "mermaid", "uml-class")
    ids: dict[str, str] = {}
    types: dict[str, dict[str, Any]] = {}
    relationships: list[dict[str, Any]] = []
    current: str | None = None

    def declare(raw: str) -> str:
        tid = _slug(raw, ids)
        types.setdefault(tid, {"id": tid, "kind": "class", "name": _clean_label(raw)[:24], "attributes": [], "methods": []})
        return tid

    for line in body:
        if current is not None:
            if line == "}":
                current = None
                continue
            if line.startswith("<<") and line.endswith(">>"):
                stereotype = line.strip("<>").strip()
                types[current]["kind"] = "interface" if stereotype.lower() == "interface" else "enum" if stereotype.lower() == "enumeration" else "class"
                continue
            member = CLASS_MEMBER_RE.match(line)
            if not member:
                ledger.drop("member", line[:40])
                continue
            text = _clean_label(member.group("body"))[:40]
            if "(" in text:
                types[current]["methods"].append(text)
            else:
                types[current]["attributes"].append(text)
            if member.group("visibility") not in (None, "+"):
                ledger.downgrade("visibility", f"{text} marker {member.group('visibility')} dropped")
            continue
        block = CLASS_BLOCK_RE.match(line)
        if block:
            current = declare(block.group("name"))
            continue
        if line.startswith("class "):
            declare(line.split()[1])
            continue
        match = CLASS_REL_RE.match(line)
        if not match:
            ledger.drop("statement", line[:40])
            continue
        arrow = match.group("arrow")
        left, right = declare(match.group("source")), declare(match.group("target"))
        if arrow in {"<|--", "--*", "--o", "<--"}:
            left, right = right, left
        relationship: dict[str, Any] = {
            "id": f"rel{len(relationships) + 1}",
            "source": left,
            "target": right,
            "kind": CLASS_KIND[arrow],
        }
        label = _clean_label(match.group("label") or "")
        if label:
            relationship["label"] = label[:16]
        relationships.append(relationship)
    if not types:
        raise ImportError_("mermaid class diagram has no types")
    for item in types.values():
        for field, limit in (("attributes", 6), ("methods", 5)):
            if len(item[field]) > limit:
                ledger.drop(field, f"{item['id']} truncated to {limit}")
                item[field] = item[field][:limit]
    _bound(types, relationships)
    ledger.keep("types", str(len(types)))
    ledger.keep("relationships", str(len(relationships)))
    payload = {
        "schema_version": "3.0",
        "kind": "uml-class",
        "title": _title_from(source, "Imported Class Diagram"),
        "layout": "class-grid",
        "types": list(types.values()),
        "relationships": relationships,
    }
    return payload, ledger
