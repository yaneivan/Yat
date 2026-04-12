"""
Тесты для PermissionService, AuditService и соответствующих API endpoints.
"""

import pytest
from app import app
from services.user_service import user_service
from services.permission_service import permission_service
from services.audit_service import audit_service
from services.project_service import project_service
from database.session import SessionLocal
from database.models import User, ProjectPermission, AuditLog


# ═══════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════


@pytest.fixture(autouse=True)
def clean_tables():
    """Очистка users, permissions, audit_log, projects перед каждым тестом."""
    session = SessionLocal()
    try:
        session.query(AuditLog).delete()
        session.query(ProjectPermission).delete()
        session.query(User).delete()
        # Projects удаляем через service (каскад)
        from database.models import Project
        session.query(Project).delete()
        session.commit()
    finally:
        session.close()
    yield
    session = SessionLocal()
    try:
        session.query(AuditLog).delete()
        session.query(ProjectPermission).delete()
        session.query(User).delete()
        session.query(Project).delete()
        session.commit()
    finally:
        session.close()


# ═══════════════════════════════════════
# PermissionService Tests
# ═══════════════════════════════════════


class TestPermissionGrantRevoke:
    def test_grant_access(self):
        user_service.create_user("alice", "pass1")
        alice = user_service.get_user("alice")
        project_service.create_project("proj1", "desc")

        result = permission_service.grant_access(alice["id"], "proj1", "read")
        assert result is not None
        assert result["role"] == "read"

    def test_grant_access_nonexistent_project(self):
        user_service.create_user("alice", "pass1")
        alice = user_service.get_user("alice")
        result = permission_service.grant_access(alice["id"], "no_project", "read")
        assert result is None

    def test_revoke_access(self):
        user_service.create_user("alice", "pass1")
        alice = user_service.get_user("alice")
        project_service.create_project("proj1")
        permission_service.grant_access(alice["id"], "proj1", "write")

        assert permission_service.revoke_access(alice["id"], "proj1") is True
        assert permission_service.can_access_project(alice["id"], "proj1") is False

    def test_revoke_nonexistent_access(self):
        user_service.create_user("alice", "pass1")
        alice = user_service.get_user("alice")
        assert permission_service.revoke_access(alice["id"], "proj1") is False

    def test_upsert_same_permission(self):
        user_service.create_user("alice", "pass1")
        alice = user_service.get_user("alice")
        project_service.create_project("proj1")

        permission_service.grant_access(alice["id"], "proj1", "read")
        permission_service.grant_access(alice["id"], "proj1", "write")

        perms = permission_service.get_user_permissions(alice["id"])
        assert len(perms) == 1
        assert perms[0]["role"] == "write"


class TestPermissionQueries:
    def test_can_access_project(self):
        user_service.create_user("alice", "pass1")
        alice = user_service.get_user("alice")
        project_service.create_project("proj1")

        assert permission_service.can_access_project(alice["id"], "proj1") is False
        permission_service.grant_access(alice["id"], "proj1")
        assert permission_service.can_access_project(alice["id"], "proj1") is True

    def test_get_user_permissions(self):
        user_service.create_user("alice", "pass1")
        alice = user_service.get_user("alice")
        project_service.create_project("proj1")
        project_service.create_project("proj2")
        permission_service.grant_access(alice["id"], "proj1", "read")
        permission_service.grant_access(alice["id"], "proj2", "write")

        perms = permission_service.get_user_permissions(alice["id"])
        assert len(perms) == 2
        names = {p["project_name"] for p in perms}
        assert names == {"proj1", "proj2"}

    def test_get_project_permissions(self):
        user_service.create_user("alice", "pass1")
        user_service.create_user("bob", "pass2")
        alice = user_service.get_user("alice")
        bob = user_service.get_user("bob")
        project_service.create_project("proj1")
        permission_service.grant_access(alice["id"], "proj1", "read")
        permission_service.grant_access(bob["id"], "proj1", "write")

        perms = permission_service.get_project_permissions("proj1")
        assert len(perms) == 2
        names = {p["username"] for p in perms}
        assert names == {"alice", "bob"}

    def test_get_accessible_projects(self):
        user_service.create_user("alice", "pass1")
        alice = user_service.get_user("alice")
        project_service.create_project("proj1")
        project_service.create_project("proj2")
        permission_service.grant_access(alice["id"], "proj1")

        projects = permission_service.get_accessible_projects(alice["id"])
        assert projects == ["proj1"]


# ═══════════════════════════════════════
# AuditService Tests
# ═══════════════════════════════════════


class TestAuditLog:
    def test_log_entry(self):
        result = audit_service.log(1, "create", "project", entity_id=42, details="test")
        assert result is not None
        assert result["action"] == "create"
        assert result["entity_type"] == "project"
        assert result["entity_id"] == 42
        assert result["details"] == "test"
        assert result["username"] == "system"  # user_id=1 не существует в БД

    def test_log_with_old_and_new_value(self):
        result = audit_service.log(
            1, "update", "annotation", entity_id=5,
            old_value={"text": "old"},
            new_value={"text": "new"}
        )
        assert result["old_value"] == {"text": "old"}
        assert result["new_value"] == {"text": "new"}

    def test_get_logs(self):
        audit_service.log(1, "create", "project", entity_id=1)
        audit_service.log(1, "update", "project", entity_id=1)
        audit_service.log(2, "delete", "image", entity_id=5)

        logs = audit_service.get_logs()
        assert len(logs) == 3

        # Filter by user
        logs_user = audit_service.get_logs(user_id=1)
        assert len(logs_user) == 2

        # Filter by entity_type
        logs_type = audit_service.get_logs(entity_type="image")
        assert len(logs_type) == 1

        # Filter by action
        logs_action = audit_service.get_logs(action="delete")
        assert len(logs_action) == 1

    def test_get_logs_with_limit_offset(self):
        for i in range(10):
            audit_service.log(1, "create", "project", entity_id=i)

        logs = audit_service.get_logs(limit=3, offset=0)
        assert len(logs) == 3

        logs2 = audit_service.get_logs(limit=3, offset=7)
        assert len(logs2) == 3

    def test_user_stats(self):
        audit_service.log(1, "create", "project", entity_id=1)
        audit_service.log(1, "create", "project", entity_id=2)
        audit_service.log(1, "update", "annotation", entity_id=3)
        audit_service.log(1, "delete", "image", entity_id=4)

        stats = audit_service.get_user_stats(1)
        assert stats["total_actions"] == 4
        assert stats["by_action"]["create"] == 2
        assert stats["by_action"]["update"] == 1
        assert stats["by_action"]["delete"] == 1
        assert stats["by_entity_type"]["project"] == 2


# ═══════════════════════════════════════
# Permission + Audit API Tests
# ═══════════════════════════════════════


@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.test_client() as test_client:
        yield test_client


class TestPermissionAPI:
    def _login_admin(self, client):
        user_service.create_user("admin", "admin123", is_admin=True)
        with client.session_transaction() as sess:
            sess['is_admin'] = True
            sess['username'] = 'admin'
            sess['user_id'] = 1

    def test_grant_permission(self, client):
        self._login_admin(client)
        user_service.create_user("alice", "pass1")
        project_service.create_project("proj1")
        alice = user_service.get_user("alice")

        resp = client.post('/api/projects/proj1/permissions', json={
            "user_id": alice["id"],
            "role": "read"
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["permission"]["role"] == "read"

    def test_grant_permission_no_user_id(self, client):
        self._login_admin(client)
        project_service.create_project("proj1")
        resp = client.post('/api/projects/proj1/permissions', json={"role": "read"})
        assert resp.status_code == 400

    def test_get_project_permissions(self, client):
        self._login_admin(client)
        user_service.create_user("alice", "pass1")
        alice = user_service.get_user("alice")
        project_service.create_project("proj1")
        permission_service.grant_access(alice["id"], "proj1", "write")

        resp = client.get('/api/projects/proj1/permissions')
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["permissions"]) == 1

    def test_revoke_permission(self, client):
        self._login_admin(client)
        user_service.create_user("alice", "pass1")
        alice = user_service.get_user("alice")
        project_service.create_project("proj1")
        permission_service.grant_access(alice["id"], "proj1")

        resp = client.delete(f'/api/projects/proj1/permissions/{alice["id"]}')
        assert resp.status_code == 200

    def test_get_user_permissions(self, client):
        self._login_admin(client)
        user_service.create_user("alice", "pass1")
        alice = user_service.get_user("alice")
        project_service.create_project("proj1")
        permission_service.grant_access(alice["id"], "proj1", "write")

        resp = client.get(f'/api/users/{alice["id"]}/permissions')
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["permissions"]) == 1


class TestAuditAPI:
    def _login_admin(self, client):
        user_service.create_user("admin", "admin123", is_admin=True)
        with client.session_transaction() as sess:
            sess['is_admin'] = True
            sess['username'] = 'admin'
            sess['user_id'] = 1

    def test_get_audit_log(self, client):
        self._login_admin(client)
        audit_service.log(1, "create", "project", entity_id=1, details="test")

        resp = client.get('/api/audit')
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["logs"]) == 1

    def test_get_audit_log_filter_by_action(self, client):
        self._login_admin(client)
        audit_service.log(1, "create", "project")
        audit_service.log(1, "delete", "image")

        resp = client.get('/api/audit?action=create')
        data = resp.get_json()
        assert len(data["logs"]) == 1

    def test_get_user_stats(self, client):
        self._login_admin(client)
        user_service.create_user("alice", "pass1", is_admin=True)
        alice = user_service.get_user("alice")
        for i in range(5):
            audit_service.log(alice["id"], "create", "project", entity_id=i)

        resp = client.get(f'/api/audit/stats/{alice["id"]}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["stats"]["total_actions"] == 5


class TestProjectAccessFiltering:
    """Тесты фильтрации проектов по правам в реальных API endpoints."""

    def _login_as(self, client, username, is_admin=False):
        user_service.create_user(username, "pass123", is_admin=is_admin)
        user = user_service.get_user(username)
        with client.session_transaction() as sess:
            sess['is_admin'] = is_admin
            sess['username'] = username
            sess['user_id'] = user["id"]

    def test_admin_sees_all_projects(self, client):
        """Admin видит все проекты."""
        from app import app, USE_AUTH
        monkeypatch_available = True
        try:
            import app as app_module
            old_use_auth = app_module.USE_AUTH
            app_module.USE_AUTH = True
        except:
            monkeypatch_available = False

        project_service.create_project("proj1")
        project_service.create_project("proj2")
        self._login_as(client, "admin", is_admin=True)

        resp = client.get('/api/projects')
        data = resp.get_json()
        names = {p["name"] for p in data["projects"]}
        assert "proj1" in names
        assert "proj2" in names

        if monkeypatch_available:
            app_module.USE_AUTH = old_use_auth

    def test_user_sees_only_assigned_projects(self, client, monkeypatch):
        """Non-admin видит только назначенные проекты."""
        monkeypatch.setattr("app.USE_AUTH", True)
        project_service.create_project("proj1")
        project_service.create_project("proj2")
        project_service.create_project("proj3")

        user_service.create_user("alice", "pass123")
        alice = user_service.get_user("alice")
        permission_service.grant_access(alice["id"], "proj1", "write")
        permission_service.grant_access(alice["id"], "proj3", "read")

        with client.session_transaction() as sess:
            sess['is_admin'] = False
            sess['username'] = 'alice'
            sess['user_id'] = alice["id"]

        resp = client.get('/api/projects')
        data = resp.get_json()
        names = {p["name"] for p in data["projects"]}
        assert "proj1" in names
        assert "proj3" in names
        assert "proj2" not in names  # нет доступа

    def test_user_with_no_permissions_sees_nothing(self, client, monkeypatch):
        """Пользователь без прав не видит проектов."""
        monkeypatch.setattr("app.USE_AUTH", True)
        project_service.create_project("secret_proj")

        user_service.create_user("nobody", "pass123")
        nobody = user_service.get_user("nobody")

        with client.session_transaction() as sess:
            sess['is_admin'] = False
            sess['username'] = 'nobody'
            sess['user_id'] = nobody["id"]

        resp = client.get('/api/projects')
        data = resp.get_json()
        assert data["projects"] == []

    def test_project_detail_denied_without_access(self, client, monkeypatch):
        """GET /api/projects/<name> — 403 без прав."""
        monkeypatch.setattr("app.USE_AUTH", True)
        project_service.create_project("restricted")

        user_service.create_user("alice", "pass123")
        alice = user_service.get_user("alice")

        with client.session_transaction() as sess:
            sess['is_admin'] = False
            sess['username'] = 'alice'
            sess['user_id'] = alice["id"]

        resp = client.get('/api/projects/restricted')
        assert resp.status_code == 403
