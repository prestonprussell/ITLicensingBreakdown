from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

INTEGRICOM_DIRECTORY_DB = Path(__file__).resolve().parent / "data" / "integricom_users.sqlite3"


@dataclass
class IntegricomDirectoryUser:
    email: str
    first_name: str
    last_name: str
    branch: str
    is_active: bool
    created_at: str
    updated_at: str
    last_seen_at: str | None


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _connect() -> sqlite3.Connection:
    INTEGRICOM_DIRECTORY_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(INTEGRICOM_DIRECTORY_DB, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_integricom_directory() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS integricom_users (
                email TEXT PRIMARY KEY,
                first_name TEXT NOT NULL DEFAULT '',
                last_name TEXT NOT NULL DEFAULT '',
                branch TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_seen_at TEXT
            )
            """
        )
        conn.execute(
            "UPDATE integricom_users SET branch = 'Home Office' WHERE TRIM(COALESCE(branch, '')) = ''"
        )
        conn.commit()
    init_allocation_rules()
    seed_allocation_rules_if_empty()


def list_integricom_users(*, active_only: bool = False) -> dict[str, IntegricomDirectoryUser]:
    init_integricom_directory()
    with _connect() as conn:
        query = """
            SELECT email, first_name, last_name, branch, is_active, created_at, updated_at, last_seen_at
            FROM integricom_users
        """
        if active_only:
            query += " WHERE is_active = 1"
        rows = conn.execute(query).fetchall()

    users: dict[str, IntegricomDirectoryUser] = {}
    for row in rows:
        email = (row["email"] or "").strip().lower()
        if not email:
            continue
        users[email] = IntegricomDirectoryUser(
            email=email,
            first_name=row["first_name"] or "",
            last_name=row["last_name"] or "",
            branch=row["branch"] or "",
            is_active=bool(row["is_active"]),
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
            last_seen_at=row["last_seen_at"],
        )
    return users


def upsert_integricom_users(
    users: list[dict[str, str]],
    *,
    last_seen_at: str | None = None,
) -> None:
    if not users:
        return

    init_integricom_directory()
    now = _utc_now()
    seen = last_seen_at or now
    with _connect() as conn:
        for user in users:
            email = (user.get("email") or "").strip().lower()
            if not email:
                continue
            first_name = (user.get("first_name") or "").strip()
            last_name = (user.get("last_name") or "").strip()
            branch = (user.get("branch") or "").strip()
            if not branch:
                continue

            conn.execute(
                """
                INSERT INTO integricom_users (
                    email, first_name, last_name, branch, is_active, created_at, updated_at, last_seen_at
                )
                VALUES (?, ?, ?, ?, 1, ?, ?, ?)
                ON CONFLICT(email) DO UPDATE SET
                    first_name=excluded.first_name,
                    last_name=excluded.last_name,
                    branch=excluded.branch,
                    is_active=1,
                    updated_at=excluded.updated_at,
                    last_seen_at=excluded.last_seen_at
                """,
                (email, first_name, last_name, branch, now, now, seen),
            )
        conn.commit()


def touch_seen_integricom_users(users: list[dict[str, str]]) -> None:
    if not users:
        return

    init_integricom_directory()
    now = _utc_now()
    with _connect() as conn:
        for user in users:
            email = (user.get("email") or "").strip().lower()
            if not email:
                continue
            first_name = (user.get("first_name") or "").strip()
            last_name = (user.get("last_name") or "").strip()
            conn.execute(
                """
                UPDATE integricom_users
                SET
                    first_name=CASE WHEN ? <> '' THEN ? ELSE first_name END,
                    last_name=CASE WHEN ? <> '' THEN ? ELSE last_name END,
                    is_active=1,
                    updated_at=?,
                    last_seen_at=?
                WHERE email=?
                """,
                (first_name, first_name, last_name, last_name, now, now, email),
            )
        conn.commit()


def find_missing_integricom_users(current_emails: set[str]) -> list[IntegricomDirectoryUser]:
    init_integricom_directory()
    normalized = {email.strip().lower() for email in current_emails if email.strip()}

    with _connect() as conn:
        if not normalized:
            rows = conn.execute(
                """
                SELECT email, first_name, last_name, branch, is_active, created_at, updated_at, last_seen_at
                FROM integricom_users
                WHERE is_active = 1
                ORDER BY email
                """
            ).fetchall()
        else:
            placeholders = ",".join("?" for _ in normalized)
            rows = conn.execute(
                f"""
                SELECT email, first_name, last_name, branch, is_active, created_at, updated_at, last_seen_at
                FROM integricom_users
                WHERE is_active = 1
                  AND email NOT IN ({placeholders})
                ORDER BY email
                """,
                tuple(sorted(normalized)),
            ).fetchall()

    missing: list[IntegricomDirectoryUser] = []
    for row in rows:
        missing.append(
            IntegricomDirectoryUser(
                email=row["email"] or "",
                first_name=row["first_name"] or "",
                last_name=row["last_name"] or "",
                branch=row["branch"] or "",
                is_active=bool(row["is_active"]),
                created_at=row["created_at"] or "",
                updated_at=row["updated_at"] or "",
                last_seen_at=row["last_seen_at"],
            )
        )
    return missing


def init_branch_item_assignments() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS integricom_branch_item_assignments (
                canonical_name TEXT NOT NULL,
                prompt_index INTEGER NOT NULL,
                branch TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (canonical_name, prompt_index)
            )
            """
        )
        conn.commit()


def load_branch_item_assignments() -> list[dict]:
    """Return saved extra-unit branch assignments as [{canonical_name, prompt_index, branch}]."""
    init_branch_item_assignments()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT canonical_name, prompt_index, branch FROM integricom_branch_item_assignments"
        ).fetchall()
    return [{"canonical_name": row["canonical_name"], "prompt_index": row["prompt_index"], "branch": row["branch"]} for row in rows]


def save_branch_item_assignments(items: list[dict]) -> None:
    """Upsert extra-unit branch assignments so they are pre-filled on future runs."""
    if not items:
        return
    now = _utc_now()
    init_branch_item_assignments()
    with _connect() as conn:
        for item in items:
            conn.execute(
                """
                INSERT INTO integricom_branch_item_assignments (canonical_name, prompt_index, branch, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(canonical_name, prompt_index) DO UPDATE SET
                    branch = excluded.branch,
                    updated_at = excluded.updated_at
                """,
                (item["canonical_name"], item["prompt_index"], item["branch"], now),
            )
        conn.commit()


# ---------------------------------------------------------------------------
# Allocation rules: the formerly-hardcoded Integricom branch template, now a
# living DB table. Seeded once from these literals, then editable in Admin and
# self-learned at upload time. Branch names are transcribed here so this module
# stays import-free of processing.py (single source of seed truth).
# ---------------------------------------------------------------------------

_SEED_DISTRICT_BRANCHES = [
    "Acworth", "Canton", "Charleston", "Cobb", "Color Burst", "Doraville",
    "Destin", "Fort Walton", "Pensacola", "Nashville", "Savannah", "St. Pete", "Tampa",
]
_SEED_MANAGED_INTERNET_BRANCHES = ["Home Office", *_SEED_DISTRICT_BRANCHES]
_SEED_DISTRICT_OFFICE_BRANCHES = [
    "Canton", "Cobb", "Doraville", "Destin", "Fort Walton", "Tampa",
    "Savannah", "Charleston", "Nashville", "Color Burst", "Acworth",
]
_SEED_HOME_OFFICE_NAMES = [
    "Ticketing System User License", "Documentation System License", "Monthly Block Hours",
    "Dark Web Monitoring", "IT Automation Tool", "Teams Rooms Pro", "NetWatch360 MAC",
    "NetWatch360 Managed Server", "Dropbox Business Standard", "DP Server Image Backup Cloud",
    "Power BI Pro", "Microsoft Teams Essentials NCE Annual", "M365 Microsoft E5", "M365 Intune",
    "Prorated M365", "AWS Cloud Server", "Keeper Enterprise Password Manager",
    "Teams Audio Conferencing", "NetWatch360 Managed Network Device",
]

# Microsoft license tokens used by dynamic_user matching.
_T_BP = "Microsoft 365 Business Premium"
_T_P1 = "Exchange Online (Plan 1)"
_T_P2 = "Exchange Online (Plan 2)"
_T_F3 = "Microsoft 365 F3"
_T_TEAMS = "Microsoft Teams Essentials"

SEED_INTEGRICOM_RULES: list[dict] = (
    [{"canonical_name": name, "rule_type": "home_office", "params": {}} for name in _SEED_HOME_OFFICE_NAMES]
    + [
        {"canonical_name": "Firewall Security Subscription Latest 2025", "rule_type": "single_branch", "params": {"branch": "St. Pete"}},
        {"canonical_name": "Project Plan 3", "rule_type": "single_branch", "params": {"branch": "Sugar Hill"}},
        {"canonical_name": "NetWatch360 Managed Firewall", "rule_type": "unit_sequence", "params": {"branches": list(_SEED_DISTRICT_BRANCHES)}},
        {"canonical_name": "NetWatch360 Managed Internet", "rule_type": "unit_sequence", "params": {"branches": list(_SEED_MANAGED_INTERNET_BRANCHES)}},
        {"canonical_name": "Firewall Security Subscription District Office", "rule_type": "unit_sequence", "params": {"branches": list(_SEED_DISTRICT_OFFICE_BRANCHES)}},
        {"canonical_name": "Firewall Security Subscription Main Office", "rule_type": "split", "params": {"branch": "Sugar Hill", "amount": "97.00"}},
        {"canonical_name": "Workstation", "rule_type": "dynamic_user", "params": {"match_tokens": [_T_BP, _T_P1, _T_P2, _T_F3, _T_TEAMS]}},
        {"canonical_name": "Office 365 Cloud Backup", "rule_type": "dynamic_user", "params": {"match_tokens": [_T_BP, _T_P1]}},
        {"canonical_name": "Microsoft Business Premium Annual", "rule_type": "dynamic_user", "params": {"match_tokens": [_T_BP]}},
        {"canonical_name": "Exchange Online P1 Annual", "rule_type": "dynamic_user", "params": {"match_tokens": [_T_P1]}},
        {"canonical_name": "Microsoft F3 Annual", "rule_type": "dynamic_user", "params": {"match_tokens": [_T_F3]}},
        {"canonical_name": "Exchange Online P2 Annual", "rule_type": "dynamic_user", "params": {"match_tokens": [_T_P2]}},
    ]
)

VALID_RULE_TYPES = {"home_office", "single_branch", "unit_sequence", "split", "dynamic_user"}


def init_allocation_rules() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS integricom_allocation_rules (
                canonical_name TEXT PRIMARY KEY,
                rule_type      TEXT NOT NULL,
                params         TEXT NOT NULL DEFAULT '{}',
                source         TEXT NOT NULL DEFAULT 'seed',
                updated_at     TEXT NOT NULL
            )
            """
        )
        conn.commit()


def seed_allocation_rules_if_empty() -> None:
    """Seed the rules table from SEED_INTEGRICOM_RULES only when empty.

    INSERT OR IGNORE keeps a cold-start double-seed race (multiple uvicorn
    workers) benign. User edits are never clobbered: once any row exists, the
    empty-check short-circuits.
    """
    init_allocation_rules()
    now = _utc_now()
    with _connect() as conn:
        count = conn.execute("SELECT COUNT(*) FROM integricom_allocation_rules").fetchone()[0]
        if count:
            return
        for rule in SEED_INTEGRICOM_RULES:
            conn.execute(
                """
                INSERT OR IGNORE INTO integricom_allocation_rules
                    (canonical_name, rule_type, params, source, updated_at)
                VALUES (?, ?, ?, 'seed', ?)
                """,
                (rule["canonical_name"], rule["rule_type"], json.dumps(rule["params"]), now),
            )
        conn.commit()


def list_allocation_rules() -> list[dict]:
    """Return rules for the Admin UI: [{canonical_name, rule_type, params, source, updated_at}]."""
    init_allocation_rules()
    seed_allocation_rules_if_empty()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT canonical_name, rule_type, params, source, updated_at FROM integricom_allocation_rules ORDER BY canonical_name"
        ).fetchall()
    return [
        {
            "canonical_name": row["canonical_name"],
            "rule_type": row["rule_type"],
            "params": json.loads(row["params"] or "{}"),
            "source": row["source"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]


def load_allocation_rules() -> dict[str, dict]:
    """Return rules keyed by canonical_name for the allocation engine: {name: {rule_type, params}}."""
    return {
        row["canonical_name"]: {"rule_type": row["rule_type"], "params": row["params"]}
        for row in list_allocation_rules()
    }


def upsert_allocation_rules(rules: list[dict], *, source: str = "admin") -> int:
    """Upsert rules. Each item: {canonical_name, rule_type, params(dict)}. Returns count saved."""
    if not rules:
        return 0
    now = _utc_now()
    init_allocation_rules()
    saved = 0
    with _connect() as conn:
        for rule in rules:
            name = (rule.get("canonical_name") or "").strip()
            rule_type = (rule.get("rule_type") or "").strip()
            if not name or rule_type not in VALID_RULE_TYPES:
                continue
            params = rule.get("params") or {}
            conn.execute(
                """
                INSERT INTO integricom_allocation_rules (canonical_name, rule_type, params, source, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(canonical_name) DO UPDATE SET
                    rule_type = excluded.rule_type,
                    params = excluded.params,
                    source = excluded.source,
                    updated_at = excluded.updated_at
                """,
                (name, rule_type, json.dumps(params), source, now),
            )
            saved += 1
        conn.commit()
    return saved


def delete_allocation_rules(canonical_names: list[str]) -> int:
    """Delete rules by canonical_name. Deleted lines revert to the learn/prompt path."""
    names = sorted({(n or "").strip() for n in canonical_names if (n or "").strip()})
    if not names:
        return 0
    init_allocation_rules()
    placeholders = ",".join("?" for _ in names)
    with _connect() as conn:
        result = conn.execute(
            f"DELETE FROM integricom_allocation_rules WHERE canonical_name IN ({placeholders})",
            (*names,),
        )
        conn.commit()
        return int(result.rowcount or 0)


def deactivate_integricom_users(emails: list[str]) -> int:
    if not emails:
        return 0

    init_integricom_directory()
    now = _utc_now()
    normalized = sorted({(email or "").strip().lower() for email in emails if (email or "").strip()})
    if not normalized:
        return 0

    placeholders = ",".join("?" for _ in normalized)
    with _connect() as conn:
        result = conn.execute(
            f"""
            UPDATE integricom_users
            SET is_active = 0, updated_at = ?
            WHERE LOWER(TRIM(email)) IN ({placeholders})
            """,
            (now, *normalized),
        )
        conn.commit()
        return int(result.rowcount or 0)
