from __future__ import annotations

import tomllib
from copy import deepcopy
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
class BuffetConversion:
    """The price and result of one buffet conversion package."""

    source: ResourceType
    target: ResourceType
    source_amount: int
    target_amount: int


@dataclass(frozen=True)
class ShieldMitigation:
    """Result of applying one shield to incoming damage."""

    incoming_damage: int
    blocked_damage: int
    remaining_damage: int


@dataclass(frozen=True)
class ShieldRules:
    """Global limits for shield values editable in the TOML balance file."""

    min_reduction_percent: int = 0
    max_reduction_percent: int = 100
    max_flat_absorption: int = 1_000_000


@dataclass(frozen=True)
class MineLevel:
    """Production and upgrade balance for one mine level."""

    coin_per_minute: int = 0
    diamond_per_minute: int = 0
    banana_per_minute: int = 0
    upgrade_cost: int | None = None
    required_player_level: int = 1


@dataclass(frozen=True)
class LevelProgression:
    """XP required to move from each level; values are balance-editable."""

    xp_by_level: tuple[tuple[int, int], ...] = ()
    reset_xp_on_level_up: bool = True

    def required_xp(self, level: int) -> int | None:
        return dict(self.xp_by_level).get(level)


@dataclass(frozen=True)
class StudyPack:
    """One configurable study timer and its completion reward."""

    duration_minutes: int
    reward_resource: ResourceType
    reward_amount: int

    def __post_init__(self) -> None:
        if self.duration_minutes <= 0 or self.reward_amount < 0:
            raise ValueError("study pack values are invalid")


@dataclass(frozen=True)
class ChanceBoxRules:
    expiry_minutes: int = 2

    def __post_init__(self) -> None:
        if self.expiry_minutes <= 0:
            raise ValueError("chance box expiry must be positive")


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
    buffet_conversions: tuple[BuffetConversion, ...] = ()
    shield_rules: ShieldRules = field(default_factory=ShieldRules)
    mine_levels: dict[int, MineLevel] = field(default_factory=dict)
    mine_max_catchup_minutes: int = 1_440
    level_progression: LevelProgression = field(default_factory=LevelProgression)
    buildings: dict[str, dict[int, dict[str, int]]] = field(default_factory=dict)
    study_packs: dict[str, StudyPack] = field(default_factory=dict)
    chance_box_rules: ChanceBoxRules = field(default_factory=ChanceBoxRules)

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
        if (
            self.teacher_sell_ratio is not None
            and not 0 <= self.teacher_sell_ratio <= 1
        ):
            raise ValueError("teacher_sell_ratio must be between 0 and 1")
        if any(
            level < 2 or multiplier < 1
            for level, multiplier in self.teacher_damage_multipliers_by_level.items()
        ):
            raise ValueError("teacher damage multipliers are invalid")
        if self.referral_reward_amount is not None and self.referral_reward_amount < 0:
            raise ValueError("referral_reward_amount cannot be negative")
        if not (
            0
            <= self.shield_rules.min_reduction_percent
            <= self.shield_rules.max_reduction_percent
            <= 100
        ):
            raise ValueError("shield reduction limits are invalid")
        if self.shield_rules.max_flat_absorption < 0:
            raise ValueError("shield absorption limit cannot be negative")
        if self.mine_max_catchup_minutes < 1:
            raise ValueError("mine_max_catchup_minutes must be positive")
        for level, mine_level in self.mine_levels.items():
            if level < 1 or mine_level.required_player_level < 1:
                raise ValueError("mine levels are invalid")
            if (
                min(
                    mine_level.coin_per_minute,
                    mine_level.diamond_per_minute,
                    mine_level.banana_per_minute,
                )
                < 0
            ):
                raise ValueError("mine production cannot be negative")
            if mine_level.upgrade_cost is not None and mine_level.upgrade_cost < 0:
                raise ValueError("mine upgrade cost cannot be negative")
        seen: set[tuple[ResourceType, ResourceType]] = set()
        for conversion in self.buffet_conversions:
            key = (conversion.source, conversion.target)
            if conversion.source == conversion.target:
                raise ValueError("buffet conversion cannot use the same resource")
            if key in seen:
                raise ValueError("duplicate buffet conversion")
            if conversion.source_amount <= 0 or conversion.target_amount <= 0:
                raise ValueError("buffet conversion amounts must be positive")
            seen.add(key)

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

    def buffet_conversion(
        self, source: ResourceType, target: ResourceType
    ) -> BuffetConversion:
        for conversion in self.buffet_conversions:
            if conversion.source == source and conversion.target == target:
                return conversion
        raise GameConfigurationError("Buffet conversion is not configured")

    def buffet_options(self) -> tuple[BuffetConversion, ...]:
        return self.buffet_conversions

    def apply_shield(
        self,
        incoming_damage: int,
        *,
        reduction_percent: int,
        flat_absorption: int,
    ) -> ShieldMitigation:
        """Calculate damage after one shield, without mutating game state."""
        if incoming_damage < 0:
            raise GameConfigurationError("Incoming damage cannot be negative")
        if not (
            self.shield_rules.min_reduction_percent
            <= reduction_percent
            <= self.shield_rules.max_reduction_percent
        ):
            raise GameConfigurationError("Shield reduction percent is invalid")
        if not 0 <= flat_absorption <= self.shield_rules.max_flat_absorption:
            raise GameConfigurationError("Shield absorption is invalid")
        blocked = min(
            incoming_damage,
            round(incoming_damage * reduction_percent / 100) + flat_absorption,
        )
        return ShieldMitigation(
            incoming_damage=incoming_damage,
            blocked_damage=blocked,
            remaining_damage=incoming_damage - blocked,
        )

    def mine_level(self, level: int) -> MineLevel:
        try:
            return self.mine_levels[level]
        except KeyError as exc:
            raise GameConfigurationError("Mine level is not configured") from exc

    def mine_upgrade(self, level: int, player_level: int) -> MineLevel:
        next_level = self.mine_level(level + 1)
        if player_level < next_level.required_player_level:
            raise GameConfigurationError("Mine level is locked")
        if next_level.upgrade_cost is None:
            raise GameConfigurationError("Mine upgrade is not configured")
        return next_level

    def level_xp(self, level: int) -> int | None:
        return self.level_progression.required_xp(level)

    def study_pack(self, key: str) -> StudyPack:
        try:
            return self.study_packs[key]
        except KeyError as exc:
            raise GameConfigurationError("Study pack is not configured") from exc

    @classmethod
    def from_toml(cls, path: str | Path) -> GameConfig:
        config_path = Path(path)
        if not config_path.exists():
            return cls()

        # Balance is split into small files under config/game_balance/.  The
        # legacy game_balance.toml remains supported for deployments that have
        # not migrated yet; fragment values override legacy values.
        if config_path.is_dir():
            legacy = config_path.with_name("game_balance.toml")
            paths = ([legacy] if legacy.exists() else []) + sorted(config_path.glob("*.toml"))
        else:
            paths = [config_path]
        data: dict = {}
        for fragment in paths:
            with fragment.open("rb") as config_file:
                fragment_data = tomllib.load(config_file)
            for key, value in fragment_data.items():
                if isinstance(value, dict) and isinstance(data.get(key), dict):
                    merged = deepcopy(data[key])
                    merged.update(value)
                    data[key] = merged
                else:
                    data[key] = value

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
        buffet_conversions = tuple(
            BuffetConversion(
                source=ResourceType(str(item["source"]).upper()),
                target=ResourceType(str(item["target"]).upper()),
                source_amount=int(item["source_amount"]),
                target_amount=int(item["target_amount"]),
            )
            for item in data.get("buffet", {}).get("conversions", [])
        )
        shield_data = data.get("shield_rules", {})
        mine_data = data.get("mine", {})
        progression = data.get("progression", {})
        study_packs = {
            str(key): StudyPack(
                duration_minutes=int(values["duration_minutes"]),
                reward_resource=ResourceType(str(values["reward_resource"]).upper()),
                reward_amount=int(values["reward_amount"]),
            )
            for key, values in data.get("study", {}).get("packs", {}).items()
        }
        chance_box_data = data.get("chance_box", {})
        xp_by_level = tuple(sorted(
            (int(key.removeprefix("level_")), int(value))
            for key, value in progression.get("xp_to_next_level", {}).items()
        ))
        mine_levels = {
            int(level.removeprefix("level_")): MineLevel(
                coin_per_minute=int(values.get("coin_per_minute", 0)),
                diamond_per_minute=int(values.get("diamond_per_minute", 0)),
                banana_per_minute=int(values.get("banana_per_minute", 0)),
                upgrade_cost=(
                    None
                    if values.get("upgrade_cost") is None
                    else int(values["upgrade_cost"])
                ),
                required_player_level=int(values.get("required_player_level", 1)),
            )
            for level, values in mine_data.get("levels", {}).items()
        }
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
                    referral_reward.get("inviter_resource", ResourceType.DIAMOND.value)
                ).upper()
            ),
            referral_reward_amount=referral_reward_amount,
            buffet_conversions=buffet_conversions,
            shield_rules=ShieldRules(
                min_reduction_percent=int(shield_data.get("min_reduction_percent", 0)),
                max_reduction_percent=int(
                    shield_data.get("max_reduction_percent", 100)
                ),
                max_flat_absorption=int(
                    shield_data.get("max_flat_absorption", 1_000_000)
                ),
            ),
            mine_levels=mine_levels,
            mine_max_catchup_minutes=int(mine_data.get("max_catchup_minutes", 1_440)),
            level_progression=LevelProgression(
                xp_by_level=xp_by_level,
                reset_xp_on_level_up=bool(progression.get("reset_xp_on_level_up", True)),
            ),
            buildings={
                str(name): {
                    int(level.removeprefix("level_")): {str(k): int(v) for k, v in values.items()}
                    for level, values in levels.items()
                }
                for name, levels in data.get("buildings", {}).items()
            },
            study_packs=study_packs,
            chance_box_rules=ChanceBoxRules(
                expiry_minutes=int(chance_box_data.get("expiry_minutes", 2))
            ),
        )


DEFAULT_GAME_CONFIG_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "game_balance"
)
game_config = GameConfig.from_toml(DEFAULT_GAME_CONFIG_PATH)
