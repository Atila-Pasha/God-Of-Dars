import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message
from aiogram.types import User as TelegramUser
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.banners import MARKDOWN_V2, rich_banner
from app.bot.callbacks import ChannelCallback, FirstLoginCallback, HelpCallback
from app.bot.handlers.quick import SLOGANS
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
from app.core.game_logic import game_config
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
    return rich_banner(
        f"📢 یک قدم تا شروع بازی\n\n"
        f"برای ورود، عضو کانال {channels} شو. بعد از عضویت، دکمهٔ «بررسی عضویت» رو بزن تا حسابت آماده بشه."
    )


MEMBERSHIP_ERROR_MESSAGE = (
    "در حال حاضر بررسی عضویت امکان‌پذیر نیست. لطفاً کمی بعد دوباره تلاش کنید."
)
USER_ERROR_MESSAGE = "در آماده‌سازی حساب شما مشکلی پیش آمد. لطفاً دوباره تلاش کنید."
BANNED_USER_MESSAGE = "حساب شما مسدود شده است. لطفاً با پشتیبانی تماس بگیرید."
MAIN_MENU_MESSAGE = rich_banner(
    "🔥 به God of Dars خوش اومدی، فرمانده!\n\n"
    "🎁 ۱۰۰ سکهٔ شروع توی حسابت نشست. حالا وقتشه مدرسه‌ات رو بسازی و اولین تیم رو جمع کنی.\n\n"
    "از منوی پایین «معدن منابع» رو باز کن؛ قدم‌به‌قدم کنارت هستم. 👇"
)
RETURNING_USER_MESSAGE = rich_banner(
    "👑 خوش برگشتی، فرمانده!\n\n"
    "مدرسه و منابع منتظرت هستن. از منوی پایین ببین امروز از کجا می‌خوای شروع کنی. 👇"
)
FIRST_LOGIN_GUIDE = rich_banner(
    "🎯 مأموریت اول: اولین تیم تو\n\n"
    "⛏️ «معدن منابع» رو باز کن. تولید طلا شروع می‌شه و ۱۰۰ سکهٔ دیگه هدیه می‌گیری.\n\n"
    "🍽 «بوفه» رو باز کن. با ۲۰۰ سکهٔ مجموع دو هدیه، یکی از دبیرهای شروع، «براتی» یا «عمارلو» رو بخر.\n\n"
    "🏫 در «مدرسه من» دبیرت رو ببین و وقتی آماده بودی، از بخش «حمله» اولین نبردت رو شروع کن.\n\n"
    "هر وقت خواستی، راهنمای هر بخش همین پایین در دسترسه. آماده‌ای؟"
)
UNAVAILABLE_MESSAGE = "این بخش به‌زودی فعال می‌شود."
HELP_MENU_TEXT = rich_banner(
    "📖 راهنمای بازی\n\n"
    "راهنمای کدام بخش رو می‌خوای؟ اگر تازه شروع کردی، «راهنمای کامل بازی» مسیر رو از اولین سکه تا اولین نبرد نشونت می‌ده. 👇"
)
HELP_TEXTS = {
    "overview": (
        "🧭 نقشهٔ راه فرمانده\n\n"
        "🎯 قراره چی کار کنی؟\n"
        "منابع جمع کن، دبیرها رو به تیمت بیار، مدرسه‌ات رو قوی کن و با نبرد و درس‌خوندن در رتبه‌بندی بالا برو.\n\n"
        "⛏️ شروع از معدن منابع\n"
        "معدن رو یک‌بار باز کن تا تولید فعال بشه و هدیهٔ دوم ۱۰۰ سکه‌ای رو بگیری. بعد هر وقت محموله آماده بود، طلا و الماس رو برداشت کن.\n\n"
        "🍽 بوفه و اولین دبیر\n"
        "با ۲۰۰ سکهٔ شروع، یک دبیر تازه‌کار بخر. همین‌جا می‌تونی سپر بگیری یا طلا و الماس رو به هم تبدیل کنی.\n\n"
        "🏫 مدرسه من\n"
        "دبیرها، دژ و بیمارستانت اینجاست. دژ آسیب‌دیده رو تعمیر کن؛ دبیر مصدوم هم بعد از درمان باید ترخیص بشه تا دوباره بجنگه.\n\n"
        "⚔️ حمله\n"
        "حریف و دبیرهای آماده رو انتخاب کن. پیش‌نمایش نبرد رو بخون و بعد حمله رو تأیید کن؛ نتیجه پس از پایان زمان حمله می‌رسه.\n\n"
        "📚 کتابخانه و فعالیت‌های روزانه\n"
        "سؤال روزانه رو جواب بده، مطالعه رو شروع کن و بعد از پایان زمان پاداشش رو بگیر. مأموریت‌های روز رو هم کامل کن و جایزه‌شون رو جداگانه دریافت کن.\n\n"
        "🧙 پروفایل، دعوت و رتبه‌بندی\n"
        "در پروفایل دارایی، جنگ و دانش خودت رو ببین. موز برای ارتقای سطح فرمانده لازمه. با /referral لینک دعوت بگیر؛ هر دعوت موفق "
        f"{game_config.referral_reward_amount} الماس به معرف می‌دهد. با /leaderboard هم رتبه‌ها رو ببین.\n\n"
        "💡 برای جزئیات بیشتر، دکمهٔ راهنمای همون بخش رو بزن."
    ),
    "attack": (
        "⚔️ راهنمای حمله\n\n"
        "🎯 انتخاب هدف\n"
        "از دکمهٔ «حمله» حریف رو پیدا کن، یا در گفت‌وگوی خصوصی بنویس: حمله @player فراهانی\n\n"
        "👥 نبرد در گروه\n"
        "روی پیام حریف Reply بزن و «حمله» یا «حمله فراهانی» بنویس. برای حریف تصادفی هم می‌تونی «حمله رندوم فراهانی» رو بفرستی.\n\n"
        "⏳ قبل از تأیید\n"
        "فقط دبیر سالم و آماده می‌تونه بجنگه. پیش‌نمایش خسارت و غنیمت رو ببین؛ نتیجهٔ نبرد بعد از پایان زمان حمله اعلام می‌شه."
    ),
    "school": (
        "🏫 راهنمای مدرسه من\n\n"
        "👨‍🏫 دبیرها\n"
        "دبیرهایی که از بوفه می‌خری اینجا دیده می‌شن. می‌تونی ارتقاشون بدی یا در صورت نیاز بفروشی. ظرفیت تیم با سطح فرمانده بیشتر می‌شه.\n\n"
        "🏰 دژ\n"
        "دژ از منابعت دفاع می‌کنه. بعد از نبرد آسیبش رو تعمیر کن و برای دفاع قوی‌تر ارتقاش بده.\n\n"
        "🏥 بیمارستان\n"
        "دبیر مصدوم رو بستری کن. زمان باقی‌ماندهٔ درمان رو همین‌جا می‌بینی؛ وقتی تمام شد، «ترخیص» رو بزن تا دوباره آمادهٔ نبرد بشه."
    ),
    "buffet": (
        "🍽 راهنمای بوفه\n\n"
        "👨‍🏫 خرید دبیر\n"
        "فهرست رو باز کن، سطح بازشدن و قیمت رو ببین و بعد خرید رو تأیید کن. در گروه هم می‌تونی بنویسی: خرید فراهانی\n\n"
        "🛡️ خرید سپر\n"
        "سپر برای مدت مشخص جلوی حمله به دژت رو می‌گیره. زمان و محدودیت روزانهٔ هر سپر رو پیش از خرید بخون. در گروه: خرید سپر زنگ تفریح\n\n"
        "🔄 تبدیل منابع\n"
        "در صرافی طلا رو به الماس یا الماس رو به طلا تبدیل کن. مقدار رو طبق نرخ همان صفحه وارد کن و موجودی جدیدت رو بعد از تأیید ببین."
    ),
    "library": (
        "📚 راهنمای کتابخانه\n\n"
        "❓ سؤال روزانه\n"
        "سؤال رو با دقت بخون؛ برای هر سؤال فقط یک بار می‌تونی پاسخ بدی.\n\n"
        "📖 مطالعه\n"
        "یک نوبت مطالعه شروع کن. بعد از پایان زمان، دوباره به کتابخانه سر بزن و پاداشت رو بگیر.\n\n"
        "👨‍🏫 دانشنامه\n"
        "پروندهٔ دبیرها و سپرها رو پیش از خرید اینجا ببین. برای سؤال گروهی هم روی پیام سؤال Reply بزن."
    ),
    "profile": (
        "🧙 راهنمای پروفایل\n\n"
        "از دکمهٔ «پروفایل» شناسنامه، دارایی، کارنامهٔ نبرد و آمار دانش و دعوت‌ها رو باز کن. موزی که به دست میاری برای ارتقای سطح فرمانده مصرف می‌شه.\n\n"
        "فرمان‌های مستقیم: /stat برای شناسنامه، /war برای جنگ، /assets برای دارایی و /knowledge برای دانش. /profile هم منوی پروفایل رو باز می‌کنه."
    ),
    "mine": (
        "⛏️ راهنمای معدن منابع\n\n"
        "اولین بازدیدت تولید رو فعال می‌کنه و هدیهٔ شروع معدن رو می‌ده. بعد از اون، هر وقت محموله آماده بود طلا و الماس رو برداشت کن.\n\n"
        "📈 ارتقای معدن\n"
        "ارتقا تولید رو بیشتر می‌کنه؛ برای هر سطح، مقدار الماس و سطح فرماندهٔ لازم در پیش‌نمایش نشون داده می‌شه."
    ),
    "referral": (
        "👥 راهنمای دعوت دوستان\n\n"
        "با /referral لینک مخصوص خودت رو بگیر و برای دوستت بفرست. وقتی با همون لینک برای اولین بار وارد بازی بشه، "
        f"هر دعوت موفق {game_config.referral_reward_amount} الماس به معرف می‌دهد. تعداد دعوت‌های موفق رو هم در بخش دانش پروفایل می‌بینی."
    ),
    "slogans": (
        "🎯 شعارهایی که پاداش می‌دن\n\n"
        + "\n".join(f"{index}. «{slogan}»" for index, slogan in enumerate(SLOGANS, 1))
        + f"\n\nهر {game_config.slogan_cooldown_seconds // 60} دقیقه یکی از این شعارها رو بفرست "
        f"تا {game_config.slogan_reward_banana} موز بگیری."
    ),
}
HELP_TEXTS = {section: rich_banner(body) for section, body in HELP_TEXTS.items()}


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
        # Recheck at initialization and the explicit membership button too.
        # Only real database sessions can refresh the persisted channel list.
        if isinstance(session, AsyncSession):
            await refresh_channels(session, force=force_refresh)
        member = await subscription_service.is_member(
            bot, user_id, force_refresh=force_refresh
        )
        return member
    except (MembershipCheckError, SQLAlchemyError, ValueError):
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
                parse_mode=MARKDOWN_V2,
            )
        except TelegramAPIError:
            logger.exception("Could not send main menu after callback")
            return False
    else:
        try:
            await target.answer(
                greeting, reply_markup=main_menu_keyboard(), parse_mode=MARKDOWN_V2
            )
        except TelegramAPIError:
            logger.exception("Could not send main menu message")
            return False
    if is_first_login:
        if isinstance(target, CallbackQuery) or hasattr(target, "message"):
            if target.message is not None:
                await target.message.answer(
                    FIRST_LOGIN_GUIDE,
                    reply_markup=first_login_guide_keyboard(),
                    parse_mode=MARKDOWN_V2,
                )
        else:
            await target.answer(
                FIRST_LOGIN_GUIDE,
                reply_markup=first_login_guide_keyboard(),
                parse_mode=MARKDOWN_V2,
            )
    if isinstance(target, CallbackQuery) or hasattr(target, "message"):
        if target.message is not None:
            await target.message.answer(
                HELP_MENU_TEXT,
                reply_markup=help_keyboard(),
                parse_mode=MARKDOWN_V2,
            )
    else:
        await target.answer(
            HELP_MENU_TEXT, reply_markup=help_keyboard(), parse_mode=MARKDOWN_V2
        )
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
            parse_mode=MARKDOWN_V2,
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
    await message.answer(
        HELP_MENU_TEXT, reply_markup=help_keyboard(), parse_mode=MARKDOWN_V2
    )


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
            rich_banner(
                "✅ مأموریت اول شروع شد!\n\n"
                "اول برو سراغ «معدن منابع» تا تولید و هدیهٔ دوم فعال بشه. بعد توی بوفه اولین دبیرت رو بخر."
            ),
            reply_markup=None,
            parse_mode=MARKDOWN_V2,
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
        parse_mode=MARKDOWN_V2,
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
                parse_mode=MARKDOWN_V2,
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
            parse_mode=MARKDOWN_V2,
        )
        return

    try:
        await message.answer(
            UNAVAILABLE_MESSAGE,
            reply_markup=main_menu_keyboard(),
        )
    except TelegramAPIError:
        logger.exception("Could not respond to main menu selection")
