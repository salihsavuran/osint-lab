"""Data model.

The schema is intentionally small:

    Case -> Entity -> Attribute -> Provenance
    Case -> Edge  (entity-to-entity relations, also carrying provenance)
    Case -> AuditEvent
    CacheEntry

Every *fact* (Attribute) points at the Provenance row that produced it, which in
turn points at the raw evidence snapshot on disk. Nothing in the database is
allowed to be unattributed.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

ENTITY_TYPES = (
    "domain",
    "ip",
    "prefix",
    "asn",
    "url",
    "organization",
    "sanctions",
    "phone",
)


def utcnow() -> datetime:
    return datetime.now(UTC)


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    scope_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    entities: Mapped[list[Entity]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )
    edges: Mapped[list[Edge]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )
    audits: Mapped[list[AuditEvent]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )


class Entity(Base):
    __tablename__ = "entities"
    __table_args__ = (
        UniqueConstraint("case_id", "type", "value", name="uq_entity_case_type_value"),
        Index("ix_entity_case_type", "case_id", "type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(String(32), index=True)
    value: Mapped[str] = mapped_column(String(512), index=True)
    display_name: Mapped[str] = mapped_column(String(512), default="")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    case: Mapped[Case] = relationship(back_populates="entities")
    attributes: Mapped[list[Attribute]] = relationship(
        back_populates="entity", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Entity {self.type}:{self.value}>"


class Provenance(Base):
    """Where a fact came from, and how to prove it."""

    __tablename__ = "provenance"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(64), index=True)
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(default=utcnow)
    method: Mapped[str] = mapped_column(String(200), default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.8)
    # SHA-256 over the concatenated digests of every raw response in this run.
    raw_sha256: Mapped[str] = mapped_column(String(64), default="")
    # JSON list of {"sha256", "url", "status"} for each captured response.
    evidence_refs: Mapped[str] = mapped_column(Text, default="[]")
    legal_basis: Mapped[str] = mapped_column(Text, default="")


class Attribute(Base):
    __tablename__ = "attributes"
    __table_args__ = (Index("ix_attribute_entity_key", "entity_id", "key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(120))
    value: Mapped[str] = mapped_column(Text)
    provenance_id: Mapped[int | None] = mapped_column(
        ForeignKey("provenance.id", ondelete="SET NULL"), nullable=True, index=True
    )

    entity: Mapped[Entity] = relationship(back_populates="attributes")
    provenance: Mapped[Provenance | None] = relationship()


class Edge(Base):
    __tablename__ = "edges"
    __table_args__ = (
        UniqueConstraint(
            "case_id", "source_id", "target_id", "relation", name="uq_edge"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[int] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), index=True
    )
    target_id: Mapped[int] = mapped_column(
        ForeignKey("entities.id", ondelete="CASCADE"), index=True
    )
    relation: Mapped[str] = mapped_column(String(64), default="related")
    provenance_id: Mapped[int | None] = mapped_column(
        ForeignKey("provenance.id", ondelete="SET NULL"), nullable=True
    )

    case: Mapped[Case] = relationship(back_populates="edges")
    source: Mapped[Entity] = relationship(foreign_keys=[source_id])
    target: Mapped[Entity] = relationship(foreign_keys=[target_id])
    provenance: Mapped[Provenance | None] = relationship()


class AuditEvent(Base):
    """Accountability log: who collected what, against which target, and when."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int | None] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=True, index=True
    )
    actor: Mapped[str] = mapped_column(String(120), default="local")
    action: Mapped[str] = mapped_column(String(64), index=True)
    target: Mapped[str] = mapped_column(String(512), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)

    case: Mapped[Case | None] = relationship(back_populates="audits")


class CacheEntry(Base):
    """Metadata for a cached response body. The body itself lives on disk."""

    __tablename__ = "cache_entries"
    __table_args__ = (UniqueConstraint("cache_key", name="uq_cache_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(64), index=True)
    cache_key: Mapped[str] = mapped_column(String(128))
    url: Mapped[str] = mapped_column(String(1024), default="")
    status: Mapped[int] = mapped_column(default=200)
    fetched_at: Mapped[datetime] = mapped_column(default=utcnow)
    ttl_seconds: Mapped[int] = mapped_column(default=3600)
    body_path: Mapped[str] = mapped_column(String(1024))
    sha256: Mapped[str] = mapped_column(String(64))
