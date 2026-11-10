"""Markdown report generation.

The report is the point of the whole exercise. It renders each fact together
with the source that produced it, the time it was retrieved and the digest of
the raw evidence, then collects those sources into a numbered bibliography.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Case, Edge, Entity, Provenance


def _escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def render_report(session: Session, case: Case) -> str:
    entities = session.scalars(
        select(Entity).where(Entity.case_id == case.id).order_by(Entity.type, Entity.value)
    ).all()
    edges = session.scalars(select(Edge).where(Edge.case_id == case.id)).all()

    provenance_ids = {
        attr.provenance_id
        for entity in entities
        for attr in entity.attributes
        if attr.provenance_id is not None
    }
    provenances: dict[int, Provenance] = {}
    if provenance_ids:
        for prov in session.scalars(
            select(Provenance).where(Provenance.id.in_(provenance_ids))
        ):
            provenances[prov.id] = prov

    by_source: dict[str, list[Provenance]] = defaultdict(list)
    for prov in provenances.values():
        by_source[prov.source].append(prov)
    source_numbers = {source: index + 1 for index, source in enumerate(sorted(by_source))}

    out: list[str] = []
    out.append(f"# OSINT Report: {case.title}")
    out.append("")
    out.append(f"- **Case:** #{case.id}")
    out.append(f"- **Generated:** {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}")
    out.append(f"- **Scope:** {case.scope_note or '_not recorded_'}")
    out.append("")

    type_counts = defaultdict(int)
    for entity in entities:
        type_counts[entity.type] += 1

    out.append("## Summary")
    out.append("")
    out.append(f"- Entities: **{len(entities)}**")
    out.append(f"- Relationships: **{len(edges)}**")
    out.append(f"- Sources consulted: **{len(by_source)}**")
    if type_counts:
        breakdown = ", ".join(f"{count} {name}" for name, count in sorted(type_counts.items()))
        out.append(f"- Breakdown: {breakdown}")
    out.append("")

    out.append("## Entities")
    out.append("")
    for entity in entities:
        heading = entity.display_name or entity.value
        out.append(f"### {entity.type}: {heading}")
        out.append("")
        if entity.display_name and entity.display_name != entity.value:
            out.append(f"`{entity.value}`")
            out.append("")

        if not entity.attributes:
            out.append("_No attributes collected._")
            out.append("")
            continue

        out.append("| Attribute | Value | Source | Retrieved | Confidence |")
        out.append("| --- | --- | --- | --- | --- |")
        for attr in sorted(entity.attributes, key=lambda a: a.key):
            prov = provenances.get(attr.provenance_id) if attr.provenance_id else None
            if prov is None:
                out.append(f"| `{attr.key}` | {_escape(attr.value)} | _unattributed_ | — | — |")
                continue
            retrieved = prov.retrieved_at.strftime("%Y-%m-%d %H:%M")
            source_ref = f"[{source_numbers[prov.source]}]({prov.url or ''})"
            out.append(
                f"| `{attr.key}` | {_escape(attr.value)} | {source_ref} "
                f"({prov.source}) | {retrieved} | {prov.confidence:.2f} |"
            )
        out.append("")

    if edges:
        out.append("## Relationships")
        out.append("")
        out.append("| From | Relation | To |")
        out.append("| --- | --- | --- |")
        lookup = {entity.id: entity for entity in entities}
        for edge in edges:
            source = lookup.get(edge.source_id)
            target = lookup.get(edge.target_id)
            if source is None or target is None:
                continue
            out.append(
                f"| `{source.value}` | {edge.relation} | `{target.value}` |"
            )
        out.append("")

    out.append("## Sources and legal basis")
    out.append("")
    for source, provs in sorted(by_source.items(), key=lambda item: source_numbers[item[0]]):
        number = source_numbers[source]
        first = provs[0]
        out.append(f"{number}. **{source}** — {first.method}")
        out.append(f"   - Legal basis: {first.legal_basis or '_not recorded_'}")
        if first.url:
            out.append(f"   - Example URL: {first.url}")
        digests = sorted({prov.raw_sha256 for prov in provs if prov.raw_sha256})
        if digests:
            out.append(f"   - Evidence digest: `{digests[0][:16]}…` ({len(digests)} run(s))")
        out.append("")

    out.append("## Evidence manifest")
    out.append("")
    out.append("Raw responses are stored content-addressed next to the database.")
    out.append("")
    out.append("| Source | Retrieved | Raw responses | Digest |")
    out.append("| --- | --- | --- | --- |")
    for prov in sorted(provenances.values(), key=lambda p: (p.source, p.id)):
        try:
            refs = json.loads(prov.evidence_refs or "[]")
        except ValueError:
            refs = []
        digest_cell = f"`{prov.raw_sha256[:16]}`" if prov.raw_sha256 else "offline (no request)"
        out.append(
            f"| {prov.source} | {prov.retrieved_at.strftime('%Y-%m-%d %H:%M')} "
            f"| {len(refs)} | {digest_cell} |"
        )
    out.append("")

    out.append("---")
    out.append("")
    out.append(
        "Generated by osint-lab. Every fact above is attributed to a source and a "
        "retrieval time. Verify before relying on any single source."
    )
    out.append("")

    return "\n".join(out)
