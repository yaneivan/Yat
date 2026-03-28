"""
Pytest conftest fixtures for Yat tests.

IMPORTANT: This module patches database and storage paths at pytest_configure time,
which happens BEFORE any test modules are imported.

Fixtures here are automatically available in all test files.
"""
import pytest
import tempfile
import os
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

# =============================================================================
# CRITICAL: Patch at pytest_configure time (BEFORE any imports)
# =============================================================================

_temp_test_dir = None
_original_db_path = None
_original_database_url = None
_original_engine = None
_original_SessionLocal = None
_original_storage = None


def pytest_configure(config):
    """
    Called BEFORE any test modules are imported.
    This is the earliest point where we can patch modules.
    """
    global _temp_test_dir, _original_db_path, _original_database_url
    global _original_engine, _original_SessionLocal, _original_storage
    
    import tempfile
    from sqlalchemy import create_engine
    
    # Create temporary directory for all test data
    _temp_test_dir = tempfile.mkdtemp(prefix="yat_test_")
    temp_db_path = os.path.join(_temp_test_dir, 'test_database.db')
    
    # Patch database.session module
    import database.session as session_module
    
    # Store original values
    _original_db_path = session_module.DB_PATH
    _original_database_url = session_module.DATABASE_URL
    _original_engine = session_module.engine
    _original_SessionLocal = session_module.SessionLocal
    
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
    _original_storage = {
        'PROJECTS_FOLDER': storage.PROJECTS_FOLDER,
        'IMAGE_FOLDER': storage.IMAGE_FOLDER,
        'ANNOTATION_FOLDER': storage.ANNOTATION_FOLDER,
        'ORIGINALS_FOLDER': storage.ORIGINALS_FOLDER,
    }
    
    storage.PROJECTS_FOLDER = os.path.join(_temp_test_dir, 'projects')
    storage.IMAGE_FOLDER = os.path.join(_temp_test_dir, 'images')
    storage.ANNOTATION_FOLDER = os.path.join(_temp_test_dir, 'annotations')
    storage.ORIGINALS_FOLDER = os.path.join(_temp_test_dir, 'originals')
    
    # Create directories
    os.makedirs(storage.PROJECTS_FOLDER)
    os.makedirs(storage.IMAGE_FOLDER)
    os.makedirs(storage.ANNOTATION_FOLDER)
    os.makedirs(storage.ORIGINALS_FOLDER)


def pytest_unconfigure(config):
    """
    Called AFTER all tests are done.
    Cleanup temporary files and restore original paths.
    """
    global _temp_test_dir, _original_db_path, _original_database_url
    global _original_engine, _original_SessionLocal, _original_storage
    
    if _temp_test_dir:
        # Restore database.session
        import database.session as session_module
        session_module.DB_PATH = _original_db_path
        session_module.DATABASE_URL = _original_database_url
        session_module.engine = _original_engine
        session_module.SessionLocal = _original_SessionLocal
        
        # Restore storage
        import storage
        storage.PROJECTS_FOLDER = _original_storage['PROJECTS_FOLDER']
        storage.IMAGE_FOLDER = _original_storage['IMAGE_FOLDER']
        storage.ANNOTATION_FOLDER = _original_storage['ANNOTATION_FOLDER']
        storage.ORIGINALS_FOLDER = _original_storage['ORIGINALS_FOLDER']
        
        # Cleanup temp directory
        shutil.rmtree(_temp_test_dir, ignore_errors=True)


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
    # First run the database setup
    _setup_test_database(config)
    
    # Then patch AI service
    patcher = patch('services.ai_service.ai_service', mock_ai_service)
    patcher.start()
    config.mock_ai_service = mock_ai_service


def _setup_test_database(config):
    """Setup test database and storage paths."""
    global _temp_test_dir, _original_db_path, _original_database_url
    global _original_engine, _original_SessionLocal, _original_storage
    
    import tempfile
    from sqlalchemy import create_engine
    
    # Create temporary directory for all test data
    _temp_test_dir = tempfile.mkdtemp(prefix="yat_test_")
    temp_db_path = os.path.join(_temp_test_dir, 'test_database.db')
    
    # Patch database.session module
    import database.session as session_module
    
    # Store original values
    _original_db_path = session_module.DB_PATH
    _original_database_url = session_module.DATABASE_URL
    _original_engine = session_module.engine
    _original_SessionLocal = session_module.SessionLocal
    
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
    _original_storage = {
        'PROJECTS_FOLDER': storage.PROJECTS_FOLDER,
        'IMAGE_FOLDER': storage.IMAGE_FOLDER,
        'ANNOTATION_FOLDER': storage.ANNOTATION_FOLDER,
        'ORIGINALS_FOLDER': storage.ORIGINALS_FOLDER,
    }
    
    storage.PROJECTS_FOLDER = os.path.join(_temp_test_dir, 'projects')
    storage.IMAGE_FOLDER = os.path.join(_temp_test_dir, 'images')
    storage.ANNOTATION_FOLDER = os.path.join(_temp_test_dir, 'annotations')
    storage.ORIGINALS_FOLDER = os.path.join(_temp_test_dir, 'originals')
    
    # Create directories
    os.makedirs(storage.PROJECTS_FOLDER)
    os.makedirs(storage.IMAGE_FOLDER)
    os.makedirs(storage.ANNOTATION_FOLDER)
    os.makedirs(storage.ORIGINALS_FOLDER)


def pytest_unconfigure(config):
    """Cleanup after all tests."""
    global _temp_test_dir, _original_db_path, _original_database_url
    global _original_engine, _original_SessionLocal, _original_storage
    
    if _temp_test_dir:
        # Restore database.session
        import database.session as session_module
        session_module.DB_PATH = _original_db_path
        session_module.DATABASE_URL = _original_database_url
        session_module.engine = _original_engine
        session_module.SessionLocal = _original_SessionLocal
        
        # Restore storage
        import storage
        storage.PROJECTS_FOLDER = _original_storage['PROJECTS_FOLDER']
        storage.IMAGE_FOLDER = _original_storage['IMAGE_FOLDER']
        storage.ANNOTATION_FOLDER = _original_storage['ANNOTATION_FOLDER']
        storage.ORIGINALS_FOLDER = _original_storage['ORIGINALS_FOLDER']
        
        # Cleanup temp directory
        shutil.rmtree(_temp_test_dir, ignore_errors=True)


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
def client():
    """
    Create test Flask client.
    
    Database and storage are already patched by pytest_configure().
    """
    from app import app
    
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False  # Отключить CSRF для тестов
    
    with app.test_client() as test_client:
        yield test_client
