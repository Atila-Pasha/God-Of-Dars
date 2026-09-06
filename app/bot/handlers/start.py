import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message
from aiogram.types import User as TelegramUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.callbacks import ChannelCallback, HelpCallback
from app.bot.keyboards.help import help_keyboard
from app.bot.keyboards.main_menu import (
    MENU_SECTION_BY_LABEL,
    MENU_SECTION_KEYS,
    NON_SCHOOL_MENU_SECTION_LABELS,
    main_menu_keyboard,
)
from app.bot.keyboards.start import join_channel_keyboard
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
MAIN_MENU_MESSAGE = "🏫 به بازی خوش آمدید! یکی از بخش‌های زیر را انتخاب کنید:"
RETURNING_USER_MESSAGE = "سلام دوباره فرمانده! 👑"
UNAVAILABLE_MESSAGE = "این بخش به‌زودی فعال می‌شود."
HELP_MENU_TEXT = "📖 راهنمای کدام بخش را می‌خواهی فرمانده؟"
HELP_TEXTS = {
    "attack": (
        "⚔️ راهنمای حمله\n\n"
        "در خصوصی: حمله {نام‌کاربری هدف} {اسم دبیر}\n"
        "مثال: حمله @player فراهانی\n\n"
        "در گروه: روی پیام هدف Reply بزن و بنویس:\n"
        "حمله {اسم دبیر}"
    ),
    "school": (
        "🏫 راهنمای مدرسه و دبیرها\n\n"
        "از «مدرسه من» دبیرهای خودت، بیمارستان و دژ را مدیریت کن.\n"
        "برای خرید دبیر از «بوفه» وارد بخش «خرید دبیر» شو.\n"
        "اگر ظرفیت دبیرها پر باشد، یک دبیر را بفروش یا سطح فرمانده را افزایش بده."
    ),
    "buffet": (
        "🍽 راهنمای بوفه و خرید\n\n"
        "در بوفه می‌توانی دبیر و سپر بخری یا منابع را تبدیل کنی.\n"
        "برای خرید دبیر بنویس:\n"
        "خرید {اسم دبیر}\n\n"
        "برای خرید سپر بنویس:\n"
        "خرید سپر {اسم سپر}"
    ),
    "library": (
        "📚 راهنمای کتابخانه\n\n"
        "از بخش «کتابخانه» سؤال روزانه، سؤال گروهی، مطالعه و فهرست دبیرها را ببین."
    ),
    "profile": (
        "🧙 راهنمای پروفایل\n\n"
        "/profile — منوی پروفایل\n"
        "/stat — اطلاعات پروفایل\n"
        "/war — آمار جنگ\n"
        "/assets — دارایی‌ها\n"
        "/knowledge — دانش و دعوت‌ها"
    ),
    "mine": (
        "⛏ راهنمای معدن منابع\n\n"
        "از معدن منابع، طلا و الماس تولیدشده را برداشت کن و معدن را ارتقا بده."
    ),
    "referral": (
        "👥 راهنمای دعوت دوستان\n\n"
        "با /referral لینک دعوت اختصاصی خودت را بگیر و دوستانت را دعوت کن."
    ),
}


async def _membership_status(
    user_id: int,
    bot: Bot,
    session: AsyncSession | None = None,
    *,
    force_refresh: bool = False,
) -> bool | None:
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
    except MembershipCheckError:
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
    if referral_payload:
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
        await daily_quest_service.record_event(
            session,
            user_id=user.id,
            event_type="DAILY_LOGIN",
            event_id=str(user.id),
        )

    greeting = (
        MAIN_MENU_MESSAGE
        if getattr(user, "_was_created", False) is True
        else RETURNING_USER_MESSAGE
    )
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
