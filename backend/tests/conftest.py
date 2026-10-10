from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models import User


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override
    try:
        yield session_factory
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


@pytest.fixture
def client(db):
    with TestClient(app) as test_client:
        yield test_client


def register(client, email="user@example.com", password="StrongPass123", name="Участник"):
    response = client.post("/api/auth/register", json={"email": email, "password": password, "display_name": name})
    assert response.status_code == 201, response.text
    return response.json()


def promote(db, email, role):
    with db() as session:
        user = session.scalar(select(User).where(User.email == email))
        user.role = role
        session.commit()


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def challenge_data():
    now = datetime.now(timezone.utc)
    return {
        "title": "Неделя бега",
        "description": "Пробегите за неделю не меньше тридцати километров.",
        "sport": "Бег",
        "unit": "км",
        "target_value": 30,
        "starts_at": (now - timedelta(days=1)).isoformat(),
        "ends_at": (now + timedelta(days=7)).isoformat(),
    }
