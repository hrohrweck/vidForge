#!/usr/bin/env python3
"""CLI utilities for VidForge administration."""

import asyncio
import sys
from getpass import getpass

from app.database import async_session, User
from sqlalchemy import select


async def create_superuser() -> None:
    """Create a superuser interactively."""
    print("Create VidForge Superuser")
    print("=" * 40)

    email = input("Email: ").strip()
    if not email:
        print("Error: Email is required")
        sys.exit(1)

    password = getpass("Password: ")
    if not password:
        print("Error: Password is required")
        sys.exit(1)

    password_confirm = getpass("Confirm password: ")
    if password != password_confirm:
        print("Error: Passwords do not match")
        sys.exit(1)

    async with async_session() as session:
        # Check if user exists
        result = await session.execute(select(User).where(User.email == email))
        if result.scalar_one_or_none():
            print(f"Error: User with email '{email}' already exists")
            sys.exit(1)

        # Create user
        from passlib.context import CryptContext

        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

        user = User(
            email=email,
            hashed_password=pwd_context.hash(password),
            is_superuser=True,
            is_active=True,
        )
        session.add(user)
        await session.commit()

        print(f"\nSuperuser '{email}' created successfully!")


async def reset_password(email: str) -> None:
    """Reset a user's password."""
    import os

    password = os.environ.get("NEW_PASSWORD") or getpass("New password: ")
    if not password:
        print("Error: Password is required (or set NEW_PASSWORD env var)")
        sys.exit(1)

    if not os.environ.get("NEW_PASSWORD"):
        password_confirm = getpass("Confirm password: ")
        if password != password_confirm:
            print("Error: Passwords do not match")
            sys.exit(1)

    async with async_session() as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if not user:
            print(f"Error: User '{email}' not found")
            sys.exit(1)

        from passlib.context import CryptContext

        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

        user.hashed_password = pwd_context.hash(password)
        await session.commit()

        print(f"Password reset for '{email}'")


async def list_users() -> None:
    """List all users."""
    async with async_session() as session:
        result = await session.execute(select(User).order_by(User.created_at))
        users = result.scalars().all()

        print("\nVidForge Users")
        print("=" * 80)
        print(f"{'Email':<40} {'Active':<10} {'Superuser':<10} {'Created'}")
        print("-" * 80)

        for user in users:
            print(
                f"{user.email:<40} "
                f"{'Yes' if user.is_active else 'No':<10} "
                f"{'Yes' if user.is_superuser else 'No':<10} "
                f"{user.created_at.strftime('%Y-%m-%d %H:%M')}"
            )


def main() -> None:
    """Main CLI entrypoint."""
    if len(sys.argv) < 2:
        print("Usage: python -m app.cli <command>")
        print("\nCommands:")
        print("  createsuperuser   Create a superuser interactively")
        print("  resetpassword     Reset a user's password")
        print("  listusers         List all users")
        sys.exit(1)

    command = sys.argv[1]

    if command == "createsuperuser":
        asyncio.run(create_superuser())
    elif command == "resetpassword":
        if len(sys.argv) < 3:
            print("Usage: python -m app.cli resetpassword <email>")
            sys.exit(1)
        asyncio.run(reset_password(sys.argv[2]))
    elif command == "listusers":
        asyncio.run(list_users())
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
