from __future__ import annotations

from datetime import UTC, datetime

from app.api.schemas.domain import (
    BattlePreviewView,
    BattleView,
    CastleView,
    MineProduction,
    MineView,
    OwnedShieldView,
    OwnedTeacherView,
    ProfileView,
    ResourceBalances,
    ShieldCatalogView,
    StudySessionView,
    StudyStateView,
    TeacherCatalogView,
    UserSummary,
)
from app.core.game_logic import GameConfigurationError, game_config
from app.models.attack import Attack
from app.models.castle import Castle
from app.models.resource import Resource
from app.models.shield import Shield
from app.models.study_session import StudySession
from app.models.teacher import Teacher
from app.models.user_shield import UserShield
from app.models.user_teacher import UserTeacher
from app.repositories.profile import ProfileSnapshot
from app.services.attack_service import AttackPreview
from app.services.mine_service import MineSnapshot
from app.services.school_errors import OperationNotConfigured
from app.services.teacher_service import TeacherService


def resources(value: Resource | None) -> ResourceBalances:
    return ResourceBalances(
        coin=value.coin if value else 0,
        diamond=value.diamond if value else 0,
        banana=value.banana if value else 0,
    )


def user_summary(user) -> UserSummary:
    return UserSummary(
        id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        level=user.level,
    )


def profile(snapshot: ProfileSnapshot) -> ProfileView:
    return ProfileView(
        user=user_summary(snapshot.user),
        resources=resources(snapshot.user.resources),
        member_since=snapshot.user.created_at,
        teachers_count=snapshot.teachers_count,
        active_teachers_count=snapshot.active_teachers_count,
        attacks_sent=snapshot.attacks_sent,
        successful_attacks=snapshot.successful_attacks,
        pending_attacks=snapshot.pending_attacks,
        attacks_received=snapshot.attacks_received,
        damage_dealt=snapshot.damage_dealt,
        loot=ResourceBalances(
            coin=snapshot.loot_coin,
            diamond=snapshot.loot_diamond,
            banana=snapshot.loot_banana,
        ),
        answers_count=snapshot.answers_count,
        correct_answers=snapshot.correct_answers,
        referrals_count=snapshot.referrals_count,
    )


def teacher_catalog(item: Teacher) -> TeacherCatalogView:
    return TeacherCatalogView(
        id=item.id,
        name=item.name,
        damage=item.damage,
        max_hp=item.max_hp,
        purchase_price=item.purchase_price,
        purchase_resource=item.purchase_resource.value,
        upgrade_price=item.upgrade_price,
        unlock_level=item.unlock_level,
        ability_text=item.ability_text,
        description=item.description,
        sticker=item.sticker,
        emoji=item.emoji,
    )


def owned_teacher(item: UserTeacher, service: TeacherService) -> OwnedTeacherView:
    try:
        upgrade_cost = service.upgrade_cost(item) if service.can_upgrade(item) else None
    except OperationNotConfigured:
        upgrade_cost = None
    try:
        sell_price = service.sell_price(item) if service.can_sell(item) else None
    except OperationNotConfigured:
        sell_price = None
    active_recovery = next(
        (recovery for recovery in item.recoveries if recovery.completed_at is None),
        None,
    )
    return OwnedTeacherView(
        id=item.id,
        teacher_id=item.teacher_id,
        name=item.teacher.name,
        level=item.level,
        damage=service.damage(item),
        current_hp=item.current_hp,
        max_hp=item.teacher.max_hp,
        status=item.status.value,
        upgrade_cost=upgrade_cost,
        sell_price=sell_price,
        can_upgrade=service.can_upgrade(item),
        can_sell=service.can_sell(item),
        recovery_ends_at=(active_recovery.recovery_end_at if active_recovery else None),
    )


def castle(item: Castle) -> CastleView:
    from app.services.castle_service import CastleService

    service = CastleService()
    quote = service.repair_quote(item)
    try:
        upgrade_cost = game_config.castle_upgrade(item.level).diamond_cost
    except GameConfigurationError:
        upgrade_cost = None
    return CastleView(
        level=item.level,
        strength=item.strength,
        maximum_strength=game_config.castle_max_strength(item.level),
        defense_power=item.defense.defense_power if item.defense else 0,
        repair_missing_strength=quote.missing_strength,
        repair_diamond_cost=quote.diamond_cost,
        next_upgrade_diamond_cost=upgrade_cost,
        can_upgrade=upgrade_cost is not None,
    )


def shield_catalog(item: Shield) -> ShieldCatalogView:
    return ShieldCatalogView(
        id=item.id,
        name=item.name,
        reduction_percent=item.reduction_percent,
        flat_absorption=item.flat_absorption,
        purchase_price=item.purchase_price,
        purchase_resource=item.purchase_resource.value,
        unlock_level=item.unlock_level,
        duration_minutes=item.duration_minutes,
        description=item.description,
    )


def owned_shield(item: UserShield) -> OwnedShieldView:
    return OwnedShieldView(
        id=item.id,
        shield_id=item.shield_id,
        name=item.shield.name,
        is_equipped=item.is_equipped,
        active_until=item.active_until,
    )


def mine(snapshot: MineSnapshot, *, player_level: int) -> MineView:
    try:
        next_level = game_config.mine_upgrade(snapshot.level, player_level)
        next_cost = next_level.diamond_cost
        required_level = next_level.required_player_level
    except GameConfigurationError:
        next_cost = None
        required_level = None
    return MineView(
        level=snapshot.level,
        collected_minutes=snapshot.collected_minutes,
        pending=ResourceBalances(
            coin=snapshot.today_coin,
            diamond=snapshot.today_diamond,
            banana=snapshot.today_banana,
        ),
        production=MineProduction(
            coin_per_minute=snapshot.production.coin_per_minute,
            diamond_per_minute=snapshot.production.diamond_per_minute,
            banana_per_minute=snapshot.production.banana_per_minute,
            next_upgrade_diamond_cost=next_cost,
            next_required_player_level=required_level,
        ),
        server_time=datetime.now(UTC),
    )


def study_session(item: StudySession) -> StudySessionView:
    return StudySessionView(
        id=item.id,
        pack_key=item.pack_key,
        started_at=item.started_at,
        ends_at=item.ends_at,
        completed_at=item.completed_at,
        server_time=datetime.now(UTC),
    )


def study_state(
    item: StudySession | None,
    reward: tuple | None = None,
) -> StudyStateView:
    reward_payload = None
    if reward is not None:
        reward_payload = {reward[0].value: reward[1]}
    return StudyStateView(
        active=study_session(item)
        if item is not None and item.completed_at is None
        else None,
        settled_reward=reward_payload,
    )


def battle(item: Attack) -> BattleView:
    return BattleView(
        id=item.id,
        attacker_id=item.attacker_id,
        target_id=item.target_id,
        teacher_id=item.teacher_id,
        status=item.status.value,
        created_at=item.created_at,
        resolve_at=item.resolve_at,
        resolved_at=item.resolved_at,
        damage=item.result_damage,
        loot=ResourceBalances(
            coin=item.loot_coin or 0,
            diamond=item.loot_diamond or 0,
            banana=item.loot_banana or 0,
        ),
        successful=item.is_successful,
    )


def battle_preview(
    item: AttackPreview, teacher_names: list[str], *, attacker_user_id: int
) -> BattlePreviewView:
    return BattlePreviewView(
        # AttackPreview is shared with the Telegram bot and carries the
        # Telegram identifier.  Public API responses expose only our internal
        # user identifier.
        attacker_id=attacker_user_id,
        target_id=item.target_id,
        attacker_name=item.attacker_name,
        target_name=item.target_name,
        teacher_names=teacher_names,
        teacher_damage=item.teacher_damage,
        defense_power=item.defense_power,
        estimated_castle_damage=item.estimated_castle_damage,
        estimated_teacher_injury=item.estimated_teacher_injury,
        loot=ResourceBalances(
            coin=item.loot_coin,
            diamond=item.loot_diamond,
            banana=item.loot_banana,
        ),
    )
