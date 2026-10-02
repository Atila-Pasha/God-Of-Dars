from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import AttackStatus
from app.models.attack import Attack
from app.models.resource import Resource
from app.models.teacher import Teacher
from app.models.user import User
from app.models.user_teacher import UserTeacher


class TeacherRepository:
    async def has_active_attack(
        self, session: AsyncSession, user_id: int, user_teacher_id: int
    ) -> bool:
        # The caller holds the user lock shared with attack launch/resolution.
        # Do not lock the attack row here: resolvers lock it before the user.
        result = await session.scalar(
            select(Attack.id)
            .where(
                Attack.attacker_id == user_id,
                Attack.teacher_id == user_teacher_id,
                Attack.status.in_((AttackStatus.PENDING, AttackStatus.PROCESSING))
                | (
                    (Attack.status == AttackStatus.FAILED)
                    & Attack.next_retry_at.is_not(None)
                ),
            )
            .limit(1)
        )
        return result is not None

    async def get_user(self, session: AsyncSession, user_id: int) -> User | None:
        result = await session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_user_for_update(
        self, session: AsyncSession, user_id: int
    ) -> User | None:
        result = await session.execute(
            select(User).where(User.id == user_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_resources_for_update(
        self, session: AsyncSession, user_id: int
    ) -> Resource | None:
        result = await session.execute(
            select(Resource)
            .where(Resource.user_id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def count_owned(self, session: AsyncSession, user_id: int) -> int:
        result = await session.execute(
            select(func.count(UserTeacher.id)).where(UserTeacher.user_id == user_id)
        )
        return int(result.scalar_one())

    async def get_catalog_teacher(
        self, session: AsyncSession, teacher_id: int
    ) -> Teacher | None:
        result = await session.execute(select(Teacher).where(Teacher.id == teacher_id))
        return result.scalar_one_or_none()

    async def list_catalog(
        self, session: AsyncSession, user_id: int | None = None
    ) -> list[Teacher]:
        statement = (
            select(Teacher).where(Teacher.is_active.is_(True)).order_by(Teacher.id)
        )
        if user_id is not None:
            owned_teacher_ids = select(UserTeacher.teacher_id).where(
                UserTeacher.user_id == user_id
            )
            statement = statement.where(~Teacher.id.in_(owned_teacher_ids))
        result = await session.execute(statement)
        return list(result.scalars().all())

    async def list_public(self, session: AsyncSession) -> list[Teacher]:
        result = await session.execute(
            select(Teacher).where(Teacher.is_active.is_(True)).order_by(Teacher.id)
        )
        return list(result.scalars().all())

    async def list_owned(
        self, session: AsyncSession, user_id: int
    ) -> list[UserTeacher]:
        result = await session.execute(
            select(UserTeacher)
            .where(UserTeacher.user_id == user_id)
            .options(
                selectinload(UserTeacher.teacher),
                selectinload(UserTeacher.recoveries),
            )
            .order_by(UserTeacher.id)
        )
        return list(result.scalars().unique().all())

    async def get_owned_for_update(
        self,
        session: AsyncSession,
        user_id: int,
        user_teacher_id: int,
    ) -> UserTeacher | None:
        result = await session.execute(
            select(UserTeacher)
            .where(
                UserTeacher.id == user_teacher_id,
                UserTeacher.user_id == user_id,
            )
            .options(
                selectinload(UserTeacher.teacher),
                selectinload(UserTeacher.recoveries),
            )
            .with_for_update()
        )
        return result.scalars().unique().one_or_none()

    async def get_owned(
        self,
        session: AsyncSession,
        user_id: int,
        user_teacher_id: int,
    ) -> UserTeacher | None:
        result = await session.execute(
            select(UserTeacher)
            .where(
                UserTeacher.id == user_teacher_id,
                UserTeacher.user_id == user_id,
            )
            .options(
                selectinload(UserTeacher.teacher),
                selectinload(UserTeacher.recoveries),
            )
        )
        return result.scalars().unique().one_or_none()

    async def get_owned_by_teacher_for_update(
        self,
        session: AsyncSession,
        user_id: int,
        teacher_id: int,
    ) -> UserTeacher | None:
        result = await session.execute(
            select(UserTeacher)
            .where(
                UserTeacher.user_id == user_id,
                UserTeacher.teacher_id == teacher_id,
            )
            .options(selectinload(UserTeacher.teacher))
            .with_for_update()
        )
        return result.scalars().unique().one_or_none()

    async def get_owned_by_name_for_update(
        self, session: AsyncSession, user_id: int, name: str
    ) -> UserTeacher | None:
        result = await session.execute(
            select(UserTeacher)
            .join(UserTeacher.teacher)
            .where(
                UserTeacher.user_id == user_id,
                func.lower(Teacher.name) == name.strip().casefold(),
            )
            .options(
                selectinload(UserTeacher.teacher),
                selectinload(UserTeacher.recoveries),
            )
            .with_for_update()
        )
        return result.scalars().unique().one_or_none()
