from pathlib import Path

from app import integricom_directory


def test_integricom_directory_upsert_and_missing(tmp_path: Path) -> None:
    db_path = tmp_path / "integricom_users.sqlite3"
    integricom_directory.INTEGRICOM_DIRECTORY_DB = db_path

    integricom_directory.init_integricom_directory()
    integricom_directory.upsert_integricom_users(
        [
            {
                "email": "user1@example.com",
                "first_name": "User",
                "last_name": "One",
                "branch": "Acworth",
            },
            {
                "email": "user2@example.com",
                "first_name": "User",
                "last_name": "Two",
                "branch": "Home Office",
            },
        ]
    )

    users = integricom_directory.list_integricom_users()
    assert set(users.keys()) == {"user1@example.com", "user2@example.com"}
    assert users["user1@example.com"].branch == "Acworth"

    missing = integricom_directory.find_missing_integricom_users({"user1@example.com"})
    assert len(missing) == 1
    assert missing[0].email == "user2@example.com"


def test_deactivate_integricom_users_marks_user_inactive(tmp_path: Path) -> None:
    db_path = tmp_path / "integricom_users.sqlite3"
    integricom_directory.INTEGRICOM_DIRECTORY_DB = db_path

    integricom_directory.init_integricom_directory()
    integricom_directory.upsert_integricom_users(
        [
            {
                "email": "active@example.com",
                "first_name": "Active",
                "last_name": "User",
                "branch": "Acworth",
            }
        ]
    )

    deactivated = integricom_directory.deactivate_integricom_users(["active@example.com"])
    assert deactivated == 1

    active_users = integricom_directory.list_integricom_users(active_only=True)
    all_users = integricom_directory.list_integricom_users()

    assert "active@example.com" not in active_users
    assert all_users["active@example.com"].is_active is False


def test_allocation_rules_seed_is_idempotent(tmp_path: Path) -> None:
    integricom_directory.INTEGRICOM_DIRECTORY_DB = tmp_path / "integricom_users.sqlite3"
    integricom_directory.init_integricom_directory()
    first = integricom_directory.list_allocation_rules()
    # Re-seeding must not duplicate or change anything.
    integricom_directory.seed_allocation_rules_if_empty()
    integricom_directory.init_integricom_directory()
    second = integricom_directory.list_allocation_rules()

    assert len(first) == len(integricom_directory.SEED_INTEGRICOM_RULES)
    assert first == second
    assert all(rule["source"] == "seed" for rule in first)
    # Spot-check a few seeded shapes.
    by_name = {r["canonical_name"]: r for r in first}
    assert by_name["NetWatch360 Managed Firewall"]["rule_type"] == "unit_sequence"
    assert by_name["Firewall Security Subscription Main Office"]["params"]["amount"] == "97.00"
    assert "Microsoft 365 Business Premium" in by_name["Workstation"]["params"]["match_tokens"]


def test_allocation_rules_seed_does_not_clobber_edits(tmp_path: Path) -> None:
    integricom_directory.INTEGRICOM_DIRECTORY_DB = tmp_path / "integricom_users.sqlite3"
    integricom_directory.init_integricom_directory()
    integricom_directory.upsert_allocation_rules(
        [{"canonical_name": "NetWatch360 Managed Network Device", "rule_type": "single_branch", "params": {"branch": "Acworth"}}],
        source="admin",
    )
    # Seeding again must be a no-op (table is non-empty) and preserve the edit.
    integricom_directory.seed_allocation_rules_if_empty()
    rules = integricom_directory.load_allocation_rules()
    assert rules["NetWatch360 Managed Network Device"] == {"rule_type": "single_branch", "params": {"branch": "Acworth"}}


def test_allocation_rules_crud_and_param_roundtrip(tmp_path: Path) -> None:
    integricom_directory.INTEGRICOM_DIRECTORY_DB = tmp_path / "integricom_users.sqlite3"
    integricom_directory.init_allocation_rules()

    samples = [
        {"canonical_name": "A", "rule_type": "home_office", "params": {}},
        {"canonical_name": "B", "rule_type": "single_branch", "params": {"branch": "St. Pete"}},
        {"canonical_name": "C", "rule_type": "unit_sequence", "params": {"branches": ["Acworth", "Canton"]}},
        {"canonical_name": "D", "rule_type": "split", "params": {"branch": "Sugar Hill", "amount": "97.00"}},
        {"canonical_name": "E", "rule_type": "dynamic_user", "params": {"match_tokens": ["X", "Y"]}},
    ]
    saved = integricom_directory.upsert_allocation_rules(samples, source="admin")
    assert saved == 5

    loaded = integricom_directory.load_allocation_rules()
    for sample in samples:
        assert loaded[sample["canonical_name"]] == {"rule_type": sample["rule_type"], "params": sample["params"]}

    # Update in place (ON CONFLICT) then delete.
    integricom_directory.upsert_allocation_rules(
        [{"canonical_name": "B", "rule_type": "single_branch", "params": {"branch": "Tampa"}}], source="admin"
    )
    assert integricom_directory.load_allocation_rules()["B"]["params"]["branch"] == "Tampa"

    assert integricom_directory.delete_allocation_rules(["A", "E"]) == 2
    remaining = integricom_directory.load_allocation_rules()
    assert "A" not in remaining and "E" not in remaining
