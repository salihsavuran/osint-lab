"""Collector contract and parsing behaviour."""

from __future__ import annotations

from osintlab.collectors.base import CollectContext, all_collectors, collectors_for
from osintlab.config import settings


def test_registry_is_well_formed():
    collectors = all_collectors()
    assert len(collectors) >= 10

    for collector in collectors.values():
        assert collector.id
        assert collector.label
        assert collector.description
        assert collector.legal_basis, f"{collector.id} has no legal basis"
        assert collector.accepts
        assert collector.rate_limit.requests >= 1
        assert collector.rate_limit.per_seconds > 0


def test_every_entity_type_has_at_least_one_collector():
    for entity_type in ("domain", "ip", "organization"):
        assert collectors_for(entity_type), f"no collector for {entity_type}"


def _ctx(fetcher, value, entity_type="domain"):
    return CollectContext(
        entity_type=entity_type, value=value, fetcher=fetcher, settings=settings
    )


def test_rdap_parses_registration_data(fake_fetcher):
    from osintlab.collectors.rdap import RDAPCollector

    fake_fetcher.responses["rdap"] = {
        "ldhName": "example.com",
        "status": ["client transfer prohibited"],
        "events": [
            {"eventAction": "registration", "eventDate": "1995-08-14T04:00:00Z"},
            {"eventAction": "expiration", "eventDate": "2027-08-13T04:00:00Z"},
        ],
        "nameservers": [{"ldhName": "A.IANA-SERVERS.NET"}],
        "entities": [
            {
                "roles": ["registrar"],
                "vcardArray": ["vcard", [["fn", {}, "text", "Example Registrar"]]],
            }
        ],
    }

    result = RDAPCollector().collect(_ctx(fake_fetcher, "example.com"))
    facts = {fact.key: fact.value for fact in result.facts}

    assert facts["rdap.event.registration"] == "1995-08-14T04:00:00Z"
    assert facts["rdap.registrar"] == "Example Registrar"
    assert facts["rdap.nameserver"] == "a.iana-servers.net"
    assert any(link.value == "a.iana-servers.net" for link in result.links)


def test_crtsh_extracts_subdomains(fake_fetcher):
    from osintlab.collectors.crtsh import CrtShCollector

    fake_fetcher.responses["crtsh"] = [
        {"name_value": "*.example.com\nexample.com", "issuer_name": "Test CA"},
        {"name_value": "dev.example.com", "issuer_name": "Test CA"},
        {"name_value": "other.org", "issuer_name": "Test CA"},
    ]

    result = CrtShCollector().collect(_ctx(fake_fetcher, "example.com"))
    discovered = {link.value for link in result.links}

    assert "dev.example.com" in discovered
    # The apex and unrelated domains must not become child entities.
    assert "example.com" not in discovered
    assert "other.org" not in discovered


def test_dns_doh_maps_a_records_to_ip_entities(fake_fetcher):
    from osintlab.collectors.dns_doh import DNSDoHCollector

    fake_fetcher.responses["dns_doh"] = {
        "Status": 0,
        "Answer": [{"name": "example.com", "type": 1, "data": "93.184.216.34"}],
    }

    result = DNSDoHCollector().collect(_ctx(fake_fetcher, "example.com"))
    ip_links = [link for link in result.links if link.type == "ip"]

    assert ip_links and ip_links[0].value == "93.184.216.34"
    assert ip_links[0].relation == "resolves_to"


def test_ofac_flags_name_matches_as_leads(fake_fetcher):
    from osintlab.collectors.ofac import OFACCollector

    csv_body = (
        b'1,"ACME HOLDINGS",-0-,"SDGT","","","","","","","","test entry"\n'
        b'2,"UNRELATED ENTITY",-0-,"SDGT","","","","","","","",""\n'
    )
    fake_fetcher.responses["ofac"] = csv_body

    result = OFACCollector().collect(_ctx(fake_fetcher, "Acme Holdings", "organization"))
    facts = {fact.key: fact.value for fact in result.facts}

    assert facts["ofac.match_count"] == "1"
    assert facts["ofac.match_name"] == "ACME HOLDINGS"
    assert any("not identity matches" in note for note in result.notes)


def test_graph_projection(db_session, fake_fetcher, store):
    from osintlab.graph import build_graph, to_dot
    from osintlab.models import Case
    from osintlab.service import CollectorService

    fake_fetcher.responses["rdap"] = {
        "ldhName": "example.com",
        "nameservers": [{"ldhName": "A.IANA-SERVERS.NET"}],
    }
    case = Case(title="g")
    db_session.add(case)
    db_session.flush()

    CollectorService(db_session, fetcher=fake_fetcher, store=store).run(
        case, "example.com", collector_ids=["rdap"]
    )

    graph = build_graph(db_session, case.id)
    assert graph["stats"]["entities"] == 2
    assert graph["stats"]["relations"] == 1
    assert "digraph osint_lab" in to_dot(graph)
