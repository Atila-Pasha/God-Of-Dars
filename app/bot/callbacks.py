from typing import Literal

from aiogram.filters.callback_data import CallbackData


class ChannelCallback(CallbackData, prefix="channel"):
    action: Literal["check"]


class SchoolCallback(CallbackData, prefix="school"):
    action: Literal["castle", "teachers", "hospital", "back"]


class CastleCallback(CallbackData, prefix="castle"):
    action: Literal["view", "upgrade", "back"]


class TeacherCallback(CallbackData, prefix="teacher"):
    action: Literal[
        "view",
        "buy",
        "upgrade",
        "sell",
        "activate",
        "back_school",
        "back_teachers",
        "back_buffet",
    ]
    teacher_id: int
    origin: Literal["school", "buffet"] = "school"


class HospitalCallback(CallbackData, prefix="hospital"):
    action: Literal["activate", "recover", "back"]
    teacher_id: int


class ConfirmationCallback(CallbackData, prefix="confirm"):
    action: Literal[
        "castle_upgrade",
        "teacher_buy",
        "teacher_upgrade",
        "teacher_sell",
        "teacher_activate",
    ]
    target_id: int
    decision: Literal["confirm", "cancel"]
    origin: Literal["school", "buffet"] = "school"


class LibraryCallback(CallbackData, prefix="library"):
    action: Literal["daily", "group", "study", "back", "cancel"]


class StudyCallback(CallbackData, prefix="study"):
    pack_key: str


class ReferralCallback(CallbackData, prefix="referral"):
    action: Literal["back"]


class ProfileCallback(CallbackData, prefix="profile"):
    action: Literal["refresh", "back"]


class BuffetCallback(CallbackData, prefix="buffet"):
    action: Literal["convert"]
    source: str
    target: str


class BuffetMenuCallback(CallbackData, prefix="buffet_menu"):
    action: Literal["convert", "teachers", "shields", "back"]


class ShieldCallback(CallbackData, prefix="shield"):
    action: Literal["buy", "equip", "back"]
    shield_id: int


class MineCallback(CallbackData, prefix="mine"):
    action: Literal["upgrade", "confirm_upgrade", "cancel_upgrade", "back"]
