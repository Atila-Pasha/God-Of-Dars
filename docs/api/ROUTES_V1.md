# قرارداد سطح بالای Routeهای API v1

این سند نمای سطح‌بالای نسخه اول است. قرارداد دقیق و نهایی fieldها در OpenAPI
تولیدشده توسط برنامه و تست‌های `tests/api` تثبیت شده است.

## قواعد عمومی

- prefix عمومی: `/api/v1`
- `Authorization: Bearer <access-token>` برای routeهای authenticated
- `Idempotency-Key: <uuid>` برای تمام mutationهای اثرگذار
- `X-Request-ID` اختیاری از کلاینت؛ سرور همیشه request id معتبر تولید/برمی‌گرداند.
- زمان‌ها UTC و ISO 8601، مقدار منابع integer و شناسه‌ها opaque یا integer امن‌اند.
- لیست‌های بزرگ cursor pagination دارند.
- routeهای `/me` هرگز user id را از body نمی‌پذیرند.

## Health و metadata

| Method | Route | Auth | هدف |
|---|---|---:|---|
| GET | `/health/live` | خیر | زنده‌بودن process |
| GET | `/health/ready` | داخلی | آمادگی دریافت traffic |
| GET | `/api/v1/meta` | خیر | حداقل نسخه اپ، نسخه API و maintenance state |
| GET | `/api/v1/game-config` | اختیاری | config عمومی قابل cache و ETag |

`health` نباید جزئیات connection string، exception یا نسخه dependencyها را افشا کند.

## Authentication

| Method | Route | Auth | Idempotency | هدف |
|---|---|---:|---:|---|
| POST | `/api/v1/auth/telegram/attempts` | خیر | خیر | ساخت login attempt و URL ورود |
| GET | `/api/v1/auth/telegram/attempts/{attempt_id}` | attempt secret | خیر | وضعیت pending/approved/expired |
| GET | `/api/v1/auth/telegram/authorize/{attempt_id}` | attempt state | خیر | redirect به Telegram OIDC |
| GET | `/api/v1/auth/telegram/callback` | OIDC state | خیر | callback ثبت‌شده backend |
| POST | `/api/v1/auth/telegram/exchange` | attempt secret | خیر | مصرف یک‌باره attempt و دریافت tokenهای داخلی |
| POST | `/api/v1/auth/refresh` | refresh token | خیر | rotation یک‌باره token family |
| POST | `/api/v1/auth/logout` | بله | خیر | revoke idempotent نشست جاری |
| POST | `/api/v1/auth/logout-all` | بله | خیر | revoke idempotent همه نشست‌های کاربر |
| GET | `/api/v1/auth/sessions` | بله | خیر | فهرست دستگاه‌ها/sessionها |
| DELETE | `/api/v1/auth/sessions/{session_id}` | بله | خیر | revoke idempotent یک دستگاه |

callback مرورگر token بازی را نمایش نمی‌دهد؛ فقط attempt را approve کرده و صفحه
موفقیت یا خطای عمومی نشان می‌دهد.

## Bootstrap و همگام‌سازی

| Method | Route | Auth | هدف |
|---|---|---:|---|
| GET | `/api/v1/bootstrap` | بله | داده کمینه صفحه اول، profile/resources و timerها |
| GET | `/api/v1/sync` | بله | snapshot تازه برای resume/reconnect |

`bootstrap` جای endpointهای domain را نمی‌گیرد؛ یک read model بهینه برای کاهش
round trip موبایل است.

## User، profile و economy

| Method | Route | Auth | Idempotency | هدف |
|---|---|---:|---:|---|
| GET | `/api/v1/me` | بله | خیر | هویت و وضعیت حساب جاری |
| GET | `/api/v1/me/profile` | بله | خیر | snapshot کامل پروفایل |
| GET | `/api/v1/me/resources` | بله | خیر | موجودی authoritative |
| GET | `/api/v1/me/transactions` | بله | خیر | ledger صفحه‌بندی‌شده |
| GET | `/api/v1/users/search` | بله | خیر | جست‌وجوی محدود حریف/کاربر عمومی |
| GET | `/api/v1/users/{public_id}/profile` | بله | خیر | پروفایل عمومی محدود |

جست‌وجو اطلاعات خصوصی، شماره تلفن، telegram id یا inactive بودن دقیق را افشا نمی‌کند.

## مدرسه و دبیرها

| Method | Route | Auth | Idempotency | هدف |
|---|---|---:|---:|---|
| GET | `/api/v1/teachers/catalog` | بله | خیر | catalog متناسب با سطح کاربر |
| GET | `/api/v1/me/teachers` | بله | خیر | دبیرهای تحت مالکیت |
| GET | `/api/v1/me/teachers/{owned_teacher_id}` | بله | خیر | جزئیات دبیر کاربر |
| POST | `/api/v1/me/teachers/{teacher_id}/purchase` | بله | بله | خرید دبیر |
| POST | `/api/v1/me/teachers/{owned_teacher_id}/upgrade` | بله | بله | ارتقا |
| POST | `/api/v1/me/teachers/{owned_teacher_id}/sell` | بله | بله | فروش |
| POST | `/api/v1/me/teachers/{owned_teacher_id}/activate` | بله | بله | فعال‌سازی |
| POST | `/api/v1/me/teachers/{owned_teacher_id}/recover` | بله | بله | آغاز recovery |

routeهای action به جای PATCH عمومی استفاده می‌شوند چون هر عمل rule و اثر اقتصادی
مجزا دارد.

## دژ و سپر

| Method | Route | Auth | Idempotency | هدف |
|---|---|---:|---:|---|
| GET | `/api/v1/me/castle` | بله | خیر | snapshot دژ و دفاع |
| POST | `/api/v1/me/castle/repair` | بله | بله | تعمیر اتمیک |
| POST | `/api/v1/me/castle/upgrade` | بله | بله | ارتقای دژ |
| GET | `/api/v1/shields/catalog` | بله | خیر | catalog سپرها |
| GET | `/api/v1/me/shields` | بله | خیر | سپرهای کاربر |
| POST | `/api/v1/me/shields/{shield_id}/purchase` | بله | بله | خرید سپر |

## معدن

| Method | Route | Auth | Idempotency | هدف |
|---|---|---:|---:|---|
| GET | `/api/v1/me/mine` | بله | خیر | وضعیت، ظرفیت و زمان معدن |
| POST | `/api/v1/me/mine/collect` | بله | بله | جمع‌آوری منابع |
| POST | `/api/v1/me/mine/upgrade` | بله | بله | ارتقای معدن |

پاداش collect بر اساس ساعت سرور محاسبه می‌شود و زمان کلاینت پذیرفته نمی‌شود.

## مطالعه

| Method | Route | Auth | Idempotency | هدف |
|---|---|---:|---:|---|
| GET | `/api/v1/study/packs` | بله | خیر | پک‌های فعال |
| GET | `/api/v1/me/study` | بله | خیر | session جاری و زمان باقی‌مانده |
| POST | `/api/v1/me/study/start` | بله | بله | شروع پک مطالعه |
| POST | `/api/v1/me/study/settle` | بله | بله | settle و دریافت پاداش آماده |

## سؤال و مأموریت روزانه

| Method | Route | Auth | Idempotency | هدف |
|---|---|---:|---:|---|
| GET | `/api/v1/daily-question` | بله | خیر | سؤال فعال و وضعیت پاسخ کاربر |
| POST | `/api/v1/daily-question/answer` | بله | بله | ثبت یک‌باره پاسخ |
| GET | `/api/v1/me/daily-quests` | بله | خیر | مأموریت و progress روز جاری |
| POST | `/api/v1/me/daily-quests/{progress_id}/claim` | بله | بله | claim اتمیک progress تکمیل‌شده |

اگر پاداش مأموریت خودکار است، route `claim` حذف می‌شود تا دو مدل پاداش هم‌زمان
وجود نداشته باشد.

## نبرد

| Method | Route | Auth | Idempotency | هدف |
|---|---|---:|---:|---|
| GET | `/api/v1/battles/opponents` | بله | خیر | پیشنهاد حریف صفحه‌بندی‌شده |
| POST | `/api/v1/battles/preview` | بله | خیر | preview بدون تغییر state |
| POST | `/api/v1/battles` | بله | بله | شروع حمله و دریافت `202` |
| GET | `/api/v1/battles/{battle_id}` | بله | خیر | وضعیت/نتیجه برای طرف مجاز |
| GET | `/api/v1/battles` | بله | خیر | تاریخچه cursor-based ارسالی و دریافتی |

شروع حمله نتیجه نهایی را هم‌زمان محاسبه نمی‌کند؛ یک attack durable می‌سازد و
worker آن را resolve می‌کند. preview تضمین نتیجه نیست و state نهایی دوباره داخل
transaction بررسی می‌شود.

## بوفه و تبدیل منابع

| Method | Route | Auth | Idempotency | هدف |
|---|---|---:|---:|---|
| GET | `/api/v1/exchanges/options` | بله | خیر | گزینه‌های تبدیل authoritative |
| POST | `/api/v1/exchanges` | بله | بله | اجرای نرخ معتبر سمت سرور به‌شکل اتمیک |

کلاینت نرخ تبدیل را تعیین نمی‌کند؛ فقط نوع منبع و تعداد بسته‌ها را می‌فرستد و
backend نرخ فعال را دوباره بررسی و اعمال می‌کند.

## دعوت‌ها

| Method | Route | Auth | Idempotency | هدف |
|---|---|---:|---:|---|
| GET | `/api/v1/me/referral` | بله | خیر | کد و آمار دعوت کاربر |
| POST | `/api/v1/me/referral/apply` | بله | بله | ثبت معرف یک‌باره |
| GET | `/api/v1/me/referrals` | بله | خیر | فهرست محدود دعوت‌شده‌ها |

## شانس

| Method | Route | Auth | Idempotency | هدف |
|---|---|---:|---:|---|
| GET | `/api/v1/me/chance-cards` | بله | خیر | کارت‌های قابل claim کاربر |
| POST | `/api/v1/me/chance-cards/{card_id}/claim` | بله | بله | claim اتمیک |

جعبه شانس گروهی و captcha وابسته به پیام گروهی در API عمومی نسخه اول قرار نمی‌گیرد.

## عضویت کانال

| Method | Route | Auth | Idempotency | هدف |
|---|---|---:|---:|---|
| GET | `/api/v1/me/subscription` | بله | خیر | وضعیت cache‌شده requirementها |
| POST | `/api/v1/me/subscription/verify` | بله | خیر | بررسی مجدد rate-limited با Telegram |

اختلال Telegram نباید به‌صورت اشتباه کاربر معتبر را non-member اعلام کند. پاسخ
می‌تواند `verified_at`، `stale` و `provider_unavailable` داشته باشد تا policy
محصول تصمیم شفاف بگیرد.

## اعلان‌ها

| Method | Route | Auth | Idempotency | هدف |
|---|---|---:|---:|---|
| GET | `/api/v1/me/notifications` | بله | خیر | inbox صفحه‌بندی‌شده |
| POST | `/api/v1/me/notifications/{id}/read` | بله | بله | علامت‌گذاری خوانده‌شده |
| POST | `/api/v1/me/notifications/read-all` | بله | بله | خواندن همه تا cursor/time مشخص |

## Admin API

namespace جدا: `/admin/api/v1`. دامنه‌ها:

- users و moderation
- game catalog/config management
- question publishing
- economy adjustments
- broadcast
- operational job inspection/retry
- audit log

Admin API token audience، rate limit و authorization جدا دارد. تغییر موجودی
نیازمند reason اجباری و audit تغییر before/after است. endpointهای destructive
نباید با public token قابل دسترسی باشند.

## endpointهایی که عمداً وجود ندارند

- set کردن مستقیم موجودی، سطح، damage یا reward توسط کاربر
- گرفتن profile بر اساس Telegram numeric id
- mutation عمومی و آزاد مانند `PATCH /users/{id}`
- endpoint اجرای مستقیم worker یا scheduler از اینترنت عمومی
- endpoint دریافت Bot Token یا Telegram Client Secret
- endpointی که ORM model خام یا stack trace برگرداند

## error codeهای پایه

حداقل codeهای نسخه اول:

- `AUTH_REQUIRED`
- `TOKEN_EXPIRED`
- `SESSION_REVOKED`
- `TELEGRAM_LOGIN_EXPIRED`
- `TELEGRAM_LOGIN_INVALID`
- `USER_INACTIVE`
- `RESOURCE_NOT_FOUND`
- `INSUFFICIENT_COINS`
- `INSUFFICIENT_DIAMONDS`
- `TEACHER_NOT_OWNED`
- `TEACHER_LOCKED`
- `TEACHER_IN_HOSPITAL`
- `CASTLE_UPGRADE_UNAVAILABLE`
- `SHIELD_ALREADY_ACTIVE`
- `MINE_UPGRADE_UNAVAILABLE`
- `STUDY_ALREADY_ACTIVE`
- `QUESTION_ALREADY_ANSWERED`
- `QUESTION_EXPIRED`
- `ATTACK_IN_PROGRESS`
- `TARGET_NOT_AVAILABLE`
- `IDEMPOTENCY_KEY_REQUIRED`
- `IDEMPOTENCY_KEY_REUSED`
- `RATE_LIMITED`
- `DEPENDENCY_UNAVAILABLE`

نگاشت exceptionهای موجود service layer به این codeها باید در یک error mapper مرکزی
باشد، نه داخل هر route.
