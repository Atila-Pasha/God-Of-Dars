from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import NotificationStatus
from app.models.notification import Notification


class NotificationService:
    async def enqueue(
        self,
        session: AsyncSession,
        *,
        notification_type: str,
        recipient_user_id: int,
        idempotency_key: str,
        payload: dict,
    ) -> Notification | None:
        statement = (
            insert(Notification)
            .values(
                notification_type=notification_type,
                recipient_user_id=recipient_user_id,
                idempotency_key=idempotency_key,
                payload=payload,
            )
            .on_conflict_do_nothing(index_elements=[Notification.idempotency_key])
            .returning(Notification.id)
        )
        notification_id = await session.scalar(statement)
        if notification_id is None:
            return None
        return await session.get(Notification, notification_id)

    async def claim_due_batch(
        self,
        session: AsyncSession,
        *,
        now: datetime,
        stale_before: datetime,
        batch_size: int,
    ) -> list[Notification]:
        """Atomically lease due notifications without blocking peer workers."""
        rows = list(
            await session.scalars(
                select(Notification)
                .where(
                    or_(
                        and_(
                            Notification.status == NotificationStatus.PENDING,
                            or_(
                                Notification.next_attempt_at.is_(None),
                                Notification.next_attempt_at <= now,
                            ),
                        ),
                        and_(
                            Notification.status == NotificationStatus.FAILED,
                            Notification.next_attempt_at <= now,
                        ),
                        and_(
                            Notification.status == NotificationStatus.PROCESSING,
                            Notification.processing_at <= stale_before,
                        ),
                    ),
                )
                .order_by(Notification.created_at, Notification.id)
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
        )
        for row in rows:
            row.status = NotificationStatus.PROCESSING
            row.processing_at = now
            row.attempts += 1
        await session.flush()
        return rows

    async def claim_due(
        self, session: AsyncSession, *, now: datetime, stale_before: datetime
    ) -> Notification | None:
        """Claim one notification for callers that require single-item leasing."""
        rows = await self.claim_due_batch(
            session,
            now=now,
            stale_before=stale_before,
            batch_size=1,
        )
        return rows[0] if rows else None
