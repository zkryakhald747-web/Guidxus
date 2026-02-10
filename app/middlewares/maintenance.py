from typing import List
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse
from starlette.status import HTTP_503_SERVICE_UNAVAILABLE
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..services import settings as S

SAFE_PATHS = {"/favicon.ico", "/health", "/auth/login", "/auth/logout"}
SAFE_PREFIXES = ("/static/",)

def _ip_allowed(ip: str, allowed: List[str]) -> bool:

    return bool(ip) and ip in (allowed or [])

class MaintenanceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if path in SAFE_PATHS or any(path.startswith(p) for p in SAFE_PREFIXES):
            return await call_next(request)

        db: Session = SessionLocal()
        try:
            enabled = S.get_bool(db, "maintenance.enabled", False)
            allow_admin_bypass = S.get_bool(db, "maintenance.allow_admin_bypass", True)
            allowed_ips = S.get_json(db, "maintenance.allowed_ips", []) or []
            title = S.get_str(db, "maintenance.message_title", "النظام في وضع الصيانة")
            body = S.get_str(db, "maintenance.message_body", "نقوم حاليًا بأعمال صيانة. الرجاء المحاولة لاحقًا.")
        finally:
            db.close()

        if not enabled:
            return await call_next(request)

        session = request.scope.get("session") or {}
        user = session.get("user") if isinstance(session, dict) else None
        is_admin = bool(user and user.get("is_admin"))

        client_ip = request.client.host if request.client else ""

        if (allow_admin_bypass and is_admin) or _ip_allowed(client_ip, allowed_ips):
            return await call_next(request)

        html = f"""
        <!doctype html><html lang="ar" dir="rtl">
        <head>
          <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
          <title>{title}</title>
          <style>
            body{{font-family:Tahoma,Arial,sans-serif;background:
                 display:flex;align-items:center;justify-content:center;height:100vh;margin:0}}
            .box{{background:
            h1{{margin:0 0 10px;font-size:1.4rem}} p{{margin:0}}
          </style>
        </head>
        <body><div class="box"><h1>🛠️ {title}</h1><p>{body}</p></div></body></html>
        """
        return HTMLResponse(html, status_code=HTTP_503_SERVICE_UNAVAILABLE)