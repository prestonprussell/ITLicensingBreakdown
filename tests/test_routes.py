import asyncio
from io import BytesIO
from types import SimpleNamespace

import pytest
from starlette.datastructures import UploadFile

from app import main as main_module
from app.main import STATIC_DIR, app


def test_launcher_and_invoice_routes_registered() -> None:
    paths = {route.path for route in app.routes}

    assert "/" in paths
    assert "/apps/invoice-analyzer" in paths
    assert "/apps/admin" in paths
    assert "/api/integricom/sync/entra" in paths
    assert "/api/integricom/allocation-rules" in paths
    assert "/api/integricom/allocation-rules/save" in paths
    assert "/api/integricom/allocation-rules/delete" in paths
    assert "/api/integricom/allocation-rules/from-breakdown" in paths


def test_launcher_html_lists_invoice_analyzer() -> None:
    html = (STATIC_DIR / "launcher.html").read_text(encoding="utf-8")

    assert "Russell Toolkit" in html
    assert "Invoice Analyzer" in html
    assert "Admin" in html


def test_integricom_mode_allows_missing_csv_upload(monkeypatch) -> None:
    async def fake_analyze_integricom(_uploads, _invoice_file, _user_updates, _branch_updates, _rule_updates=None):
        return {"vendor_type": "integricom", "ok": True}

    monkeypatch.setattr(main_module, "_analyze_integricom", fake_analyze_integricom)
    invoice_file = UploadFile(filename="invoice.pdf", file=BytesIO(b"%PDF-1.4\n"))

    response = asyncio.run(
        main_module.analyze(
            vendor_type="integricom",
            csv_files=None,
            invoice_file=invoice_file,
        )
    )

    assert response["ok"] is True


def test_generic_mode_still_requires_csv_upload() -> None:
    with pytest.raises(main_module.HTTPException) as exc:
        asyncio.run(
            main_module.analyze(
                vendor_type="generic",
                csv_files=None,
                invoice_file=None,
            )
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "At least one CSV export file is required."


def test_adobe_directory_import_endpoint_uses_parsed_rows(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_parser(filename: str, _raw: bytes):
        captured["filename"] = filename
        return SimpleNamespace(
            rows=[{"email": "a@example.com", "first_name": "A", "last_name": "B", "branch": "Home Office"}],
            source="xlsx",
            warnings=[],
        )

    def fake_upsert(rows):
        captured["upsert"] = rows

    def fake_touch(rows):
        captured["touch"] = rows

    monkeypatch.setattr(main_module, "parse_adobe_directory_import_file", fake_parser)
    monkeypatch.setattr(main_module, "upsert_adobe_users", fake_upsert)
    monkeypatch.setattr(main_module, "touch_seen_users", fake_touch)

    upload = UploadFile(filename="Adobe Cost Calc.xlsx", file=BytesIO(b"placeholder"))
    result = asyncio.run(main_module.import_adobe_users(upload))

    assert captured["filename"] == "Adobe Cost Calc.xlsx"
    assert result["imported"] == 1
    assert captured["upsert"] == captured["touch"]


def test_append_integricom_reconciliation_row_adds_home_office_preview_row() -> None:
    rows = [
        {
            "branch": "Doraville",
            "license": "NetWatch360 Managed Firewall",
            "allocation_type": "Fixed Branch Item",
            "total_amount": 185.22,
        }
    ]

    updated = main_module._append_integricom_reconciliation_row(
        rows,
        adjustment=main_module.Decimal("-54.00"),
    )

    assert any(
        row["branch"] == "Home Office"
        and row["license"] == "Integricom Invoice Adjustment"
        and row["allocation_type"] == "Invoice Reconciliation"
        and row["total_amount"] == -54.0
        for row in updated
    )


def test_append_integricom_credit_row_adds_home_office_credit_preview_row() -> None:
    line_rows = [
        {"source_file": "invoice", "branch": "Doraville", "license": "Workstation", "amount": main_module.Decimal("25.00")}
    ]
    non_user_rows = []

    updated_line_rows, updated_non_user_rows = main_module._append_integricom_credit_row(
        line_rows,
        non_user_rows,
        credits_total=main_module.Decimal("-54.00"),
    )

    assert any(
        row["branch"] == "Home Office"
        and row["license"] == "Integricom Invoice Credit"
        and row["allocation_type"] == "Invoice Credit"
        and row["total_amount"] == -54.0
        for row in updated_non_user_rows
    )
    assert any(
        row["branch"] == "Home Office"
        and row["license"] == "Integricom Invoice Credit"
        and row["amount"] == main_module.Decimal("-54.00")
        for row in updated_line_rows
    )


def test_allocation_rules_endpoints_crud(monkeypatch, tmp_path) -> None:
    from app import integricom_directory
    monkeypatch.setattr(integricom_directory, "INTEGRICOM_DIRECTORY_DB", tmp_path / "rules.sqlite3")

    listing = main_module.get_integricom_allocation_rules()
    assert listing["vendor"] == "integricom"
    assert listing["count"] == len(integricom_directory.SEED_INTEGRICOM_RULES)
    assert "Home Office" in listing["branches"]
    assert "single_branch" in listing["rule_types"]

    saved = main_module.save_integricom_allocation_rules(
        [{"canonical_name": "New Managed Item", "rule_type": "single_branch", "params": {"branch": "Grayson"}}]
    )
    assert saved == {"received": 1, "saved": 1}

    rules = integricom_directory.load_allocation_rules()
    assert rules["New Managed Item"] == {"rule_type": "single_branch", "params": {"branch": "Grayson"}}

    deleted = main_module.delete_integricom_allocation_rules({"canonical_names": ["New Managed Item"]})
    assert deleted == {"requested": 1, "deleted": 1}
    assert "New Managed Item" not in integricom_directory.load_allocation_rules()


def test_allocation_rules_save_rejects_unknown_branch(monkeypatch, tmp_path) -> None:
    from app import integricom_directory
    monkeypatch.setattr(integricom_directory, "INTEGRICOM_DIRECTORY_DB", tmp_path / "rules.sqlite3")

    with pytest.raises(main_module.HTTPException) as exc:
        main_module.save_integricom_allocation_rules(
            [{"canonical_name": "X", "rule_type": "single_branch", "params": {"branch": "Atlantis"}}]
        )
    assert exc.value.status_code == 400


def test_rule_updates_parser_learn_only_restricts_types() -> None:
    import json as _json
    # Allowed at upload time.
    parsed = main_module._parse_integricom_rule_updates(
        _json.dumps([{"canonical_name": "New Line", "rule_type": "single_branch", "params": {"branch": "Tampa"}}]),
        learn_only=True,
    )
    assert parsed == [{"canonical_name": "New Line", "rule_type": "single_branch", "params": {"branch": "Tampa"}}]

    # Rich types are rejected at upload time (Admin-only).
    with pytest.raises(main_module.HTTPException):
        main_module._parse_integricom_rule_updates(
            _json.dumps([{"canonical_name": "New Line", "rule_type": "split", "params": {"branch": "Tampa", "amount": "5"}}]),
            learn_only=True,
        )


def test_breakdown_branch_edit_persists_as_rule(monkeypatch, tmp_path) -> None:
    from app import integricom_directory
    monkeypatch.setattr(integricom_directory, "INTEGRICOM_DIRECTORY_DB", tmp_path / "rules.sqlite3")
    integricom_directory.init_integricom_directory()

    # home_office line moved to a branch -> becomes single_branch and persists.
    result = main_module.update_integricom_rules_from_breakdown(
        [{"canonical_name": "Dark Web Monitoring", "old_branch": "Home Office", "new_branch": "Acworth"}]
    )
    assert result["saved"] == 1
    assert result["skipped"] == []
    rules = integricom_directory.load_allocation_rules()
    assert rules["Dark Web Monitoring"] == {"rule_type": "single_branch", "params": {"branch": "Acworth"}}


def test_breakdown_unit_sequence_edit_swaps_branch(monkeypatch, tmp_path) -> None:
    from app import integricom_directory
    monkeypatch.setattr(integricom_directory, "INTEGRICOM_DIRECTORY_DB", tmp_path / "rules.sqlite3")
    integricom_directory.init_integricom_directory()

    main_module.update_integricom_rules_from_breakdown(
        [{"canonical_name": "NetWatch360 Managed Firewall", "old_branch": "Acworth", "new_branch": "Grayson"}]
    )
    branches = integricom_directory.load_allocation_rules()["NetWatch360 Managed Firewall"]["params"]["branches"]
    assert "Acworth" not in branches
    assert branches[0] == "Grayson"


def test_breakdown_edit_skips_ambiguous_and_unknown_branch(monkeypatch, tmp_path) -> None:
    from app import integricom_directory
    monkeypatch.setattr(integricom_directory, "INTEGRICOM_DIRECTORY_DB", tmp_path / "rules.sqlite3")
    integricom_directory.init_integricom_directory()

    # Editing the Home-Office remainder of a split is ambiguous -> skipped, not saved.
    res1 = main_module.update_integricom_rules_from_breakdown(
        [{"canonical_name": "Firewall Security Subscription Main Office", "old_branch": "Home Office", "new_branch": "Tampa"}]
    )
    assert res1["saved"] == 0 and len(res1["skipped"]) == 1

    # Unknown branch is rejected (skipped), not saved.
    res2 = main_module.update_integricom_rules_from_breakdown(
        [{"canonical_name": "Dark Web Monitoring", "old_branch": "Home Office", "new_branch": "Atlantis"}]
    )
    assert res2["saved"] == 0 and "not a known branch" in res2["skipped"][0]["reason"]
