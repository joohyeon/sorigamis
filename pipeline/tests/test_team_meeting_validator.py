import importlib
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest


PIPELINE_ROOT = Path(__file__).resolve().parents[1]


def test_load_dotenv_sets_environment_and_returns_loaded_values(tmp_path, monkeypatch):
    from tests.e2e.sg_validate_team_meeting import load_dotenv

    env_file = tmp_path / ".env"
    env_file.write_text(
        """
        # comment
        SUPABASE_URL=https://example.supabase.co
        SUPABASE_SERVICE_ROLE_KEY='service-role'
        SMTP_HOST="smtp.example.com"

        NO_EQUALS
        SMTP_PORT=2525
        """,
        encoding="utf-8",
    )
    for key in [
        "SUPABASE_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
        "SMTP_HOST",
        "SMTP_PORT",
    ]:
        monkeypatch.delenv(key, raising=False)

    loaded = load_dotenv(env_file)

    assert loaded == {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "service-role",
        "SMTP_HOST": "smtp.example.com",
        "SMTP_PORT": "2525",
    }
    assert os.environ["SUPABASE_SERVICE_ROLE_KEY"] == "service-role"


def test_preflight_requires_full_base_environment(monkeypatch):
    from tests.e2e.sg_validate_team_meeting import ValidationConfig, preflight

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role")
    for key in ["GOOGLE_SERVICE_ACCOUNT_JSON", "HERMES_PROVIDER", "HERMES_MODEL"]:
        monkeypatch.delenv(key, raising=False)

    config = ValidationConfig(
        file_id="drive-file",
        server_url="http://localhost:8080",
        attendees=[],
        send_email=False,
        speakers=[],
        out_path=None,
    )

    class HealthResponse:
        def raise_for_status(self):
            return None

    monkeypatch.setattr(
        "tests.e2e.sg_validate_team_meeting.httpx.get",
        lambda url, timeout: HealthResponse(),
    )

    with pytest.raises(RuntimeError) as exc:
        preflight(config)

    message = str(exc.value)
    assert "GOOGLE_SERVICE_ACCOUNT_JSON" in message
    assert "HERMES_PROVIDER" in message
    assert "HERMES_MODEL" in message


def test_preflight_requires_smtp_settings_and_attendees_when_send_email(monkeypatch):
    from tests.e2e.sg_validate_team_meeting import ValidationConfig, preflight

    for key, value in {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "service-role",
        "GOOGLE_SERVICE_ACCOUNT_JSON": "{}",
        "HERMES_PROVIDER": "openai",
        "HERMES_MODEL": "gpt-4.1",
    }.items():
        monkeypatch.setenv(key, value)
    for key in ["SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM"]:
        monkeypatch.delenv(key, raising=False)

    config = ValidationConfig(
        file_id="drive-file",
        server_url="http://localhost:8080",
        attendees=[],
        send_email=True,
        speakers=[],
        out_path=None,
    )

    class HealthResponse:
        def raise_for_status(self):
            return None

    def fake_get(url, timeout):
        assert url == "http://localhost:8080/health"
        assert timeout == 10
        return HealthResponse()

    monkeypatch.setattr("tests.e2e.sg_validate_team_meeting.httpx.get", fake_get)

    with pytest.raises(RuntimeError) as exc:
        preflight(config)

    message = str(exc.value)
    assert "SMTP_HOST" in message
    assert "SMTP_PORT" in message
    assert "SMTP_USERNAME" in message
    assert "SMTP_PASSWORD" in message
    assert "SMTP_FROM" in message
    assert "EMAIL_FROM" not in message
    assert "attendee" in message


def test_validator_import_does_not_require_supabase_create_client(monkeypatch):
    monkeypatch.setitem(sys.modules, "supabase", SimpleNamespace())
    sys.modules.pop("tests.e2e.sg_validate_team_meeting", None)

    module = importlib.import_module("tests.e2e.sg_validate_team_meeting")

    assert module.BASE_ENV


class FakeTableQuery:
    def __init__(self, db, table_name):
        self.db = db
        self.table_name = table_name
        self.operation = None
        self.payload = None
        self.filters = []

    def select(self, columns):
        self.operation = "select"
        return self

    def insert(self, payload):
        self.operation = "insert"
        self.payload = payload
        return self

    def update(self, payload):
        self.operation = "update"
        self.payload = payload
        return self

    def eq(self, key, value):
        self.filters.append((key, value))
        return self

    def is_(self, key, value):
        self.filters.append((key, None if value == "null" else value))
        return self

    def execute(self):
        rows = self.db.rows[self.table_name]
        if self.operation == "select":
            return SimpleNamespace(data=[row for row in rows if self._matches(row)])
        if self.operation == "insert":
            row = {"id": str(uuid4()), **self.payload}
            rows.append(row)
            self.db.inserts.append((self.table_name, row))
            return SimpleNamespace(data=[row])
        if self.operation == "update":
            updated = []
            for row in rows:
                if self._matches(row):
                    row.update(self.payload)
                    updated.append(row)
                    self.db.updates.append((self.table_name, row.copy()))
            return SimpleNamespace(data=updated)
        raise AssertionError(f"Unsupported operation {self.operation}")

    def _matches(self, row):
        return all(row.get(key) == value for key, value in self.filters)


class FakeSupabase:
    def __init__(self, skills=None, modes=None, admin=None):
        self.rows = {
            "sg_skills": skills if skills is not None else [],
            "sg_modes": modes if modes is not None else [],
        }
        self.inserts = []
        self.updates = []
        self.auth = SimpleNamespace(admin=admin or FakeAuthAdmin())

    def table(self, table_name):
        return FakeTableQuery(self, table_name)


class FakeAuthAdmin:
    def __init__(self, users=None):
        self.users = users if users is not None else []
        self.created_users = []

    def list_users(self):
        return self.users

    def create_user(self, payload):
        self.created_users.append(payload)
        return SimpleNamespace(user=SimpleNamespace(id=str(uuid4())))


def test_ensure_team_meeting_mode_seeds_email_skill_with_attendees():
    from tests.e2e.sg_validate_team_meeting import ensure_team_meeting_mode

    db = FakeSupabase(
        skills=[
            {
                "id": str(uuid4()),
                "user_id": None,
                "name": "Meeting Summary",
                "description": "stale",
                "ai_prompt": "stale",
                "integration_actions": [{"type": "webhook"}],
                "is_default": True,
                "require_review": True,
            }
        ]
    )
    attendees = ["alice@example.com", "bob@example.com"]

    mode_id, user_id = ensure_team_meeting_mode(db, attendees)

    assert mode_id
    assert user_id

    skills_by_name = {row["name"]: row for row in db.rows["sg_skills"]}
    assert list(skills_by_name) == [
        "Meeting Summary",
        "Action Items",
        "Decision Log",
        "Meeting Follow-up Email",
    ]

    for name in ["Meeting Summary", "Action Items", "Decision Log"]:
        assert skills_by_name[name]["is_default"] is True
        assert skills_by_name[name]["integration_actions"] == []

    assert skills_by_name["Meeting Summary"]["description"] != "stale"
    assert any(
        table == "sg_skills" and row["name"] == "Meeting Summary"
        for table, row in db.updates
    )

    email_skill = skills_by_name["Meeting Follow-up Email"]
    assert email_skill["require_review"] is True
    assert email_skill["integration_actions"] == [
        {
            "type": "email",
            "destination": "meeting_attendees",
            "config": {
                "recipients": attendees,
                "subject": "Team Meeting follow-up",
            },
        }
    ]

    mode = db.rows["sg_modes"][0]
    assert mode["name"] == "Team Meeting"
    assert mode["user_id"] == user_id
    assert mode["skill_ids"] == [skills_by_name[name]["id"] for name in skills_by_name]


def test_ensure_team_meeting_mode_uses_first_admin_user_from_wrapper():
    from tests.e2e.sg_validate_team_meeting import ensure_team_meeting_mode

    admin_user_id = str(uuid4())
    db = FakeSupabase()
    db.auth.admin = FakeAuthAdmin(
        users=SimpleNamespace(data=[SimpleNamespace(id=admin_user_id)])
    )

    mode_id, user_id = ensure_team_meeting_mode(db, attendees=[])

    assert mode_id
    assert user_id == admin_user_id
    assert db.auth.admin.created_users == []


def test_ensure_team_meeting_mode_uses_first_admin_user_from_nested_wrapper():
    from tests.e2e.sg_validate_team_meeting import ensure_team_meeting_mode

    admin_user_id = str(uuid4())
    db = FakeSupabase()
    db.auth.admin = FakeAuthAdmin(
        users=SimpleNamespace(data=SimpleNamespace(users=[{"id": admin_user_id}]))
    )

    mode_id, user_id = ensure_team_meeting_mode(db, attendees=[])

    assert mode_id
    assert user_id == admin_user_id
    assert db.auth.admin.created_users == []


def test_ensure_team_meeting_mode_ignores_non_default_same_name_skill():
    from tests.e2e.sg_validate_team_meeting import ensure_team_meeting_mode

    user_owned_action_items_id = str(uuid4())
    db = FakeSupabase(
        skills=[
            {
                "id": user_owned_action_items_id,
                "user_id": str(uuid4()),
                "name": "Action Items",
                "description": "user-owned",
                "ai_prompt": "do not touch",
                "integration_actions": [{"type": "slack"}],
                "is_default": False,
                "require_review": False,
            }
        ]
    )

    ensure_team_meeting_mode(db, attendees=[])

    action_items = [
        row for row in db.rows["sg_skills"] if row["name"] == "Action Items"
    ]
    assert len(action_items) == 2
    user_owned = next(row for row in action_items if row["id"] == user_owned_action_items_id)
    default_seeded = next(row for row in action_items if row["id"] != user_owned_action_items_id)
    assert user_owned["is_default"] is False
    assert user_owned["ai_prompt"] == "do not touch"
    assert default_seeded["is_default"] is True
    assert default_seeded["user_id"] is None


def test_ensure_team_meeting_mode_scopes_mode_lookup_to_selected_user():
    from tests.e2e.sg_validate_team_meeting import ensure_team_meeting_mode

    selected_user_id = str(uuid4())
    other_user_id = str(uuid4())
    other_mode_id = str(uuid4())
    db = FakeSupabase(
        modes=[
            {
                "id": other_mode_id,
                "name": "Team Meeting",
                "user_id": other_user_id,
                "skill_ids": ["existing-skill"],
            }
        ],
        admin=FakeAuthAdmin(users=[SimpleNamespace(id=selected_user_id)]),
    )

    mode_id, user_id = ensure_team_meeting_mode(db, attendees=[])

    assert user_id == selected_user_id
    assert mode_id != other_mode_id
    other_mode = next(row for row in db.rows["sg_modes"] if row["id"] == other_mode_id)
    selected_mode = next(row for row in db.rows["sg_modes"] if row["id"] == mode_id)
    assert other_mode["skill_ids"] == ["existing-skill"]
    assert selected_mode["user_id"] == selected_user_id


def test_pipeline_migration_adds_require_review_column():
    migration = (
        PIPELINE_ROOT
        / "supabase"
        / "migrations"
        / "20260627000000_require_review.sql"
    )

    assert migration.exists()
    sql = migration.read_text(encoding="utf-8").lower()
    assert "alter table sg_skills" in sql
    assert "require_review" in sql
