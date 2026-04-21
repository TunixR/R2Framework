from __future__ import annotations

import settings

from sqlalchemy import Engine
from sqlmodel import Session, select

from database.auth.models import User, UserRole
from security.utils import hash_password, verify_password


def populate_users(engine: Engine) -> None:
    """Populate default users from environment configuration."""
    admin_username = settings.ADMIN_USERNAME.strip()
    admin_password = settings.ADMIN_PASSWORD.strip()

    if not admin_username or not admin_password:
        print("[populate_users] Admin credentials not set. Skipping user population.")
        return

    with Session(engine) as session:
        admin_user = session.exec(
            select(User).where(User.username == admin_username)
        ).first()

        if not admin_user:
            session.add(
                User(
                    username=admin_username,
                    password=hash_password(admin_password),
                    role=UserRole.ADMINISTRATOR,
                    enabled=True,
                )
            )
            session.commit()
            print(f"[populate_users] Created admin user '{admin_username}'.")
            return

        updated = False
        if admin_user.role != UserRole.ADMINISTRATOR:
            admin_user.role = UserRole.ADMINISTRATOR
            updated = True

        if not admin_user.enabled:
            admin_user.enabled = True
            updated = True

        if not verify_password(admin_password, admin_user.password):
            admin_user.password = hash_password(admin_password)
            updated = True

        if updated:
            session.add(admin_user)
            session.commit()
            print(f"[populate_users] Updated admin user '{admin_username}'.")
        else:
            print(f"[populate_users] Admin user '{admin_username}' already up to date.")
