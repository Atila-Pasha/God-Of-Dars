from __future__ import annotations

import base64
import hashlib
import hmac
import json

from app.api.errors import APIError
from app.core.config import settings


class CursorCodec:
    @staticmethod
    def _secret() -> bytes:
        value = settings.API_JWT_SECRET
        if not value or len(value.encode()) < 32:
            raise APIError(
                503, "API_AUTH_NOT_CONFIGURED", "سامانه هنوز پیکربندی نشده است."
            )
        return value.encode()

    @classmethod
    def encode(cls, *, resource: str, last_id: int) -> str:
        body = json.dumps(
            {"r": resource, "id": last_id}, separators=(",", ":"), sort_keys=True
        ).encode()
        payload = base64.urlsafe_b64encode(body).rstrip(b"=")
        signature = hmac.new(cls._secret(), payload, hashlib.sha256).digest()
        return f"{payload.decode()}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"

    @classmethod
    def decode(cls, value: str | None, *, resource: str) -> int | None:
        if value is None:
            return None
        try:
            payload, encoded_signature = value.split(".", 1)
            expected = hmac.new(
                cls._secret(), payload.encode(), hashlib.sha256
            ).digest()
            supplied = base64.urlsafe_b64decode(
                encoded_signature + "=" * (-len(encoded_signature) % 4)
            )
            if not hmac.compare_digest(expected, supplied):
                raise ValueError
            data = json.loads(
                base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
            )
            if data.get("r") != resource or int(data["id"]) <= 0:
                raise ValueError
            return int(data["id"])
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise APIError(400, "CURSOR_INVALID", "نشانگر صفحه معتبر نیست.") from exc
