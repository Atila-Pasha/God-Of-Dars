from typing import Literal

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

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
from app.services.recovery_service import HospitalService


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
            ],
        ]
    )


def school_navigation_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="بازگشت به منو اصلی",
                    icon_custom_emoji_id="5235864325540815679",
                )
            ]
        ],
        resize_keyboard=True,
        is_persistent=False,
    )


def castle_keyboard(
    can_upgrade: bool, can_repair: bool = False
) -> InlineKeyboardMarkup:
    buttons: list[InlineKeyboardButton] = [
        InlineKeyboardButton(
            text="ارتقای دژ",
            icon_custom_emoji_id="5866060208253441223",
            style="success",
            callback_data=CastleCallback(action="upgrade").pack(),
        ),
        InlineKeyboardButton(
            text="تعمیر دژ",
            icon_custom_emoji_id="5341715473882955310",
            callback_data=CastleCallback(action="repair").pack(),
        ),
    ]
    buttons.append(
        InlineKeyboardButton(
            text="بازگشت",
            icon_custom_emoji_id="5235864325540815679",
            style="danger",
            callback_data=CastleCallback(action="back").pack(),
        )
    )
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


ConfirmationAction = Literal[
    "castle_upgrade",
    "castle_repair",
    "teacher_buy",
    "teacher_upgrade",
    "teacher_sell",
    "teacher_activate",
    "hospital_instant_recover",
    "hospital_upgrade",
]
TeacherAction = Literal[
    "view",
    "buy",
    "page",
    "upgrade",
    "sell",
    "activate",
    "send_to_hospital",
    "back_school",
    "back_teachers",
    "back_buffet",
]
TeacherOrigin = Literal["school", "buffet"]


def confirmation_keyboard(
    *,
    action: ConfirmationAction,
    target_id: int,
    origin: TeacherOrigin = "school",
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ تأیید",
                    style="success",
                    callback_data=ConfirmationCallback(
                        action=action,
                        target_id=target_id,
                        decision="confirm",
                        origin=origin,
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text="❌ لغو",
                    style="danger",
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
    back_action: Literal["back_school", "back_buffet"] = "back_school",
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
    back_action: TeacherAction = "back_teachers",
    origin: TeacherOrigin = "school",
) -> InlineKeyboardMarkup:
    visible = [teacher for teacher in teachers if teacher.unlock_level <= player_level]
    page_size = 5
    page_count = max(1, (len(visible) + page_size - 1) // page_size)
    page = 0
    page_items = visible[:page_size]
    rows = [
        [
            InlineKeyboardButton(
                text=(
                    f"{teacher.name} — {teacher.purchase_price} "
                    f"{'الماس' if teacher.purchase_resource.value == 'DIAMOND' else 'طلا'}"
                ),
                icon_custom_emoji_id=premium_emoji_id(teacher.emoji, fallback="👨‍🏫"),
                callback_data=TeacherCallback(
                    action="buy", teacher_id=teacher.id, origin=origin, page=page
                ).pack(),
            )
        ]
        for teacher in page_items
    ]
    if page_count > 1:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"صفحه 1 از {page_count} ▶️",
                    callback_data=TeacherCallback(
                        action="page", teacher_id=0, origin=origin, page=1
                    ).pack(),
                )
            ]
        )
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


def teacher_catalog_page_keyboard(
    teachers: list[Teacher],
    *,
    player_level: int,
    page: int,
    back_action: TeacherAction = "back_teachers",
    origin: TeacherOrigin = "school",
) -> InlineKeyboardMarkup:
    visible = [teacher for teacher in teachers if teacher.unlock_level <= player_level]
    page_size = 5
    page_count = max(1, (len(visible) + page_size - 1) // page_size)
    page = max(0, min(page, page_count - 1))
    items = visible[page * page_size : (page + 1) * page_size]
    rows = [
        [
            InlineKeyboardButton(
                text=(
                    f"{teacher.name} — {teacher.purchase_price} "
                    f"{'الماس' if teacher.purchase_resource.value == 'DIAMOND' else 'طلا'}"
                ),
                icon_custom_emoji_id=premium_emoji_id(teacher.emoji, fallback="👨‍🏫"),
                callback_data=TeacherCallback(
                    action="buy", teacher_id=teacher.id, origin=origin, page=page
                ).pack(),
            )
        ]
        for teacher in items
    ]
    navigation = []
    if page > 0:
        navigation.append(
            InlineKeyboardButton(
                text="◀️ قبلی",
                callback_data=TeacherCallback(
                    action="page", teacher_id=0, origin=origin, page=page - 1
                ).pack(),
            )
        )
    if page < page_count - 1:
        navigation.append(
            InlineKeyboardButton(
                text="بعدی ▶️",
                callback_data=TeacherCallback(
                    action="page", teacher_id=0, origin=origin, page=page + 1
                ).pack(),
            )
        )
    if navigation:
        rows.append(navigation)
    rows.append(
        [
            InlineKeyboardButton(
                text=f"صفحه {page + 1} از {page_count}",
                callback_data=TeacherCallback(
                    action="page", teacher_id=0, origin=origin, page=page
                ).pack(),
            )
        ]
    )
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
    if teacher.status is TeacherStatus.ACTIVE:
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
    teachers: list[UserTeacher],
    *,
    can_activate: bool,
    can_recover: bool,
    instant_recovery_cost: int | None = None,
    can_upgrade: bool = False,
) -> InlineKeyboardMarkup:
    rows = []
    if can_upgrade:
        rows.append(
            [
                InlineKeyboardButton(
                    text="ارتقای بیمارستان",
                    icon_custom_emoji_id="5866060208253441223",
                    style="success",
                    callback_data=HospitalCallback(
                        action="upgrade", teacher_id=0
                    ).pack(),
                )
            ]
        )
    for teacher in teachers:
        if HospitalService.ready_for_discharge(teacher):
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"✅ ترخیص {teacher.teacher.name}",
                        style="success",
                        callback_data=HospitalCallback(
                            action="discharge", teacher_id=teacher.id
                        ).pack(),
                    )
                ]
            )
            continue
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
        elif (
            teacher.status is TeacherStatus.INJURED
            or (
                teacher.status is TeacherStatus.ACTIVE
                and teacher.current_hp < teacher.teacher.max_hp
            )
        ) and can_recover:
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
                text="بازگشت",
                icon_custom_emoji_id="5235864325540815679",
                style="danger",
                callback_data=HospitalCallback(action="back", teacher_id=0).pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
