"""
Pytest conftest fixtures for Yat tests.

Fixtures here are automatically available in all test files.

IMPORTANT: This fixture patches database and storage paths BEFORE any test imports.
"""
import pytest
import tempfile
import os
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

# =============================================================================
# IMPORTANT: Setup test environment BEFORE any app imports
# =============================================================================

@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """
    Setup test environment BEFORE any tests run.
    
    This fixture:
    1. Creates temporary database
    2. Creates temporary data directories
    3. Patches all paths before app is imported
    
    Must run before any other fixtures that import app or database modules.
    """
    # Create temporary directory for all test data
    tmpdir = tempfile.mkdtemp(prefix="yat_test_")
    temp_db_path = os.path.join(tmpdir, 'test_database.db')
    
    # Patch database.session module BEFORE it's imported elsewhere
    import database.session as session_module
    from sqlalchemy import create_engine
    
    # Store original values for cleanup
    original_db_path = session_module.DB_PATH
    original_database_url = session_module.DATABASE_URL
    original_engine = session_module.engine
    original_SessionLocal = session_module.SessionLocal
    
    # Patch DB_PATH and DATABASE_URL
    session_module.DB_PATH = Path(temp_db_path)
    session_module.DATABASE_URL = f"sqlite:///{temp_db_path}"
    
    # Recreate engine with temp database
    session_module.engine = create_engine(
        f"sqlite:///{temp_db_path}",
        echo=False,
        connect_args={
            "check_same_thread": False,
            "timeout": 60
        }
    )
    session_module.SessionLocal = session_module.sessionmaker(
        autocommit=False, 
        autoflush=False, 
        bind=session_module.engine
    )
    
    # Create tables
    from database import models  # noqa: F401
    session_module.Base.metadata.create_all(bind=session_module.engine)
    
    # Patch storage paths
    import storage
    original_storage = {
        'PROJECTS_FOLDER': storage.PROJECTS_FOLDER,
        'IMAGE_FOLDER': storage.IMAGE_FOLDER,
        'ANNOTATION_FOLDER': storage.ANNOTATION_FOLDER,
        'ORIGINALS_FOLDER': storage.ORIGINALS_FOLDER,
    }
    
    storage.PROJECTS_FOLDER = os.path.join(tmpdir, 'projects')
    storage.IMAGE_FOLDER = os.path.join(tmpdir, 'images')
    storage.ANNOTATION_FOLDER = os.path.join(tmpdir, 'annotations')
    storage.ORIGINALS_FOLDER = os.path.join(tmpdir, 'originals')
    
    # Create directories
    os.makedirs(storage.PROJECTS_FOLDER)
    os.makedirs(storage.IMAGE_FOLDER)
    os.makedirs(storage.ANNOTATION_FOLDER)
    os.makedirs(storage.ORIGINALS_FOLDER)
    
    yield {
        'tmpdir': tmpdir,
        'db_path': temp_db_path,
    }
    
    # Cleanup
    session_module.DB_PATH = original_db_path
    session_module.DATABASE_URL = original_database_url
    session_module.engine = original_engine
    session_module.SessionLocal = original_SessionLocal
    
    storage.PROJECTS_FOLDER = original_storage['PROJECTS_FOLDER']
    storage.IMAGE_FOLDER = original_storage['IMAGE_FOLDER']
    storage.ANNOTATION_FOLDER = original_storage['ANNOTATION_FOLDER']
    storage.ORIGINALS_FOLDER = original_storage['ORIGINALS_FOLDER']
    
    shutil.rmtree(tmpdir, ignore_errors=True)


# =============================================================================
# Mock AI Service for fast tests
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
# Flask test client
# =============================================================================

@pytest.fixture
def client(setup_test_environment):
    """
    Create test Flask client.
    
    This fixture depends on setup_test_environment to ensure
    database and storage are patched before app is imported.
    """
    from app import app
    
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False  # Отключить CSRF для тестов
    
    with app.test_client() as test_client:
        yield test_client
