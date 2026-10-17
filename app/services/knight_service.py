"""Knight purchase, selection, health and defensive combat."""

from dataclasses import dataclass
from math import ceil

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import ResourceType
from app.models.archer import UserArcher
from app.models.knight import Knight, UserKnight
from app.models.resource import Resource
from app.models.user import User
from app.services.archer_service import ArcherError
from app.services.resource_service import ResourceService


@dataclass(frozen=True)
class KnightHit:
    name: str
    emoji: str | None
    sticker: str | None
    arrow_name: str
    damage: int
    reduction: int
    died: bool


class KnightService:
    @staticmethod
    def power(owned: UserKnight) -> int:
        return owned.knight.power + (owned.level - 1) * max(
            1, ceil(owned.knight.power * 0.08)
        )

    @staticmethod
    def max_hp(owned: UserKnight) -> int:
        return owned.knight.max_hp + (owned.level - 1) * max(
            1, ceil(owned.knight.max_hp * 0.08)
        )

    @staticmethod
    def upgrade_cost(owned: UserKnight) -> int:
        return ceil(owned.knight.upgrade_price * (1 + 0.2 * (owned.level - 1)))

    async def catalog(self, session: AsyncSession) -> list[Knight]:
        return list(
            await session.scalars(
                select(Knight)
                .where(Knight.is_active.is_(True))
                .order_by(Knight.unlock_level, Knight.id)
            )
        )

    async def owned(
        self, session: AsyncSession, user_id: int, *, lock: bool = False
    ) -> UserKnight | None:
        query = (
            select(UserKnight)
            .where(UserKnight.user_id == user_id)
            .options(selectinload(UserKnight.knight))
        )
        if lock:
            query = query.with_for_update(of=UserKnight)
        return await session.scalar(query)

    async def active(
        self, session: AsyncSession, user_id: int, *, lock: bool = False
    ) -> UserKnight | None:
        owned = await self.owned(session, user_id, lock=lock)
        return owned if owned and owned.is_equipped and owned.current_hp > 0 else None

    async def _buyer(
        self, session: AsyncSession, user_id: int
    ) -> tuple[User, Resource]:
        user = await session.scalar(
            select(User).where(User.id == user_id).with_for_update()
        )
        resources = await session.scalar(
            select(Resource).where(Resource.user_id == user_id).with_for_update()
        )
        if user is None or resources is None:
            raise ArcherError("کاربر یا منابع پیدا نشد.")
        return user, resources

    async def buy(
        self, session: AsyncSession, user_id: int, knight_id: int
    ) -> UserKnight:
        user, resources = await self._buyer(session, user_id)
        knight = await session.get(Knight, knight_id)
        if knight is None or not knight.is_active or user.level < knight.unlock_level:
            raise ArcherError("این شوالیه برای شما قابل خرید نیست.")
        if await self.owned(session, user_id):
            raise ArcherError(
                "فقط یک شوالیه می‌توانید داشته باشید. برای تعویض، شوالیهٔ فعلی را بفروشید."
            )
        if knight.purchase_resource not in (ResourceType.COIN, ResourceType.DIAMOND):
            raise ArcherError("ارز خرید نامعتبر است.")
        archer = await session.scalar(
            select(UserArcher).where(UserArcher.user_id == user_id).with_for_update()
        )
        owned = UserKnight(
            user_id=user_id,
            knight_id=knight_id,
            current_hp=knight.max_hp,
            is_equipped=archer is None or not archer.is_equipped,
        )
        session.add(owned)
        await session.flush()
        await ResourceService.debit(
            session,
            resources,
            user_id=user_id,
            resource_type=knight.purchase_resource,
            amount=knight.purchase_price,
            reason="KNIGHT_PURCHASE",
            reference_type="USER_KNIGHT",
            reference_id=owned.id,
        )
        owned.knight = knight
        return owned

    async def equip(self, session: AsyncSession, user_id: int, kind: str) -> None:
        await self._buyer(session, user_id)
        archer = await session.scalar(
            select(UserArcher).where(UserArcher.user_id == user_id).with_for_update()
        )
        knight = await self.owned(session, user_id, lock=True)
        if kind == "knight":
            if knight is None or knight.current_hp <= 0:
                raise ArcherError("شوالیهٔ زنده‌ای برای فعال‌سازی ندارید.")
            knight.is_equipped = True
            if archer:
                archer.is_equipped = False
        elif kind == "archer":
            if archer is None:
                raise ArcherError("کمانداری برای فعال‌سازی ندارید.")
            archer.is_equipped = True
            if knight:
                knight.is_equipped = False
        else:
            raise ArcherError("نگهبان نامعتبر است.")
        await session.flush()

    async def upgrade(
        self, session: AsyncSession, user_id: int, owned_id: int
    ) -> UserKnight:
        user, resources = await self._buyer(session, user_id)
        owned = await self.owned(session, user_id, lock=True)
        if owned is None or owned.id != owned_id:
            raise ArcherError("شوالیه پیدا نشد.")
        if owned.level >= min(50, user.level):
            raise ArcherError("سطح شوالیه از سطح فرمانده بالاتر نمی‌رود (سقف ۵۰).")
        cost = self.upgrade_cost(owned)
        await ResourceService.debit_diamond(
            session,
            resources,
            user_id=user_id,
            amount=cost,
            reason="KNIGHT_UPGRADE",
            reference_type="USER_KNIGHT",
            reference_id=owned.id,
        )
        owned.level += 1
        await session.flush()
        return owned

    async def sell(
        self, session: AsyncSession, user_id: int, owned_id: int
    ) -> tuple[str, int, ResourceType]:
        _, resources = await self._buyer(session, user_id)
        owned = await self.owned(session, user_id, lock=True)
        if owned is None or owned.id != owned_id:
            raise ArcherError("شوالیه پیدا نشد.")
        knight = owned.knight
        refund = knight.purchase_price // 2
        if knight.purchase_resource is ResourceType.DIAMOND:
            await ResourceService.credit_diamond(
                session,
                resources,
                user_id=user_id,
                amount=refund,
                reason="KNIGHT_SALE",
                reference_type="USER_KNIGHT",
                reference_id=owned.id,
            )
        else:
            await ResourceService.credit_coin(
                session,
                resources,
                user_id=user_id,
                amount=refund,
                reason="KNIGHT_SALE",
                reference_type="USER_KNIGHT",
                reference_id=owned.id,
            )
        await session.delete(owned)
        archer = await session.scalar(
            select(UserArcher).where(UserArcher.user_id == user_id).with_for_update()
        )
        if archer:
            archer.is_equipped = True
        await session.flush()
        return knight.name, refund, knight.purchase_resource

    async def reduction(self, session: AsyncSession, defender_id: int) -> int:
        knight = await self.active(session, defender_id)
        return min(40, self.power(knight) * 2) if knight else 0

    async def strike(
        self,
        session: AsyncSession,
        defender_id: int,
        teacher_hp: int,
        teacher_max_hp: int,
        incoming_power: int = 0,
    ) -> KnightHit | None:
        knight = await self.active(session, defender_id, lock=True)
        if knight is None or teacher_hp <= 0:
            return None
        damage = min(teacher_hp, self.power(knight), max(1, ceil(teacher_max_hp * 0.3)))
        reduction = min(40, self.power(knight) * 2)
        knight.current_hp = max(
            0, knight.current_hp - max(1, ceil(incoming_power * 0.25))
        )
        hit = KnightHit(
            knight.knight.name,
            knight.knight.emoji,
            knight.knight.sticker,
            "شمشیر",
            damage,
            reduction,
            knight.current_hp == 0,
        )
        if hit.died:
            await session.delete(knight)
            await session.flush()
        return hit
