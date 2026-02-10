from fastapi.templating import Jinja2Templates

from fastapi import APIRouter
from fastapi import Request
from fastapi import Form, Depends
from fastapi.responses import RedirectResponse

from ..database import get_db
from sqlalchemy.orm import Session
from ..models import User, LoginLog
templates = Jinja2Templates(directory="app/templates")
from urllib.parse import urlparse
from ..security import verify_password
from starlette import status

router = APIRouter(prefix="/auth", tags=["Auth"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/change-password")
def change_password_form(request: Request):
    u = request.session.get("user")
    if not u:
        return RedirectResponse("/auth/login", status_code=303)
    return templates.TemplateResponse("auth/change_password.html", {"request": request, "error": None})

@router.post("/change-password")
def change_password_submit(request: Request, new_password: str = Form(...), db: Session = Depends(get_db)):
    u = request.session.get("user")
    if not u:
        return RedirectResponse("/auth/login", status_code=303)
    user = db.query(User).filter(User.id == u["id"]).first()
    if not user:
        return RedirectResponse("/auth/login", status_code=303)
    if not new_password or len(new_password) < 6:
        return templates.TemplateResponse("auth/change_password.html", {"request": request, "error": "كلمة المرور يجب أن تكون 6 أحرف على الأقل."})
    from ..security import hash_password
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    db.commit()

    return RedirectResponse("/", status_code=303)

def _safe_next(next_url: str | None) -> str | None:
    """
    يسمح فقط بالمسارات المحلية مثل /hod/... أو /admin/...
    ويتجاهل أي روابط خارجية لحماية الـ open redirect.
    """
    if not next_url:
        return None
    parsed = urlparse(next_url)

    if parsed.scheme or parsed.netloc:
        return None
    if not parsed.path.startswith("/"):
        return None
    return parsed.path + (f"?{parsed.query}" if parsed.query else "")

@router.get("/login")
def login_form(request: Request):
    u = request.session.get("user")
    if u:

        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("auth/login.html", {"request": request, "error": None})

@router.post("/login")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str | None = Form(default=None),
    db: Session = Depends(get_db),
):
    user: User | None = db.query(User).filter(User.username == username).first()

    if not user or not user.is_active or not verify_password(password, user.password_hash):
        next_url = _safe_next(next)
        return templates.TemplateResponse(
            "auth/login.html",
            {
                "request": request,
                "error": "بيانات الدخول غير صحيحة",
                "next": next_url,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if getattr(user, "must_change_password", False):
        request.session["user"] = {
            "id": user.id,
            "full_name": user.full_name,
            "username": user.username,
            "is_admin": bool(user.is_admin),
            "is_college_admin": bool(getattr(user, "is_college_admin", False)),
            "college_admin_college": getattr(user, "college_admin_college", None),
            "is_hod": bool(user.is_hod),
            "is_doc": bool(getattr(user, "is_doc", False)),
            "hod_college": user.hod_college,
        }

        ip_address = request.client.host if request.client else None
        login_log = LoginLog(user_id=user.id, username=user.username, ip_address=ip_address)
        db.add(login_log)
        db.commit()
        return RedirectResponse("/auth/change-password", status_code=303)

    request.session["user"] = {
        "id": user.id,
        "full_name": user.full_name,
        "username": user.username,
        "is_admin": bool(user.is_admin),
        "is_college_admin": bool(getattr(user, "is_college_admin", False)),
        "college_admin_college": getattr(user, "college_admin_college", None),
        "is_hod": bool(user.is_hod),
        "is_doc": bool(getattr(user, "is_doc", False)),
        "hod_college": user.hod_college,
    }

    ip_address = request.client.host if request.client else None
    login_log = LoginLog(user_id=user.id, username=user.username, ip_address=ip_address)
    db.add(login_log)
    db.commit()

    next_url = _safe_next(next)
    if next_url:
        dest = next_url
    elif bool(getattr(user, "is_doc", False)):
        dest = "/clinic/"
    elif bool(user.is_hod):
        dest = "/hod/"
    elif bool(getattr(user, "is_college_admin", False)):
        dest = "/admin/"
    elif bool(user.is_admin):
        dest = "/admin/"
    else:
        dest = "/"

    return RedirectResponse(url=dest, status_code=status.HTTP_303_SEE_OTHER)

@router.get("/logout")
@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)