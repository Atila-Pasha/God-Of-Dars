"""Short commander replies and the once-per-hour slogan reward."""

from random import choice

from aiogram import F, Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.banners import MARKDOWN_V2, bold, emoji, escape
from app.services.school_errors import SchoolUserNotFound
from app.services.slogan_service import SloganService
from app.services.user_service import UserInactiveError

router = Router(name="quick_replies")
slogan_service = SloganService()
SLOGAN = "من خدای درسم"

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
)


def _remaining_text(seconds: int) -> str:
    minutes, seconds = divmod(seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"


@router.message(F.text == "گاد")
async def god_reply_handler(message: Message) -> None:
    icon_id, fallback, response = choice(GOD_REPLIES)
    await message.answer(
        f"{emoji(icon_id, fallback)} {escape(response)}", parse_mode=MARKDOWN_V2
    )


@router.message(F.text == SLOGAN)
async def slogan_handler(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    try:
        claim = await slogan_service.claim(session, message.from_user.id)
    except SchoolUserNotFound:
        await message.answer("برای دریافت پاداش شعار، اول ربات را با /start فعال کن.")
        return
    except UserInactiveError:
        await message.answer("حساب شما مسدود شده است.")
        return

    if claim.awarded:
        text = (
            f"{emoji('5834791394639614640', '👑')} {bold('شعارت دریافت شد، فرمانده!')}\n\n"
            f"{emoji('5902520589356113908', '🍌')} {bold(f'{claim.reward_banana} موز')} {escape('به خزانه‌ات اضافه شد.')}\n"
            f"{emoji('6039496463749223185', '✨')} {escape('یک ساعت دیگه دوباره شعارت رو بگو.')}"
        )
    else:
        text = (
            f"{emoji('5825961702088254236', '🎯')} {bold('شعارت برای این ساعت ثبت شده.')}\n\n"
            f"{emoji('5388834817058035756', '🔥')} {escape('زمان تا پاداش بعدی:')} "
            f"{bold(_remaining_text(claim.retry_after_seconds))}"
        )
    await message.answer(text, parse_mode=MARKDOWN_V2)
