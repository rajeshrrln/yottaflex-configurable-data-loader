import pytest
from pathlib import Path

@pytest.fixture
def project_root(): return Path(__file__).resolve().parents[1]
