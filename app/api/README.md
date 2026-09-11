# مرز ماژول API

این پوشه در حال حاضر فقط blueprint معماری است و کد اجرایی ندارد. هنگام شروع
پیاده‌سازی، ساختار زیر به‌تدریج ایجاد می‌شود؛ فقط پوشه‌های موردنیاز همان فاز ساخته
می‌شوند.

```text
app/api/
├── main.py                    # ASGI entry point؛ بدون اجرای bot/worker
├── application.py             # app factory، router registration و lifespan
├── config.py                  # تنظیمات مخصوص HTTP/auth؛ مبتنی بر environment
├── dependencies/
│   ├── auth.py                # current user/session و policyها
│   ├── database.py            # request-scoped session/transaction
│   ├── idempotency.py         # mutation guard و replay
│   └── pagination.py          # cursor و limitهای مشترک
├── middleware/
│   ├── request_id.py          # correlation id
│   ├── access_log.py          # structured access log با redaction
│   ├── rate_limit.py          # policy توزیع‌شده
│   └── security_headers.py     # headerهای production
├── auth/
│   ├── telegram_oidc.py       # OIDC/PKCE/JWKS adapter
│   ├── tokens.py              # access/refresh signing و validation
│   ├── sessions.py            # device session و rotation/revoke
│   └── policies.py            # authenticated/admin/inactive policies
├── routers/
│   ├── health.py              # live/ready
│   ├── meta.py                # version و maintenance metadata
│   ├── auth.py                # login/refresh/logout
│   ├── bootstrap.py           # read model کمینه اپ
│   ├── profile.py
│   ├── economy.py
│   ├── teachers.py
│   ├── castle.py
│   ├── shields.py
│   ├── mine.py
│   ├── study.py
│   ├── questions.py
│   ├── quests.py
│   ├── battles.py
│   ├── buffet.py
│   ├── referrals.py
│   ├── subscription.py
│   └── notifications.py
├── schemas/
│   ├── common.py              # envelope، error و metadata
│   ├── auth.py
│   ├── profile.py
│   ├── economy.py
│   ├── school.py
│   ├── battle.py
│   ├── activity.py
│   └── notification.py
├── presenters/
│   ├── profile.py             # domain DTO → API schema
│   ├── school.py
│   ├── battle.py
│   └── activity.py
├── errors/
│   ├── codes.py               # error codeهای پایدار
│   ├── mapper.py              # service exception → HTTP error
│   └── handlers.py            # validation/unhandled exception handlers
└── observability/
    ├── logging.py
    ├── metrics.py
    └── tracing.py
```

## جهت dependency

```text
app.api → app.services → app.repositories → app.models/app.db
```

موارد ممنوع:

- `app.services` نباید `app.api` را import کند.
- `app.bot` و `app.api` نباید یکدیگر را import کنند.
- router نباید مستقیماً query اقتصادی بنویسد.
- presenter نباید transaction یا side effect داشته باشد.
- schema API نباید همان ORM model تلقی شود.

## جای مدل‌های جدید

مدل‌های persistent عمومی در `app/models` باقی می‌مانند، از جمله:

- identity و auth session
- idempotency request
- audit event
- sync/event cursor در صورت نیاز

repository آنها در `app/repositories` و use case آنها در `app/services` یا یک
application layer مشترک قرار می‌گیرد. قرار دادن منطق persistent داخل `app/api/auth`
ممنوع است؛ `app/api/auth` فقط adapter امنیتی HTTP/OIDC است.

## جای تست‌ها

```text
tests/api/
├── contract/
├── integration/
├── security/
└── performance/
```

تست‌های domain فعلی در `tests/unit` باقی می‌مانند. تست route جای تست service را
نمی‌گیرد؛ هر کدام مرز متفاوتی را پوشش می‌دهند.

## مرجع کامل

- `docs/api/ARCHITECTURE.md`
- `docs/api/ROUTES_V1.md`
- `docs/api/IMPLEMENTATION_PLAN.md`
