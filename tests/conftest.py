"""Shared test fixtures."""

from __future__ import annotations

import time
import uuid

import numpy as np
import pytest

import backend.app.core.config as config_mod
from backend.app.core.config import Settings
from backend.app.database.session_store import init_database
from backend.app.models.document_models import ChunkMetadata, SearchResult
from backend.app.models.chat_models import User


@pytest.fixture
def tmp_db(tmp_path):
    db = str(tmp_path / "test.db")
    init_database(db)
    return db


@pytest.fixture
def settings(tmp_db, tmp_path):
    s = Settings(db_path=tmp_db, faiss_index_dir=str(tmp_path / "faiss"), upload_dir=str(tmp_path / "uploads"), jwt_secret_key="test-secret")
    config_mod._settings = s
    yield s
    config_mod._settings = None


@pytest.fixture
def sample_chunks():
    texts = [
        "All new employees are entitled to 15 days of paid vacation per year. Vacation days accrue on a monthly basis starting from the first day of employment.",
        "The company offers three health insurance plans: Basic, Standard, and Premium. All full-time employees are eligible for health insurance benefits.",
        "Maternity leave policy allows for up to 16 weeks of paid leave. Employees must notify their manager at least 30 days in advance.",
        "Performance reviews are conducted annually in Q4. Managers must complete evaluations for all direct reports by December 15th.",
        "The company's 401k plan includes employer matching up to 6% of salary. Employees are eligible after 90 days of employment.",
    ]
    return [ChunkMetadata(chunk_id=str(uuid.uuid4()), document_id="doc-1", text=t, page=i+1, section_heading=f"Section {i+1}", chunk_index=i, access_roles=["employee","manager","hr_admin"], category="handbook", token_count=len(t.split()), source="Employee Handbook 2024") for i, t in enumerate(texts)]


@pytest.fixture
def sample_results(sample_chunks):
    return [SearchResult(c.chunk_id, c.text, 0.9-i*0.1, c.source, c.page) for i, c in enumerate(sample_chunks)]


@pytest.fixture
def test_user():
    return User(user_id="test-1", role="employee", department="Engineering")


@pytest.fixture
def admin_user():
    return User(user_id="admin-1", role="hr_admin", department="HR")


@pytest.fixture
def test_jwt(settings):
    from backend.app.core.security import create_access_token
    return create_access_token("test-1", "employee", "Engineering")


@pytest.fixture
def admin_jwt(settings):
    from backend.app.core.security import create_access_token
    return create_access_token("admin-1", "hr_admin", "HR")
