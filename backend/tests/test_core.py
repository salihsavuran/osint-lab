"""Core behaviour: target typing, provenance, idempotency and the report."""

from __future__ import annotations

import pytest

from osintlab.models import Attribute, Case, Edge, Entity, Provenance
from osintlab.report import render_report
from osintlab.service import CollectorService, infer_entity_type


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("example.com", "domain"),
        ("sub.example.co.uk", "domain"),
        ("8.8.8.8", "ip"),
        ("https://example.com/path", "url"),
        ("2606:4700::1111", "ip"),
        ("Acme Corporation", "organization"),
    ],
)
def test_infer_entity_type(target, expected):
    assert infer_entity_type(target) == expected


def test_provenance_is_recorded_for_every_fact(db_session, fake_fetcher, store):
    fake_fetcher.responses["rdap"] = {
        "ldhName": "example.com",
        "handle": "2336799_DOMAIN_COM-VRSN",
        "status": ["client transfer prohibited"],
        "events": [
            {"eventAction": "registration", "eventDate": "1995-08-14T04:00:00Z"},
        ],
        "nameservers": [{"ldhName": "A.IANA-SERVERS.NET"}],
        "entities": [
            {
                "roles": ["registrar"],
                "vcardArray": ["vcard", [["fn", {}, "text", "Example Registrar"]]],
            }
        ],
    }

    case = Case(title="t", scope_note="test")
    db_session.add(case)
    db_session.flush()

    service = CollectorService(db_session, fetcher=fake_fetcher, store=store)
    summary = service.run(case, "example.com", collector_ids=["rdap"])

    assert summary.failed == 0
    assert summary.ok == 1

    entity = db_session.query(Entity).filter_by(value="example.com").one()
    assert entity.attributes

    for attribute in entity.attributes:
        assert attribute.provenance_id is not None
        provenance = db_session.get(Provenance, attribute.provenance_id)
        assert provenance is not None
        assert provenance.source == "rdap"
        assert provenance.legal_basis
        assert provenance.raw_sha256

    # Nameserver became a linked entity, not just a fact.
    assert db_session.query(Edge).count() == 1
    assert db_session.query(Entity).filter_by(value="a.iana-servers.net").count() == 1


def test_repeated_runs_are_idempotent(db_session, fake_fetcher, store):
    fake_fetcher.responses["rdap"] = {
        "ldhName": "example.com",
        "events": [{"eventAction": "registration", "eventDate": "1995-08-14T04:00:00Z"}],
    }

    case = Case(title="t")
    db_session.add(case)
    db_session.flush()
    service = CollectorService(db_session, fetcher=fake_fetcher, store=store)

    service.run(case, "example.com", collector_ids=["rdap"])
    first = db_session.query(Attribute).count()
    service.run(case, "example.com", collector_ids=["rdap"])
    second = db_session.query(Attribute).count()

    assert first == second


def test_failing_collector_does_not_abort_the_run(db_session, fake_fetcher, store):
    case = Case(title="t")
    db_session.add(case)
    db_session.flush()

    service = CollectorService(db_session, fetcher=fake_fetcher, store=store)
    summary = service.run(case, "example.com", collector_ids=["rdap"])

    assert summary.failed == 1
    assert summary.runs[0].status == "error"


def test_report_cites_sources(db_session, fake_fetcher, store):
    fake_fetcher.responses["rdap"] = {
        "ldhName": "example.com",
        "events": [{"eventAction": "registration", "eventDate": "1995-08-14T04:00:00Z"}],
    }
    case = Case(title="Cited", scope_note="testing")
    db_session.add(case)
    db_session.flush()

    CollectorService(db_session, fetcher=fake_fetcher, store=store).run(
        case, "example.com", collector_ids=["rdap"]
    )

    markdown = render_report(db_session, case)
    assert "# OSINT Report: Cited" in markdown
    assert "Sources and legal basis" in markdown
    assert "rdap" in markdown
    assert "1995-08-14" in markdown
    assert "Evidence manifest" in markdown
