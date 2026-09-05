from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import ResourceType
from app.models.resource import Resource
from app.models.teacher import Teacher
from app.models.transaction import Transaction
from app.models.user import User
from app.models.user_teacher import UserTeacher


class AdminService:
    """Small, explicit write API used by the private admin bot."""

    async def find_users(self, session: AsyncSession, query: str) -> list[User]:
        statement = (
            select(User)
            .options(selectinload(User.resources))
            .order_by(User.id.desc())
            .limit(20)
        )
        query = query.strip()
        if query.isdigit():
            number = int(query)
            statement = statement.where(
                or_(User.id == number, User.telegram_user_id == number)
            )
        else:
            statement = statement.where(
                or_(
                    User.username.ilike(f"%{query.lstrip('@')}%"),
                    User.first_name.ilike(f"%{query}%"),
                    User.last_name.ilike(f"%{query}%"),
                )
            )
        result = await session.execute(statement)
        return list(result.scalars().unique().all())

    async def list_broadcast_recipients(self, session: AsyncSession) -> list[int]:
        """Return every registered Telegram account, including inactive users."""
        result = await session.execute(
            select(User.telegram_user_id).order_by(User.id)
        )
        return [int(user_id) for user_id in result.scalars().all()]

    async def get_user(self, session: AsyncSession, user_id: int) -> User | None:
        result = await session.execute(
            select(User).where(User.id == user_id).options(selectinload(User.resources))
        )
        return result.scalar_one_or_none()

    async def list_user_teachers(
        self, session: AsyncSession, user_id: int
    ) -> list[UserTeacher]:
        result = await session.execute(
            select(UserTeacher)
            .where(UserTeacher.user_id == user_id)
            .options(selectinload(UserTeacher.teacher))
            .order_by(UserTeacher.id)
        )
        return list(result.scalars().unique().all())

    async def delete_user_teacher(
        self, session: AsyncSession, user_teacher_id: int, user_id: int
    ) -> UserTeacher | None:
        result = await session.execute(
            select(UserTeacher)
            .where(
                UserTeacher.id == user_teacher_id,
                UserTeacher.user_id == user_id,
            )
            .options(selectinload(UserTeacher.teacher))
            .with_for_update()
        )
        user_teacher = result.scalars().unique().one_or_none()
        if user_teacher is None:
            return None
        await session.delete(user_teacher)
        await session.flush()
        return user_teacher

    async def set_user_active(self, session: AsyncSession, user_id: int, active: bool) -> User | None:
        user = await self.get_user(session, user_id)
        if user is None:
            return None
        user.is_active = active
        await session.flush()
        return user

    async def add_resources(
        self, session: AsyncSession, user_id: int, *, coin: int, diamond: int, banana: int
    ) -> User | None:
        """Grant resources and record each grant as an auditable transaction."""
        if banana != 0:
            raise ValueError("XP فقط از طریق حمله دریافت می‌شود")
        if min(coin, diamond, banana) < 0:
            raise ValueError("resource values cannot be negative")
        result = await session.execute(
            select(User)
            .where(User.id == user_id)
            .options(selectinload(User.resources))
            .with_for_update()
        )
        user = result.scalar_one_or_none()
        if user is None:
            return None
        if user.resources is None:
            user.resources = Resource(coin=0, diamond=0, banana=0)
            await session.flush()
        resources = user.resources
        for field, resource_type, amount in (
            ("coin", ResourceType.COIN, coin),
            ("diamond", ResourceType.DIAMOND, diamond),
            ("banana", ResourceType.BANANA, banana),
        ):
            if amount == 0:
                continue
            before = getattr(resources, field)
            setattr(resources, field, before + amount)
            session.add(Transaction(
                user_id=user.id,
                resource_type=resource_type,
                amount=amount,
                balance_before=before,
                balance_after=before + amount,
                reason="ADMIN_GRANT",
            ))
        await session.flush()
        return user

    async def list_teachers(self, session: AsyncSession) -> list[Teacher]:
        result = await session.execute(select(Teacher).order_by(Teacher.id))
        return list(result.scalars().all())

    async def get_teacher(self, session: AsyncSession, teacher_id: int) -> Teacher | None:
        result = await session.execute(
            select(Teacher).where(Teacher.id == teacher_id).options(selectinload(Teacher.owned_by_users))
        )
        return result.scalar_one_or_none()

    async def create_teacher(self, session: AsyncSession, **values: object) -> Teacher:
        name = str(values.get("name", "")).strip()
        if not name:
            raise ValueError("teacher name cannot be empty")
        for field in ("damage", "max_hp", "purchase_price", "upgrade_price"):
            if int(values.get(field, -1)) < 0:
                raise ValueError(f"{field} cannot be negative")
        if int(values.get("unlock_level", 0)) < 1:
            raise ValueError("unlock_level must be positive")
        values["name"] = name
        teacher = Teacher(**values)
        session.add(teacher)
        await session.flush()
        return teacher

    async def update_teacher(self, session: AsyncSession, teacher_id: int, **values: object) -> Teacher | None:
        teacher = await self.get_teacher(session, teacher_id)
        if teacher is None:
            return None
        if "name" in values and not str(values["name"]).strip():
            raise ValueError("teacher name cannot be empty")
        for field in ("damage", "max_hp", "purchase_price", "upgrade_price"):
            if field in values and int(values[field]) < 0:
                raise ValueError(f"{field} cannot be negative")
        if "unlock_level" in values and int(values["unlock_level"]) < 1:
            raise ValueError("unlock_level must be positive")
        for key, value in values.items():
            if key == "name":
                value = str(value).strip()
            setattr(teacher, key, value)
        await session.flush()
        return teacher

    async def delete_teacher(self, session: AsyncSession, teacher_id: int) -> tuple[bool, Teacher | None]:
        teacher = await self.get_teacher(session, teacher_id)
        if teacher is None:
            return False, None
        # Existing ownership has RESTRICT FKs. Deactivate instead of risking a
        # failed transaction and preserve historical battle data.
        if teacher.owned_by_users:
            teacher.is_active = False
            await session.flush()
            return False, teacher
        await session.delete(teacher)
        await session.flush()
        return True, teacher
