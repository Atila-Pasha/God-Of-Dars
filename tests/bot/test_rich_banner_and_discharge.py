from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from aiogram.methods import SendMessage

from app.bot.banners import rich_banner
from app.bot.callbacks import HospitalCallback
from app.bot.custom_emojis import _decorate_method
from app.bot.keyboards.school import hospital_keyboard
from app.core.enums import TeacherStatus
from app.services.recovery_service import HospitalService


def test_plain_section_banner_uses_rich_text_without_divider() -> None:
    method = SendMessage(
        chat_id=1,
        text="🏥 بیمارستان مدرسه\n━━━━━━━━━━━━━━━━━━\n\n✅ دبیر آماده است.",
    )

    _decorate_method(method, use_rich_banners=True)

    assert method.parse_mode == "MarkdownV2"
    assert "━━━━━━━━" not in method.text
    assert "*بیمارستان مدرسه*" in method.text
    assert "tg://emoji?id=" in method.text
    assert "\n\n" in method.text
    assert "ــــــــ" not in rich_banner(
        "🪙 غنیمت\nـــــــــــــــــــــــــــــــــــ\nطلا: 3"
    )


def test_ready_teacher_has_discharge_button_and_waiting_teacher_does_not() -> None:
    recovery = SimpleNamespace(
        recovery_end_at=datetime.now(UTC) - timedelta(seconds=1),
        completed_at=None,
    )
    teacher = SimpleNamespace(
        id=12,
        teacher=SimpleNamespace(name="قضاتی"),
        status=TeacherStatus.RECOVERING,
        recoveries=[recovery],
    )

    assert HospitalService.ready_for_discharge(teacher)
    markup = hospital_keyboard(
        [teacher], can_activate=True, can_recover=True, instant_recovery_cost=5
    )
    actions = [
        HospitalCallback.unpack(button.callback_data).action
        for row in markup.inline_keyboard
        for button in row
    ]
    assert actions == ["discharge", "back"]

    recovery.recovery_end_at = datetime.now(UTC) + timedelta(minutes=1)
    assert not HospitalService.ready_for_discharge(teacher)
