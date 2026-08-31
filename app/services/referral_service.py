from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.game_logic import game_config
from app.models.reward import Reward
from app.models.user import User
from app.repositories.referral import ReferralRepository
from app.services.reward_service import RewardService, RewardSpec


class ReferralError(RuntimeError):
    """Base class for invite/referral domain errors."""


class InvalidReferralCode(ReferralError):
    pass


class SelfReferral(ReferralError):
    pass


class ReferrerNotFound(ReferralError):
    pass


class ReferralAlreadySet(ReferralError):
    pass


class ReferralCycle(ReferralError):
    pass


class ReferralUserInactive(ReferralError):
    pass


@dataclass(frozen=True)
class ReferralResult:
    referred_user: User
    referrer: User | None
    applied: bool
    inviter_reward: Reward | None = None
    referred_reward: Reward | None = None


class ReferralService:
    """Owns one-time invite attribution and optional configured rewards."""

    PAYLOAD_PREFIX = "ref_"
    _PAYLOAD_RE = re.compile(r"^ref_([1-9][0-9]*)$")

    def __init__(
        self,
        repository: ReferralRepository | None = None,
        *,
        reward_service: RewardService | None = None,
        inviter_reward: RewardSpec | None = None,
        referred_reward: RewardSpec | None = None,
    ) -> None:
        self.repository = repository or ReferralRepository()
        self.reward_service = reward_service or RewardService()
        self.inviter_reward = inviter_reward or self._configured_inviter_reward()
        self.referred_reward = referred_reward

    @staticmethod
    def _configured_inviter_reward() -> RewardSpec | None:
        if game_config.referral_reward_amount is None:
            return None
        return RewardSpec(
            resource_type=game_config.referral_reward_resource,
            amount=game_config.referral_reward_amount,
        )

    @classmethod
    def payload_for(cls, referrer_id: int) -> str:
        if referrer_id <= 0:
            raise ValueError("referrer_id must be positive")
        return f"{cls.PAYLOAD_PREFIX}{referrer_id}"

    @classmethod
    def parse_payload(cls, payload: str | None) -> int | None:
        if not payload:
            return None
        match = cls._PAYLOAD_RE.fullmatch(payload.strip())
        return int(match.group(1)) if match else None

    async def apply(
        self,
        session: AsyncSession,
        *,
        referred_user_id: int,
        referrer_id: int,
    ) -> ReferralResult:
        if referred_user_id == referrer_id:
            raise SelfReferral

        # Lock in deterministic ID order.  This prevents a deadlock when two
        # users attempt to refer one another at nearly the same time.
        users: dict[int, User | None] = {}
        for user_id in sorted({referred_user_id, referrer_id}):
            users[user_id] = await self.repository.get_user_for_update(
                session, user_id
            )

        referred = users[referred_user_id]
        if referred is None:
            raise ReferralUserInactive
        if referred.is_active is False:
            raise ReferralUserInactive

        referrer = users[referrer_id]
        if referrer is None:
            raise ReferrerNotFound
        if referrer.is_active is False:
            raise ReferrerNotFound

        if referred.referrer_id is not None:
            if referred.referrer_id == referrer.id:
                return ReferralResult(
                    referred_user=referred,
                    referrer=referrer,
                    applied=False,
                )
            raise ReferralAlreadySet

        if await self.repository.is_descendant(
            session,
            ancestor_id=referred.id,
            descendant_id=referrer.id,
        ):
            raise ReferralCycle

        referred.referrer_id = referrer.id
        await session.flush()

        inviter_reward = await self.reward_service.grant(
            session,
            user_id=referrer.id,
            spec=self.inviter_reward,
            source="REFERRAL",
            reference_type="REFERRED_USER",
            reference_id=referred.id,
        )
        referred_reward = await self.reward_service.grant(
            session,
            user_id=referred.id,
            spec=self.referred_reward,
            source="REFERRAL",
            reference_type="REFERRER",
            reference_id=referrer.id,
        )
        return ReferralResult(
            referred_user=referred,
            referrer=referrer,
            applied=True,
            inviter_reward=inviter_reward.reward if inviter_reward else None,
            referred_reward=referred_reward.reward if referred_reward else None,
        )

    async def count(self, session: AsyncSession, referrer_id: int) -> int:
        return await self.repository.count_referrals(session, referrer_id)

    async def list_referrals(
        self, session: AsyncSession, referrer_id: int
    ) -> list[User]:
        return await self.repository.list_referrals(session, referrer_id)

    apply_referral = apply
    referral_count = count
