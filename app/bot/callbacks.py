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
    ]
    teacher_id: int


class HospitalCallback(CallbackData, prefix="hospital"):
    action: Literal["activate", "recover", "back"]
    teacher_id: int


class LibraryCallback(CallbackData, prefix="library"):
    action: Literal["daily", "group", "back", "cancel"]


class ReferralCallback(CallbackData, prefix="referral"):
    action: Literal["back"]


class ProfileCallback(CallbackData, prefix="profile"):
    action: Literal["refresh", "back"]
