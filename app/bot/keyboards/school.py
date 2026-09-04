from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.callbacks import (
    CastleCallback,
    ConfirmationCallback,
    HospitalCallback,
    SchoolCallback,
    TeacherCallback,
)
from app.bot.custom_emojis import premium_emoji_id
from app.core.enums import TeacherStatus
from app.models.teacher import Teacher
from app.models.user_teacher import UserTeacher


def school_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🏰 دژ",
                    callback_data=SchoolCallback(action="castle").pack(),
                ),
                InlineKeyboardButton(
                    text="👨‍🏫 دبیرها",
                    callback_data=SchoolCallback(action="teachers").pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🏥 بیمارستان",
                    callback_data=SchoolCallback(action="hospital").pack(),
                ),
                InlineKeyboardButton(
                    text="🔙 منوی اصلی",
                    callback_data=SchoolCallback(action="back").pack(),
                ),
            ],
        ]
    )


def castle_keyboard(can_upgrade: bool) -> InlineKeyboardMarkup:
    buttons = []
    if can_upgrade:
        buttons.append(
            InlineKeyboardButton(
                text="⬆️ ارتقای دژ",
                callback_data=CastleCallback(action="upgrade").pack(),
            )
        )
    buttons.append(
            InlineKeyboardButton(
                    text="🔙 مدرسه من",
            callback_data=CastleCallback(action="back").pack(),
        )
    )
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


def confirmation_keyboard(
    *, action: str, target_id: int, origin: str = "school"
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ تأیید",
                    callback_data=ConfirmationCallback(
                        action=action,
                        target_id=target_id,
                        decision="confirm",
                        origin=origin,
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text="❌ لغو",
                    callback_data=ConfirmationCallback(
                        action=action,
                        target_id=target_id,
                        decision="cancel",
                        origin=origin,
                    ).pack(),
                ),
            ]
        ]
    )


def teachers_keyboard(
    teachers: list[UserTeacher],
    catalog: list[Teacher],
    *,
    can_buy: bool,
    back_action: str = "back_school",
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=owned.teacher.name,
                icon_custom_emoji_id=premium_emoji_id(
                    owned.teacher.emoji, fallback="👨‍🏫"
                ),
                callback_data=TeacherCallback(
                    action="view", teacher_id=owned.id
                ).pack(),
            )
        ]
        for owned in teachers
    ]
    if can_buy:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🛒 خرید دبیر",
                    callback_data=TeacherCallback(action="buy", teacher_id=0).pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                    text="🔙 بوفه" if back_action == "back_buffet" else "🔙 مدرسه من",
                callback_data=TeacherCallback(
                    action=back_action,
                    teacher_id=0,
                    origin="buffet" if back_action == "back_buffet" else "school",
                ).pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def teacher_catalog_keyboard(
    teachers: list[Teacher],
    *,
    player_level: int,
    back_action: str = "back_teachers",
    origin: str = "school",
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"🛒 {teacher.name} — {teacher.purchase_price} سکه",
                callback_data=TeacherCallback(
                    action="buy", teacher_id=teacher.id, origin=origin
                ).pack(),
            )
        ]
        for teacher in teachers
        if teacher.unlock_level <= player_level
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text="🔙 دبیرها",
                callback_data=TeacherCallback(
                    action=back_action, teacher_id=0, origin=origin
                ).pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def teacher_detail_keyboard(
    teacher: UserTeacher, *, can_upgrade: bool, can_sell: bool, can_activate: bool
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="📊 اطلاعات",
                callback_data=TeacherCallback(
                    action="view", teacher_id=teacher.id
                ).pack(),
            )
        ]
    ]
    if teacher.status is TeacherStatus.ACTIVE and (can_upgrade or can_sell):
        action_buttons = []
        if can_upgrade:
            action_buttons.append(
                InlineKeyboardButton(
                    text="⬆️ ارتقا",
                    callback_data=TeacherCallback(
                        action="upgrade", teacher_id=teacher.id
                    ).pack(),
                )
            )
        if can_sell:
            action_buttons.append(
                InlineKeyboardButton(
                    text="💰 فروش",
                    callback_data=TeacherCallback(
                        action="sell", teacher_id=teacher.id
                    ).pack(),
                )
            )
        rows.append(action_buttons)
    if (
        teacher.status is TeacherStatus.ACTIVE
        and teacher.current_hp < teacher.teacher.max_hp
    ):
        rows.append(
            [
                InlineKeyboardButton(
                    text="🏥 فرستادن به بیمارستان",
                    callback_data=TeacherCallback(
                        action="send_to_hospital", teacher_id=teacher.id
                    ).pack(),
                )
            ]
        )
    elif teacher.status is TeacherStatus.DISABLED and can_activate:
        rows.append(
            [
                InlineKeyboardButton(
                    text="⚡ فعال‌سازی",
                    callback_data=TeacherCallback(
                        action="activate", teacher_id=teacher.id
                    ).pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="🔙 دبیرها",
                callback_data=TeacherCallback(
                    action="back_teachers", teacher_id=0
                ).pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def hospital_keyboard(
    teachers: list[UserTeacher], *, can_activate: bool, can_recover: bool,
    instant_recovery_cost: int | None = None
) -> InlineKeyboardMarkup:
    rows = []
    for teacher in teachers:
        if teacher.status is TeacherStatus.DISABLED and can_activate:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"⚡ فعال‌سازی {teacher.teacher.name}",
                        callback_data=HospitalCallback(
                            action="activate", teacher_id=teacher.id
                        ).pack(),
                    )
                ]
            )
        elif teacher.status is TeacherStatus.INJURED and can_recover:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"🩹 شروع بهبودی {teacher.teacher.name}",
                        callback_data=HospitalCallback(
                            action="recover", teacher_id=teacher.id
                        ).pack(),
                    )
                ]
            )
        if (
            teacher.status in {TeacherStatus.INJURED, TeacherStatus.RECOVERING}
            and instant_recovery_cost is not None
        ):
            rows.append(
                [
                    InlineKeyboardButton(
                        text=(
                            f"⚡ بهبود فوری {teacher.teacher.name} "
                            f"({instant_recovery_cost} 💎)"
                        ),
                        callback_data=HospitalCallback(
                            action="instant", teacher_id=teacher.id
                        ).pack(),
                    )
                ]
            )
    rows.append(
        [
            InlineKeyboardButton(
                text="🔙 مدرسه من",
                callback_data=HospitalCallback(action="back", teacher_id=0).pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
