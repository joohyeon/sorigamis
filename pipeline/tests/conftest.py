import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

@pytest.fixture
def mock_supabase():
    return MagicMock()

@pytest.fixture
def client(mock_supabase):
    from main import app
    from supabase_client import get_supabase
    app.dependency_overrides[get_supabase] = lambda: mock_supabase
    yield TestClient(app)
    app.dependency_overrides.clear()
