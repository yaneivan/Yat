"""
E2E tests for authorization.
"""
import os
import time
import pytest


@pytest.fixture
def server_url():
    """Base URL for tests."""
    return os.getenv("SERVER_URL", "http://127.0.0.1:5000")


@pytest.fixture
def project_name():
    """Unique project name for test."""
    return f"test_project_{int(time.time()*1000)}"


class TestLogin:
    """Login page tests."""

    def test_login_page_loads(self, page, app_server):
        """Login page loads."""
        page.goto(f"{app_server}/login")
        page.wait_for_selector('input[name="username"]')
        page.wait_for_selector('input[name="password"]')
        page.wait_for_selector('button[type="submit"]')

    def test_successful_login(self, page, app_server):
        """Successful login redirects to main page."""
        page.goto(f"{app_server}/login")
        page.fill('input[name="username"]', "admin")
        page.fill('input[name="password"]', "admin123")
        page.click('button[type="submit"]')

        if '/login' in page.url:
            error = page.query_selector('.error-message')
            if error:
                raise Exception(f"Login failed: {error.inner_text()}")

        page.wait_for_load_state('networkidle', timeout=10000)
        assert '/login' not in page.url
        assert "Yat" in page.title()

    def test_failed_login_wrong_password(self, page, app_server):
        """Wrong password shows error."""
        page.goto(f"{app_server}/login")
        page.fill('input[name="username"]', "admin")
        page.fill('input[name="password"]', "wrong")
        page.click('button[type="submit"]')

        page.wait_for_selector(".error-message", timeout=5000)
        assert "/login" in page.url


class TestLogout:
    """Logout tests."""

    def test_logout_redirects_to_login(self, page, app_server):
        """Logout redirects to login page. Uses fresh page."""
        page.goto(f"{app_server}/login")
        page.fill('input[name="username"]', "admin")
        page.fill('input[name="password"]', "admin123")
        page.click('button[type="submit"]')
        page.wait_for_load_state("domcontentloaded", timeout=10000)
        
        page.goto(f"{app_server}/logout")
        page.wait_for_url("**/login**")


class TestNavigation:
    """Navigation tests."""

    def test_main_page_loads(self, page, app_server):
        """Main page loads."""
        page.goto(f"{app_server}/")
        time.sleep(1)
        assert page.title() is not None

    def test_page_content(self, page, app_server):
        """Page contains expected content."""
        page.goto(f"{app_server}/")
        time.sleep(1)
        body = page.content()
        assert "Yat" in body or "yat" in body.lower()


class TestProjectList:
    """Project list tests."""

    def test_projects_container_exists(self, authenticated_page, app_server):
        """Projects container exists."""
        authenticated_page.goto(f"{app_server}/")
        time.sleep(0.3)
        container = authenticated_page.query_selector("#projects-container")
        assert container is not None

    def test_create_button_exists(self, authenticated_page, app_server):
        """Create project button exists."""
        authenticated_page.goto(f"{app_server}/")
        create_btn = authenticated_page.query_selector("button:has-text('+ Создать проект')")
        assert create_btn is not None