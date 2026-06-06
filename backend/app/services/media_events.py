"""Media event helper: record and publish media asset creation events."""

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.websocket import manager as ws_manager
from app.database import MediaEvent


async def record_and_publish_media_event(
    db: AsyncSession,
    user_id: UUID,
    event_type: str,
    asset_id: UUID,
) -> int:
    """Insert a MediaEvent row and broadcast it via WebSocket.

    Returns the assigned sequence number.
    """
    seq = await ws_manager.get_next_media_seq(str(user_id))
    event = MediaEvent(
        user_id=user_id,
        event_type=event_type,
        asset_id=asset_id,
        seq=seq,
    )
    db.add(event)
    await db.commit()
    await ws_manager.broadcast_media_event(
        user_id=str(user_id),
        payload={
            "type": "media_event",
            "event_type": event_type,
            "asset_id": str(asset_id),
            "seq": seq,
            "timestamp": datetime.utcnow().isoformat(),
        }
    )
    return seq
