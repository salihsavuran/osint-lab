"""Phone number structure via libphonenumber.

This collector is **offline**. It reads Google's bundled libphonenumber
metadata — the same numbering-plan data that powers Android's dialer and most
messaging apps — and answers "what kind of number is this, and where was it
allocated".

It does not answer "who owns this number". There is no subscriber lookup, no
reverse search, no HLR probe. Those either require access to carrier systems or
amount to building a profile on a private individual, which this project does
not do.
"""

from __future__ import annotations

import phonenumbers
from phonenumbers import PhoneNumberType, carrier, geocoder, timezone

from ..ratelimit import RateLimit
from .base import CollectContext, Collector, CollectorResult, Fact, register

_TYPE_NAMES = {
    PhoneNumberType.FIXED_LINE: "fixed_line",
    PhoneNumberType.MOBILE: "mobile",
    PhoneNumberType.FIXED_LINE_OR_MOBILE: "fixed_line_or_mobile",
    PhoneNumberType.TOLL_FREE: "toll_free",
    PhoneNumberType.PREMIUM_RATE: "premium_rate",
    PhoneNumberType.SHARED_COST: "shared_cost",
    PhoneNumberType.VOIP: "voip",
    PhoneNumberType.PERSONAL_NUMBER: "personal_number",
    PhoneNumberType.PAGER: "pager",
    PhoneNumberType.UAN: "uan",
    PhoneNumberType.VOICEMAIL: "voicemail",
    PhoneNumberType.UNKNOWN: "unknown",
}


@register
class PhoneNumberCollector(Collector):
    id = "phone_number"
    label = "Phone number structure (libphonenumber)"
    description = (
        "Parses a phone number against public numbering-plan metadata: validity, "
        "country and region, line type, allocated carrier and timezones. Runs "
        "offline; no request leaves the machine."
    )
    accepts = frozenset({"phone"})
    produces = frozenset()
    legal_basis = (
        "Google's libphonenumber bundles the numbering-plan metadata that national "
        "regulators publish for routing. The analysis is local, reads no "
        "third-party service and reveals nothing about a subscriber."
    )
    attribution = f"libphonenumber {phonenumbers.__version__} (bundled metadata)"
    # Offline work still goes through the limiter so a batch run stays bounded.
    rate_limit = RateLimit(requests=1000, per_seconds=1)
    priority = 10

    def collect(self, ctx: CollectContext) -> CollectorResult:
        raw = ctx.value.strip()
        region = (ctx.settings.default_phone_region or "").strip().upper() or None

        try:
            number = phonenumbers.parse(raw, region)
        except phonenumbers.NumberParseException as exc:
            hint = ""
            if not raw.startswith("+") and not region:
                hint = " (set OSINTLAB_PHONE_REGION for national-format numbers)"
            return CollectorResult(notes=[f"could not parse: {exc}{hint}"])

        facts: list[Fact] = []
        notes: list[str] = []

        facts.append(Fact("phone.e164", phonenumbers.format_number(
            number, phonenumbers.PhoneNumberFormat.E164)))
        facts.append(Fact("phone.international", phonenumbers.format_number(
            number, phonenumbers.PhoneNumberFormat.INTERNATIONAL)))
        facts.append(Fact("phone.national", phonenumbers.format_number(
            number, phonenumbers.PhoneNumberFormat.NATIONAL)))
        facts.append(Fact("phone.rfc3966", phonenumbers.format_number(
            number, phonenumbers.PhoneNumberFormat.RFC3966)))

        valid = phonenumbers.is_valid_number(number)
        possible = phonenumbers.is_possible_number(number)
        facts.append(Fact("phone.valid", "true" if valid else "false"))
        facts.append(Fact("phone.possible", "true" if possible else "false"))
        facts.append(Fact("phone.country_code", f"+{number.country_code}"))

        region_code = phonenumbers.region_code_for_number(number)
        facts.append(Fact("phone.region", region_code or "unknown"))

        line_type = _TYPE_NAMES.get(phonenumbers.number_type(number), "unknown")
        facts.append(Fact("phone.line_type", line_type))

        carrier_name = carrier.name_for_number(number, "en")
        if carrier_name:
            facts.append(Fact("phone.carrier_allocated", carrier_name))
            notes.append(
                "carrier is the numbering-plan allocation, not necessarily the "
                "current operator: number portability makes it unreliable"
            )

        geo = geocoder.description_for_number(number, "en")
        if geo:
            facts.append(Fact("phone.geo_description", geo))

        zones = timezone.time_zones_for_number(number)
        if zones:
            facts.append(Fact("phone.timezones", ", ".join(zones)))

        if not valid:
            notes.append("number is not valid within its numbering plan")

        return CollectorResult(facts=facts, notes=notes)
