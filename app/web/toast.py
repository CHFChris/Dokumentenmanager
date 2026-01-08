from __future__ import annotations

import base64
import json
from typing import Literal, Optional

from starlette.responses import Response


ToastLevel = Literal["success", "error", "warning", "info"]


def _b64url_encode(data: bytes) -> str:
    s = base64.urlsafe_b64encode(data).decode("ascii")
    return s.rstrip("=")


def set_toast_cookie(
    resp: Response,
    *,
    message: str,
    level: ToastLevel = "info",
    title: Optional[str] = None,
    max_age_seconds: int = 20,
) -> None:
    """Schreibt genau eine Toast-Nachricht in ein Cookie.

    Das Cookie ist NICHT httponly, damit die UI es per JS lesen und danach loeschen kann.
    Es enthaelt keine sensitiven Daten.
    """
    payload = {"level": level, "message": message}
    if title:
        payload["title"] = title

    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    value = _b64url_encode(raw)

    resp.set_cookie(
        key="dm_toast",
        value=value,
        max_age=max_age_seconds,
        path="/",
        httponly=False,
        samesite="lax",
        secure=False,
    )