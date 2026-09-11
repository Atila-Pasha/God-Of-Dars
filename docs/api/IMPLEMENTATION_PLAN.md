# برنامه ساخت API بدون شکستن بات فعلی

> وضعیت: baseline اجرایی فازهای ۱ تا ۷ پیاده‌سازی و با تست‌های پروژه تأیید شده
> است. آیتم‌های عملیاتی فاز ۸ مانند WAF، PgBouncer، پایش production، تست بار
> staging و rollout تدریجی به زیرساخت مقصد وابسته‌اند و پیش از انتشار عمومی
> باید انجام شوند.

## اصل تحویل

هر فاز باید deployable، تست‌شده و backward-compatible باشد. API جدید نباید برای
شروع، handlerهای بات را بازنویسی کامل کند. migration از transport-coupled به
domain-oriented به‌صورت تدریجی انجام می‌شود.

## فاز ۰ — baseline و ظرفیت

خروجی‌ها:

- ثبت baseline تست‌های موجود
- تعریف DAU، concurrency و RPS هدف
- اندازه‌گیری queryهای پرتکرار و connection pool
- inventory متغیرهای محیطی و secretها
- تعریف staging جدا با bot/client تلگرام جدا

دروازه خروج:

- همه تست‌های فعلی سبز
- load profile مستند
- backup و restore دیتابیس staging آزمایش شده

## فاز ۱ — جداسازی هویت domain از aiogram

خروجی‌ها:

- DTO مستقل برای هویت تلگرام
- مسیر service مبتنی بر `user_id` داخلی
- migration امن `auth_identities`
- backfill identity کاربران موجود
- unique constraint و تست عدم ساخت حساب تکراری

دروازه خروج:

- بات بدون تغییر رفتاری کار می‌کند.
- کاربر قدیمی و ورود جدید به یک `user_id` می‌رسند.
- service layer برای use caseهای API نیازی به aiogram ندارد.

## فاز ۲ — پوسته API و قرارداد مشترک

خروجی‌ها:

- application factory و lifecycle
- config مستقل API
- database dependency و transaction boundary
- error envelope و error mapper
- request id، logging، metrics و health
- `/api/v1/meta` و version policy
- OpenAPI اولیه و contract tests

دروازه خروج:

- process API stateless و چندreplica قابل اجراست.
- readiness هنگام قطع دیتابیس traffic نمی‌گیرد.
- هیچ secret یا PII حساس در log دیده نمی‌شود.

## فاز ۳ — Telegram OIDC و session security

خروجی‌ها:

- login attempt lifecycle
- state، nonce و PKCE
- callback HTTPS و exchange یک‌بارمصرف
- اعتبارسنجی JWKS/issuer/audience/expiry
- access token و refresh rotation
- revoke دستگاه و logout-all
- rate limit و audit رخدادهای auth

دروازه خروج:

- replay، CSRF، code reuse و refresh reuse تست شده‌اند.
- secretها فقط server-side هستند.
- ورود روی Windows، Android و Linux به یک حساب مشترک می‌رسد.

## فاز ۴ — API فقط‌خواندنی و bootstrap

خروجی‌ها:

- `me/profile/resources`
- catalog دبیر، سپر و مطالعه
- castle، mine، quest و battle history
- cursor pagination
- ETag برای داده عمومی
- bootstrap و sync baseline

دروازه خروج:

- N+1 query وجود ندارد.
- p95 هدف در load test staging رعایت می‌شود.
- داده خصوصی با user دیگر قابل خواندن نیست.

## فاز ۵ — mutationهای کم‌ریسک و idempotency platform

خروجی‌ها:

- جدول idempotency دیتابیسی
- hash payload و replay response
- profile settings، notification preferences و referral apply
- study start/settle و daily answer
- تست retry، double tap و قطع connection بعد از commit

دروازه خروج:

- اجرای هم‌زمان یک action با یک key فقط یک اثر دارد.
- key تکراری با payload متفاوت رد می‌شود.
- ledger و پاسخ API پس از retry سازگارند.

## فاز ۶ — mutationهای اقتصادی

خروجی‌ها:

- خرید/فروش/ارتقای دبیر
- دژ، سپر و معدن
- quote/execute بوفه
- transaction ledger و audit تکمیل‌شده
- تست concurrency با PostgreSQL واقعی

دروازه خروج:

- موجودی منفی در race test ممکن نیست.
- هر تغییر موجودی ledger متناظر دارد.
- rollback میانی هیچ اثر نیمه‌کاره باقی نمی‌گذارد.

## فاز ۷ — نبرد async، worker و realtime fallback

خروجی‌ها:

- preview و start attack
- worker pool مستقل با claim و recovery
- battle status/history
- notification outbox و inbox اپ
- sync cursor و polling fallback

دروازه خروج:

- چند worker یک حمله را دوبار resolve نمی‌کنند.
- crash در هر نقطه با retry به state معتبر می‌رسد.
- خاموشی realtime correctness اپ را نمی‌شکند.

## فاز ۸ — hardening و انتشار تدریجی

خروجی‌ها:

- WAF و rate limit توزیع‌شده
- PgBouncer و تنظیم pool بر اساس replica count
- Redis cache با fallback
- dashboard و alert
- soak، spike و failure injection test
- canary release و feature flag
- runbook incident/rollback/restore

دروازه خروج:

- خطای 5xx و latency زیر SLO در بار هدف‌اند.
- قطع Redis فساد یا توقف کامل بازی ایجاد نمی‌کند.
- قطع Telegram فقط قابلیت‌های وابسته را degrade می‌کند.
- restore backup و rollback release تمرین شده‌اند.

## ترتیب پیشنهادی فعال‌سازی برای کاربران

1. تیم داخلی و حساب‌های تست
2. درصد کوچک کاربران با feature flag
3. کاربران فقط‌خواندنی
4. mutationهای غیرمالی
5. mutationهای اقتصادی با سقف محدود
6. نبرد و اعلان‌ها
7. rollout کامل پس از دوره پایش

## مجموعه تست اجباری

### Unit

- service rules و error mapping
- token/session state machine
- idempotency payload hashing
- cursor encode/decode

### Integration با PostgreSQL واقعی

- row lock و deadlock retry
- unique constraintهای identity/idempotency
- transaction rollback
- worker claim با `SKIP LOCKED`
- read-after-write موجودی

### Contract

- OpenAPI snapshot
- field optionality و error codes
- سازگاری حداقل یک نسخه قدیمی Flet

### Security

- authorization افقی بین دو کاربر
- expired/revoked token
- OIDC state/nonce/PKCE replay
- refresh token reuse
- rate limit bypass
- log redaction

### Performance

- steady load
- spike login پس از اعلان عمومی
- spike daily question
- battle start burst
- soak چندساعته برای connection/memory leak

### Resilience

- قطع Redis
- latency و timeout تلگرام
- restart worker وسط job
- failover/restart PostgreSQL در staging
- deploy هم‌زمان با requestهای قدیمی

## معیار Definition of Done هر endpoint

- schema ورودی و خروجی صریح
- authentication/authorization مشخص
- error codeهای پایدار
- idempotency decision مشخص
- transaction boundary مشخص
- rate limit class مشخص
- cache policy مشخص
- metric و log مناسب
- unit/integration/contract test
- مستندات OpenAPI و نمونه رفتار retry
- عدم افشای ORM، secret یا PII

## کارهایی که نباید در نسخه اول انجام شوند

- انتقال منطق بازی به Flet
- دیتابیس مستقیم از داخل Flet
- نگهداری login session فقط در حافظه یک API replica
- استفاده از Redis به‌عنوان ledger
- اضافه‌کردن message broker جدید بدون نیاز اندازه‌گیری‌شده
- sharding زودهنگام PostgreSQL
- microservice کردن هر پوشه service
- rewrite هم‌زمان بات و API
- عمومی‌کردن Admin API با access token معمولی
