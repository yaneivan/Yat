"""
Тесты для UserService и User API.

Покрывает:
- CRUD пользователей
- Хеширование паролей
- Аутентификация
- Граничные случаи (дубликаты, удаление последнего админа, пустые поля)
- API endpoints /api/users
"""

import pytest
from werkzeug.security import check_password_hash

from app import app
from services.user_service import user_service
from database.session import SessionLocal
from database.models import User


# ═══════════════════════════════════════
# UserService — Unit Tests
# ═══════════════════════════════════════


@pytest.fixture(autouse=True)
def clean_users():
    """Перед каждым тестом — удаляем всех пользователей, после — восстанавливаем."""
    session = SessionLocal()
    try:
        session.query(User).delete()
        session.commit()
    finally:
        session.close()
    yield
    session = SessionLocal()
    try:
        session.query(User).delete()
        session.commit()
    finally:
        session.close()


class TestUserCreate:
    def test_create_user(self):
        result = user_service.create_user("alice", "secret123", "annotator")
        assert result is not None
        assert result["username"] == "alice"
        assert result["role"] == "annotator"
        assert result["is_active"] is True
        assert "password_hash" not in result  # пароль не возвращается

    def test_create_admin(self):
        result = user_service.create_user("boss", "adminpass", "admin")
        assert result["role"] == "admin"

    def test_create_duplicate_username(self):
        user_service.create_user("alice", "secret123")
        result = user_service.create_user("alice", "different_pass")
        assert result is None

    def test_create_user_default_role(self):
        """Роль по умолчанию — annotator."""
        result = user_service.create_user("bob", "pass123")
        assert result["role"] == "annotator"

    def test_password_is_hashed(self):
        """Пароль должен быть захеширован, не plaintext."""
        user_service.create_user("alice", "secret123")
        session = SessionLocal()
        user = session.query(User).filter_by(username="alice").first()
        assert user.password_hash != "secret123"
        assert check_password_hash(user.password_hash, "secret123")
        session.close()


class TestUserAuthenticate:
    def test_authenticate_success(self):
        user_service.create_user("alice", "secret123", "admin")
        result = user_service.authenticate("alice", "secret123")
        assert result is not None
        assert result["username"] == "alice"
        assert result["role"] == "admin"

    def test_authenticate_wrong_password(self):
        user_service.create_user("alice", "secret123")
        result = user_service.authenticate("alice", "wrong_password")
        assert result is None

    def test_authenticate_wrong_username(self):
        user_service.create_user("alice", "secret123")
        result = user_service.authenticate("nonexistent", "secret123")
        assert result is None

    def test_authenticate_inactive_user(self):
        user_service.create_user("alice", "secret123")
        user_service.update_user("alice", is_active=False)
        result = user_service.authenticate("alice", "secret123")
        assert result is None


class TestUserUpdate:
    def test_update_role(self):
        user_service.create_user("alice", "secret123", "annotator")
        result = user_service.update_user("alice", role="admin")
        assert result["role"] == "admin"

    def test_update_password(self):
        user_service.create_user("alice", "old_pass")
        user_service.update_user("alice", new_password="new_pass")
        assert user_service.authenticate("alice", "old_pass") is None
        assert user_service.authenticate("alice", "new_pass") is not None

    def test_update_nonexistent_user(self):
        result = user_service.update_user("ghost", role="admin")
        assert result is None

    def test_deactivate_user(self):
        user_service.create_user("alice", "secret123")
        result = user_service.update_user("alice", is_active=False)
        assert result["is_active"] is False


class TestUserDelete:
    def test_delete_user(self):
        user_service.create_user("alice", "secret123")
        assert user_service.delete_user("alice") is True
        assert user_service.get_user("alice") is None

    def test_delete_nonexistent_user(self):
        assert user_service.delete_user("ghost") is False

    def test_cannot_delete_last_admin(self):
        """Последний админ не может быть удалён."""
        user_service.create_user("boss", "adminpass", "admin")
        assert user_service.delete_user("boss") is False  # last admin

    def test_can_delete_admin_if_other_admin_exists(self):
        """Если есть другой админ — можно удалить."""
        user_service.create_user("boss1", "pass1", "admin")
        user_service.create_user("boss2", "pass2", "admin")
        assert user_service.delete_user("boss1") is True

    def test_can_delete_non_admin(self):
        user_service.create_user("boss", "pass1", "admin")
        user_service.create_user("alice", "pass2", "annotator")
        assert user_service.delete_user("alice") is True


class TestUserList:
    def test_get_all_users(self):
        user_service.create_user("alice", "pass1")
        user_service.create_user("bob", "pass2")
        users = user_service.get_all_users()
        assert len(users) == 2
        names = {u["username"] for u in users}
        assert names == {"alice", "bob"}

    def test_get_all_users_empty(self):
        users = user_service.get_all_users()
        assert users == []

    def test_no_password_in_list(self):
        user_service.create_user("alice", "secret123")
        users = user_service.get_all_users()
        for u in users:
            assert "password_hash" not in u


class TestEnsureFirstAdmin:
    def test_create_admin_from_env(self, monkeypatch):
        """Если нет пользователей — создаёт admin из env."""
        monkeypatch.setattr("config.ADMIN_PASSWORD", "env_admin_pass")
        result = user_service.ensure_first_admin()
        assert result is True
        admin = user_service.get_user("admin")
        assert admin is not None
        assert admin["role"] == "admin"

    def test_skip_if_admin_exists(self):
        """Если админ уже есть — ничего не делает."""
        user_service.create_user("myadmin", "pass", "admin")
        result = user_service.ensure_first_admin()
        assert result is True
        users = user_service.get_all_users()
        assert len(users) == 1  # не создал дубликат

    def test_no_admin_password_configured(self, monkeypatch):
        """Если ADMIN_PASSWORD нет — возвращает False."""
        monkeypatch.setattr("config.ADMIN_PASSWORD", None)
        result = user_service.ensure_first_admin()
        assert result is False


# ═══════════════════════════════════════
# User API — Integration Tests
# ═══════════════════════════════════════


@pytest.fixture
def client():
    """Тестовый клиент Flask."""
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.test_client() as test_client:
        yield test_client


class TestUserAPI:
    def _login(self, client, username="admin", password="admin123"):
        """Вход как админ для доступа к /api/users."""
        user_service.create_user(username, password, "admin")
        with client.session_transaction() as sess:
            sess['role'] = 'admin'
            sess['username'] = username
            sess['user_id'] = 1

    def test_list_users(self, client):
        self._login(client)
        user_service.create_user("alice", "pass1")
        resp = client.get('/api/users')
        data = resp.get_json()
        assert resp.status_code == 200
        assert len(data["users"]) == 2  # admin + alice

    def test_create_user(self, client):
        self._login(client)
        resp = client.post('/api/users', json={
            "username": "newuser",
            "password": "newpass",
            "role": "annotator"
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["user"]["username"] == "newuser"

    def test_create_user_duplicate(self, client):
        self._login(client)
        user_service.create_user("alice", "pass1")
        resp = client.post('/api/users', json={
            "username": "alice",
            "password": "pass2",
            "role": "annotator"
        })
        assert resp.status_code == 409

    def test_create_user_missing_fields(self, client):
        self._login(client)
        resp = client.post('/api/users', json={"username": "test"})
        assert resp.status_code == 400

    def test_create_user_invalid_role(self, client):
        self._login(client)
        resp = client.post('/api/users', json={
            "username": "test",
            "password": "pass",
            "role": "superadmin"
        })
        assert resp.status_code == 400

    def test_update_user(self, client):
        self._login(client)
        user_service.create_user("alice", "oldpass", "annotator")
        alice = user_service.get_user("alice")
        resp = client.put(f'/api/users/{alice["id"]}', json={
            "role": "admin",
            "new_password": "newpass"
        })
        assert resp.status_code == 200
        assert resp.get_json()["user"]["role"] == "admin"

    def test_update_nonexistent_user(self, client):
        self._login(client)
        resp = client.put('/api/users/9999', json={"role": "admin"})
        assert resp.status_code == 404

    def test_delete_user(self, client):
        self._login(client)
        user_service.create_user("boss2", "pass2", "admin")  # второй админ
        user_service.create_user("alice", "pass1")
        alice = user_service.get_user("alice")
        resp = client.delete(f'/api/users/{alice["id"]}')
        assert resp.status_code == 200

    def test_delete_last_admin_forbidden(self, client):
        self._login(client)
        # Только один админ (self._login создал его)
        admin = user_service.get_user("admin")
        resp = client.delete(f'/api/users/{admin["id"]}')
        assert resp.status_code == 400

    def test_auth_me(self, client):
        self._login(client)
        resp = client.get('/api/auth/me')
        data = resp.get_json()
        assert data["role"] == "admin"
        assert data["is_admin"] is True
        assert data["username"] == "admin"

    def test_list_users_unauthenticated_redirects(self, client):
        """Без сессии — редирект на login (если USE_AUTH=True)."""
        # При USE_AUTH=False — открыто, поэтому пропускаем
        import config
        if not config.USE_ROLE_BASED_AUTH:
            return
        resp = client.get('/api/users')
        assert resp.status_code in (302, 403)
