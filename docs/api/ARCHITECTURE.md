# معماری فنی API پروژه GodOfDars

## ۱. هدف و قیود

هدف، تبدیل GodOfDars از یک بازی وابسته به رابط تلگرام به یک backend
چندکلاینتی است؛ به شکلی که بات فعلی و اپ Flet هر دو یک منطق بازی، یک اقتصاد و
یک منبع داده داشته باشند.

قیود اصلی:

- کلاینت Flet قابل اعتماد نیست و نباید منطق اقتصادی یا secret در آن باشد.
- یک کاربر باید در بات و اپ دقیقاً یک حساب و یک موجودی داشته باشد.
- endpointهای API نباید handlerهای aiogram را صدا بزنند.
- handlerهای بات و routeهای API فقط adapter هستند و منطق در service layer می‌ماند.
- processهای API باید stateless باشند تا چند replica هم‌زمان قابل اجرا باشد.
- تکرار request، قطع اینترنت و retry کلاینت نباید پاداش یا برداشت مالی را تکرار کند.
- معماری باید از رشد زیاد کاربر پشتیبانی کند، اما پیچیدگی microservice را قبل از
  مشاهده bottleneck وارد نکند.

## ۲. نمای کلان

```text
                        ┌──────────────────────────┐
 Flet / Telegram Login │ CDN / WAF / Load Balancer│
            ──────────►└────────────┬─────────────┘
                                   │ HTTPS
                          ┌────────▼────────┐
                          │ API replicas    │
                          │ stateless       │
                          └───┬────────┬────┘
                              │        │
                    cache/rate│        │transactions
                              │        │
                        ┌─────▼──┐  ┌──▼────────────────┐
                        │ Redis  │  │ PgBouncer          │
                        └────────┘  └──┬────────────────┘
                                      │
                                 ┌────▼─────┐
                                 │PostgreSQL│
                                 │ primary  │
                                 └────┬─────┘
                                      │ durable jobs/outbox
              ┌───────────────────────┼────────────────────────┐
              │                       │                        │
       ┌──────▼──────┐         ┌──────▼──────┐          ┌─────▼──────┐
       │Telegram Bot │         │Worker pool  │          │Scheduler   │
       │process      │         │SKIP LOCKED  │          │singleton   │
       └─────────────┘         └─────────────┘          └────────────┘
```

API، بات و workerها همگی از `services` و `repositories` موجود استفاده می‌کنند.
ارتباط صحیح transportها با دامنه به این صورت است:

```text
HTTP/Telegram input
       ↓
transport validation and authentication
       ↓
application service / use case
       ↓
repository + database transaction
       ↓
transport-specific response formatting
```

## ۳. سبک معماری

### انتخاب: modular monolith

هر دامنه یک مرز روشن دارد، ولی deployment و دیتابیس فعلاً مشترک‌اند. مزیت‌ها:

- استفاده مستقیم از serviceهای فعلی بدون RPC داخلی
- تراکنش‌های ساده و اتمیک برای اقتصاد بازی
- latency کمتر نسبت به microservice
- امکان چند replica از API و worker
- امکان استخراج یک دامنه در آینده بدون بازنویسی قرارداد عمومی

### شرط استخراج microservice

یک دامنه فقط زمانی جدا می‌شود که حداقل یکی از این موارد با داده ثابت شود:

- بار آن دامنه مستقل و بسیار بیشتر از بقیه باشد.
- failure آن دامنه مرتباً کل backend را مختل کند.
- نیاز استقرار یا مقیاس مستقل داشته باشد.
- مالکیت تیمی مستقل ایجاد شده باشد.

تعداد زیاد کاربر به‌تنهایی دلیل microservice نیست.

## ۴. اجزای runtime

### API process

- FastAPI/ASGI و stateless
- چند worker process یا چند container replica
- بدون job زمان‌بندی‌شده و بدون state احراز هویت در حافظه
- transaction مستقل در هر request
- timeout مشخص برای دیتابیس و سرویس‌های خارجی
- graceful shutdown و readiness/liveness probe

### Telegram Bot process

- aiogram فعلی به‌عنوان یک transport مستقل
- استفاده از service layer مشترک
- عدم import از `app.api`
- امکان polling در توسعه و webhook در محیط پرترافیک

### Worker pool

- پردازش حملات زمان‌دار، اعلان‌ها و outbox
- claim اتمیک jobها با `FOR UPDATE SKIP LOCKED`
- retry محدود با exponential backoff و jitter
- recovery برای jobهای گیرکرده در حالت processing
- dead-letter state برای خطاهای غیرقابل‌بازیابی

### Scheduler

- تنها یک scheduler فعال یا scheduler دارای distributed lock
- فقط ایجاد job؛ اجرای کار سنگین توسط workerها
- قابل جایگزینی با scheduler مدیریت‌شده cloud بدون تغییر service layer

### PostgreSQL

- تنها منبع حقیقت برای حساب، اقتصاد، نبرد و وضعیت بازی
- primary برای تمام writeها
- read replica فقط برای queryهای واقعاً eventual-consistent مانند leaderboard،
  گزارش و history در فاز رشد
- backup رمزگذاری‌شده، PITR و آزمون دوره‌ای restore

### PgBouncer

- بین processهای متعدد و PostgreSQL قرار می‌گیرد.
- از انفجار تعداد connection هنگام scale افقی جلوگیری می‌کند.
- سقف pool برنامه باید با ظرفیت واقعی دیتابیس و تعداد replica محاسبه شود.

### Redis

کاربردهای مجاز:

- rate limit توزیع‌شده
- cache داده‌های عمومی و کم‌تغییر
- session کوتاه ورود تلگرام
- nonce/state موقت در کنار ثبت ضروری یا قابلیت بازیابی امن
- presence یا fan-out رویدادهای زودگذر

کاربردهای غیرمجاز:

- منبع اصلی موجودی یا پاداش
- تنها محل ثبت idempotency اقتصادی
- تنها صف durable برای عملیات حیاتی بازی

از دست‌رفتن Redis باید فقط باعث افت performance یا خروج کاربران از login موقت
شود، نه فساد داده‌های بازی.

## ۵. مرزهای دامنه

### Identity & Access

ورود تلگرام، session دستگاه، access/refresh token، logout، revoke، RBAC و audit.

### User & Profile

پروفایل، سطح، تاریخ عضویت، وضعیت فعال و snapshot صفحه اصلی.

### Economy

منابع، transaction ledger، reward و تبادل بوفه. همه writeها اتمیک و idempotent.

### School

فهرست دبیرها، دبیرهای کاربر، خرید، ارتقا، فروش، فعال‌سازی و recovery.

### Castle & Defense

دژ، تعمیر، ارتقا، دفاع و سپر.

### Mine

وضعیت معدن، جمع‌آوری و ارتقا.

### Study

پک‌ها، session مطالعه، وضعیت فعال و settle پاداش.

### Questions & Daily Quests

سؤال روزانه، ثبت پاسخ، نتیجه، مأموریت‌ها و پیشرفت. سؤال‌های گروهی transport
بات باقی می‌مانند.

### Battle

جست‌وجو/انتخاب حریف، preview، شروع حمله async، وضعیت و تاریخچه.

### Referral

کد دعوت، ثبت معرف، آمار و فهرست دعوت‌ها.

### Notification

outbox قابل retry، inbox اپ، وضعیت خوانده‌شدن و کانال ارسال تلگرام/push.

### Admin

API ادمین زیر namespace و policy جدا قرار می‌گیرد و بخشی از public API نیست.
عملیات ادمین حساس دارای audit اجباری است.

## ۶. هویت و ورود با تلگرام

### پروتکل اصلی

Telegram OIDC با Authorization Code Flow و PKCE استفاده می‌شود. Allowed URL و
Client ID/Secret در BotFather تنظیم می‌شوند. مرجع رسمی:
`https://core.telegram.org/bots/telegram-login`.

### جریان پیشنهادی چندسکویی

1. Flet یک login attempt از API ایجاد می‌کند.
2. API شناسه attempt، URL ورود و secret اتصال یک‌بارمصرف را برمی‌گرداند.
3. Flet URL را در مرورگر سیستم باز می‌کند.
4. backend کاربر را با `state` و PKCE به Telegram OIDC می‌فرستد.
5. تلگرام به callback HTTPS ثبت‌شده روی backend برمی‌گردد.
6. backend کد را server-side exchange و ID token را اعتبارسنجی می‌کند.
7. claimهای `iss`، `aud`، `exp`، امضا و nonce بررسی می‌شوند.
8. `telegram user id` به identity داخلی متصل می‌شود.
9. attempt به حالت approved می‌رود و یک exchange code کوتاه‌عمر تولید می‌شود.
10. Flet با poll دارای backoff یا channel realtime نتیجه را می‌گیرد.
11. attempt secret فقط یک‌بار به access/refresh token داخلی تبدیل می‌شود.

این جریان callback سفارشی متفاوت برای Windows، Android و Linux را الزامی
نمی‌کند و token را داخل URL عمومی اپ قرار نمی‌دهد.

### مدل identity

وابستگی مستقیم domain به `aiogram.types.User` باید حذف شود. مدل پیاده‌سازی‌شده:

- `users`: هویت داخلی بازی و داده‌های domain
- `auth_identities`: provider، provider subject، telegram user id و user id داخلی
- `auth_login_attempts`: state، PKCE metadata، expiry، status و used_at
- `auth_sessions`: هر دستگاه، refresh token hash، rotation family و revoked_at
- `auth_audit_events`: login، refresh reuse، revoke و رخداد مشکوک

`users.telegram_user_id` فعلی در migration اول می‌تواند حفظ شود و به تدریج
مرجع اصلی احراز هویت به `auth_identities` منتقل شود. unique constraint روی شناسه
تلگرام مانع ساخت حساب تکراری می‌شود.

### tokenهای داخلی

- access token کوتاه‌عمر با پیش‌فرض ۱۵ دقیقه
- refresh token چرخشی با پیش‌فرض ۳۰ روز
- ذخیره فقط hash refresh token در دیتابیس
- revoke کل token family در صورت reuse شدن refresh token مصرف‌شده
- جداسازی signing key محیط توسعه، staging و production
- نگهداری token کلاینت در secure storage سیستم‌عامل، نه فایل ساده
- logout همان دستگاه و logout همه دستگاه‌ها به‌صورت جدا

### session و دستگاه

هر session شامل device id تصادفی برنامه، platform، app version، زمان آخرین
استفاده و وضعیت revoke است. device id شناسه سخت‌افزاری یا fingerprint تهاجمی نیست.

## ۷. قرارداد HTTP

### نسخه‌بندی

- API عمومی: `/api/v1`
- API ادمین: `/admin/api/v1`
- endpointهای زیرساخت: خارج از version عمومی، مانند `/health/live`
- تغییر breaking نسخه جدید می‌خواهد؛ افزودن field اختیاری breaking نیست.

### قالب پاسخ موفق

پاسخ موفق resource به‌شکل مستقیم و schemaدار برگردانده می‌شود؛ پاسخ‌های
صفحه‌بندی‌شده `items` و `next_cursor` دارند. request id در header با نام
`X-Request-ID` است. زمان‌ها ISO 8601 و UTC هستند و مبلغ‌ها integer باقی می‌مانند.

### قالب خطا

هر خطا دارای این مفاهیم است:

- code پایدار و machine-readable، مانند `INSUFFICIENT_COINS`
- پیام قابل نمایش یا کلید ترجمه
- details ساختاریافته و بدون اطلاعات حساس
- request id برای پشتیبانی
- field errors برای validation

کلاینت نباید رفتار خود را بر اساس متن فارسی خطا تعیین کند؛ فقط `code` معتبر است.

### status codeها

- `200`: خواندن یا mutation هم‌زمان موفق
- `201`: resource جدید ساخته شد
- `202`: job یا عملیات async پذیرفته شد
- `204`: logout/revoke بدون body
- `400`: درخواست معنایی نامعتبر
- `401`: token نامعتبر یا منقضی
- `403`: کاربر معتبر ولی بدون مجوز یا inactive
- `404`: resource قابل مشاهده وجود ندارد
- `409`: تعارض domain یا idempotency
- `422`: validation ساختاری
- `429`: rate limit
- `503`: dependency موقتاً unavailable

### pagination

- cursor opaque و امضاشده
- ترتیب deterministic با ستون یکتا به‌عنوان tie-breaker
- `limit` با default و سقف محدود
- عدم استفاده از offset در historyهای بزرگ

### caching HTTP

- catalogها و config عمومی: `ETag` و `Cache-Control`
- داده شخصی و اقتصادی: `private, no-store` یا TTL بسیار محافظه‌کارانه
- mutation responseها cache نمی‌شوند.
- هر cache key شامل API version و schema/config version است.

## ۸. idempotency و سازگاری داده

### درخواست‌های مشمول

تمام عملیات دارای اثر باید header به نام `Idempotency-Key` داشته باشند؛ از جمله:

- خرید/فروش/ارتقا
- تعمیر و تجهیز سپر
- جمع‌آوری معدن
- شروع/تسویه مطالعه
- ثبت پاسخ
- شروع حمله
- تبادل منابع
- ثبت referral

### ذخیره‌سازی

جدول `api_idempotency_requests` شامل user، route operation، key، hash
درخواست، status، response code/body محدودشده و expiry است. unique constraint روی
ترکیب `(user_id, operation, key)` قرار می‌گیرد.

قواعد:

- همان key و همان payload: پاسخ قبلی replay می‌شود.
- همان key و payload متفاوت: `409 IDEMPOTENCY_KEY_REUSED`.
- رکورد idempotency و تغییر اقتصادی در یک transaction ثبت می‌شوند.
- Redis می‌تواند lookup را سریع کند، اما رکورد PostgreSQL مرجع نهایی است.
- کلاینت برای retry همان key را نگه می‌دارد و برای action جدید key جدید می‌سازد.

### تراکنش و lock

- یک request domain برابر یک transaction دیتابیس است.
- row lockهای فعلی برای موجودی و resourceهای رقابتی حفظ می‌شوند.
- ترتیب lock بین userها و resourceها ثابت و مستند می‌ماند.
- external API call داخل transaction طولانی دیتابیس انجام نمی‌شود.
- event/notification پس از commit از outbox پردازش می‌شود.

### concurrency response

در تعارض قابل انتظار، API خطای domain پایدار می‌دهد؛ برای مثال
`ATTACK_IN_PROGRESS` یا `STUDY_ALREADY_ACTIVE`. deadlock یا serialization failure
داخلی با تعداد محدود retry و jitter مدیریت می‌شود.

## ۹. طراحی برای تعداد کاربر بالا

### اصل اول: target قابل اندازه‌گیری

«کاربر زیاد» باید قبل از production به این متغیرها تبدیل شود:

- MAU و DAU
- concurrent users پیک
- read/write requests per second
- نرخ شروع حمله، پاسخ سؤال و collect معدن
- نسبت cache hit
- اندازه دیتابیس و رشد روزانه transactionها

بدون این اعداد، ظرفیت نهایی قابل تضمین نیست؛ معماری عمداً scale افقی و قابل
اندازه‌گیری طراحی شده است.

### API scaling

- replicaهای stateless پشت load balancer
- autoscaling بر اساس CPU، latency، RPS و saturation pool
- limit سخت برای request body و timeout
- جلوگیری از N+1 query در serializerها
- endpoint تجمیعی bootstrap برای کاهش round trip اپ
- عملیات طولانی با `202 Accepted` و status endpoint

### Database scaling

ترتیب رشد:

1. index و query plan صحیح
2. pool و PgBouncer صحیح
3. حذف N+1 و کوچک‌کردن transactionها
4. cache داده‌های عمومی
5. partition/retention برای ledger، audit و eventهای بسیار بزرگ
6. read replica برای workloadهای eventual-consistent
7. vertical scaling primary
8. sharding فقط پس از اثبات محدودیت primary و طراحی کلید shard

برای داده‌های اقتصادی read-after-write از primary خوانده می‌شود. replica برای
موجودی بلافاصله بعد از mutation استفاده نمی‌شود.

### Cache strategy

موارد مناسب cache:

- teacher/shield/study catalog
- game balance config منتشرشده
- channel subscription status با TTL کوتاه
- profileهای عمومی و opponent summary با TTL کوتاه

موارد نامناسب cache به‌عنوان مرجع:

- موجودی جاری
- active attack/study decision
- claim پاداش
- وضعیت idempotency mutation

invalidating cache با version یا event پس از commit انجام می‌شود. TTL همیشه
fallback ایمنی دارد.

### Rate limiting

چند لایه:

- edge: IP و الگوی حمله
- auth: IP، device و login attempt
- API: user id + route group
- domain: cooldown واقعی بازی در PostgreSQL

پاسخ `429` شامل زمان retry است. محدودیت‌ها برای read، mutation اقتصادی، login و
search جدا هستند. IP هرگز تنها شناسه محدودسازی نیست چون کاربران موبایل IP مشترک
دارند.

### Backpressure

- صف worker طول و oldest-job-age metric دارد.
- وقتی dependency اشباع است، درخواست جدید سریع و قابل retry رد می‌شود.
- batch size و concurrency worker مستقل تنظیم می‌شود.
- broadcast و notification نباید connection pool عملیات بازی را مصرف کنند.

## ۱۰. realtime و همگام‌سازی Flet

baseline قابل اعتماد:

- هر mutation snapshot جدید resourceهای مرتبط را برمی‌گرداند.
- endpoint `sync` تغییرات بعد از cursor را می‌دهد.
- Flet هنگام resume شدن اپ sync کامل یا delta انجام می‌دهد.
- clock سرور مبنای countdown است و پاسخ‌ها `server_time` دارند.

WebSocket یا SSE فقط برای تجربه سریع‌تر است، نه correctness. قطع realtime باید با
poll/sync جبران شود. برای Android background notification در فاز جدا push provider
اضافه می‌شود؛ Telegram notification موجود می‌تواند کانال مکمل باشد.

## ۱۱. امنیت

### مرز اعتماد

- تمام مقدارهای Flet ورودی مهاجم فرض می‌شوند.
- user id از access token استخراج می‌شود، نه body/path قابل انتخاب کاربر.
- قیمت، پاداش، damage و زمان روی سرور محاسبه می‌شوند.
- client version و platform فقط metadata هستند و منبع مجوز نیستند.

### secret management

- secretها فقط در secret manager یا environment runtime
- عدم ثبت token، authorization code، Client Secret یا اطلاعات حساس در log
- rotation دوره‌ای signing key با `kid`
- TLS اجباری و HSTS در production
- محیط‌های development، staging و production دارای bot/client/key جدا

### کنترل دسترسی

- public، authenticated، moderator و admin policyهای جدا
- endpoint ادمین روی audience/token جدا
- عملیات حساس ادمین با audit قبل/بعد، actor، reason و request id
- CORS محدود به originهای واقعی نسخه web؛ CORS جای authentication نیست.

### abuse prevention

- محدودسازی login attempt و token exchange
- detection برای refresh-token reuse
- جلوگیری از enumeration کاربر در search و خطاها
- سقف query و pagination
- replay protection با state، nonce، PKCE و idempotency
- dependency scanning و تست authorization روی همه routeها

## ۱۲. observability و SLO

### telemetry

- log ساختاریافته JSON با request id، user id داخلی hash/محدود و operation
- metrics برای RPS، error rate، p50/p95/p99، pool، query time و worker lag
- distributed trace از API تا service و query/outbox
- error tracking با حذف PII و secret

### health endpoints

- liveness فقط زنده‌بودن process را می‌سنجد.
- readiness آمادگی دریافت traffic و dependencyهای ضروری را می‌سنجد.
- metrics عمومی نیست و فقط شبکه monitoring به آن دسترسی دارد.

### SLO اولیه پیشنهادی

- availability ماهانه API: 99.9%
- p95 read داخلی: کمتر از 300ms
- p95 mutation داخلی: کمتر از 500ms
- خطای 5xx: کمتر از 0.5%

زمان Telegram و providerهای خارجی جدا اندازه‌گیری می‌شود. این اعداد پس از load
test روی زیرساخت واقعی بازتنظیم می‌شوند.

## ۱۳. استقرار

حداقل processهای production:

- `api`
- `bot`
- `attack-worker`
- `notification-worker`
- `scheduler`
- PostgreSQL مدیریت‌شده یا HA
- PgBouncer
- Redis با authentication و شبکه خصوصی
- reverse proxy/load balancer

قواعد rollout:

- migrationها backward-compatible و قبل از replica جدید اجرا شوند.
- ابتدا expand، سپس deploy، سپس backfill و در release بعد contract انجام شود.
- rolling deployment نباید دو نسخه ناسازگار schema را هم‌زمان اجرا کند.
- readiness قبل از ورود traffic و graceful drain قبل از توقف replica لازم است.
- rollback برنامه و rollback داده جدا طراحی می‌شوند؛ migration مخرب فوری ممنوع است.

## ۱۴. تغییرات لازم در کد موجود هنگام پیاده‌سازی

این سند کد ایجاد نمی‌کند، اما implementation باید این بدهی‌ها را رفع کند:

1. `UserService` دیگر `aiogram.types.User` را در مرز domain دریافت نکند.
2. serviceهای نبرد که ورودی اصلی‌شان `attacker_telegram_id` است، مسیر مبتنی بر
   `user_id` داخلی داشته باشند.
3. presentation فارسی و ساخت Telegram message از serviceها جدا بماند.
4. transaction boundary routeها در dependency/application layer واحد تعریف شود.
5. خطاهای service به error codeهای پایدار API map شوند.
6. side effect تلگرام از transaction اقتصادی با outbox جدا شود.
7. response modelها ORM object خام را serialize نکنند؛ DTO صریح داشته باشند.

## ۱۵. تصمیم‌هایی که قبل از کدنویسی نهایی باید مقداردهی شوند

- دامنه production و redirect URI تلگرام
- Android package id و شناسه برنامه‌های Desktop/Linux
- lifetime نهایی tokenها و سیاست logout
- تخمین DAU/concurrency/RPS پیک
- سقف هزینه زیرساخت
- retention تاریخچه transaction، audit و notification
- سیاست mandatory بودن عضویت کانال در اپ خارج تلگرام
- انتخاب push provider برای Android
