from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, IntegrityError, SQLAlchemyError

from app.services.buffet_service import (
    BuffetUserNotFound,
    ConversionAmountError,
    InsufficientResource,
    InvalidBuffetConversion,
)
from app.services.chance_service import AlreadyClaimed, BoxExpired, WrongCaptcha
from app.services.library_errors import (
    DuplicateAnswer,
    InvalidAnswer,
    InvalidQuestion,
    QuestionExpired,
    QuestionNotFound,
)
from app.services.referral_service import (
    ReferralAlreadySet,
    ReferralCycle,
    ReferralUserInactive,
    ReferrerNotFound,
    SelfReferral,
)
from app.services.school_errors import (
    AttackerNotRegistered,
    AttackInProgress,
    AttackTargetNotRegistered,
    CannotAttackSelf,
    CastleNotFound,
    CastleUpgradeUnavailable,
    InsufficientCoins,
    InsufficientDiamonds,
    InvalidTeacherState,
    MaxLevelReached,
    MineLevelLocked,
    MineNotFound,
    MineUpgradeUnavailable,
    OperationNotConfigured,
    RandomOpponentNotFound,
    ResourceNotFound,
    SchoolUserNotFound,
    ShieldAlreadyActive,
    ShieldLocked,
    ShieldNotFound,
    ShieldNotPurchasable,
    TeacherAlreadyOwned,
    TeacherInHospital,
    TeacherLimitReached,
    TeacherLocked,
    TeacherNotFound,
    TeacherNotOwned,
    TeacherNotPurchasable,
    TeacherSlotLocked,
)
from app.services.study_service import StudyAlreadyActive, StudyPackNotFound
from app.services.user_service import UserInactiveError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ErrorSpec:
    status: int
    code: str
    message: str


class APIError(RuntimeError):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}
        self.headers = headers or {}


DOMAIN_ERRORS: tuple[tuple[type[Exception], ErrorSpec], ...] = (
    (UserInactiveError, ErrorSpec(403, "USER_INACTIVE", "حساب کاربری غیرفعال است.")),
    (AttackerNotRegistered, ErrorSpec(403, "USER_INACTIVE", "حساب کاربری فعال نیست.")),
    (SchoolUserNotFound, ErrorSpec(404, "USER_NOT_FOUND", "کاربر پیدا نشد.")),
    (ResourceNotFound, ErrorSpec(404, "RESOURCE_NOT_FOUND", "منابع کاربر پیدا نشد.")),
    (InsufficientDiamonds, ErrorSpec(409, "INSUFFICIENT_DIAMONDS", "الماس کافی نیست.")),
    (InsufficientCoins, ErrorSpec(409, "INSUFFICIENT_RESOURCES", "موجودی کافی نیست.")),
    (TeacherNotFound, ErrorSpec(404, "TEACHER_NOT_FOUND", "دبیر پیدا نشد.")),
    (
        TeacherNotOwned,
        ErrorSpec(404, "TEACHER_NOT_OWNED", "این دبیر متعلق به شما نیست."),
    ),
    (
        TeacherAlreadyOwned,
        ErrorSpec(409, "TEACHER_ALREADY_OWNED", "این دبیر را قبلاً خریده‌اید."),
    ),
    (
        TeacherLocked,
        ErrorSpec(403, "TEACHER_LOCKED", "سطح لازم برای این دبیر را ندارید."),
    ),
    (
        TeacherSlotLocked,
        ErrorSpec(409, "TEACHER_SLOT_LOCKED", "ظرفیت دبیرهای شما پر است."),
    ),
    (
        TeacherLimitReached,
        ErrorSpec(409, "TEACHER_LIMIT_REACHED", "به سقف تعداد دبیر رسیده‌اید."),
    ),
    (
        TeacherNotPurchasable,
        ErrorSpec(409, "TEACHER_NOT_PURCHASABLE", "این دبیر قابل خرید نیست."),
    ),
    (
        TeacherInHospital,
        ErrorSpec(409, "TEACHER_IN_HOSPITAL", "دبیر در بیمارستان است."),
    ),
    (
        InvalidTeacherState,
        ErrorSpec(409, "INVALID_TEACHER_STATE", "وضعیت دبیر برای این کار معتبر نیست."),
    ),
    (CastleNotFound, ErrorSpec(404, "CASTLE_NOT_FOUND", "دژ پیدا نشد.")),
    (
        CastleUpgradeUnavailable,
        ErrorSpec(409, "CASTLE_UPGRADE_UNAVAILABLE", "ارتقای دژ ممکن نیست."),
    ),
    (ShieldNotFound, ErrorSpec(404, "SHIELD_NOT_FOUND", "سپر پیدا نشد.")),
    (ShieldLocked, ErrorSpec(403, "SHIELD_LOCKED", "سطح لازم برای این سپر را ندارید.")),
    (
        ShieldAlreadyActive,
        ErrorSpec(409, "SHIELD_ALREADY_ACTIVE", "یک سپر فعال دارید."),
    ),
    (
        ShieldNotPurchasable,
        ErrorSpec(409, "SHIELD_NOT_PURCHASABLE", "این سپر قابل استفاده نیست."),
    ),
    (MineNotFound, ErrorSpec(404, "MINE_NOT_FOUND", "معدن پیدا نشد.")),
    (
        MineLevelLocked,
        ErrorSpec(403, "MINE_LEVEL_LOCKED", "سطح لازم برای ارتقای معدن را ندارید."),
    ),
    (
        MineUpgradeUnavailable,
        ErrorSpec(409, "MINE_UPGRADE_UNAVAILABLE", "ارتقای معدن ممکن نیست."),
    ),
    (StudyPackNotFound, ErrorSpec(404, "STUDY_PACK_NOT_FOUND", "پک مطالعه پیدا نشد.")),
    (
        StudyAlreadyActive,
        ErrorSpec(409, "STUDY_ALREADY_ACTIVE", "یک مطالعه فعال دارید."),
    ),
    (QuestionNotFound, ErrorSpec(404, "QUESTION_NOT_FOUND", "سؤال فعال پیدا نشد.")),
    (
        QuestionExpired,
        ErrorSpec(409, "QUESTION_EXPIRED", "زمان پاسخ‌گویی تمام شده است."),
    ),
    (
        DuplicateAnswer,
        ErrorSpec(409, "QUESTION_ALREADY_ANSWERED", "قبلاً به این سؤال پاسخ داده‌اید."),
    ),
    (InvalidAnswer, ErrorSpec(400, "INVALID_ANSWER", "پاسخ معتبر نیست.")),
    (InvalidQuestion, ErrorSpec(409, "INVALID_QUESTION", "سؤال معتبر نیست.")),
    (AttackInProgress, ErrorSpec(409, "ATTACK_IN_PROGRESS", "یک حمله فعال دارید.")),
    (
        AttackTargetNotRegistered,
        ErrorSpec(404, "TARGET_NOT_AVAILABLE", "حریف در دسترس نیست."),
    ),
    (
        RandomOpponentNotFound,
        ErrorSpec(404, "OPPONENT_NOT_FOUND", "حریف مناسبی پیدا نشد."),
    ),
    (
        CannotAttackSelf,
        ErrorSpec(409, "CANNOT_ATTACK_SELF", "نمی‌توانید به خودتان حمله کنید."),
    ),
    (
        InvalidBuffetConversion,
        ErrorSpec(409, "INVALID_EXCHANGE", "این تبدیل فعال نیست."),
    ),
    (
        ConversionAmountError,
        ErrorSpec(400, "INVALID_EXCHANGE_AMOUNT", "مقدار تبدیل معتبر نیست."),
    ),
    (
        InsufficientResource,
        ErrorSpec(409, "INSUFFICIENT_RESOURCES", "موجودی کافی نیست."),
    ),
    (BuffetUserNotFound, ErrorSpec(404, "USER_NOT_FOUND", "کاربر پیدا نشد.")),
    (SelfReferral, ErrorSpec(409, "SELF_REFERRAL", "نمی‌توانید معرف خودتان باشید.")),
    (
        ReferralCycle,
        ErrorSpec(409, "REFERRAL_CYCLE", "این دعوت یک چرخه نامعتبر ایجاد می‌کند."),
    ),
    (
        ReferralAlreadySet,
        ErrorSpec(409, "REFERRAL_ALREADY_SET", "معرف قبلاً ثبت شده است."),
    ),
    (ReferrerNotFound, ErrorSpec(404, "REFERRER_NOT_FOUND", "معرف پیدا نشد.")),
    (ReferralUserInactive, ErrorSpec(403, "USER_INACTIVE", "حساب کاربری غیرفعال است.")),
    (
        AlreadyClaimed,
        ErrorSpec(409, "ALREADY_CLAIMED", "این جایزه قبلاً دریافت شده است."),
    ),
    (WrongCaptcha, ErrorSpec(400, "WRONG_CAPTCHA", "پاسخ کپچا اشتباه است.")),
    (BoxExpired, ErrorSpec(409, "CHANCE_EXPIRED", "زمان دریافت جایزه تمام شده است.")),
    (MaxLevelReached, ErrorSpec(409, "MAX_LEVEL_REACHED", "به بالاترین سطح رسیده‌اید.")),
    (
        OperationNotConfigured,
        ErrorSpec(409, "OPERATION_NOT_CONFIGURED", "این عملیات هنوز تنظیم نشده است."),
    ),
)


def error_payload(
    request: Request, code: str, message: str, details: Any = None
) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "request_id": getattr(request.state, "request_id", None),
        }
    }


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(APIError)
    async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
        headers = dict(exc.headers)
        if exc.status_code == 401:
            headers.setdefault("WWW-Authenticate", "Bearer")
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(request, exc.code, exc.message, exc.details),
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        fields = [
            {
                "location": list(item["loc"]),
                "message": item["msg"],
                "type": item["type"],
            }
            for item in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=error_payload(
                request,
                "VALIDATION_ERROR",
                "داده‌های درخواست معتبر نیستند.",
                {"fields": fields},
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        for exception_type, spec in DOMAIN_ERRORS:
            if isinstance(exc, exception_type):
                return JSONResponse(
                    status_code=spec.status,
                    content=error_payload(request, spec.code, spec.message),
                )
        if isinstance(exc, IntegrityError):
            logger.info("Database constraint rejected request", exc_info=exc)
            return JSONResponse(
                status_code=409,
                content=error_payload(
                    request, "CONFLICT", "درخواست با وضعیت فعلی سازگار نیست."
                ),
            )
        if isinstance(exc, (DBAPIError, SQLAlchemyError)):
            logger.exception("Database request failed")
            return JSONResponse(
                status_code=503,
                content=error_payload(
                    request,
                    "DATABASE_UNAVAILABLE",
                    "سرویس موقتاً در دسترس نیست.",
                ),
            )
        logger.exception("Unhandled API error")
        return JSONResponse(
            status_code=500,
            content=error_payload(
                request, "INTERNAL_ERROR", "خطای پیش‌بینی‌نشده‌ای رخ داد."
            ),
        )
