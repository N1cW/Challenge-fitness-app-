from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import engine, get_db, initialize_database
from .models import Challenge, Participation, ProgressEntry, User
from .schemas import (
    ChallengeIn, ChallengeOut, ChallengePatch, LeaderboardRow, LoginIn,
    ProgressIn, ProgressOut, RegisterIn, TokenOut, UserOut,
)
from .security import create_token, current_user, decode_token, hash_password, require_organizer, verify_password


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database(engine)
    yield


app = FastAPI(title="Challenge Fitness API", version="1.0.0", lifespan=lifespan)


class EventHub:
    def __init__(self):
        self.clients: dict[int, set[WebSocket]] = {}

    async def connect(self, challenge_id: int, socket: WebSocket):
        self.clients.setdefault(challenge_id, set()).add(socket)

    def disconnect(self, challenge_id: int, socket: WebSocket):
        sockets = self.clients.get(challenge_id)
        if sockets:
            sockets.discard(socket)
            if not sockets:
                self.clients.pop(challenge_id, None)

    async def publish(self, challenge_id: int, event: str):
        for socket in list(self.clients.get(challenge_id, ())):
            try:
                await socket.send_json({"event": event, "challenge_id": challenge_id})
            except Exception:
                self.disconnect(challenge_id, socket)


hub = EventHub()


def get_challenge(db: Session, challenge_id: int) -> Challenge:
    challenge = db.get(Challenge, challenge_id)
    if not challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")
    return challenge


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def challenge_out(challenge: Challenge) -> ChallengeOut:
    return ChallengeOut.model_validate(challenge).model_copy(update={"participant_count": len(challenge.participations)})


def ensure_owner_or_admin(challenge: Challenge, user: User):
    if user.role != "admin" and challenge.created_by != user.id:
        raise HTTPException(status_code=403, detail="Only creator or admin can change this challenge")


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.post("/api/auth/register", response_model=TokenOut, status_code=201)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    email = str(data.email).lower()
    user = User(email=email, display_name=data.display_name.strip(), password_hash=hash_password(data.password), role="user")
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Email already registered")
    db.refresh(user)
    return TokenOut(access_token=create_token(user), user=UserOut.model_validate(user))


@app.post("/api/auth/login", response_model=TokenOut)
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == str(data.email).lower()))
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return TokenOut(access_token=create_token(user), user=UserOut.model_validate(user))


@app.get("/api/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


@app.get("/api/challenges", response_model=list[ChallengeOut])
def list_challenges(sport: str | None = None, status: str | None = None, db: Session = Depends(get_db)):
    query = select(Challenge).order_by(Challenge.created_at.desc(), Challenge.id.desc())
    if sport:
        query = query.where(Challenge.sport == sport)
    if status:
        if status not in {"open", "closed"}:
            raise HTTPException(status_code=422, detail="Invalid status filter")
        query = query.where(Challenge.status == status)
    return [challenge_out(item) for item in db.scalars(query).all()]


@app.post("/api/challenges", response_model=ChallengeOut, status_code=201)
async def create_challenge(data: ChallengeIn, user: User = Depends(require_organizer), db: Session = Depends(get_db)):
    challenge = Challenge(**data.model_dump(), created_by=user.id)
    db.add(challenge)
    db.commit()
    db.refresh(challenge)
    return challenge_out(challenge)


@app.get("/api/challenges/{challenge_id}", response_model=ChallengeOut)
def read_challenge(challenge_id: int, db: Session = Depends(get_db)):
    return challenge_out(get_challenge(db, challenge_id))


@app.patch("/api/challenges/{challenge_id}", response_model=ChallengeOut)
async def update_challenge(challenge_id: int, data: ChallengePatch, user: User = Depends(require_organizer), db: Session = Depends(get_db)):
    challenge = get_challenge(db, challenge_id)
    ensure_owner_or_admin(challenge, user)
    for key, value in data.model_dump(exclude_unset=True).items():
        if value is None:
            raise HTTPException(status_code=422, detail=f"{key} cannot be null")
        setattr(challenge, key, value)
    if as_utc(challenge.ends_at) <= as_utc(challenge.starts_at):
        raise HTTPException(status_code=422, detail="ends_at must be after starts_at")
    db.commit()
    await hub.publish(challenge_id, "challenge.updated")
    return challenge_out(challenge)


@app.delete("/api/challenges/{challenge_id}", status_code=204)
async def delete_challenge(challenge_id: int, user: User = Depends(require_organizer), db: Session = Depends(get_db)):
    challenge = get_challenge(db, challenge_id)
    ensure_owner_or_admin(challenge, user)
    db.delete(challenge)
    db.commit()
    await hub.publish(challenge_id, "challenge.deleted")


@app.post("/api/challenges/{challenge_id}/join", status_code=201)
async def join(challenge_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    challenge = get_challenge(db, challenge_id)
    if challenge.status != "open" or as_utc(challenge.ends_at) < datetime.now(timezone.utc):
        raise HTTPException(status_code=409, detail="Challenge is closed")
    existing = db.scalar(select(Participation).where(Participation.user_id == user.id, Participation.challenge_id == challenge_id))
    if existing:
        raise HTTPException(status_code=409, detail="Already participating")
    db.add(Participation(user_id=user.id, challenge_id=challenge_id))
    db.commit()
    await hub.publish(challenge_id, "participant.joined")
    return {"status": "joined"}


@app.delete("/api/challenges/{challenge_id}/join", status_code=204)
async def leave(challenge_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    participation = db.scalar(select(Participation).where(Participation.user_id == user.id, Participation.challenge_id == challenge_id))
    if not participation:
        raise HTTPException(status_code=404, detail="Participation not found")
    db.delete(participation)
    db.commit()
    await hub.publish(challenge_id, "participant.left")


@app.post("/api/challenges/{challenge_id}/progress", response_model=ProgressOut, status_code=201)
async def add_progress(challenge_id: int, data: ProgressIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    challenge = get_challenge(db, challenge_id)
    if challenge.status != "open" or not (as_utc(challenge.starts_at) <= datetime.now(timezone.utc) <= as_utc(challenge.ends_at)):
        raise HTTPException(status_code=409, detail="Challenge is not active")
    participation = db.scalar(select(Participation).where(Participation.user_id == user.id, Participation.challenge_id == challenge_id))
    if not participation:
        raise HTTPException(status_code=403, detail="Join the challenge first")
    entry = ProgressEntry(participation_id=participation.id, value=data.value, note=data.note.strip())
    db.add(entry)
    db.commit()
    db.refresh(entry)
    await hub.publish(challenge_id, "progress.added")
    return entry


@app.get("/api/challenges/{challenge_id}/progress", response_model=list[ProgressOut])
def my_progress(challenge_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    get_challenge(db, challenge_id)
    participation = db.scalar(select(Participation).where(Participation.user_id == user.id, Participation.challenge_id == challenge_id))
    if not participation:
        return []
    return sorted(participation.entries, key=lambda item: item.recorded_at, reverse=True)


@app.get("/api/challenges/{challenge_id}/leaderboard", response_model=list[LeaderboardRow])
def leaderboard(challenge_id: int, db: Session = Depends(get_db)):
    challenge = get_challenge(db, challenge_id)
    rows = [LeaderboardRow(user_id=p.user_id, display_name=p.user.display_name,
                           total=sum(e.value for e in p.entries), target_value=challenge.target_value,
                           completed=sum(e.value for e in p.entries) >= challenge.target_value)
            for p in challenge.participations]
    return sorted(rows, key=lambda row: (-row.total, row.display_name.lower()))


@app.websocket("/ws/challenges/{challenge_id}")
async def challenge_events(socket: WebSocket, challenge_id: int, db: Session = Depends(get_db)):
    await socket.accept()
    try:
        first = await socket.receive_json()
        token = first.get("token") if isinstance(first, dict) else None
        user = db.get(User, decode_token(token)) if isinstance(token, str) else None
        if not user or not db.get(Challenge, challenge_id):
            await socket.close(code=1008)
            return
        await hub.connect(challenge_id, socket)
        await socket.send_json({"event": "ready", "challenge_id": challenge_id})
        while True:
            await socket.receive_text()
    except (WebSocketDisconnect, HTTPException, ValueError):
        pass
    finally:
        hub.disconnect(challenge_id, socket)


frontend = Path(__file__).resolve().parents[2] / "frontend"
if frontend.exists():
    app.mount("/assets", StaticFiles(directory=frontend), name="assets")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(frontend / "index.html")
