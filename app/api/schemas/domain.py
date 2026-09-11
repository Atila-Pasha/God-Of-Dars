from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class ResourceBalances(BaseModel):
    coin: int = Field(ge=0)
    diamond: int = Field(ge=0)
    banana: int = Field(ge=0)


class UserSummary(BaseModel):
    id: int
    username: str | None
    first_name: str
    last_name: str | None
    level: int


class ProfileView(BaseModel):
    user: UserSummary
    resources: ResourceBalances
    member_since: datetime
    teachers_count: int
    active_teachers_count: int
    attacks_sent: int
    successful_attacks: int
    pending_attacks: int
    attacks_received: int
    damage_dealt: int
    loot: ResourceBalances
    answers_count: int
    correct_answers: int
    referrals_count: int


class PublicProfileView(BaseModel):
    user: UserSummary
    member_since: datetime
    teachers_count: int
    attacks_sent: int
    successful_attacks: int
    answers_count: int
    correct_answers: int


class TransactionView(BaseModel):
    id: int
    resource_type: str
    amount: int
    balance_before: int | None
    balance_after: int | None
    reason: str
    reference_type: str | None
    reference_id: int | None
    created_at: datetime


class TransactionPage(BaseModel):
    items: list[TransactionView]
    next_cursor: str | None


class LevelView(BaseModel):
    level: int
    next_upgrade_cost: int | None
    maximum_level: int
    resources: ResourceBalances


class TeacherCatalogView(BaseModel):
    id: int
    name: str
    damage: int
    max_hp: int
    purchase_price: int
    purchase_resource: str
    upgrade_price: int
    unlock_level: int
    ability_text: str | None
    description: str | None
    sticker: str | None
    emoji: str | None


class OwnedTeacherView(BaseModel):
    id: int
    teacher_id: int
    name: str
    level: int
    damage: int
    current_hp: int
    max_hp: int
    status: str
    upgrade_cost: int | None
    sell_price: int | None
    can_upgrade: bool
    can_sell: bool
    recovery_ends_at: datetime | None


class TeacherListView(BaseModel):
    items: list[OwnedTeacherView]
    owned: int
    available: int
    maximum: int | None


class CastleView(BaseModel):
    level: int
    strength: int
    maximum_strength: int
    defense_power: int
    repair_missing_strength: int
    repair_diamond_cost: int
    next_upgrade_diamond_cost: int | None
    can_upgrade: bool


class ShieldCatalogView(BaseModel):
    id: int
    name: str
    reduction_percent: int
    flat_absorption: int
    purchase_price: int
    purchase_resource: str
    unlock_level: int
    duration_minutes: int
    description: str | None


class OwnedShieldView(BaseModel):
    id: int
    shield_id: int
    name: str
    is_equipped: bool
    active_until: datetime | None


class MineProduction(BaseModel):
    coin_per_minute: int
    diamond_per_minute: int
    banana_per_minute: int
    next_upgrade_diamond_cost: int | None
    next_required_player_level: int | None


class MineView(BaseModel):
    level: int
    collected_minutes: int
    pending: ResourceBalances
    production: MineProduction
    server_time: datetime


class MineCollectView(BaseModel):
    mine: MineView
    collected: ResourceBalances
    balances: ResourceBalances


class StudyPackView(BaseModel):
    key: str
    name: str
    duration_minutes: int
    reward_resource: str
    reward_amount: int


class StudySessionView(BaseModel):
    id: int
    pack_key: str
    started_at: datetime
    ends_at: datetime
    completed_at: datetime | None
    server_time: datetime


class StudyStateView(BaseModel):
    active: StudySessionView | None
    settled_reward: dict[str, int] | None = None


class StudyStartRequest(BaseModel):
    pack_key: str = Field(min_length=1, max_length=64)


class DailyQuestionView(BaseModel):
    id: int
    question_text: str
    expires_at: datetime | None
    rewards: ResourceBalances
    already_answered: bool


class DailyAnswerRequest(BaseModel):
    question_id: int = Field(gt=0)
    answer: str = Field(min_length=1, max_length=2000)


class DailyAnswerView(BaseModel):
    answer_id: int
    correct: bool
    rewards: ResourceBalances
    balances: ResourceBalances


class DailyQuestView(BaseModel):
    id: int
    activity_date: date
    quest_type: str
    title: str
    description: str | None
    target: int
    progress_id: int | None
    progress: int
    completed: bool
    claimed: bool
    rewards: dict[str, int]
    metadata: dict


class BattlePreviewRequest(BaseModel):
    target_user_id: int = Field(gt=0)
    teacher_ids: list[int] = Field(min_length=1, max_length=4)


class BattlePreviewView(BaseModel):
    attacker_id: int
    target_id: int
    attacker_name: str
    target_name: str
    teacher_names: list[str]
    teacher_damage: int
    defense_power: int
    estimated_castle_damage: int
    estimated_teacher_injury: int
    loot: ResourceBalances


class BattleStartRequest(BattlePreviewRequest):
    pass


class BattleLaunchView(BaseModel):
    battle_ids: list[int]
    status: str
    target_name: str
    teacher_names: list[str]
    resolve_at: datetime


class BattleView(BaseModel):
    id: int
    attacker_id: int
    target_id: int
    teacher_id: int | None
    status: str
    created_at: datetime
    resolve_at: datetime
    resolved_at: datetime | None
    damage: int | None
    loot: ResourceBalances
    successful: bool | None


class BattlePage(BaseModel):
    items: list[BattleView]
    next_cursor: str | None


class OpponentView(BaseModel):
    id: int
    username: str | None
    name: str
    level: int


class ExchangeOptionView(BaseModel):
    source: str
    target: str
    source_amount: int
    target_amount: int


class ExchangeRequest(BaseModel):
    source: str = Field(min_length=1, max_length=16)
    target: str = Field(min_length=1, max_length=16)
    source_amount: int = Field(gt=0)


class ExchangeView(BaseModel):
    option: ExchangeOptionView
    packages: int
    balances: ResourceBalances


class ReferralView(BaseModel):
    code: str
    deep_link: str | None
    count: int
    referrer_id: int | None


class ReferralApplyRequest(BaseModel):
    code: str = Field(min_length=5, max_length=64)


class ReferralApplyView(BaseModel):
    applied: bool
    referrer_id: int | None


class ReferredUserView(BaseModel):
    id: int
    username: str | None
    name: str
    level: int
    joined_at: datetime


class ChanceCardView(BaseModel):
    id: int
    resource_type: str
    amount: int
    claimed: bool
    created_at: datetime


class ChanceClaimRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=16)


class NotificationView(BaseModel):
    id: int
    type: str
    payload: dict
    delivery_status: str
    created_at: datetime
    sent_at: datetime | None
    read_at: datetime | None


class NotificationPage(BaseModel):
    items: list[NotificationView]
    next_cursor: str | None


class NotificationReadAllRequest(BaseModel):
    through_id: int | None = Field(default=None, gt=0)


class SubscriptionChannelView(BaseModel):
    id: int
    title: str
    url: str | None


class SubscriptionView(BaseModel):
    member: bool | None
    provider_available: bool
    checked_at: datetime
    channels: list[SubscriptionChannelView]


class BootstrapView(BaseModel):
    profile: ProfileView
    castle: CastleView
    mine: MineView
    study: StudyStateView
    server_time: datetime
