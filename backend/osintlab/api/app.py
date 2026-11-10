"""FastAPI application.

Design notes:

* collection is synchronous inside the request. For a single-user local tool
  that is the honest trade-off: a run takes seconds, and a job queue would add
  a moving part without changing what the user experiences.
* every response shape is derived from the same service layer the CLI uses.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import __version__
from ..collectors.base import all_collectors, collectors_for
from ..config import settings
from ..db import init_db, session
from ..graph import build_graph
from ..models import AuditEvent, Case, Entity
from ..report import render_report
from ..service import CollectorService, infer_entity_type

app = FastAPI(
    title="osint-lab",
    version=__version__,
    description=(
        "Educational OSINT workbench. Every fact is attributed to a source, a "
        "retrieval time and a raw evidence digest."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    init_db()


def get_db() -> Iterator[Session]:
    with session() as db:
        yield db


# -- schemas ----------------------------------------------------------------


class CaseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    scope_note: str = ""


class CollectRequest(BaseModel):
    target: str = Field(min_length=1)
    collectors: list[str] | None = None
    depth: int = Field(default=0, ge=0, le=2)
    max_entities: int = Field(default=15, ge=1, le=50)


# -- serialisers ------------------------------------------------------------


def entity_dict(entity: Entity) -> dict:
    return {
        "id": entity.id,
        "type": entity.type,
        "value": entity.value,
        "display_name": entity.display_name,
        "attributes": [
            {
                "key": attr.key,
                "value": attr.value,
                "source": attr.provenance.source if attr.provenance else None,
                "retrieved_at": attr.provenance.retrieved_at.isoformat()
                if attr.provenance
                else None,
                "confidence": attr.provenance.confidence if attr.provenance else None,
                "url": attr.provenance.url if attr.provenance else None,
            }
            for attr in sorted(entity.attributes, key=lambda a: a.key)
        ],
    }


def case_dict(case: Case, *, include_entities: bool = False) -> dict:
    payload = {
        "id": case.id,
        "title": case.title,
        "scope_note": case.scope_note,
        "created_at": case.created_at.isoformat(),
        "entity_count": len(case.entities),
    }
    if include_entities:
        payload["entities"] = [entity_dict(entity) for entity in case.entities]
    return payload


# -- routes -----------------------------------------------------------------


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": __version__, "offline": settings.offline}


@app.get("/api/sources")
def list_sources() -> list[dict]:
    return [
        {
            "id": collector.id,
            "label": collector.label,
            "description": collector.description,
            "accepts": sorted(collector.accepts),
            "produces": sorted(collector.produces),
            "legal_basis": collector.legal_basis,
            "attribution": collector.attribution,
            "rate_limit": {
                "requests": collector.rate_limit.requests,
                "per_seconds": collector.rate_limit.per_seconds,
            },
        }
        for collector in all_collectors().values()
    ]


@app.get("/api/cases")
def list_cases(db: Session = Depends(get_db)) -> list[dict]:
    cases = db.scalars(select(Case).order_by(Case.id)).all()
    return [case_dict(case) for case in cases]


@app.post("/api/cases", status_code=201)
def create_case(payload: CaseCreate, db: Session = Depends(get_db)) -> dict:
    case = Case(title=payload.title, scope_note=payload.scope_note)
    db.add(case)
    db.flush()
    CollectorService(db).audit(case.id, "case_created", case.title, case.scope_note)
    return case_dict(case)


@app.get("/api/cases/{case_id}")
def get_case(case_id: int, db: Session = Depends(get_db)) -> dict:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(404, f"no case #{case_id}")
    return case_dict(case, include_entities=True)


@app.get("/api/cases/{case_id}/graph")
def get_graph(case_id: int, db: Session = Depends(get_db)) -> dict:
    if db.get(Case, case_id) is None:
        raise HTTPException(404, f"no case #{case_id}")
    return build_graph(db, case_id)


@app.get("/api/cases/{case_id}/audit")
def get_audit(
    case_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[dict]:
    events = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.case_id == case_id)
        .order_by(AuditEvent.id.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": event.id,
            "action": event.action,
            "target": event.target,
            "detail": event.detail,
            "actor": event.actor,
            "created_at": event.created_at.isoformat(),
        }
        for event in events
    ]


@app.get("/api/cases/{case_id}/report", response_class=PlainTextResponse)
def get_report(case_id: int, db: Session = Depends(get_db)) -> str:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(404, f"no case #{case_id}")
    return render_report(db, case)


@app.post("/api/cases/{case_id}/collect")
def collect(
    case_id: int, payload: CollectRequest, db: Session = Depends(get_db)
) -> dict:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(404, f"no case #{case_id}")

    entity_type = infer_entity_type(payload.target)
    applicable = collectors_for(entity_type)
    if not applicable:
        raise HTTPException(
            400, f"no collector accepts entity type {entity_type!r}"
        )

    if payload.collectors:
        known = {collector.id for collector in all_collectors().values()}
        unknown = [cid for cid in payload.collectors if cid not in known]
        if unknown:
            raise HTTPException(400, f"unknown collectors: {', '.join(unknown)}")

    summary = CollectorService(db).run(
        case,
        payload.target,
        collector_ids=payload.collectors,
        depth=payload.depth,
        max_entities=payload.max_entities,
    )

    return {
        "case_id": summary.case_id,
        "target": summary.target,
        "entity_id": summary.entity_id,
        "entity_type": summary.entity_type,
        "ok": summary.ok,
        "failed": summary.failed,
        "runs": [
            {
                "collector_id": run.collector_id,
                "label": run.label,
                "status": run.status,
                "facts": run.facts,
                "links": run.links,
                "notes": run.notes,
                "error": run.error,
            }
            for run in summary.runs
        ],
    }


# -- static UI (only when a production build exists) ------------------------


def _resolve_ui_dir() -> Path | None:
    """Locate the built SvelteKit app.

    Explicit configuration wins; otherwise fall back to the in-repo layout used
    by an editable install. A wheel install has no sibling ``frontend/``, so
    that case must be configured via ``OSINTLAB_UI_DIR``.
    """
    if settings.ui_dir:
        candidate = Path(settings.ui_dir)
        return candidate if candidate.is_dir() else None
    candidate = Path(__file__).resolve().parents[3] / "frontend" / "build"
    return candidate if candidate.is_dir() else None


_UI_DIR = _resolve_ui_dir()
if _UI_DIR is not None:  # pragma: no cover - depends on build artefacts
    app.mount("/", StaticFiles(directory=_UI_DIR, html=True), name="ui")


def _dump(payload: object) -> str:  # pragma: no cover - debug helper
    return json.dumps(payload, indent=2)
