import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from .conftest import auth, challenge_data, promote, register


@pytest.fixture
def challenge_context(client, db):
    participant = register(client)
    organizer = register(client, "organizer@example.com", name="Организатор")
    promote(db, "organizer@example.com", "organizer")
    created = client.post("/api/challenges", json=challenge_data(), headers=auth(organizer["access_token"]))
    challenge_id = created.json()["id"]
    client.post(f"/api/challenges/{challenge_id}/join", headers=auth(participant["access_token"]))
    return participant, challenge_id


@pytest.fixture
def organizer_context(client, db):
    organizer = register(client, "organizer@example.com", name="Организатор")
    promote(db, "organizer@example.com", "organizer")
    return organizer


@settings(max_examples=35, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(value=st.integers(max_value=0))
def test_fuzz_progress_rejects_nonpositive_values(client, challenge_context, value):
    participant, challenge_id = challenge_context
    result = client.post(f"/api/challenges/{challenge_id}/progress", json={"value":value}, headers=auth(participant["access_token"]))
    assert result.status_code == 422
    assert client.get(f"/api/challenges/{challenge_id}/leaderboard").json()[0]["total"] == 0


@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(title=st.text(max_size=2), target=st.integers(max_value=0))
def test_fuzz_challenge_schema_rejects_invalid_fields(client, organizer_context, title, target):
    data = challenge_data()
    data["title"] = title
    data["target_value"] = target
    result = client.post("/api/challenges", json=data, headers=auth(organizer_context["access_token"]))
    assert result.status_code == 422
    assert client.get("/api/challenges").json() == []
