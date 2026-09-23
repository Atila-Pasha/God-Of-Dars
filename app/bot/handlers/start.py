import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message
from aiogram.types import User as TelegramUser
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.callbacks import ChannelCallback, FirstLoginCallback, HelpCallback
from app.bot.keyboards.help import help_keyboard
from app.bot.keyboards.main_menu import (
    MENU_SECTION_BY_LABEL,
    MENU_SECTION_KEYS,
    NON_SCHOOL_MENU_SECTION_LABELS,
    main_menu_keyboard,
)
from app.bot.keyboards.start import first_login_guide_keyboard, join_channel_keyboard
from app.bot.middlewares.subscription import refresh_channels, subscription_service
from app.bot.utils.telegram import safe_edit_text
from app.services.daily_quest_service import DailyQuestService
from app.services.referral_service import (
    ReferralCycle,
    ReferralError,
    ReferralService,
    SelfReferral,
)
from app.services.subscription_service import MembershipCheckError
from app.services.user_service import (
    UserInactiveError,
    UserInitializationError,
    UserService,
)

logger = logging.getLogger(__name__)

router = Router(name="start")
user_service = UserService()
referral_service = ReferralService()
daily_quest_service = DailyQuestService()


def join_message() -> str:
    channels = subscription_service.channels_label or "کانال اعلام‌شده در ربات"
    return f"برای استفاده از ربات، ابتدا باید عضو کانال {channels} شوید.\nپس از عضویت، روی «بررسی عضویت» بزنید."


MEMBERSHIP_ERROR_MESSAGE = (
    "در حال حاضر بررسی عضویت امکان‌پذیر نیست. لطفاً کمی بعد دوباره تلاش کنید."
)
USER_ERROR_MESSAGE = "در آماده‌سازی حساب شما مشکلی پیش آمد. لطفاً دوباره تلاش کنید."
BANNED_USER_MESSAGE = "حساب شما مسدود شده است. لطفاً با پشتیبانی تماس بگیرید."
MAIN_MENU_MESSAGE = (
    "🔥 به قلمرو «God of Dars» خوش اومدی، فرمانده!\n\n"
    "مدرسه‌ات رو بساز، دبیرها رو قدرتمند کن و برای فتح رتبه‌بندی آماده شو.\n"
    "از منوی پایین، اولین حرکتت رو انتخاب کن 👇"
)
RETURNING_USER_MESSAGE = (
    "👑 فرمانده برگشت!\n\nقلمرو منتظر دستور توئه؛ حرکت بعدی رو انتخاب کن 👇"
)
FIRST_LOGIN_GUIDE = (
    "🚀 مأموریت شروع | ساخت اولین تیم\n\n"
    "1️⃣ وارد «⛏ معدن منابع» شو تا معدن فعال و تولید طلا آغاز بشه.\n\n"
    "2️⃣ وقتی ۲۰۰ طلا جمع کردی، وارد «🍽 بوفه» شو و یکی از دبیرهای "
    "شروع، «براتی» یا «عمارلو»، رو بخر.\n\n"
    "3️⃣ دبیرت رو در «🏫 مدرسه من» فعال کن و بعد برای اولین نبرد برو!\n\n"
    "آماده‌ای فرمانده؟ دکمهٔ زیر رو بزن ⚡"
)
UNAVAILABLE_MESSAGE = "این بخش به‌زودی فعال می‌شود."
HELP_MENU_TEXT = (
    "📖 مرکز فرماندهی و راهنما\n\n"
    "راهنمای کدام بخش رو می‌خوای، فرمانده؟\n"
    "برای شروع، «راهنمای کامل بازی» رو بخون یا مستقیم سراغ بخش موردنظرت برو 👇"
)
HELP_TEXTS = {
    "overview": (
        "🧭 راهنمای کامل God of Dars\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "🎯 هدف بازی\n"
        "منابع جمع کن، دبیر بخر و ارتقا بده، دژت رو قوی کن، به حریف‌ها حمله کن "
        "و در جدول برترین‌ها بالا برو.\n\n"
        "🚀 شروع سریع\n"
        "1. «معدن منابع» رو باز کن تا تولید شروع بشه.\n"
        "2. منابع آماده رو مرتب جمع کن و معدن رو ارتقا بده.\n"
        "3. با ۲۰۰ طلا از «بوفه» یک دبیر شروع بخر.\n"
        "4. در «مدرسه من» دبیرها، دژ و بیمارستان رو مدیریت کن.\n"
        "5. از بخش «حمله» حریف انتخاب کن و با حداکثر تعداد مجاز دبیر حمله کن.\n\n"
        "🏫 مدرسه من\n"
        "دژ خط دفاعی توئه. استحکام و دفاعش رو ارتقا بده و آسیب‌ها رو تعمیر کن. "
        "دبیرهای مصدوم یا غیرفعال از بیمارستان درمان و دوباره فعال می‌شن.\n\n"
        "🍽 بوفه\n"
        "محل خرید دبیر و سپر و تبدیل منابعه. سطح هر آیتم، قیمت و ظرفیت دبیرها رو "
        "قبل از خرید بررسی کن. سپر در مدت فعال‌بودن جلوی حمله رو می‌گیره.\n\n"
        "📚 کتابخانه\n"
        "به سؤال روزانه پاسخ بده، مطالعهٔ زمان‌دار شروع کن و مشخصات همهٔ دبیرها رو "
        "ببین. سؤال‌های گروهی هم با Reply پاسخ داده می‌شن.\n\n"
        "⚔️ حمله\n"
        "حملهٔ رندوم یا با آیدی انتخاب کن، دبیرهای سالم و فعال رو بچین و پیش‌نمایش "
        "خسارت و غنیمت رو قبل از تأیید ببین. حمله بعد از شروع زمان می‌بره.\n\n"
        "🎯 فعالیت‌های روزانه\n"
        "مأموریت‌های روز رو کامل کن و بعد از تکمیل، جایزهٔ هر مورد رو دریافت کن.\n\n"
        "🧙 پروفایل و پیشرفت\n"
        "منابع، آمار جنگ، دانش و دعوت‌ها رو ببین. موز، شرط اصلی بالا بردن سطح "
        "فرمانده است؛ افزایش سطح ظرفیت‌ها و امکانات جدید رو باز می‌کنه.\n\n"
        "👥 دعوت و رتبه‌بندی\n"
        "با /referral لینک اختصاصی بگیر. از /leaderboard هم رتبهٔ فرمانده‌ها، "
        "دانش‌آموزها و مبارزها رو در بازه‌های روزانه، هفتگی و ماهانه ببین.\n\n"
        "💡 هرجا گیر کردی، از همین منو راهنمای همان بخش رو باز کن."
    ),
    "attack": (
        "⚔️ راهنمای میدان نبرد\n━━━━━━━━━━━━━━━━━━\n\n"
        "در خصوصی: حمله {نام‌کاربری هدف} {اسم دبیر}\n"
        "مثال: حمله @player فراهانی\n\n"
        "در گروه: روی پیام هدف Reply بزن و بنویس:\n"
        "حمله {اسم دبیر}\n\n"
        "برای حمله تصادفی به یکی از بازیکنان هم‌سطح یا نزدیک:\n"
        "حمله رندوم {اسم دبیر}\n"
        "مثال: حمله رندوم فراهانی"
    ),
    "school": (
        "🏫 راهنمای مدرسه و دبیرها\n━━━━━━━━━━━━━━━━━━\n\n"
        "از «مدرسه من» دبیرهای خودت، بیمارستان و دژ را مدیریت کن.\n"
        "برای خرید دبیر از «بوفه» وارد بخش «خرید دبیر» شو.\n"
        "اگر ظرفیت دبیرها پر باشد، یک دبیر را بفروش یا سطح فرمانده را افزایش بده."
    ),
    "buffet": (
        "🍽 راهنمای بوفه و خرید\n━━━━━━━━━━━━━━━━━━\n\n"
        "در بوفه می‌توانی دبیر و سپر بخری یا منابع را تبدیل کنی.\n"
        "برای خرید دبیر بنویس:\n"
        "خرید {اسم دبیر}\n\n"
        "برای خرید سپر بنویس:\n"
        "خرید سپر {اسم سپر}"
    ),
    "library": (
        "📚 راهنمای کتابخانه\n━━━━━━━━━━━━━━━━━━\n\n"
        "از بخش «کتابخانه» سؤال روزانه، مطالعه و فهرست دبیرها رو ببین.\n"
        "برای سؤال روزانه فقط یک فرصت پاسخ داری. مطالعهٔ زمان‌دار رو شروع کن و بعد "
        "از پایان زمان پاداشت رو بگیر. در گروه، پاسخ سؤال گروهی رو با Reply بفرست."
    ),
    "profile": (
        "🧙 راهنمای پروفایل\n━━━━━━━━━━━━━━━━━━\n\n"
        "/profile — منوی پروفایل\n"
        "/stat — اطلاعات پروفایل\n"
        "/war — آمار جنگ\n"
        "/assets — دارایی‌ها\n"
        "/knowledge — دانش و دعوت‌ها"
    ),
    "mine": (
        "⛏ راهنمای معدن منابع\n━━━━━━━━━━━━━━━━━━\n\n"
        "اولین بار با بازکردن معدن، تولید منابع فعال می‌شه. طلا و الماس آماده رو "
        "مرتب برداشت کن. ارتقای معدن سرعت تولید رو بیشتر می‌کنه و به سطح فرمانده و "
        "الماس نیاز داره."
    ),
    "referral": (
        "👥 راهنمای دعوت دوستان\n━━━━━━━━━━━━━━━━━━\n\n"
        "با /referral لینک اختصاصی خودت رو بگیر و برای دوست‌هات بفرست. هر دعوت "
        "موفق در بخش دانش پروفایل ثبت می‌شه."
    ),
}


async def _membership_status(
    user_id: int,
    bot: Bot | None,
    session: AsyncSession | None = None,
    *,
    force_refresh: bool = False,
) -> bool | None:
    if bot is None:
        logger.error("Telegram bot context is missing for user %s", user_id)
        return None
    try:
        # /start bypasses the subscription middleware by design, so refresh the
        # channel list only for real database sessions. This keeps the hot path
        # cached while preserving lightweight unit-test doubles.
        if isinstance(session, AsyncSession):
            await refresh_channels(session, force=force_refresh)
        member = await subscription_service.is_member(
            bot, user_id, force_refresh=force_refresh
        )
        return member
    except (MembershipCheckError, SQLAlchemyError):
        logger.exception("Could not refresh membership state for user %s", user_id)
        return None


async def _initialize_and_show_menu(
    *,
    target: Message | CallbackQuery,
    telegram_user: TelegramUser,
    session: AsyncSession,
    referral_payload: str | None = None,
) -> bool:
    try:
        user = await user_service.get_or_create_from_telegram(session, telegram_user)
    except UserInitializationError:
        logger.exception("Could not initialize user %s", telegram_user.id)
        return False

    referral_notice = None
    # Referral attribution is an acquisition reward, not a transferable bonus
    # for established accounts. Accept it only during the account's first
    # successful initialization.
    if referral_payload and getattr(user, "_was_created", False) is True:
        referrer_id = referral_service.parse_payload(referral_payload)
        if referrer_id is not None:
            try:
                await referral_service.apply(
                    session,
                    referred_user_id=user.id,
                    referrer_id=referrer_id,
                )
            except SelfReferral:
                referral_notice = "می‌خوای خودتو دعوت کنی رفیق؟ 😁"
            except ReferralCycle:
                referral_notice = (
                    "این لینک دعوت قابل استفاده نیست؛ دعوت متقابل مجاز نیست."
                )
            except ReferralError:
                # Referral attribution must never prevent a valid user from
                # entering the bot. Invalid or already-used links are ignored.
                logger.info(
                    "Referral payload %s could not be applied to user %s",
                    referral_payload,
                    user.id,
                )

    if user.is_active is False:
        raise UserInactiveError
    if isinstance(session, AsyncSession):
        try:
            async with session.begin_nested():
                await daily_quest_service.record_event(
                    session,
                    user_id=user.id,
                    event_type="DAILY_LOGIN",
                    event_id=str(user.id),
                )
        except SQLAlchemyError:
            # Quest tracking must not prevent a valid user from entering the
            # bot when quest storage is unavailable or being migrated.
            logger.exception("Could not record daily login for user %s", user.id)

    is_first_login = getattr(user, "_was_created", False) is True
    greeting = MAIN_MENU_MESSAGE if is_first_login else RETURNING_USER_MESSAGE
    if isinstance(target, CallbackQuery) or hasattr(target, "message"):
        if target.message is None:
            return False
        try:
            await target.message.answer(
                greeting,
                reply_markup=main_menu_keyboard(),
            )
        except TelegramAPIError:
            logger.exception("Could not send main menu after callback")
            return False
    else:
        try:
            await target.answer(greeting, reply_markup=main_menu_keyboard())
        except TelegramAPIError:
            logger.exception("Could not send main menu message")
            return False
    if is_first_login:
        if isinstance(target, CallbackQuery) or hasattr(target, "message"):
            if target.message is not None:
                await target.message.answer(
                    FIRST_LOGIN_GUIDE, reply_markup=first_login_guide_keyboard()
                )
        else:
            await target.answer(
                FIRST_LOGIN_GUIDE, reply_markup=first_login_guide_keyboard()
            )
    if isinstance(target, CallbackQuery) or hasattr(target, "message"):
        if target.message is not None:
            await target.message.answer(
                HELP_MENU_TEXT,
                reply_markup=help_keyboard(),
            )
    else:
        await target.answer(HELP_MENU_TEXT, reply_markup=help_keyboard())
    if referral_notice:
        if isinstance(target, CallbackQuery):
            if target.message is not None:
                await target.message.answer(referral_notice)
        else:
            await target.answer(referral_notice)
    return True


@router.message(CommandStart())
async def start_handler(
    message: Message,
    session: AsyncSession,
    command: CommandObject | None = None,
) -> None:
    if message.from_user is None:
        return

    is_member = await _membership_status(
        message.from_user.id, message.bot, session, force_refresh=True
    )
    if is_member is None:
        await message.answer(
            MEMBERSHIP_ERROR_MESSAGE,
            reply_markup=join_channel_keyboard(subscription_service),
        )
        return
    if not is_member:
        await message.answer(
            join_message(),
            reply_markup=join_channel_keyboard(subscription_service),
        )
        return

    try:
        initialized = await _initialize_and_show_menu(
            target=message,
            telegram_user=message.from_user,
            session=session,
            referral_payload=command.args if command else None,
        )
    except UserInactiveError:
        await message.answer(BANNED_USER_MESSAGE)
        return

    if not initialized:
        await message.answer(USER_ERROR_MESSAGE)


@router.message(Command("help"))
async def help_handler(message: Message) -> None:
    await message.answer(HELP_MENU_TEXT, reply_markup=help_keyboard())


@router.callback_query(FirstLoginCallback.filter())
async def first_login_confirmation_handler(
    callback: CallbackQuery, callback_data: FirstLoginCallback
) -> None:
    if callback_data.action != "confirm":
        await callback.answer()
        return
    if callback.message is not None:
        await safe_edit_text(
            callback.message,
            "✅ مأموریت شروع فعال شد!\n\n"
            "اولین مقصد: «⛏ معدن منابع» — برو که قلمرو منتظرته، فرمانده 🔥",
            reply_markup=None,
        )
    await callback.answer("آماده‌ایم؛ بزن بریم! 🚀")


@router.callback_query(HelpCallback.filter())
async def help_callback_handler(
    callback: CallbackQuery,
    callback_data: HelpCallback,
) -> None:
    if callback.message is None:
        await callback.answer()
        return
    text = HELP_TEXTS[callback_data.section]
    await safe_edit_text(
        callback.message,
        text,
        reply_markup=help_keyboard(),
    )
    await callback.answer()


@router.message(F.text.regexp(r"^/\S+"))
async def unknown_command_handler(message: Message) -> None:
    await message.answer(
        "این فرمان شناخته نشد.\n\nبرای دیدن فرمان‌های قابل استفاده، /help را بزنید."
    )


@router.callback_query(ChannelCallback.filter(F.action == "check"))
async def check_membership_handler(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return

    is_member = await _membership_status(
        callback.from_user.id, callback.bot, session, force_refresh=True
    )
    if is_member is None:
        await callback.answer(MEMBERSHIP_ERROR_MESSAGE, show_alert=True)
        return
    if not is_member:
        await callback.answer("هنوز عضویت شما تأیید نشده است.", show_alert=True)
        try:
            await safe_edit_text(
                callback.message,
                join_message(),
                reply_markup=join_channel_keyboard(subscription_service),
            )
        except TelegramAPIError:
            logger.exception("Could not restore channel join prompt")
        return

    try:
        initialized = await _initialize_and_show_menu(
            target=callback,
            telegram_user=callback.from_user,
            session=session,
        )
    except UserInactiveError:
        await callback.answer(BANNED_USER_MESSAGE, show_alert=True)
        return

    if not initialized:
        await callback.answer(USER_ERROR_MESSAGE, show_alert=True)
        return
    await callback.answer("عضویت تأیید شد.")


@router.message(F.text == "بازگشت به منو اصلی")
async def main_menu_back_handler(message: Message) -> None:
    await message.answer(
        "به منوی اصلی برگشتید.",
        reply_markup=main_menu_keyboard(),
    )


@router.message(F.text.in_(NON_SCHOOL_MENU_SECTION_LABELS))
async def main_menu_handler(
    message: Message,
) -> None:
    if message.from_user is None or message.text is None:
        return

    section = MENU_SECTION_BY_LABEL.get(message.text)
    if section not in MENU_SECTION_KEYS:
        return

    is_member = await _membership_status(message.from_user.id, message.bot)
    if is_member is None:
        await message.answer(MEMBERSHIP_ERROR_MESSAGE)
        return
    if not is_member:
        await message.answer(
            join_message(),
            reply_markup=join_channel_keyboard(subscription_service),
        )
        return

    try:
        await message.answer(
            UNAVAILABLE_MESSAGE,
            reply_markup=main_menu_keyboard(),
        )
    except TelegramAPIError:
        logger.exception("Could not respond to main menu selection")
