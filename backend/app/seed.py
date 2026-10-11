"""Create repeatable demo users and example challenges.

Local usage: APP_ENV=development SEED_PASSWORD=<chosen-password> python -m app.seed
Hosted demo: set SEED_DEMO_DATA=true and provide SEED_PASSWORD as a secret.
"""
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from .database import Base, SessionLocal, engine
from .models import Challenge, User
from .security import hash_password


def main():
    app_env = os.getenv("APP_ENV", "development")
    seed_demo_data = os.getenv("SEED_DEMO_DATA", "false").lower() == "true"
    if app_env != "development" and not seed_demo_data:
        raise SystemExit("Set SEED_DEMO_DATA=true explicitly to seed a hosted demo")
    password = os.getenv("SEED_PASSWORD", "")
    if len(password) < 10:
        raise SystemExit("Set SEED_PASSWORD to at least 10 characters")
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        users = {}
        for role, name in (("admin", "Администратор"), ("organizer", "Организатор"), ("user", "Участник")):
            email = f"{role}@example.com"
            user = db.scalar(select(User).where(User.email == email))
            if not user:
                user = User(email=email, display_name=name, password_hash=hash_password(password), role=role)
                db.add(user)
                db.flush()
            users[role] = user
        if not db.scalar(select(Challenge).limit(1)):
            now = datetime.now(timezone.utc)
            db.add_all([
                Challenge(title="30 километров за неделю", description="Бегайте в удобном темпе и фиксируйте пройденные километры.", sport="Бег", unit="км", target_value=30, starts_at=now - timedelta(days=1), ends_at=now + timedelta(days=7), created_by=users["organizer"].id),
                Challenge(title="100 отжиманий", description="Выполните сто отжиманий за неделю, разбивая нагрузку на подходы.", sport="Силовые", unit="раз", target_value=100, starts_at=now - timedelta(days=1), ends_at=now + timedelta(days=7), created_by=users["organizer"].id),
            ])
        db.commit()
    print("Demo users and challenges are ready")


if __name__ == "__main__":
    main()
