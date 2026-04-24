"""Playwright E2E tests conftest."""
import os
import pytest
from pathlib import Path
from dotenv import load_dotenv


def _load_config():
    """Load configuration from .env file."""
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=True)


_load_config()

BASE_URL = os.getenv("SERVER_URL", "http://127.0.0.1:5000")
USE_AUTOMATIC_SERVER = os.getenv("USE_AUTOMATIC_SERVER", "false").lower() == "true"
HEADED = os.getenv("HEADED", "false").lower() == "true" and bool(os.environ.get("DISPLAY"))


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    """Configure headed/headless mode."""
    browser_type_launch_args["headless"] = not HEADED
    return browser_type_launch_args


@pytest.fixture(scope="session")
def base_url():
    """Base URL for tests."""
    return BASE_URL


@pytest.fixture(scope="session")
def app_server():
    """Flask server for tests with separate test database."""
    if not USE_AUTOMATIC_SERVER:
        yield None
        return

    import subprocess
    import time
    import signal
    import tempfile

    project_root = Path(__file__).parent.parent.parent

    temp_test_dir = tempfile.mkdtemp(prefix="yat_e2e_test_")
    test_db_path = os.path.join(temp_test_dir, "test_database.db")
    test_images_dir = os.path.join(temp_test_dir, "images")
    test_projects_dir = os.path.join(temp_test_dir, "projects")
    test_annotations_dir = os.path.join(temp_test_dir, "annotations")
    test_originals_dir = os.path.join(temp_test_dir, "originals")

    os.makedirs(test_images_dir, exist_ok=True)
    os.makedirs(test_projects_dir, exist_ok=True)
    os.makedirs(test_annotations_dir, exist_ok=True)
    os.makedirs(test_originals_dir, exist_ok=True)

    env = os.environ.copy()
    env["FLASK_ENV"] = "testing"
    env["USE_AUTOMATIC_SERVER"] = "false"
    env["TESTING"] = "true"
    env["DB_PATH"] = test_db_path
    env["STORAGE_IMAGES"] = test_images_dir
    env["STORAGE_PROJECTS"] = test_projects_dir
    env["STORAGE_ANNOTATIONS"] = test_annotations_dir
    env["STORAGE_ORIGINALS"] = test_originals_dir

    proc = subprocess.Popen(
        ["python", "app.py"],
        cwd=str(project_root),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    max_wait = 30
    for _ in range(max_wait):
        try:
            import requests
            requests.get(BASE_URL, timeout=1)
            break
        except Exception:
            time.sleep(1)

    yield BASE_URL

    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()

    import shutil
    shutil.rmtree(temp_test_dir, ignore_errors=True)


@pytest.fixture
def page(browser):
    """Create a new browser page for each test."""
    page = browser.new_page()
    yield page
    page.close()


@pytest.fixture(scope="session")
def authenticated_page(browser, base_url):
    """Create one authenticated page for session."""
    page = browser.new_page()
    page.goto(f"{base_url}/login")
    page.wait_for_selector('input[name="username"]', timeout=10000)
    page.fill('input[name="username"]', "admin")
    page.fill('input[name="password"]', "admin123")
    page.click('button[type="submit"]')
    page.wait_for_load_state("domcontentloaded", timeout=10000)
    yield page