from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_web, CurrentUser
from app.db.database import get_db
from app.services.user_preferences_service import (
    set_dashboard_protected_view,
    toggle_dashboard_protected_view,
)

router = APIRouter()


@router.post("/profile/dashboard/protected/enable", include_in_schema=False)
def web_enable_protected_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user_web),
):
    try:
        user = set_dashboard_protected_view(db, user_id=current_user.id, enabled=True)
    except ValueError:
        raise HTTPException(status_code=404, detail="User nicht gefunden")

    accept = request.headers.get("accept", "")
    if "application/json" in accept.lower() or request.headers.get("x-requested-with"):
        return JSONResponse({"dashboard_protected_view": bool(user.dashboard_protected_view)})

    referer = request.headers.get("referer") or "/profile"
    return RedirectResponse(url=referer, status_code=303)


@router.post("/profile/dashboard/protected/disable", include_in_schema=False)
def web_disable_protected_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user_web),
):
    try:
        user = set_dashboard_protected_view(db, user_id=current_user.id, enabled=False)
    except ValueError:
        raise HTTPException(status_code=404, detail="User nicht gefunden")

    accept = request.headers.get("accept", "")
    if "application/json" in accept.lower() or request.headers.get("x-requested-with"):
        return JSONResponse({"dashboard_protected_view": bool(user.dashboard_protected_view)})

    referer = request.headers.get("referer") or "/profile"
    return RedirectResponse(url=referer, status_code=303)


@router.post("/profile/dashboard/protected/toggle", include_in_schema=False)
def web_toggle_protected_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user_web),
):
    try:
        user = toggle_dashboard_protected_view(db, user_id=current_user.id)
    except ValueError:
        raise HTTPException(status_code=404, detail="User nicht gefunden")

    accept = request.headers.get("accept", "")
    if "application/json" in accept.lower() or request.headers.get("x-requested-with"):
        return JSONResponse({"dashboard_protected_view": bool(user.dashboard_protected_view)})

    referer = request.headers.get("referer") or "/profile"
    return RedirectResponse(url=referer, status_code=303)
