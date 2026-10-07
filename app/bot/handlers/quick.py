"""Quick commander replies and nine phrases sharing one hourly reward."""

from random import choice

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.banners import BANANA, MARKDOWN_V2, bold, emoji, escape
from app.bot.callbacks import SloganCallback
from app.services.school_errors import SchoolUserNotFound
from app.services.slogan_service import SloganService
from app.services.user_service import UserInactiveError

router = Router(name="quick_replies")
slogan_service = SloganService()
SLOGANS = (
    "من خدای درسم",
    "امروز درس رو فتح میکنم",
    "هر روز از دیروز بهترم",
    "با دانش قلعه میسازم",
    "تا آخر مسیر میجنگم",
    "کیری قویم",
    "من خدام",
    "میجنگم",
    "یا خدا",
)

# Each response has its own premium emoji. Telegram displays the fallback icon
# on clients that cannot render custom emoji entities.
GOD_REPLIES: tuple[tuple[str, str, str], ...] = (
    ("6039496463749223185", "✨", "سلام فرمانده! امروز کدوم درس رو فتح می‌کنی؟"),
    (
        "5388834817058035756",
        "🔥",
        "چخبر فرمانده؟ درس خوندی یا هنوز لشکر دبیرها منتظرته؟",
    ),
    ("5825961702088254236", "🎯", "یه هدف کوچیک برای امروز انتخاب کن و بزن وسط خال!"),
    ("5834681271678144844", "📚", "هر سؤال درست یه قدم تا فرمانده شدن فاصله‌ست."),
    ("5834791394639614640", "👑", "گاد حاضر شد! گزارش پیشرفت امروزت چیه؟"),
    ("6039496463749223185", "✨", "اگه دیروز سخت بود، امروز یه صفحه ازش جلو بزن."),
    ("5388834817058035756", "🔥", "دبیرها آماده‌ان؛ فرمان حمله یا فرمان مطالعه؟"),
    ("5825961702088254236", "🎯", "امروز رکورد خودت رو نشونه بگیر، فرمانده."),
    ("5834681271678144844", "📚", "کتابخونه منتظرته؛ یه سؤال حل کن و برگرد."),
    ("5834791394639614640", "👑", "فرمانده، قلعه‌ات رو سر زدی یا هنوز تو راهی؟"),
    ("6039496463749223185", "✨", "یه دقیقه تمرکز هم بهتر از صفر دقیقه‌ست؛ شروع کن!"),
    ("5388834817058035756", "🔥", "پشت هر پیروزی، چند بار تلاش دوباره خوابیده."),
    ("5825961702088254236", "🎯", "هدفت برای یک ساعت آینده چیه؟ همون رو بزن!"),
    ("5834681271678144844", "📚", "جزوه رو باز کن؛ قلمرو دانش خودش فتح نمی‌شه."),
    (
        "5834791394639614640",
        "👑",
        "شعار «من خدای درسم» رو بگو و پاداش ساعتی‌ات رو بگیر.",
    ),
    ("6039496463749223185", "✨", "امروز فقط با خودِ دیروزت رقابت کن."),
    ("5388834817058035756", "🔥", "وقتشه اون مبحث سخت رو به زانو دربیاری."),
    ("5825961702088254236", "🎯", "سه سؤال حل کن؛ بعد برای سه سؤال بعدی تصمیم بگیر."),
    ("5834681271678144844", "📚", "امروز یه نکتهٔ تازه یاد گرفتی؟ برام تعریف کن!"),
    ("5834791394639614640", "👑", "فرماندهٔ بزرگ از یه شروع کوچیک ساخته می‌شه."),
    ("6039496463749223185", "✨", "هر صفحه‌ای که می‌خونی، قلمروت رو بزرگ‌تر می‌کنه."),
    ("5388834817058035756", "🔥", "تایمر رو روشن کن؛ یه دور تمرکز حسابی بزن."),
    ("5825961702088254236", "🎯", "هدف امروزت رو بنویس تا از دستت در نره."),
    ("5834681271678144844", "📚", "اگه مبحثی گنگه، از ساده‌ترین مثالش شروع کن."),
    ("5834791394639614640", "👑", "دژ دانش با تمرین‌های کوچیک ساخته می‌شه."),
    ("6039496463749223185", "✨", "یه استراحت کوتاه بکن و با انرژی برگرد."),
    ("5388834817058035756", "🔥", "امروز یه رکورد مطالعهٔ تازه ثبت می‌کنی؟"),
    ("5825961702088254236", "🎯", "اول سخت‌ترین کار امروز رو مشخص کن."),
    ("5834681271678144844", "📚", "یه سؤال اشتباه هم می‌تونه بهترین درس امروز باشه."),
    ("5834791394639614640", "👑", "فرمانده، برنامهٔ امروزی‌ات رو چیدی؟"),
    ("6039496463749223185", "✨", "پیشرفت آرام هم پیشرفته؛ ادامه بده."),
    ("5388834817058035756", "🔥", "حواست رو جمع کن؛ وقت فتح فصل بعدیه."),
    ("5825961702088254236", "🎯", "یه هدف دقیق بهتر از ده تا تصمیم مبهمه."),
    ("5834681271678144844", "📚", "مرور کوتاه امروز، فراموشی فردا رو کم می‌کنه."),
    ("5834791394639614640", "👑", "هر بار برگشتی سر درس، یه پیروزی ثبت کردی."),
    ("6039496463749223185", "✨", "بگو کدوم درس رو شروع می‌کنی تا همراهت باشم."),
    ("5388834817058035756", "🔥", "سؤال سخت دیدی؟ تکه‌تکه‌اش کن و جلو برو."),
    ("5825961702088254236", "🎯", "پنج دقیقه اول رو شروع کن؛ ادامه‌اش راحت‌تر می‌شه."),
    ("5834681271678144844", "📚", "یه مرور سریع از نکته‌های دیروز بزن."),
    ("5834791394639614640", "👑", "فرمانده، برای تلاش امروزت به خودت اعتبار بده."),
)

SLOGAN_HEADERS = (
    "جوووون! همینطوره فرمانده!",
    "این شد شعار یه فرماندهٔ واقعی!",
    "آفرین! صدای فرمانده تا قلعه رسید!",
    "دمت گرم! امروز هم پرقدرت شروع شد!",
    "همین انرژی رو نگه دار، فرمانده!",
    "عالیه! قلمرو دانش منتظرته!",
)
SLOGAN_REWARDS = (
    "هدیه برای شما!",
    "به خزانه‌ات اضافه شد!",
    "پاداش این انرژی بود!",
    "جایزهٔ شعار امروزت شد!",
    "تقدیم به فرماندهٔ پرتلاش!",
    "برای فتح درس‌های امروزت!",
)
_god_rotation: dict[int, tuple[object, tuple]] = {}
_header_rotation: dict[int, tuple[object, tuple]] = {}
_reward_rotation: dict[int, tuple[object, tuple]] = {}


def _fresh_choice(options: tuple, user_id: int, history: dict):
    previous, remaining = history.get(user_id, (None, options))
    if not remaining:
        remaining = tuple(item for item in options if item != previous)
    selected = choice(remaining or options)
    if len(history) >= 4096:
        history.clear()
    history[user_id] = (selected, tuple(item for item in remaining if item != selected))
    return selected


def _remaining_text(seconds: int) -> str:
    minutes, seconds = divmod(seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"


def _timer_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="زمان تا شعار بعدی",
                    icon_custom_emoji_id="6039539366177541657",
                    callback_data=SloganCallback(user_id=user_id).pack(),
                )
            ]
        ]
    )


@router.message(F.text == "گاد")
async def god_reply_handler(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else 0
    icon_id, fallback, response = _fresh_choice(GOD_REPLIES, user_id, _god_rotation)
    await message.answer(
        f"{emoji(icon_id, fallback)} {escape(response)}", parse_mode=MARKDOWN_V2
    )


@router.message(F.text.in_(SLOGANS))
async def slogan_handler(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    user_id = message.from_user.id
    try:
        claim = await slogan_service.claim(session, user_id)
    except SchoolUserNotFound:
        await message.answer("برای دریافت پاداش شعار، اول ربات را با /start فعال کن.")
        return
    except UserInactiveError:
        await message.answer("حساب شما مسدود شده است.")
        return

    if claim.awarded:
        header = _fresh_choice(SLOGAN_HEADERS, user_id, _header_rotation)
        reward_line = _fresh_choice(SLOGAN_REWARDS, user_id, _reward_rotation)
        text = (
            f"{escape(header)} {emoji('5915888842568638290', '🛡️')}\n\n"
            f"{bold(f'{claim.reward_banana} موز')} {BANANA} {escape(reward_line)}\n\n"
            f"> {escape('● موز فعلی:')} {bold(f'{claim.current_banana:,}')}\n\n"
            f"{escape('“Keep going, commander.”')} {emoji('5825647731388981287', '🌟')}"
        )
    else:
        text = (
            f"{emoji('5825961702088254236', '🎯')} {bold('شعارت برای این ساعت ثبت شده.')}\n\n"
            f"{emoji('5388834817058035756', '🔥')} {escape('زمان تا پاداش بعدی:')} "
            f"{bold(_remaining_text(claim.retry_after_seconds))}"
        )
    await message.answer(
        text, parse_mode=MARKDOWN_V2, reply_markup=_timer_keyboard(user_id)
    )


@router.callback_query(SloganCallback.filter())
async def slogan_timer_handler(
    callback: CallbackQuery, callback_data: SloganCallback, session: AsyncSession
) -> None:
    if callback.from_user is None or callback.from_user.id != callback_data.user_id:
        await callback.answer("این دکمه برای فرماندهٔ صاحب شعار است.", show_alert=True)
        return
    try:
        remaining = await slogan_service.remaining_seconds(
            session, callback_data.user_id
        )
    except SchoolUserNotFound:
        await callback.answer("حساب فرمانده پیدا نشد.", show_alert=True)
        return
    if remaining:
        await callback.answer(
            f"زمان باقی‌مانده تا شعار بعدی: {_remaining_text(remaining)}",
            show_alert=True,
        )
    else:
        await callback.answer(
            "وقت شعار بعدی رسیده! یکی از نه شعار رو بگو.", show_alert=True
        )
