# app/web/routes_favorites.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_web, CurrentUser
from app.db.database import get_db
from app.services.favorite_service import toggle_favorite, set_favorite, list_favorite_documents
from app.services.audit_log_service import log_event_safe

router = APIRouter()


@router.post("/documents/{document_id}/favorite-toggle", include_in_schema=False)
def web_toggle_favorite_alias(
    request: Request,
    document_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user_web),
):
    try:
        doc = toggle_favorite(db, document_id=document_id, owner_user_id=current_user.id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden")

    # Audit-Log: Favorit toggeln (success)
    log_event_safe(
        db,
        actor_user_id=current_user.id,
        action="document.favorite.toggle",
        entity_type="document",
        entity_id=doc.id,
        outcome="success",
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    accept = request.headers.get("accept", "")
    if "application/json" in accept.lower() or request.headers.get("x-requested-with"):
        return JSONResponse({"document_id": doc.id, "is_favorite": bool(doc.is_favorite)})

    referer = request.headers.get("referer") or "/documents"
    return RedirectResponse(url=referer, status_code=303)


@router.post("/documents/{document_id}/favorite/toggle", include_in_schema=False)
def web_toggle_favorite(
    request: Request,
    document_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user_web),
):
    try:
        doc = toggle_favorite(db, document_id=document_id, owner_user_id=current_user.id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden")

    # Audit-Log: Favorit toggeln (success)
    log_event_safe(
        db,
        actor_user_id=current_user.id,
        action="document.favorite.toggle",
        entity_type="document",
        entity_id=doc.id,
        outcome="success",
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    accept = request.headers.get("accept", "")
    if "application/json" in accept.lower() or request.headers.get("x-requested-with"):
        return JSONResponse({"document_id": doc.id, "is_favorite": bool(doc.is_favorite)})

    referer = request.headers.get("referer") or "/documents"
    return RedirectResponse(url=referer, status_code=303)


@router.post("/documents/{document_id}/favorite", include_in_schema=False)
def web_set_favorite(
    request: Request,
    document_id: int,
    is_favorite: bool,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user_web),
):
    try:
        doc = set_favorite(
            db,
            document_id=document_id,
            owner_user_id=current_user.id,
            is_favorite=is_favorite,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden")

    # Audit-Log: Favorit explizit setzen (success)
    log_event_safe(
        db,
        actor_user_id=current_user.id,
        action="document.favorite.set",
        entity_type="document",
        entity_id=doc.id,
        outcome="success",
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    accept = request.headers.get("accept", "")
    if "application/json" in accept.lower() or request.headers.get("x-requested-with"):
        return JSONResponse({"document_id": doc.id, "is_favorite": bool(doc.is_favorite)})

    referer = request.headers.get("referer") or "/documents"
    return RedirectResponse(url=referer, status_code=303)


@router.get("/favorites", include_in_schema=False)
def web_list_favorites(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user_web),
):
    docs = list_favorite_documents(db, owner_user_id=current_user.id, limit=200, offset=0)
    return [{"id": d.id, "filename": d.filename, "is_favorite": bool(d.is_favorite)} for d in docs]
