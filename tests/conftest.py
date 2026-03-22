"""
Pytest conftest fixtures for Yat tests.

Fixtures here are automatically available in all test files.
"""
import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

# =============================================================================
# Mock AI Service for fast tests - patch BEFORE any test imports
# =============================================================================

# Create mock AI service
mock_ai_service = MagicMock()
mock_ai_service.is_trocr_available.return_value = False
mock_ai_service.is_yolo_available.return_value = False
mock_ai_service.detect_lines.return_value = []
mock_ai_service.recognize_text.return_value = {}
mock_ai_service.initialize_models = MagicMock()

# Patch at pytest configure time - before any test modules are imported
def pytest_configure(config):
    """Called before any test modules are imported."""
    # Patch services.ai_service.ai_service
    patcher = patch('services.ai_service.ai_service', mock_ai_service)
    patcher.start()
    
    # Also patch in app module (where it's imported as 'from services import ai_service')
    # This needs to be done after app is imported, so we'll do it in a fixture
    config.mock_ai_service = mock_ai_service


@pytest.fixture(autouse=True, scope="function")
def reset_mocks():
    """Reset mock call history before each test."""
    mock_ai_service.reset_mock()
    mock_ai_service.is_trocr_available.return_value = False
    mock_ai_service.is_yolo_available.return_value = False
    mock_ai_service.detect_lines.return_value = []
    mock_ai_service.recognize_text.return_value = {}
    yield mock_ai_service


# =============================================================================
# Temporary Database for tests
# =============================================================================

@pytest.fixture(autouse=True, scope="session")
def temp_db():
    """
    Create temporary database for all tests.

    This prevents tests from destroying the main database.db
    """
    from database.session import engine, Base, DB_PATH
    import sqlite3

    # Create temporary file for test database
    tmpdir = tempfile.mkdtemp()
    temp_db_path = os.path.join(tmpdir, 'test_database.db')

    # Patch DB_PATH to use temp database
    import database.session
    original_db_path = database.session.DB_PATH
    database.session.DB_PATH = Path(temp_db_path)
    database.session.DATABASE_URL = f"sqlite:///{temp_db_path}"

    # Recreate engine with new database path
    database.session.engine = database.session.create_engine(
        f"sqlite:///{temp_db_path}",
        echo=False,
        pool_pre_ping=True,
        connect_args={"check_same_thread": False}
    )

    # Create tables
    Base.metadata.create_all(bind=database.session.engine)

    yield temp_db_path

    # Cleanup
    database.session.DB_PATH = original_db_path
    database.session.DATABASE_URL = f"sqlite:///{original_db_path}"
    if os.path.exists(temp_db_path):
        os.remove(temp_db_path)
    if os.path.exists(tmpdir):
        os.rmdir(tmpdir)

