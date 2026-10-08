import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.services.storage import storage_service
from app.main import app


@pytest.fixture(scope="session")
def test_temp_dir():
    """Creates a temporary directory for test storage and database."""
    tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    yield Path(tmp.name)
    try:
        tmp.cleanup()
    except Exception:
        pass


@pytest.fixture(scope="session")
def test_engine(test_temp_dir):
    """Creates a temporary SQLite test database."""
    db_path = test_temp_dir / "test_certificates.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(test_engine):
    """Provides an isolated database session per test."""
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(test_engine, test_temp_dir):
    """Provides a TestClient with overridden get_db and temporary storage."""
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    # Point storage and processor to temp dir
    test_storage = test_temp_dir / "storage"
    test_storage.mkdir(parents=True, exist_ok=True)
    storage_service.base_dir = test_storage

    # Also override database SessionLocal in processor module for background tasks
    import app.services.processor as processor_module
    processor_module.SessionLocal = TestingSessionLocal
    processor_module.storage_service = storage_service

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
