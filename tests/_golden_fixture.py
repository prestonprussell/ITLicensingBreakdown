"""Shared fixture builder for Integricom allocation parity testing.

Builds one invoice line per canonical_name (all rule types) plus edge
quantities, and a deterministic serialization of the full allocation output.
Used both to capture the pre-refactor golden baseline and to assert the
post-refactor code reproduces it byte-for-byte.
"""
from __future__ import annotations

import json
from decimal import Decimal

from app.processing import (
    IntegricomExportUser,
    IntegricomInvoiceLine,
    build_breakdown,
    build_integricom_user_allocations,
    summary_to_csv,
)


def _line(canonical: str, qty, unit, amount) -> IntegricomInvoiceLine:
    return IntegricomInvoiceLine(
        description=canonical,
        canonical_name=canonical,
        quantity=Decimal(str(qty)),
        unit_price=Decimal(str(unit)),
        amount=Decimal(str(amount)),
    )


HOME_OFFICE_NAMES = [
    "Ticketing System User License",
    "Documentation System License",
    "Monthly Block Hours",
    "Dark Web Monitoring",
    "IT Automation Tool",
    "Teams Rooms Pro",
    "NetWatch360 MAC",
    "NetWatch360 Managed Server",
    "Dropbox Business Standard",
    "DP Server Image Backup Cloud",
    "Power BI Pro",
    "Microsoft Teams Essentials NCE Annual",
    "M365 Microsoft E5",
    "M365 Intune",
    "Prorated M365",
    "AWS Cloud Server",
    "Keeper Enterprise Password Manager",
    "Teams Audio Conferencing",
    "NetWatch360 Managed Network Device",
]


def build_fixture_lines() -> list[IntegricomInvoiceLine]:
    lines: list[IntegricomInvoiceLine] = []

    # home_office (all 19)
    for i, name in enumerate(HOME_OFFICE_NAMES, start=1):
        lines.append(_line(name, 1, 10 + i, 10 + i))

    # single_branch
    lines.append(_line("Firewall Security Subscription Latest 2025", 1, 50, 50))
    lines.append(_line("Project Plan 3", 1, 60, 60))

    # unit_sequence — exercise qty < / == / > list length
    lines.append(_line("NetWatch360 Managed Firewall", 3, 20, 60))     # < 13
    lines.append(_line("NetWatch360 Managed Internet", 14, 5, 70))     # == 14
    lines.append(_line("Firewall Security Subscription District Office", 13, 7, 91))  # > 11 -> 2 extra prompts

    # split — above and below $97.00
    lines.append(_line("Firewall Security Subscription Main Office", 1, 150, 150))   # >= 97 -> Sugar Hill 97 + HO 53
    lines.append(_line("Firewall Security Subscription Main Office", 1, 40, 40))     # < 97 -> all HO + warning

    # dynamic_user — matched_count == qty, and a case where matched != qty (Invoice Delta)
    lines.append(_line("Workstation", 2, 25, 50))                       # 2 users match
    lines.append(_line("Office 365 Cloud Backup", 5, 4, 20))            # 1 match, qty 5 -> remainder HO

    # unknown / fallback
    lines.append(_line("Totally Unknown Charge XYZ", 1, 99, 99))
    return lines


def build_fixture_users() -> list[IntegricomExportUser]:
    return [
        IntegricomExportUser(
            source_file="t", email="alice@x.com", first_name="Alice", last_name="A",
            office="Acworth", default_branch="Acworth",
            licenses=["Microsoft 365 Business Premium"],
        ),
        IntegricomExportUser(
            source_file="t", email="bob@x.com", first_name="Bob", last_name="B",
            office="Canton", default_branch="Canton",
            licenses=["Exchange Online (Plan 1)"],
        ),
    ]


def build_fixture_directory() -> dict:
    return {
        "alice@x.com": {"branch": "Acworth", "first_name": "Alice", "last_name": "A"},
        "bob@x.com": {"branch": "Canton", "first_name": "Bob", "last_name": "B"},
    }


def canonical_output(rules=None) -> str:
    """Deterministic JSON serialization of the full allocation result."""
    lines = build_fixture_lines()
    users = build_fixture_users()
    directory = build_fixture_directory()

    kwargs = {}
    if rules is not None:
        kwargs["rules"] = rules

    result = build_integricom_user_allocations(users, directory, lines, **kwargs)
    # Tolerate both pre-refactor (6-tuple) and post-refactor (7-tuple) shapes.
    line_rows, user_rows, non_user_rows, warnings, unresolved_emails, unresolved_branch_prompts = result[:6]
    rule_prompts = result[6] if len(result) > 6 else []

    breakdown_csv = summary_to_csv(build_breakdown(line_rows))

    payload = {
        "breakdown_csv": breakdown_csv,
        "non_user_rows": sorted(
            non_user_rows, key=lambda r: (r["branch"], r["license"], r["allocation_type"])
        ),
        "user_rows": user_rows,
        "warnings": sorted(warnings),
        "unresolved_emails": sorted(unresolved_emails),
        "branch_prompts": sorted(
            ({"license": p.get("license"), "prompt_index": p.get("prompt_index"), "branch": p.get("branch")}
             for p in unresolved_branch_prompts),
            key=lambda p: (p["license"], p["prompt_index"]),
        ),
        "rule_prompts": sorted(
            ({"canonical_name": p.get("canonical_name")} for p in rule_prompts),
            key=lambda p: p["canonical_name"],
        ),
    }
    return json.dumps(payload, indent=2, sort_keys=True, default=str)


if __name__ == "__main__":
    print(canonical_output())
