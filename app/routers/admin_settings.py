
from typing import Optional, List
import json
import smtplib

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from starlette import status
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps_auth import require_admin
from ..services import settings as S
from ..models import CertificateTemplate

router = APIRouter(prefix="/admin/settings", tags=["admin-settings"])
templates = Jinja2Templates(directory="app/templates")

def _booly(v) -> bool:
    if v is None:
        return False
    return str(v).strip().lower() in {"1", "true", "yes", "on"}

def _norm(s: Optional[str]) -> str:
    return " ".join((s or "").strip().split())

def gs(db: Session, key: str, default: str = "") -> str:
    """get string"""
    try:
        return S.get_str(db, key, default)  # type: ignore[attr-defined]
    except AttributeError:
        try:
            v = S.get_value(db, key, default)  # legacy optional
            return str(v) if v is not None else default
        except AttributeError:
            return default

def gi(db: Session, key: str, default: int = 0) -> int:
    """get int (fallback from string)"""
    try:
        return S.get_int(db, key, default)
    except AttributeError:
        try:
            return int(gs(db, key, str(default)))
        except Exception:
            return int(default)

def gb(db: Session, key: str, default: bool = False) -> bool:
    """get bool (fallback from string)"""
    try:
        return S.get_bool(db, key, default)  # type: ignore[attr-defined]
    except AttributeError:
        return _booly(gs(db, key, "true" if default else "false"))

def gj(db: Session, key: str, default=None):
    """get json (list/dict) with fallback from string"""
    try:
        return S.get_json(db, key, default)
    except AttributeError:
        try:
            raw = gs(db, key, "")
            return json.loads(raw) if raw else (default if default is not None else None)
        except Exception:
            return default

def ss(db: Session, key: str, value) -> None:
    """set string"""
    val = _norm(value if value is not None else "")
    try:
        S.set_str(db, key, val)  # type: ignore[attr-defined]
    except AttributeError:
        try:
            S.set_value(db, key, val, "string")  # legacy optional
        except AttributeError:
            pass

def si(db: Session, key: str, value, default: int = 0) -> None:
    """set int as string (compatible)"""
    try:
        iv = int(value)
    except Exception:
        iv = int(default)
    ss(db, key, str(iv))

def sb(db: Session, key: str, value) -> None:
    """set bool"""
    val = _booly(value)
    try:
        S.set_bool(db, key, val)  # type: ignore[attr-defined]
    except AttributeError:
        try:
            S.set_value(db, key, "true" if val else "false", "bool")  # legacy
        except AttributeError:
            ss(db, key, "true" if val else "false")

def sj(db: Session, key: str, value) -> None:
    """set json (fallback to stringified json)"""
    try:
        S.set_json(db, key, value)
    except AttributeError:
        ss(db, key, json.dumps(value or []))

def sj_list_from_csv(db: Session, key: str, csv_or_list) -> None:
    if isinstance(csv_or_list, str):
        arr: List[str] = [x.strip() for x in csv_or_list.split(",") if x and x.strip()]
    elif isinstance(csv_or_list, list):
        arr = [str(x).strip() for x in csv_or_list if str(x).strip()]
    else:
        arr = []
    sj(db, key, arr)

def _bust_settings_cache(db: Session) -> None:
    """
    يحاول تفريغ كاش الإعدادات بعد أي حفظ:
    - ينادي invalidate_cache() لو متوفرة في الخدمات.
    - يرفع رقم نسخة cache_version في الجدول كحل مضمون.
    - يعمل commit لضمان كتابة القيمة قبل إعادة القراءة.
    """

    try:
        S.invalidate_cache()
    except Exception:
        pass

    try:
        current = gi(db, "settings.cache_version", 0)
        si(db, "settings.cache_version", current + 1, 0)
    except Exception:
        pass

    try:
        db.commit()
    except Exception:
        pass

@router.get("")
@router.get("/")
def settings_index(
    request: Request,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
    tab: Optional[str] = "general",
):
    ctx = {"request": request, "tab": tab}

    ctx.update({
        "app_name":      gs(db, "app.name", "Training Courses System"),
        "ui_footer":     gs(db, "ui.footer_text", ""),
        "ui_logo_url":   gs(db, "ui.logo_url", ""),
        "ui_favicon_url":gs(db, "ui.favicon_url", ""),
        "tz":            gs(db, "app.timezone", "Asia/Riyadh"),
        "date_fmt":      gs(db, "app.date_format", "YYYY-MM-DD"),
    })

    ctx.update({
        "lang":  gs(db, "ui.lang", "ar"),
        "theme": gs(db, "ui.theme", "light"),
    })

    ctx.update({
        "sess_ttl":            gi(db, "auth.session_ttl_minutes", 60 * 24),
        "sess_sliding":        gi(db, "auth.sliding_seconds", 15 * 60),
        "login_lock_attempts": gi(db, "auth.login_lockout_attempts", 5),
        "login_lock_window":   gi(db, "auth.login_lockout_window_minutes", 15),
    })

    ctx.update({
        "feat_admin_colleges":    gb(db, "features.admin.colleges", True),
        "feat_admin_departments": gb(db, "features.admin.departments", True),
        "feat_admin_courses":     gb(db, "features.admin.courses", True),
    })

    ctx.update({
        "course_capacity":    gi(db, "courses.default_capacity", 30),
        "course_policy":      gs(db, "courses.registration_policy", "open"),
        "course_prevent_dups":gb(db, "courses.prevent_duplicates", True),
        "course_attendance":  gs(db, "courses.attendance_verification", "paper"),
        "course_completion":  gi(db, "courses.completion_threshold", 80),
        "course_status":      gs(db, "courses.default_status", "published"),
    })

    ctx.update({
        "smtp_host": gs(db, "smtp.host", ""),
        "smtp_port": gi(db, "smtp.port", 587),
        "smtp_user": gs(db, "smtp.username", ""),
        "smtp_from": gs(db, "smtp.from_email", ""),
        "smtp_tls":  gb(db, "smtp.use_tls", True),
        "smtp_ssl":  gb(db, "smtp.use_ssl", False),
    })

    ctx.update({
        "force_https":  gb(db, "security.force_https", False),
        "cors_origins": gs(db, "security.cors_allowed_origins", ""),
    })

    ctx.update({
        "colleges_source": "departments",
        "colleges_activation_hint": "لا تُفَعَّل الكلية حتى تُكمل (عميد + وكيلي الشؤون + الاسم).",
    })

    ctx.update({
        "mnt_enabled":      gb(db, "maintenance.enabled", False),
        "mnt_title":        gs(db, "maintenance.message_title", ""),
        "mnt_body":         gs(db, "maintenance.message_body", ""),
        "mnt_admin_bypass": gb(db, "maintenance.allow_admin_bypass", True),
        "mnt_allowed_ips":  gs(db, "maintenance.allowed_ips_csv", ""),
    })

    return templates.TemplateResponse("admin/settings/index.html", ctx)

@router.post("/save")
def settings_save(
    request: Request,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
    tab: str = Form(...),

    app_name: Optional[str] = Form(None),
    ui_footer: Optional[str] = Form(None),
    ui_logo_url: Optional[str] = Form(None),
    ui_favicon_url: Optional[str] = Form(None),
    tz: Optional[str] = Form(None),
    date_fmt: Optional[str] = Form(None),

    lang: Optional[str] = Form(None),
    theme: Optional[str] = Form(None),

    sess_ttl: Optional[int] = Form(None),
    sess_sliding: Optional[int] = Form(None),
    login_lock_attempts: Optional[int] = Form(None),
    login_lock_window: Optional[int] = Form(None),

    feat_admin_colleges: Optional[str] = Form(None),
    feat_admin_departments: Optional[str] = Form(None),
    feat_admin_courses: Optional[str] = Form(None),

    course_capacity: Optional[int] = Form(None),
    course_policy: Optional[str] = Form(None),
    course_prevent_dups: Optional[str] = Form(None),
    course_attendance: Optional[str] = Form(None),
    course_completion: Optional[int] = Form(None),
    course_status: Optional[str] = Form(None),

    smtp_host: Optional[str] = Form(None),
    smtp_port: Optional[int] = Form(None),
    smtp_user: Optional[str] = Form(None),
    smtp_from: Optional[str] = Form(None),
    smtp_tls: Optional[str] = Form(None),
    smtp_ssl: Optional[str] = Form(None),

    force_https: Optional[str] = Form(None),
    cors_origins: Optional[str] = Form(None),

    mnt_enabled: Optional[str] = Form(None),
    mnt_title: Optional[str] = Form(None),
    mnt_body: Optional[str] = Form(None),
    mnt_admin_bypass: Optional[str] = Form(None),
    mnt_allowed_ips: Optional[str] = Form(None),
):
    t = (tab or "").strip().lower()

    if t == "general":
        ss(db, "app.name", app_name)
        ss(db, "ui.footer_text", ui_footer)
        ss(db, "ui.logo_url", ui_logo_url)
        ss(db, "ui.favicon_url", ui_favicon_url)
        ss(db, "app.timezone", tz)
        ss(db, "app.date_format", date_fmt)

    elif t == "localization":
        ss(db, "ui.lang",  lang or "ar")
        ss(db, "ui.theme", theme or "light")

    elif t == "auth":
        si(db, "auth.session_ttl_minutes",          sess_ttl, 1440)
        si(db, "auth.sliding_seconds",              sess_sliding, 900)
        si(db, "auth.login_lockout_attempts",       login_lock_attempts, 5)
        si(db, "auth.login_lockout_window_minutes", login_lock_window, 15)

    elif t == "roles":
        sb(db, "features.admin.colleges",    feat_admin_colleges)
        sb(db, "features.admin.departments", feat_admin_departments)
        sb(db, "features.admin.courses",     feat_admin_courses)

    elif t == "courses":
        si(db, "courses.default_capacity",        course_capacity, 30)
        ss(db, "courses.registration_policy",     course_policy or "open")
        sb(db, "courses.prevent_duplicates",      course_prevent_dups)
        ss(db, "courses.attendance_verification", course_attendance or "paper")
        si(db, "courses.completion_threshold",    course_completion, 80)
        ss(db, "courses.default_status",          course_status or "published")

    elif t == "smtp":
        ss(db, "smtp.host",       smtp_host)
        si(db, "smtp.port",       smtp_port, 587)
        ss(db, "smtp.username",   smtp_user)
        ss(db, "smtp.from_email", smtp_from)
        sb(db, "smtp.use_tls",    smtp_tls or "on")
        sb(db, "smtp.use_ssl",    smtp_ssl or "")

    elif t == "security":
        sb(db, "security.force_https",          force_https)
        ss(db, "security.cors_allowed_origins", cors_origins or "")

    elif t == "colleges":

        pass

    elif t == "maintenance":
        sb(db, "maintenance.enabled",            mnt_enabled)
        ss(db, "maintenance.message_title",      mnt_title or "")
        ss(db, "maintenance.message_body",       mnt_body or "")
        sb(db, "maintenance.allow_admin_bypass", mnt_admin_bypass or "on")
        csv = (mnt_allowed_ips or "").strip()
        ss(db, "maintenance.allowed_ips_csv", csv)
        sj_list_from_csv(db, "maintenance.allowed_ips", csv)

    _bust_settings_cache(db)

    return RedirectResponse(url=f"/admin/settings?tab={t}", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/smtp-test")
def smtp_test(
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    host    = gs(db, "smtp.host", "")
    port    = gi(db, "smtp.port", 587)
    use_ssl = gb(db, "smtp.use_ssl", False)
    timeout = 5

    if not host:
        return JSONResponse({"ok": False, "error": "لم يتم ضبط مضيف SMTP"}, status_code=400)

    try:
        if use_ssl:
            s = smtplib.SMTP_SSL(host, port, timeout=timeout)
        else:
            s = smtplib.SMTP(host, port, timeout=timeout)
            if gb(db, "smtp.use_tls", True):
                s.starttls()
        s.quit()
        return JSONResponse({"ok": True})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

@router.get("/cert-template")
def cert_tpl_form(request: Request, admin=Depends(require_admin), db: Session = Depends(get_db)):
    item = (
        db.query(CertificateTemplate)
        .filter(CertificateTemplate.scope == "global")
        .order_by(CertificateTemplate.updated_at.desc())
        .first()
    )
    return templates.TemplateResponse(
        "admin/settings/cert_template.html",
        {"request": request, "item": item}
    )

@router.post("/cert-template")
def cert_tpl_save(
    request: Request,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
    name: str = Form(...),
    content_html: str = Form(...),
    is_active: Optional[str] = Form(""),
):
    item = (
        db.query(CertificateTemplate)
        .filter(CertificateTemplate.scope == "global")
        .order_by(CertificateTemplate.updated_at.desc())
        .first()
    )
    if not item:
        item = CertificateTemplate(
            scope="global",
            name=_norm(name),
            content_html=content_html,
            is_active=_booly(is_active),
        )
        db.add(item)
    else:
        item.name = _norm(name)
        item.content_html = content_html
        item.is_active = _booly(is_active)
    db.commit()
    return RedirectResponse(url="/admin/settings/cert-template", status_code=status.HTTP_303_SEE_OTHER)