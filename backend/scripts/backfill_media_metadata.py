"""Backfill MediaAsset.asset_metadata for existing media rows."""

import asyncio
import logging
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select  # noqa: E402

from app.database import async_session  # noqa: E402
from app.models.media import MediaAsset  # noqa: E402
from app.services.media_metadata import probe_audio, probe_image, probe_video  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)


async def backfill_media_metadata() -> None:
    updated = 0
    skipped = 0
    failed = 0

    async with async_session() as db:
        result = await db.execute(
            select(MediaAsset).where(MediaAsset.asset_metadata.is_(None))
        )
        assets = result.scalars().all()

        for asset in assets:
            file_path = Path(asset.file_path)
            if not file_path.exists():
                logger.warning("Skipping missing file for asset %s: %s", asset.id, file_path)
                skipped += 1
                continue

            metadata = _probe_asset(asset.file_type, file_path)
            if metadata is None:
                failed += 1
                continue

            asset.asset_metadata = metadata
            updated += 1

        await db.commit()

    logger.info(
        "Media metadata backfill complete: %s updated, %s skipped, %s failed",
        updated,
        skipped,
        failed,
    )


def _probe_asset(file_type: str, file_path: Path) -> dict | None:
    if file_type == "image":
        return probe_image(file_path)
    if file_type == "video":
        return probe_video(file_path)
    if file_type == "audio":
        return probe_audio(file_path)
    return None


if __name__ == "__main__":
    asyncio.run(backfill_media_metadata())
