"""Collection orchestration.

This is the only place where collectors, the database and the evidence store
meet. Keeping it in one module makes the guarantees easy to audit:

* every fact is written together with a provenance row,
* every run writes an audit event,
* a failing collector never aborts the whole run,
* entity and edge creation is idempotent.
"""

from __future__ import annotations

import ipaddress
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .cache import Cache
from .collectors.base import (
    CollectContext,
    Collector,
    collectors_for,
)
from .config import Settings
from .config import settings as default_settings
from .evidence import EvidenceStore, digest
from .fetch import Fetcher, FetchError
from .models import Attribute, AuditEvent, Case, Edge, Entity, Provenance
from .ratelimit import RateLimiter

_PHONE_SEPARATORS = str.maketrans("", "", " -()./")


def _looks_like_phone(value: str) -> bool:
    compact = value.translate(_PHONE_SEPARATORS)
    if not compact:
        return False
    digits = compact[1:] if compact.startswith("+") else compact
    if not digits.isdigit():
        return False
    return 7 <= len(digits) <= 15


def infer_entity_type(target: str) -> str:
    value = target.strip()
    if value.startswith(("http://", "https://")):
        return "url"

    candidate = value.split("/")[0].strip("[]")

    # Let the standard library decide what an address is; hand-rolling IPv6
    # detection is a reliable way to get it wrong.
    probes = [candidate]
    if candidate.count(":") == 1:  # host:port form
        probes.append(candidate.rsplit(":", 1)[0])

    for probe in probes:
        try:
            ipaddress.ip_address(probe)
            return "ip"
        except ValueError:
            continue

    if _looks_like_phone(candidate):
        return "phone"

    if "." in candidate and " " not in candidate:
        return "domain"
    return "organization"


@dataclass
class CollectorRun:
    collector_id: str
    label: str
    status: str = "ok"
    facts: int = 0
    links: int = 0
    notes: list[str] = field(default_factory=list)
    error: str | None = None
    provenance_id: int | None = None


@dataclass
class RunSummary:
    case_id: int
    target: str
    entity_id: int
    entity_type: str
    runs: list[CollectorRun] = field(default_factory=list)

    @property
    def ok(self) -> int:
        return sum(1 for run in self.runs if run.status == "ok")

    @property
    def failed(self) -> int:
        return sum(1 for run in self.runs if run.status == "error")


class CollectorService:
    #: Shared across services in one process so rate limits actually hold
    #: between API requests, not just within a single collection run.
    _limiter = RateLimiter()

    def __init__(
        self,
        session: Session,
        *,
        config: Settings | None = None,
        fetcher: Fetcher | None = None,
        store: EvidenceStore | None = None,
    ) -> None:
        self.session = session
        self.settings = config or default_settings
        self.store = store or EvidenceStore()
        self.cache = Cache(session, self.store)
        self.fetcher = fetcher or Fetcher(
            self.cache, self.store, CollectorService._limiter, self.settings
        )

    # -- entities ----------------------------------------------------------

    def ensure_entity(
        self,
        case_id: int,
        entity_type: str,
        value: str,
        display_name: str = "",
    ) -> Entity:
        value = value.strip()
        existing = self.session.scalar(
            select(Entity).where(
                Entity.case_id == case_id,
                Entity.type == entity_type,
                Entity.value == value,
            )
        )
        if existing is not None:
            if display_name and not existing.display_name:
                existing.display_name = display_name
            return existing

        entity = Entity(
            case_id=case_id,
            type=entity_type,
            value=value,
            display_name=display_name,
        )
        self.session.add(entity)
        self.session.flush()
        return entity

    # -- audit -------------------------------------------------------------

    def audit(
        self,
        case_id: int | None,
        action: str,
        target: str = "",
        detail: str = "",
        actor: str = "local",
    ) -> AuditEvent:
        event = AuditEvent(
            case_id=case_id, action=action, target=target, detail=detail, actor=actor
        )
        self.session.add(event)
        self.session.flush()
        return event

    # -- collection --------------------------------------------------------

    def _select(self, entity_type: str, wanted: list[str] | None) -> list[Collector]:
        candidates = collectors_for(entity_type)
        if wanted:
            allowed = set(wanted)
            candidates = [c for c in candidates if c.id in allowed]
        return sorted(candidates, key=lambda c: c.priority)

    def _children(self, case_id: int, entity_id: int) -> list[Entity]:
        edges = self.session.scalars(
            select(Edge).where(Edge.case_id == case_id, Edge.source_id == entity_id)
        ).all()
        children: list[Entity] = []
        for edge in edges:
            child = self.session.get(Entity, edge.target_id)
            if child is not None:
                children.append(child)
        return children

    def run(
        self,
        case: Case,
        target: str,
        *,
        collector_ids: list[str] | None = None,
        depth: int = 0,
        max_entities: int = 15,
    ) -> RunSummary:
        entity_type = infer_entity_type(target)
        root = self.ensure_entity(case.id, entity_type, target)
        self.audit(
            case.id,
            "collect_start",
            target,
            json.dumps({"type": entity_type, "depth": depth, "collectors": collector_ids}),
        )

        summary = RunSummary(
            case_id=case.id,
            target=target,
            entity_id=root.id,
            entity_type=entity_type,
        )

        queue: list[tuple[int, int]] = [(root.id, 0)]
        processed: set[int] = set()

        while queue:
            entity_id, level = queue.pop(0)
            if entity_id in processed:
                continue
            if len(processed) >= max_entities:
                summary.runs.append(
                    CollectorRun(
                        collector_id="*",
                        label="expansion limit",
                        status="skipped",
                        notes=[f"stopped after {max_entities} entities"],
                    )
                )
                break

            entity = self.session.get(Entity, entity_id)
            if entity is None:
                continue
            processed.add(entity_id)

            for collector in self._select(entity.type, collector_ids):
                summary.runs.append(self._run_one(case, entity, collector))

            if level < depth:
                for child in self._children(case.id, entity_id):
                    if child.id not in processed:
                        queue.append((child.id, level + 1))

        self.audit(
            case.id,
            "collect_finish",
            target,
            json.dumps(
                {
                    "ok": summary.ok,
                    "failed": summary.failed,
                    "entities": len(processed),
                }
            ),
        )
        return summary

    def _run_one(self, case: Case, entity: Entity, collector: Collector) -> CollectorRun:
        ctx = CollectContext(
            entity_type=entity.type,
            value=entity.value,
            fetcher=self.fetcher,
            settings=self.settings,
        )

        try:
            result = collector.collect(ctx)
        except FetchError as exc:
            self.audit(case.id, "collect_error", entity.value, f"{collector.id}: {exc}")
            return CollectorRun(
                collector_id=collector.id,
                label=collector.label,
                status="error",
                error=str(exc),
            )
        except Exception as exc:  # noqa: BLE001 - a bad collector must not kill the run
            self.audit(
                case.id,
                "collect_error",
                entity.value,
                f"{collector.id}: {type(exc).__name__}: {exc}",
            )
            return CollectorRun(
                collector_id=collector.id,
                label=collector.label,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )

        provenance = self._record_provenance(collector, ctx, result)

        existing = {
            (attr.key, attr.value)
            for attr in self.session.scalars(
                select(Attribute).where(Attribute.entity_id == entity.id)
            )
        }

        seen: set[tuple[str, str]] = set()
        for fact in result.facts:
            key = (fact.key, fact.value)
            if key in seen or key in existing:
                continue
            seen.add(key)
            self.session.add(
                Attribute(
                    entity_id=entity.id,
                    key=fact.key,
                    value=fact.value,
                    provenance_id=provenance.id,
                )
            )

        linked = 0
        for link in result.links:
            other = self.ensure_entity(
                case.id, link.type, link.value, link.display_name
            )
            if other.id == entity.id:
                continue
            exists = self.session.scalar(
                select(Edge).where(
                    Edge.case_id == case.id,
                    Edge.source_id == entity.id,
                    Edge.target_id == other.id,
                    Edge.relation == link.relation,
                )
            )
            if exists is None:
                self.session.add(
                    Edge(
                        case_id=case.id,
                        source_id=entity.id,
                        target_id=other.id,
                        relation=link.relation,
                        provenance_id=provenance.id,
                    )
                )
                linked += 1

        self.session.flush()

        return CollectorRun(
            collector_id=collector.id,
            label=collector.label,
            status="ok",
            facts=len(seen),
            links=linked,
            notes=result.notes,
            provenance_id=provenance.id,
        )

    def _record_provenance(
        self, collector: Collector, ctx: CollectContext, result
    ) -> Provenance:
        combined = ""
        if ctx.evidence:
            combined = digest("".join(item.sha256 for item in ctx.evidence).encode())

        provenance = Provenance(
            source=collector.id,
            url=ctx.evidence[0].url if ctx.evidence else None,
            retrieved_at=datetime.now(UTC),
            method=f"{collector.label} ({len(ctx.evidence)} request(s))",
            confidence=max((fact.confidence for fact in result.facts), default=0.8),
            raw_sha256=combined,
            evidence_refs=json.dumps(
                [item.evidence_ref() for item in ctx.evidence], ensure_ascii=False
            ),
            legal_basis=collector.legal_basis,
        )
        self.session.add(provenance)
        self.session.flush()
        return provenance
