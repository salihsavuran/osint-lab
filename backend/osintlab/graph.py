"""Graph projection of a case.

The database is the source of truth; this module only reshapes entities and
edges into something a renderer (Cytoscape in the UI, DOT on the CLI) can
consume.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Edge, Entity


def build_graph(session: Session, case_id: int) -> dict:
    entities = session.scalars(
        select(Entity).where(Entity.case_id == case_id).order_by(Entity.type, Entity.value)
    ).all()
    edges = session.scalars(select(Edge).where(Edge.case_id == case_id)).all()

    degree: dict[int, int] = {}
    for edge in edges:
        degree[edge.source_id] = degree.get(edge.source_id, 0) + 1
        degree[edge.target_id] = degree.get(edge.target_id, 0) + 1

    nodes = [
        {
            "id": entity.id,
            "label": entity.display_name or entity.value,
            "value": entity.value,
            "type": entity.type,
            "degree": degree.get(entity.id, 0),
        }
        for entity in entities
    ]

    links = [
        {
            "id": edge.id,
            "source": edge.source_id,
            "target": edge.target_id,
            "relation": edge.relation,
        }
        for edge in edges
    ]

    return {
        "case_id": case_id,
        "nodes": nodes,
        "edges": links,
        "stats": {
            "entities": len(nodes),
            "relations": len(links),
            "types": _count_by_type(nodes),
        },
    }


def _count_by_type(nodes: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for node in nodes:
        counts[node["type"]] = counts.get(node["type"], 0) + 1
    return counts


def to_dot(graph: dict) -> str:
    """Render the graph as Graphviz DOT for terminal/CI use."""
    colours = {
        "domain": "#4C8BF5",
        "ip": "#34A853",
        "prefix": "#FBBC05",
        "asn": "#EA4335",
        "url": "#9AA0A6",
        "organization": "#A142F4",
        "sanctions": "#D93025",
    }
    lines = ["digraph osint_lab {", "  rankdir=LR;", "  node [shape=box, style=rounded];"]

    for node in graph["nodes"]:
        colour = colours.get(node["type"], "#9AA0A6")
        label = node["value"].replace('"', '\\"')
        lines.append(
            f'  n{node["id"]} [label="{label}", color="{colour}", fontcolor="{colour}"];'
        )

    for edge in graph["edges"]:
        lines.append(
            f'  n{edge["source"]} -> n{edge["target"]} [label="{edge["relation"]}"];'
        )

    lines.append("}")
    return "\n".join(lines)
