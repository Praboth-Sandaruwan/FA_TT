"""Seed script for populating development data."""

from __future__ import annotations

import asyncio

from ..models import TaskStatus
from ..services import TaskService, UserService
from .session import async_session_maker


async def seed() -> None:
    """Populate the database with a small set of development fixtures."""
    async with async_session_maker() as session:
        user_service = UserService(session)
        task_service = TaskService(session)

        email = "demo@example.com"
        user = await user_service.get_user_by_email(email)
        if user is None:
            user = await user_service.create_user(
                email=email,
                password="demo-password",
                full_name="Demo User",
            )

        if user.id is None:  # pragma: no cover - defensive guard
            raise ValueError("Seed user was not persisted correctly")

        existing_tasks = await task_service.list_tasks_for_owner(user.id)
        if existing_tasks:
            return

        await task_service.create_task(
            owner_id=user.id,
            title="Set up local environment",
            description="Install dependencies and run the application.",
        )
        await task_service.create_task(
            owner_id=user.id,
            title="Draft initial tasks",
            description="Outline work items to deliver the MVP.",
            status=TaskStatus.IN_PROGRESS,
        )
        await task_service.create_task(
            owner_id=user.id,
            title="Celebrate first release",
            description="Ship the first release and celebrate the milestone.",
            status=TaskStatus.PENDING,
        )


def main() -> None:
    """Entry-point hook for ``python -m`` execution."""
    asyncio.run(seed())


if __name__ == "__main__":  # pragma: no cover - manual execution entry-point
    main()
