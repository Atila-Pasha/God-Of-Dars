"""Archer shop and deterministic, bounded counterfire."""

from dataclasses import dataclass
from math import ceil

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import ResourceType
from app.models.archer import Archer, ArrowPack, UserArcher, UserArrow
from app.models.resource import Resource
from app.models.user import User
from app.services.resource_service import ResourceService


class ArcherError(ValueError):
    pass


@dataclass(frozen=True)
class ArcherHit:
    name: str
    emoji: str | None
    sticker: str | None
    arrow_name: str
    damage: int


class ArcherService:
    @staticmethod
    def power(owned: UserArcher) -> int:
        # Moderate linear growth. Arrow quality remains relevant at high levels.
        return owned.archer.power + (owned.level - 1) * max(
            1, ceil(owned.archer.power * 0.08)
        )

    @staticmethod
    def upgrade_cost(owned: UserArcher) -> int:
        return ceil(owned.archer.upgrade_price * (1 + 0.2 * (owned.level - 1)))

    async def catalog(self, session: AsyncSession) -> list[Archer]:
        return list(
            await session.scalars(
                select(Archer)
                .where(Archer.is_active.is_(True))
                .order_by(Archer.unlock_level, Archer.id)
            )
        )

    async def packs(self, session: AsyncSession) -> list[ArrowPack]:
        return list(
            await session.scalars(
                select(ArrowPack)
                .where(ArrowPack.is_active.is_(True))
                .order_by(ArrowPack.unlock_level, ArrowPack.id)
            )
        )

    async def owned(
        self, session: AsyncSession, user_id: int, *, lock: bool = False
    ) -> list[UserArcher]:
        statement = (
            select(UserArcher)
            .where(UserArcher.user_id == user_id)
            .options(selectinload(UserArcher.archer))
            .order_by(UserArcher.id)
        )
        if lock:
            statement = statement.with_for_update(of=UserArcher)
        return list((await session.scalars(statement)).all())

    async def ammunition(
        self, session: AsyncSession, user_id: int, *, lock: bool = False
    ) -> list[UserArrow]:
        statement = (
            select(UserArrow)
            .where(UserArrow.user_id == user_id, UserArrow.quantity > 0)
            .options(selectinload(UserArrow.pack))
            .order_by(UserArrow.id)
        )
        if lock:
            statement = statement.with_for_update(of=UserArrow)
        return list((await session.scalars(statement)).all())

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

    async def buy_archer(
        self, session: AsyncSession, user_id: int, archer_id: int
    ) -> UserArcher:
        user, resources = await self._buyer(session, user_id)
        archer = await session.get(Archer, archer_id)
        if archer is None or not archer.is_active or user.level < archer.unlock_level:
            raise ArcherError("این کماندار برای شما قابل خرید نیست.")
        if await session.scalar(
            select(UserArcher.id).where(
                UserArcher.user_id == user_id, UserArcher.archer_id == archer_id
            )
        ):
            raise ArcherError("این کماندار را قبلاً خریده‌اید.")
        if await self.owned(session, user_id):
            raise ArcherError(
                "فقط یک کماندار می‌توانید داشته باشید. برای تعویض، کماندار فعلی را بفروشید."
            )
        if archer.purchase_resource not in (ResourceType.COIN, ResourceType.DIAMOND):
            raise ArcherError("ارز خرید نامعتبر است.")
        owned = UserArcher(user_id=user_id, archer_id=archer_id)
        session.add(owned)
        await session.flush()
        await ResourceService.debit(
            session,
            resources,
            user_id=user_id,
            resource_type=archer.purchase_resource,
            amount=archer.purchase_price,
            reason="ARCHER_PURCHASE",
            reference_type="USER_ARCHER",
            reference_id=owned.id,
        )
        owned.archer = archer
        return owned

    async def upgrade(
        self, session: AsyncSession, user_id: int, owned_id: int
    ) -> UserArcher:
        user, resources = await self._buyer(session, user_id)
        owned = await session.scalar(
            select(UserArcher)
            .where(UserArcher.id == owned_id, UserArcher.user_id == user_id)
            .options(selectinload(UserArcher.archer))
            .with_for_update(of=UserArcher)
        )
        if owned is None:
            raise ArcherError("کماندار پیدا نشد.")
        if owned.level >= min(50, user.level):
            raise ArcherError("سطح کماندار از سطح فرمانده بالاتر نمی‌رود (سقف ۵۰).")
        cost = self.upgrade_cost(owned)
        await ResourceService.debit_diamond(
            session,
            resources,
            user_id=user_id,
            amount=cost,
            reason="ARCHER_UPGRADE",
            reference_type="USER_ARCHER",
            reference_id=owned.id,
        )
        owned.level += 1
        await session.flush()
        return owned

    async def sell(
        self, session: AsyncSession, user_id: int, owned_id: int
    ) -> tuple[str, int, ResourceType]:
        _, resources = await self._buyer(session, user_id)
        owned = await session.scalar(
            select(UserArcher)
            .where(UserArcher.id == owned_id, UserArcher.user_id == user_id)
            .options(selectinload(UserArcher.archer))
            .with_for_update(of=UserArcher)
        )
        if owned is None:
            raise ArcherError("کماندار پیدا نشد.")
        archer = owned.archer
        refund = archer.purchase_price // 2
        name = archer.name
        currency = archer.purchase_resource
        if currency is ResourceType.DIAMOND:
            await ResourceService.credit_diamond(
                session,
                resources,
                user_id=user_id,
                amount=refund,
                reason="ARCHER_SALE",
                reference_type="USER_ARCHER",
                reference_id=owned.id,
            )
        else:
            await ResourceService.credit_coin(
                session,
                resources,
                user_id=user_id,
                amount=refund,
                reason="ARCHER_SALE",
                reference_type="USER_ARCHER",
                reference_id=owned.id,
            )
        await session.delete(owned)
        await session.flush()
        return name, refund, currency

    async def buy_pack(
        self, session: AsyncSession, user_id: int, pack_id: int
    ) -> UserArrow:
        user, resources = await self._buyer(session, user_id)
        pack = await session.get(ArrowPack, pack_id)
        if pack is None or not pack.is_active or user.level < pack.unlock_level:
            raise ArcherError("این پک تیر برای شما قابل خرید نیست.")
        if pack.purchase_resource not in (ResourceType.COIN, ResourceType.DIAMOND):
            raise ArcherError("ارز خرید نامعتبر است.")
        owned = await session.scalar(
            select(UserArrow)
            .where(UserArrow.user_id == user_id, UserArrow.pack_id == pack_id)
            .with_for_update()
        )
        if owned is None:
            has_equipped = await session.scalar(
                select(UserArrow.id).where(
                    UserArrow.user_id == user_id, UserArrow.is_equipped.is_(True)
                )
            )
            owned = UserArrow(
                user_id=user_id,
                pack_id=pack_id,
                quantity=0,
                is_equipped=has_equipped is None,
            )
            session.add(owned)
            await session.flush()
        await ResourceService.debit(
            session,
            resources,
            user_id=user_id,
            resource_type=pack.purchase_resource,
            amount=pack.purchase_price,
            reason="ARROW_PACK_PURCHASE",
            reference_type="USER_ARROW",
            reference_id=owned.id,
        )
        owned.quantity += pack.quantity
        has_equipped = await session.scalar(
            select(UserArrow.id).where(
                UserArrow.user_id == user_id,
                UserArrow.is_equipped.is_(True),
                UserArrow.id != owned.id,
            )
        )
        if has_equipped is None:
            owned.is_equipped = True
        owned.pack = pack
        await session.flush()
        return owned

    async def equip_pack(
        self, session: AsyncSession, user_id: int, pack_id: int
    ) -> UserArrow:
        await self._buyer(session, user_id)
        rows = list(
            (
                await session.scalars(
                    select(UserArrow)
                    .where(UserArrow.user_id == user_id)
                    .options(selectinload(UserArrow.pack))
                    .order_by(UserArrow.id)
                    .with_for_update(of=UserArrow)
                )
            ).all()
        )
        selected = next(
            (row for row in rows if row.pack_id == pack_id and row.quantity > 0), None
        )
        if selected is None:
            raise ArcherError("از این پک تیر موجودی ندارید.")
        for row in rows:
            row.is_equipped = row.id == selected.id
        await session.flush()
        return selected

    async def fire(
        self,
        session: AsyncSession,
        defender_id: int,
        teacher_hp: int,
        teacher_max_hp: int,
        shot_index: int,
    ) -> ArcherHit | None:
        """Fire once per attacking teacher; strongest stocked arrow is spent first."""
        archers = await self.owned(session, defender_id, lock=True)
        arrows = await self.ammunition(session, defender_id, lock=True)
        if not archers or not arrows or teacher_hp <= 0:
            return None
        archer = archers[shot_index % len(archers)]
        stock = next((item for item in arrows if item.is_equipped), None)
        if stock is None:
            # An exhausted selected pack never silently consumes a premium pack.
            return None
        raw = self.power(archer) + stock.pack.power
        cap = max(1, ceil(teacher_max_hp * 0.3))
        damage = min(teacher_hp, raw, cap)
        stock.quantity -= 1
        return ArcherHit(
            archer.archer.name,
            archer.archer.emoji,
            archer.archer.sticker,
            stock.pack.name,
            damage,
        )
