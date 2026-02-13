from pathlib import Path

from app import adobe_directory


def test_adobe_directory_upsert_and_missing(tmp_path: Path) -> None:
    db_path = tmp_path / "adobe_users.sqlite3"
    adobe_directory.ADOBE_DIRECTORY_DB = db_path

    adobe_directory.init_adobe_directory()
    adobe_directory.upsert_adobe_users(
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

    users = adobe_directory.list_adobe_users()
    assert set(users.keys()) == {"user1@example.com", "user2@example.com"}
    assert users["user1@example.com"].branch == "Acworth"

    missing = adobe_directory.find_missing_users({"user1@example.com"})
    assert len(missing) == 1
    assert missing[0].email == "user2@example.com"


def test_init_adobe_directory_migrates_legacy_department_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "adobe_users.sqlite3"
    adobe_directory.ADOBE_DIRECTORY_DB = db_path

    conn = adobe_directory.sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE adobe_users (
            email TEXT PRIMARY KEY,
            first_name TEXT NOT NULL DEFAULT '',
            last_name TEXT NOT NULL DEFAULT '',
            branch TEXT NOT NULL,
            department TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_seen_at TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO adobe_users (email, first_name, last_name, branch, department, is_active, created_at, updated_at, last_seen_at)
        VALUES ('legacy@example.com', 'Legacy', 'User', 'Acworth', 'IT', 1, '2025-01-01T00:00:00+00:00', '2025-01-01T00:00:00+00:00', NULL)
        """
    )
    conn.commit()
    conn.close()

    adobe_directory.init_adobe_directory()
    users = adobe_directory.list_adobe_users()

    assert "legacy@example.com" in users
    assert users["legacy@example.com"].branch == "Acworth"


def test_deactivate_adobe_users_marks_user_inactive(tmp_path: Path) -> None:
    db_path = tmp_path / "adobe_users.sqlite3"
    adobe_directory.ADOBE_DIRECTORY_DB = db_path

    adobe_directory.init_adobe_directory()
    adobe_directory.upsert_adobe_users(
        [
            {
                "email": "active@example.com",
                "first_name": "Active",
                "last_name": "User",
                "branch": "Acworth",
            }
        ]
    )

    deactivated = adobe_directory.deactivate_adobe_users(["active@example.com"])
    assert deactivated == 1

    active_users = adobe_directory.list_adobe_users(active_only=True)
    all_users = adobe_directory.list_adobe_users()

    assert "active@example.com" not in active_users
    assert all_users["active@example.com"].is_active is False
