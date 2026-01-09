# app/services/trash_service.py
from __future__ import annotations

import asyncio

from app.db.database import SessionLocal
from app.repositories.document_repo import purge_expired_deleted_documents


TRASH_RETENTION_DAYS = 30
CLEANUP_INTERVAL_SECONDS = 24 * 60 * 60  # 24h


def _purge_once() -> int:
    db = SessionLocal()
    try:
        return purge_expired_deleted_documents(
            db,
            older_than_days=TRASH_RETENTION_DAYS,
            batch_size=200,
        )
    finally:
        db.close()


async def _cleanup_loop() -> None:
    # Einmal direkt beim Start aufräumen
    try:
        purged = _purge_once()
        if purged:
            print(f"[TRASH] {purged} Dokument(e) endgültig gelöscht (Startlauf)")
    except Exception as exc:
        print(f"[TRASH] Fehler im Startlauf: {exc!r}")

    # Danach regelmäßig
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
        try:
            purged = _purge_once()
            if purged:
                print(f"[TRASH] {purged} Dokument(e) endgültig gelöscht")
        except Exception as exc:
            print(f"[TRASH] Fehler im Cleanup: {exc!r}")


def start_trash_cleanup_task() -> None:
    asyncio.create_task(_cleanup_loop())
