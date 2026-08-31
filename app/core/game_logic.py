from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from app.core.enums import ResourceType


class GameConfigurationError(RuntimeError):
    """Raised when a required game balance value is missing or invalid."""


@dataclass(frozen=True)
class CastleUpgrade:
    coin_cost: int
    strength_delta: int
    defense_delta: int


@dataclass(frozen=True)
class GameConfig:
    """Central home for game balance and progression rules.

    The TOML file is the source of the default balance. Empty mappings are
    still valid for custom/test configurations and disable that operation
    safely instead of silently inventing an economy.
    """

    max_teacher_slots: int = 4
    teacher_slots_by_level: tuple[tuple[int, int], ...] = ()
    castle_upgrade_by_level: dict[int, CastleUpgrade] = field(default_factory=dict)
    teacher_sell_prices: dict[int, int] = field(default_factory=dict)
    teacher_activation_cost: int | None = None
    teacher_damage_by_level: dict[tuple[int, int], int] = field(default_factory=dict)
    teacher_damage_multipliers_by_level: dict[int, float] = field(default_factory=dict)
    teacher_sell_ratio: float | None = None
    recovery_minutes_by_strength: tuple[tuple[int, int], ...] = ()
    initial_castle_strength: int = 0
    initial_defense_power: int = 0
    referral_reward_resource: ResourceType = ResourceType.DIAMOND
    referral_reward_amount: int | None = None

    def __post_init__(self) -> None:
        if self.max_teacher_slots < 1:
            raise ValueError("max_teacher_slots must be positive")
        if self.max_teacher_slots > 4:
            raise ValueError("max_teacher_slots cannot exceed 4")
        previous_level = 0
        for level, slots in self.teacher_slots_by_level:
            if level < 1 or level <= previous_level:
                raise ValueError("teacher slot levels must be strictly increasing")
            if slots < 0 or slots > self.max_teacher_slots:
                raise ValueError("teacher slot capacity is outside the valid range")
            previous_level = level
        previous_strength = -1
        for strength, minutes in self.recovery_minutes_by_strength:
            if strength < 0 or strength <= previous_strength or minutes <= 0:
                raise ValueError("recovery strength thresholds are invalid")
            previous_strength = strength
        if self.teacher_sell_ratio is not None and not 0 <= self.teacher_sell_ratio <= 1:
            raise ValueError("teacher_sell_ratio must be between 0 and 1")
        if any(
            level < 2 or multiplier < 1
            for level, multiplier in self.teacher_damage_multipliers_by_level.items()
        ):
            raise ValueError("teacher damage multipliers are invalid")
        if self.referral_reward_amount is not None and self.referral_reward_amount < 0:
            raise ValueError("referral_reward_amount cannot be negative")

    def teacher_slots(self, player_level: int) -> int:
        capacity = 0
        for unlock_level, slots in self.teacher_slots_by_level:
            if player_level < unlock_level:
                break
            capacity = slots
        return min(capacity, self.max_teacher_slots)

    def castle_upgrade(self, castle_level: int) -> CastleUpgrade:
        try:
            upgrade = self.castle_upgrade_by_level[castle_level]
        except KeyError as exc:
            raise GameConfigurationError(
                "Castle upgrade balance is not configured"
            ) from exc
        if (
            min(
                upgrade.coin_cost,
                upgrade.strength_delta,
                upgrade.defense_delta,
            )
            < 0
        ):
            raise GameConfigurationError("Castle upgrade values cannot be negative")
        return upgrade

    def teacher_damage(
        self,
        teacher_id: int,
        teacher_level: int,
        base_damage: int | None = None,
    ) -> int:
        if teacher_level == 1:
            if base_damage is None:
                raise GameConfigurationError("Base teacher damage is required")
            return base_damage
        damage = self.teacher_damage_by_level.get((teacher_id, teacher_level))
        if damage is None:
            multiplier = self.teacher_damage_multipliers_by_level.get(teacher_level)
            if multiplier is None or base_damage is None:
                raise GameConfigurationError(
                    "Teacher damage progression is not configured"
                )
            damage = round(base_damage * multiplier)
        if damage < 0:
            raise GameConfigurationError("Teacher damage cannot be negative")
        return damage

    def teacher_sell_price(
        self, teacher_id: int, purchase_price: int | None = None
    ) -> int:
        price = self.teacher_sell_prices.get(teacher_id)
        if price is None:
            if self.teacher_sell_ratio is None or purchase_price is None:
                raise GameConfigurationError("Teacher sell price is not configured")
            price = round(purchase_price * self.teacher_sell_ratio)
        if price < 0:
            raise GameConfigurationError("Teacher sell price cannot be negative")
        return price

    def recovery_minutes(self, castle_strength: int) -> int:
        duration = 0
        for minimum_strength, minutes in self.recovery_minutes_by_strength:
            if castle_strength < minimum_strength:
                break
            duration = minutes
        if duration <= 0:
            raise GameConfigurationError("Teacher recovery duration is not configured")
        return duration

    @property
    def recovery_is_configured(self) -> bool:
        return bool(self.recovery_minutes_by_strength)

    @classmethod
    def from_toml(cls, path: str | Path) -> GameConfig:
        config_path = Path(path)
        if not config_path.exists():
            return cls()

        with config_path.open("rb") as config_file:
            data = tomllib.load(config_file)

        castle_upgrades = {
            int(level): CastleUpgrade(**values)
            for level, values in data.get("castle_upgrades", {}).items()
        }
        damage_by_level = {}
        for key, damage in data.get("teacher_damage", {}).get("explicit", {}).items():
            teacher_id, teacher_level = (
                int(part) for part in key.split(":", maxsplit=1)
            )
            damage_by_level[(teacher_id, teacher_level)] = int(damage)

        slots = tuple(
            sorted(
                (
                    int(level.removeprefix("level_")),
                    int(capacity),
                )
                for level, capacity in data.get("teacher_slots", {}).items()
            )
        )
        recovery = tuple(
            sorted(
                (
                    int(strength.removeprefix("strength_")),
                    int(minutes),
                )
                for strength, minutes in data.get("recovery_minutes", {}).items()
            )
        )
        referral_reward = data.get("referral_reward", {})
        referral_reward_amount_raw = referral_reward.get("inviter_amount")
        referral_reward_amount = (
            None
            if referral_reward_amount_raw is None
            else int(referral_reward_amount_raw)
        )
        return cls(
            max_teacher_slots=int(data.get("max_teacher_slots", 4)),
            teacher_slots_by_level=slots,
            castle_upgrade_by_level=castle_upgrades,
            teacher_sell_prices={
                int(teacher_id): int(price)
                for teacher_id, price in data.get("teacher_sell_prices", {}).items()
            },
            teacher_activation_cost=data.get("teacher_activation_cost"),
            teacher_damage_by_level=damage_by_level,
            teacher_damage_multipliers_by_level={
                int(level.removeprefix("level_")): float(multiplier)
                for level, multiplier in data.get("teacher_damage", {}).items()
                if level != "explicit"
            },
            teacher_sell_ratio=data.get("teacher_sell_ratio"),
            recovery_minutes_by_strength=recovery,
            initial_castle_strength=int(data.get("initial_castle_strength", 0)),
            initial_defense_power=int(data.get("initial_defense_power", 0)),
            referral_reward_resource=ResourceType(
                str(
                    referral_reward.get(
                        "inviter_resource", ResourceType.DIAMOND.value
                    )
                ).upper()
            ),
            referral_reward_amount=referral_reward_amount,
        )


DEFAULT_GAME_CONFIG_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "game_balance.toml"
)
game_config = GameConfig.from_toml(DEFAULT_GAME_CONFIG_PATH)
