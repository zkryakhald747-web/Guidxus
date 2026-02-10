
import os
import time
from dotenv import load_dotenv

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, FileResponse, Response, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette import status
from app.routers import verify

load_dotenv()
APP_NAME = os.getenv("APP_NAME", "Training Courses System")
DEBUG = os.getenv("DEBUG", "true").strip().lower() in ("1", "true", "yes")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
SESSION_MAX_AGE_DAYS = int(os.getenv("SESSION_MAX_AGE_DAYS", "7"))
SLIDING_TOUCH_SECONDS = 15 * 60
HTTPS_ONLY = os.getenv("HTTPS_ONLY", "false").strip().lower() in ("1", "true", "yes")

from .database import Base, engine, SessionLocal
from . import models
from .services import settings as S

from .routers import auth as auth_router
from .routers import hod as hod_router
from .routers import admin as admin_router
from .routers import admin_users as admin_users_router
from .routers import admin_departments as admin_departments_router
from .routers import admin_colleges as admin_colleges_router
from .routers import admin_settings as admin_settings_router
from .routers import clinic as clinic_router
from .routers import pharmacy as pharmacy_router
from .routers import first_aid as first_aid_router
from .routers import inventory as inventory_router
from .routers import profile as profile_router
from .routers import excel_api as excel_api_router

from .middlewares.maintenance import MaintenanceMiddleware

app = FastAPI(title=APP_NAME, debug=DEBUG)

app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    max_age=SESSION_MAX_AGE_DAYS * 24 * 3600,
    same_site="lax",
    https_only=HTTPS_ONLY,
)

app.add_middleware(MaintenanceMiddleware)

class SessionHelperMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        session = request.scope.get("session") or {}
        request.state.current_user = session.get("user")

        if session:
            try:
                last_touch = session.get("last_touch", 0)
                now = int(time.time())
                if now - last_touch >= SLIDING_TOUCH_SECONDS:
                    session["last_touch"] = now
            except Exception:
                pass

        response = await call_next(request)

        try:
            if hasattr(response, "template") and hasattr(response, "context") and isinstance(response.context, dict):

                if request.state.current_user:
                    response.context.setdefault("current_user", request.state.current_user)
                else:
                    response.context.setdefault("current_user", None)

                db = SessionLocal()
                try:
                    app_name       = S.get_str(db, "app.name", "Training Courses System")
                    ui_footer      = S.get_str(db, "ui.footer_text", "")
                    ui_logo_url    = S.get_str(db, "ui.logo_url", "")
                    ui_favicon_url = S.get_str(db, "ui.favicon_url", "")
                finally:
                    db.close()

                response.context.setdefault("app_name", app_name)
                response.context.setdefault("ui_footer", ui_footer)
                response.context.setdefault("ui_logo_url", ui_logo_url)
                response.context.setdefault("ui_favicon_url", ui_favicon_url)
        except Exception:
            pass

        return response

app.add_middleware(SessionHelperMiddleware)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

from jinja2 import Environment
def first_letter(text):
    """استخراج أول حرف من النص"""
    if not text:
        return "؟"
    return str(text)[0].upper()

# تسجيل الفلتر
templates.env.filters['first_letter'] = first_letter
import itertools

def _flatten_filter(value):
    """Flatten an iterable of iterables into a single list for Jinja templates.

    - Treats strings as atomic (not iterables to flatten).
    - Skips None values.
    """
    try:
        def to_iter(x):
            if x is None:
                return []
            if isinstance(x, (str, bytes)):
                return [x]
            try:
                iter(x)
                return x
            except TypeError:
                return [x]

        return list(itertools.chain.from_iterable(to_iter(v) for v in value))
    except Exception:
        return []

templates.env.filters['flatten'] = _flatten_filter

# ── إنشاء الجداول (مرة أولى) ────────────────────────────
Base.metadata.create_all(bind=engine)

# ── تضمين الراوترات (⚠️ الترتيب يهم) ────────────────────
app.include_router(auth_router.router)
app.include_router(profile_router.router)  # الملف الشخصي
app.include_router(hod_router.router)

# المسارات المتخصصة أولًا
app.include_router(admin_users_router.router)         # /admin/users
app.include_router(admin_departments_router.router)   # /admin/departments
app.include_router(admin_colleges_router.router)      # /admin/colleges
app.include_router(admin_settings_router.router)      # /admin/settings
app.include_router(clinic_router.router)
app.include_router(pharmacy_router.router)
app.include_router(first_aid_router.router)
app.include_router(inventory_router.router)
app.include_router(excel_api_router.router)            # Excel Data API
app.include_router(verify.router)
# ثم الراوتر العام
app.include_router(admin_router.router)               # /admin/...

# ────────────────────────────────────────────────────────
# PDF Export for Skills Record (direct endpoint)
# ────────────────────────────────────────────────────────
@app.get("/hod/skills-record-pdf/{trainee_no}")
def export_skills_record_pdf(trainee_no: str):
    """Export trainee skills record as PDF"""
    try:
        from sqlalchemy import text
        from xhtml2pdf import pisa
        
        db = SessionLocal()
        

        query = text(f"""
        SELECT trainee_no, trainee_name 
        FROM course_enrollments 
        WHERE trainee_no = '{trainee_no}' 
        LIMIT 1
        """)
        result = db.execute(query).first()
        
        if not result:
            db.close()
            return PlainTextResponse("متدرب غير موجود", status_code=404)
        
        # Create simple HTML
        html_str = f"""
        <!DOCTYPE html>
        <html dir="rtl">
        <head>
            <meta charset="UTF-8">
            <title>تقرير</title>
        </head>
        <body>
            <h1>تقرير سجل المهارات</h1>
            <p>الرقم: {result[0]}</p>
            <p>الاسم: {result[1]}</p>
        </body>
        </html>
        """
        

        pdf_bytes = io.BytesIO()
        pisa.CreatePDF(html_str.encode('utf-8'), dest=pdf_bytes)
        pdf_bytes.seek(0)
        db.close()
        
        return StreamingResponse(
            pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=report_{trainee_no}.pdf"}
        )
    except Exception as e:
        return PlainTextResponse(f"خطأ: {str(e)}", status_code=500)

@app.get("/health", include_in_schema=False)
def health():
    return {"ok": True}

@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    path = "app/static/images/favicon.ico"
    if os.path.exists(path):
        return FileResponse(path)
    return Response(status_code=204)

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == status.HTTP_401_UNAUTHORIZED:
        return RedirectResponse(
            url=f"/auth/login?next={request.url.path}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    if exc.status_code == status.HTTP_403_FORBIDDEN:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    if exc.status_code == status.HTTP_404_NOT_FOUND:
        if request.url.path == "/favicon.ico":
            return Response(status_code=404)
        return PlainTextResponse("الصفحة غير موجودة", status_code=404)
    return PlainTextResponse(str(exc.detail or "خطأ"), status_code=exc.status_code)

@app.get("/", include_in_schema=False)
def index(request: Request):
    u = (request.scope.get("session") or {}).get("user")
    if not u:
        return RedirectResponse("/auth/login", status_code=303)

    is_admin = bool(u.get("is_admin"))
    is_hod   = bool(u.get("is_hod"))
    is_doc   = bool(u.get("is_doc"))

    if is_doc:
        return RedirectResponse("/clinic/", status_code=303)
    if is_hod:
        return RedirectResponse("/hod/", status_code=303)
    if is_admin:
        return RedirectResponse("/admin/", status_code=303)

    return RedirectResponse("/admin/", status_code=303)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)