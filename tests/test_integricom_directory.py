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
