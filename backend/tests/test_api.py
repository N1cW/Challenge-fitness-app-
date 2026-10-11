from .conftest import auth, challenge_data, promote, register


def test_registration_login_and_validation(client):
    created = register(client)
    assert created["user"]["role"] == "user"
    assert "password_hash" not in created["user"]
    assert client.get("/api/me", headers=auth(created["access_token"])).status_code == 200
    assert client.post("/api/auth/register", json={"email":"user@example.com","display_name":"Other","password":"StrongPass123"}).status_code == 409
    assert client.post("/api/auth/register", json={"email":"bad","display_name":"x","password":"short"}).status_code == 422
    assert client.post("/api/auth/login", json={"email":"user@example.com","password":"wrong"}).status_code == 401
    assert client.get("/api/me").status_code == 401
    assert client.get("/api/me", headers=auth("bad.token")).status_code == 401


def test_role_crud_participation_and_progress(client, db):
    participant = register(client)
    organizer = register(client, "organizer@example.com", name="Организатор")
    other = register(client, "other@example.com", name="Другой")
    admin = register(client, "admin@example.com", name="Администратор")
    promote(db, "organizer@example.com", "organizer")
    promote(db, "other@example.com", "organizer")
    promote(db, "admin@example.com", "admin")
    data = challenge_data()
    assert client.post("/api/challenges", json=data, headers=auth(participant["access_token"])).status_code == 403
    result = client.post("/api/challenges", json=data, headers=auth(organizer["access_token"]))
    assert result.status_code == 201, result.text
    challenge_id = result.json()["id"]
    url = f"/api/challenges/{challenge_id}"
    assert client.get(url).json()["title"] == data["title"]
    assert len(client.get("/api/challenges?sport=Бег").json()) == 1
    assert client.patch(url, json={"title":"Новая цель"}, headers=auth(other["access_token"])).status_code == 403
    assert client.patch(url, json={"title":"Цель администратора"}, headers=auth(admin["access_token"])).status_code == 200
    assert client.post(f"{url}/progress", json={"value":5}, headers=auth(participant["access_token"])).status_code == 403
    assert client.post(f"{url}/join", headers=auth(participant["access_token"])).status_code == 201
    assert client.post(f"{url}/join", headers=auth(participant["access_token"])).status_code == 409
    assert client.post(f"{url}/progress", json={"value":0}, headers=auth(participant["access_token"])).status_code == 422
    assert client.post(f"{url}/progress", json={"value":12,"note":"Тренировка"}, headers=auth(participant["access_token"])).status_code == 201
    assert client.get(f"{url}/leaderboard").json()[0]["total"] == 12
    assert len(client.get(f"{url}/progress", headers=auth(participant["access_token"])).json()) == 1
    assert client.patch(url, json={"ends_at":data["starts_at"]}, headers=auth(organizer["access_token"])).status_code == 422
    assert client.patch(url, json={"status":"closed"}, headers=auth(organizer["access_token"])).status_code == 200
    assert client.post(f"{url}/join", headers=auth(other["access_token"])).status_code == 409
    assert client.post(f"{url}/progress", json={"value":2}, headers=auth(participant["access_token"])).status_code == 409
    assert client.delete(url, headers=auth(organizer["access_token"])).status_code == 204
    assert client.get(url).status_code == 404


def test_websocket_broadcast(client, db):
    participant = register(client)
    organizer = register(client, "organizer@example.com", name="Организатор")
    promote(db, "organizer@example.com", "organizer")
    created = client.post("/api/challenges", json=challenge_data(), headers=auth(organizer["access_token"]))
    challenge_id = created.json()["id"]
    with client.websocket_connect(f"/ws/challenges/{challenge_id}") as websocket:
        websocket.send_json({"token": participant["access_token"]})
        assert websocket.receive_json()["event"] == "ready"
        joined = client.post(f"/api/challenges/{challenge_id}/join", headers=auth(participant["access_token"]))
        assert joined.status_code == 201
        assert websocket.receive_json()["event"] == "participant.joined"


def test_health(client):
    assert client.get("/api/health").json() == {"status":"ok"}


def test_render_database_url_uses_declared_psycopg_driver(monkeypatch):
    from app import database

    captured = {}

    def fake_create_engine(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(database, "create_engine", fake_create_engine)
    database.make_engine("postgresql://user:password@db.example/app")

    assert captured["url"] == "postgresql+psycopg://user:password@db.example/app"
    assert captured["kwargs"]["pool_pre_ping"] is True
