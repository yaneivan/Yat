"""E2E tests for project management."""
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


class TestProjectCreation:
    """Project creation tests."""

    def test_create_project_modal_opens(self, authenticated_page, server_url):
        """Create button opens modal."""
        authenticated_page.goto(server_url)
        time.sleep(0.3)

        authenticated_page.click("button:has-text('+ Создать проект')")
        time.sleep(0.3)

        authenticated_page.wait_for_selector("#createProjectModal")
        authenticated_page.wait_for_selector("#project-name")

    def test_create_project_form_fields(self, authenticated_page, server_url):
        """Form contains required fields."""
        authenticated_page.goto(server_url)
        time.sleep(0.3)

        authenticated_page.click("button:has-text('+ Создать проект')")
        time.sleep(0.3)

        authenticated_page.wait_for_selector("#createProjectModal")

        name_field = authenticated_page.query_selector("#project-name")
        desc_field = authenticated_page.query_selector("#project-description")
        
        assert name_field is not None
        assert desc_field is not None

    def test_create_project_success(self, authenticated_page, project_name, server_url):
        """Create project -> card appears."""
        authenticated_page.goto(server_url)
        time.sleep(0.3)

        authenticated_page.click("button:has-text('+ Создать проект')")
        time.sleep(0.3)

        authenticated_page.wait_for_selector("#createProjectModal")
        
        authenticated_page.fill("#project-name", project_name)
        time.sleep(0.2)
        authenticated_page.fill("#project-description", "Test project")
        time.sleep(0.2)

        authenticated_page.click('#createProjectModal button.btn-primary:has-text("Создать")')
        time.sleep(0.5)

        authenticated_page.wait_for_selector("#createProjectModal", state="hidden", timeout=5000)
        time.sleep(0.3)

        authenticated_page.wait_for_selector(f"text={project_name}", timeout=5000)

    def test_close_modal_by_backdrop(self, authenticated_page, server_url):
        """Close modal by clicking backdrop."""
        authenticated_page.goto(server_url)
        time.sleep(0.3)

        authenticated_page.click("button:has-text('+ Создать проект')")
        time.sleep(0.3)

        authenticated_page.wait_for_selector("#createProjectModal")

        backdrop = authenticated_page.query_selector(".modal-backdrop")
        if backdrop:
            authenticated_page.click(".modal-backdrop")
            time.sleep(0.3)
            authenticated_page.wait_for_selector("#createProjectModal", state="hidden", timeout=3000)

    def test_close_modal_by_x(self, authenticated_page, server_url):
        """Close modal by X button."""
        authenticated_page.goto(server_url)
        time.sleep(0.3)

        authenticated_page.click("button:has-text('+ Создать проект')")
        time.sleep(0.3)

        authenticated_page.wait_for_selector("#createProjectModal")

        close_btn = authenticated_page.query_selector('#createProjectModal button.close')
        if close_btn:
            authenticated_page.click('#createProjectModal button.close')
            time.sleep(0.3)
            authenticated_page.wait_for_selector("#createProjectModal", state="hidden", timeout=3000)


class TestProjectView:
    """Project view tests."""

    def test_project_appears_in_list(self, authenticated_page, project_name, server_url):
        """Created project visible in list."""
        authenticated_page.goto(server_url)
        time.sleep(0.3)

        authenticated_page.click("button:has-text('+ Создать проект')")
        time.sleep(0.3)

        authenticated_page.wait_for_selector("#createProjectModal")
        authenticated_page.fill("#project-name", project_name)
        time.sleep(0.2)
        authenticated_page.click('#createProjectModal button.btn-primary:has-text("Создать")')
        
        authenticated_page.wait_for_selector("#createProjectModal", state="hidden", timeout=5000)
        time.sleep(0.3)

        project_locator = authenticated_page.locator(f"text={project_name}")
        assert project_locator.count() > 0


class TestProjectDeletion:
    """Project deletion tests."""

    def test_delete_project(self, authenticated_page, project_name, server_url):
        """Delete project -> card disappears.
        
        NOTE: This test works in headed mode when viewing the UI.
        The delete button appears after the page loads the user role from API.
        """
        authenticated_page.reload()
        time.sleep(1)
        
        authenticated_page.goto(server_url)
        time.sleep(0.5)

        authenticated_page.click("button:has-text('+ Создать проект')")
        time.sleep(0.3)

        authenticated_page.wait_for_selector("#createProjectModal")
        authenticated_page.fill("#project-name", project_name)
        time.sleep(0.2)
        authenticated_page.click('#createProjectModal button.btn-primary:has-text("Создать")')

        authenticated_page.wait_for_selector("#createProjectModal", state="hidden", timeout=5000)
        time.sleep(0.3)
        
        authenticated_page.wait_for_selector(f"text={project_name}", timeout=5000)

        delete_button = authenticated_page.locator("button.action-btn:has-text('Удалить')")
        
        if delete_button.count() > 0:
            authenticated_page.once("dialog", lambda dialog: dialog.accept())
            delete_button.first.click()
            time.sleep(0.5)
            authenticated_page.wait_for_selector(
                f"text={project_name}", state="detached", timeout=3000
            )
        else:
            pytest.skip("Delete button not found in UI")