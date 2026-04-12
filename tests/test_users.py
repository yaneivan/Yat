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
from services.audit_service import audit_service
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
        result = user_service.create_user("alice", "secret123")
        assert result is not None
        assert result["username"] == "alice"
        assert result["is_admin"] is False

    def test_create_admin(self):
        result = user_service.create_user("boss", "adminpass", is_admin=True)
        assert result["is_admin"] is True

    def test_create_duplicate_username(self):
        user_service.create_user("alice", "secret123")
        result = user_service.create_user("alice", "different_pass")
        assert result is None

    def test_create_user_default_role(self):
        """По умолчанию пользователь не админ."""
        result = user_service.create_user("bob", "pass123")
        assert result["is_admin"] is False

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
        user_service.create_user("alice", "secret123", is_admin=True)
        result = user_service.authenticate("alice", "secret123")
        assert result is not None
        assert result["username"] == "alice"
        assert result["is_admin"] is True

    def test_authenticate_wrong_password(self):
        user_service.create_user("alice", "secret123")
        result = user_service.authenticate("alice", "wrong_password")
        assert result is None

    def test_authenticate_wrong_username(self):
        user_service.create_user("alice", "secret123")
        result = user_service.authenticate("nonexistent", "secret123")
        assert result is None

    def test_authenticate_inactive_user(self):
        """Нет is_active — тест не нужен."""
        pass


class TestUserUpdate:
    def test_update_to_admin(self):
        user_service.create_user("alice", "secret123")
        result = user_service.update_user("alice", is_admin=True)
        assert result["is_admin"] is True

    def test_update_password(self):
        user_service.create_user("alice", "old_pass")
        user_service.update_user("alice", new_password="new_pass")
        assert user_service.authenticate("alice", "old_pass") is None
        assert user_service.authenticate("alice", "new_pass") is not None

    def test_update_nonexistent_user(self):
        result = user_service.update_user("ghost", is_admin=True)
        assert result is None

    def test_update_all_fields(self):
        """Проверяет что update_user работает без is_active."""
        user_service.create_user("alice", "oldpass")
        result = user_service.update_user("alice", new_password="newpass", is_admin=True)
        assert result is not None
        assert result["is_admin"] is True


class TestUserDelete:
    def test_delete_user(self):
        user_service.create_user("alice", "secret123")
        assert user_service.delete_user("alice") is True
        assert user_service.get_user("alice") is None

    def test_delete_nonexistent_user(self):
        assert user_service.delete_user("ghost") is False

    def test_cannot_delete_last_admin(self):
        """Последний админ не может быть удалён."""
        user_service.create_user("boss", "adminpass", is_admin=True)
        assert user_service.delete_user("boss") is False  # last admin

    def test_can_delete_admin_if_other_admin_exists(self):
        """Если есть другой админ — можно удалить."""
        user_service.create_user("boss1", "pass1", is_admin=True)
        user_service.create_user("boss2", "pass2", is_admin=True)
        assert user_service.delete_user("boss1") is True

    def test_can_delete_non_admin(self):
        user_service.create_user("boss", "pass1", is_admin=True)
        user_service.create_user("alice", "pass2")
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


class TestHasUsers:
    def test_has_users_true(self):
        user_service.create_user("alice", "pass1")
        assert user_service.has_users() is True

    def test_has_users_false(self):
        assert user_service.has_users() is False


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


def _login_admin_for_test(client):
    """Создаёт админа и логинит его."""
    user_service.create_user("admin", "admin123", is_admin=True)
    admin = user_service.get_user("admin")
    with client.session_transaction() as sess:
        sess['is_admin'] = True
        sess['username'] = 'admin'
        sess['user_id'] = admin["id"]


class TestUserAPI:
    def _login(self, client, username="admin", password="admin123"):
        """Вход как админ для доступа к /api/users."""
        user_service.create_user(username, password, is_admin=True)
        with client.session_transaction() as sess:
            sess['is_admin'] = True
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
            "is_admin": False
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
            "is_admin": False
        })
        assert resp.status_code == 409

    def test_create_user_missing_fields(self, client):
        self._login(client)
        resp = client.post('/api/users', json={"username": "test"})
        assert resp.status_code == 400

    def test_create_user_is_admin_flag(self, client):
        """is_admin=True создаёт админа."""
        import uuid
        uniq = uuid.uuid4().hex[:8]
        user_service.create_user(f"admin_{uniq}", "admin123", is_admin=True)
        with client.session_transaction() as sess:
            sess['is_admin'] = True
            sess['username'] = f'admin_{uniq}'
            sess['user_id'] = user_service.get_user(f"admin_{uniq}")["id"]
        resp = client.post('/api/users', json={
            "username": f"user_{uniq}",
            "password": "pass",
            "is_admin": True
        })
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["user"]["is_admin"] is True

    def test_update_user(self, client):
        self._login(client)
        user_service.create_user("alice", "oldpass")
        alice = user_service.get_user("alice")
        resp = client.put(f'/api/users/{alice["id"]}', json={
            "is_admin": True,
            "new_password": "newpass"
        })
        assert resp.status_code == 200
        assert resp.get_json()["user"]["is_admin"] is True

    def test_update_nonexistent_user(self, client):
        self._login(client)
        resp = client.put('/api/users/9999', json={"is_admin": True})
        assert resp.status_code == 404

    def test_delete_user(self, client):
        self._login(client)
        user_service.create_user("boss2", "pass2", is_admin=True)  # второй админ
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
        assert data["is_admin"] is True
        assert data["username"] == "admin"

    def test_list_users_unauthenticated_redirects(self, client):
        """Без сессии — редирект на login (если USE_AUTH=True)."""
        # При USE_AUTH=False — открыто, поэтому пропускаем
        import config
        if not config.ENABLE_AUTH:
            return
        resp = client.get('/api/users')
        assert resp.status_code in (302, 403)

    def test_non_admin_cannot_access_users(self, client, monkeypatch):
        """Non-admin не может получить список пользователей."""
        monkeypatch.setattr("app.USE_AUTH", True)
        user_service.create_user("regular", "pass123")
        with client.session_transaction() as sess:
            sess['is_admin'] = False
            sess['username'] = 'regular'
            sess['user_id'] = 1
        resp = client.get('/api/users')
        assert resp.status_code == 403

    def test_non_admin_cannot_create_user(self, client, monkeypatch):
        monkeypatch.setattr("app.USE_AUTH", True)
        user_service.create_user("regular", "pass123")
        with client.session_transaction() as sess:
            sess['is_admin'] = False
            sess['username'] = 'regular'
            sess['user_id'] = 1
        resp = client.post('/api/users', json={"username": "new", "password": "pass", "is_admin": False})
        assert resp.status_code == 403

    def test_non_admin_cannot_delete_user(self, client, monkeypatch):
        monkeypatch.setattr("app.USE_AUTH", True)
        user_service.create_user("regular", "pass123")
        user_service.create_user("admin2", "pass", is_admin=True)  # второй админ
        with client.session_transaction() as sess:
            sess['is_admin'] = False
            sess['username'] = 'regular'
            sess['user_id'] = 1
        resp = client.delete('/api/users/1')
        assert resp.status_code == 403


class TestLoginFlow:
    """Интеграционные тесты /login endpoint."""

    def test_login_db_success(self, client, monkeypatch):
        monkeypatch.setattr("app.USE_AUTH", True)
        user_service.create_user("alice", "secret123", is_admin=True)
        resp = client.post('/login', data={'username': 'alice', 'password': 'secret123'}, follow_redirects=False)
        assert resp.status_code in (302, 303)
        with client.session_transaction() as sess:
            assert sess['username'] == 'alice'
            assert sess.get('is_admin', False)

    def test_login_db_wrong_password(self, client, monkeypatch):
        monkeypatch.setattr("app.USE_AUTH", True)
        user_service.create_user("alice", "secret123")
        resp = client.post('/login', data={'username': 'alice', 'password': 'wrong'}, follow_redirects=False)
        assert resp.status_code == 200
        assert 'Неверный' in resp.data.decode('utf-8')

    def test_login_empty_username(self, client, monkeypatch):
        monkeypatch.setattr("app.USE_AUTH", True)
        user_service.create_user("admin", "admin123", is_admin=True)
        resp = client.post('/login', data={'username': '   ', 'password': 'admin123'}, follow_redirects=False)
        assert resp.status_code == 200  # ошибка — пустой username


class TestUserEdgeCases:
    """Граничные случаи UserService."""

    def test_get_user_by_id(self):
        user_service.create_user("alice", "pass1")
        alice = user_service.get_user("alice")
        result = user_service.get_user_by_id(alice["id"])
        assert result is not None
        assert result["username"] == "alice"

    def test_get_user_by_id_nonexistent(self):
        assert user_service.get_user_by_id(9999) is None

    def test_create_user_whitespace_username(self):
        result = user_service.create_user("   ", "pass123")
        assert result is not None
        result2 = user_service.create_user("  ", "pass456")
        assert result2 is not None

    def test_create_user_very_long_password(self):
        long_pass = "x" * 500
        result = user_service.create_user("longpass", long_pass)
        assert result is not None
        assert user_service.authenticate("longpass", long_pass) is not None

    def test_create_user_special_characters(self):
        username = "user@#$%^&*()"
        password = "p@$$w0rd!№;%:?"
        result = user_service.create_user(username, password)
        assert result is not None
        assert user_service.authenticate(username, password) is not None

    def test_rollback_on_duplicate(self):
        """Убедиться что rollback работает после дубликата."""
        user_service.create_user("alice", "pass1")
        result1 = user_service.create_user("alice", "pass2")
        assert result1 is None
        result2 = user_service.create_user("bob", "pass3")
        assert result2 is not None

    def test_xss_username(self):
        """XSS в username не должен ломать систему."""
        result = user_service.create_user("<script>alert(1)</script>", "pass123")
        assert result is not None
        user = user_service.get_user("<script>alert(1)</script>")
        assert user is not None  # имя сохраняется как есть, экранируется при выводе


class TestPasswordChange:
    """Тесты смены пароля."""

    def test_change_own_password_success(self, client, monkeypatch):
        monkeypatch.setattr("app.USE_AUTH", True)
        user_service.create_user("alice", "oldpass")
        alice = user_service.get_user("alice")
        with client.session_transaction() as sess:
            sess['is_admin'] = False
            sess['username'] = 'alice'
            sess['user_id'] = alice['id']

        resp = client.post('/api/users/me/password', json={
            'current_password': 'oldpass',
            'new_password': 'newpass'
        })
        assert resp.status_code == 200
        # Проверяем что новый пароль работает
        assert user_service.authenticate("alice", "oldpass") is None
        assert user_service.authenticate("alice", "newpass") is not None

    def test_change_own_password_wrong_current(self, client, monkeypatch):
        monkeypatch.setattr("app.USE_AUTH", True)
        user_service.create_user("alice", "oldpass")
        alice = user_service.get_user("alice")
        with client.session_transaction() as sess:
            sess['is_admin'] = False
            sess['username'] = 'alice'
            sess['user_id'] = alice['id']

        resp = client.post('/api/users/me/password', json={
            'current_password': 'wrong',
            'new_password': 'newpass'
        })
        assert resp.status_code == 403

    def test_change_own_password_empty_fields(self, client, monkeypatch):
        monkeypatch.setattr("app.USE_AUTH", True)
        user_service.create_user("alice", "oldpass")
        alice = user_service.get_user("alice")
        with client.session_transaction() as sess:
            sess['is_admin'] = False
            sess['username'] = 'alice'
            sess['user_id'] = alice['id']

        resp = client.post('/api/users/me/password', json={
            'current_password': '',
            'new_password': ''
        })
        assert resp.status_code == 400

    def test_change_own_password_not_authenticated(self, client, monkeypatch):
        monkeypatch.setattr("app.USE_AUTH", True)
        resp = client.post('/api/users/me/password', json={
            'current_password': 'x',
            'new_password': 'y'
        }, follow_redirects=False)
        # check_auth() редиректит на /login при отсутствии сессии
        assert resp.status_code in (302, 401)

    def test_admin_reset_user_password(self, client, monkeypatch):
        monkeypatch.setattr("app.USE_AUTH", True)
        _login_admin_for_test(client)
        user_service.create_user("alice", "oldpass")
        alice = user_service.get_user("alice")

        resp = client.post(f'/api/users/{alice["id"]}/reset-password', json={
            'password': 'temppass'
        })
        assert resp.status_code == 200
        # Проверяем что новый пароль работает
        assert user_service.authenticate("alice", "oldpass") is None
        assert user_service.authenticate("alice", "temppass") is not None

    def test_admin_reset_password_nonexistent_user(self, client, monkeypatch):
        monkeypatch.setattr("app.USE_AUTH", True)
        _login_admin_for_test(client)
        resp = client.post('/api/users/9999/reset-password', json={
            'password': 'newpass'
        })
        assert resp.status_code == 404

    def test_admin_reset_password_empty(self, client, monkeypatch):
        monkeypatch.setattr("app.USE_AUTH", True)
        _login_admin_for_test(client)
        user_service.create_user("alice", "oldpass")
        alice = user_service.get_user("alice")
        resp = client.post(f'/api/users/{alice["id"]}/reset-password', json={})
        assert resp.status_code == 400

    def test_non_admin_cannot_reset_password(self, client, monkeypatch):
        monkeypatch.setattr("app.USE_AUTH", True)
        user_service.create_user("regular", "pass")
        regular = user_service.get_user("regular")
        with client.session_transaction() as sess:
            sess['is_admin'] = False
            sess['username'] = 'regular'
            sess['user_id'] = regular['id']

        resp = client.post('/api/users/1/reset-password', json={'password': 'hacked'})
        assert resp.status_code == 403

    def test_change_password_writes_audit_log(self, client, monkeypatch):
        monkeypatch.setattr("app.USE_AUTH", True)
        user_service.create_user("alice", "oldpass")
        alice = user_service.get_user("alice")
        with client.session_transaction() as sess:
            sess['is_admin'] = False
            sess['username'] = 'alice'
            sess['user_id'] = alice['id']

        client.post('/api/users/me/password', json={
            'current_password': 'oldpass',
            'new_password': 'newpass'
        })
        logs = audit_service.get_logs(action="change_password")
        assert len(logs) >= 1
        assert "alice" in logs[0]["details"]

    def test_admin_reset_writes_audit_log(self, client, monkeypatch):
        monkeypatch.setattr("app.USE_AUTH", True)
        _login_admin_for_test(client)
        user_service.create_user("alice", "oldpass")
        alice = user_service.get_user("alice")

        client.post(f'/api/users/{alice["id"]}/reset-password', json={
            'password': 'temppass'
        })
        logs = audit_service.get_logs(action="reset_password")
        assert len(logs) >= 1
        assert "alice" in logs[0]["details"]
