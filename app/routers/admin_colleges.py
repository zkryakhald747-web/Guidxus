from typing import Optional, List, Dict
from pathlib import Path
import os, secrets

from fastapi import APIRouter, Depends, Request, Form, HTTPException, UploadFile, File
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from starlette import status

from ..database import get_db
from ..deps_auth import require_admin, require_user, CurrentUser, get_current_user
from ..models import Department, College

router = APIRouter(prefix="/admin/colleges", tags=["admin-colleges"])
templates = Jinja2Templates(directory="app/templates")

STATIC_ROOT = Path("app/static").resolve()
UPLOAD_ROOT = STATIC_ROOT / "uploads" / "colleges"
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".webp"}

def _safe_save(college_id: int, up: UploadFile | None, prefix: str) -> Optional[str]:
    """يحفظ ملفًا اختياريًا ويعيد مسارًا نسبيًا عبر الويب /static/... أو None."""
    if not up or not getattr(up, "filename", None):
        return None
    ext = os.path.splitext(up.filename)[1].lower()
    if ext not in ALLOWED_EXT:
        return None
    dest_dir = UPLOAD_ROOT / str(college_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    rnd = secrets.token_hex(6)
    fname = f"{prefix}-{rnd}{ext}"
    dest_path = dest_dir / fname
    with open(dest_path, "wb") as f:
        f.write(up.file.read())
    return f"/static/uploads/colleges/{college_id}/{fname}"

# -------- Helpers --------
def normalize(s: Optional[str]) -> str:
    if not s:
        return ""
    return " ".join(str(s).strip().split())

def deps_count_map_norm(db: Session) -> Dict[str, int]:
    rows = (
        db.query(Department.college, func.count(Department.id))
        .filter(Department.college.isnot(None))
        .filter(func.trim(Department.college) != "")
        .group_by(Department.college)
        .all()
    )
    out: Dict[str, int] = {}
    for name, cnt in rows:
        key = normalize(name)
        if key:
            out[key] = out.get(key, 0) + int(cnt or 0)
    return out

def get_distinct_dept_colleges_norm(db: Session) -> List[str]:
    rows = (
        db.query(Department.college)
        .filter(Department.college.isnot(None))
        .filter(func.trim(Department.college) != "")
        .distinct()
        .all()
    )
    names = [normalize(r[0]) for r in rows if r and r[0]]
    return sorted({n for n in names if n})

def ensure_unique_name(db: Session, name: str, exclude_id: Optional[int] = None) -> bool:
    """التحقق من أن الاسم فريد (بعد التطبيع)"""
    normalized_name = normalize(name)
    if not normalized_name:
        return True
    

    all_colleges = db.query(College).all()
    for college in all_colleges:
        if exclude_id and college.id == exclude_id:
            continue
        if normalize(college.name) == normalized_name:
            return False
    return True

def fields_complete(name: str, *args, **kwargs) -> bool:
    return bool(normalize(name))

@router.get("")
@router.get("/")
def colleges_list(
    request: Request,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
    q: Optional[str] = None,
):

    current_user = get_current_user(request, db)
    if current_user and current_user.is_college_admin and current_user.college_admin_college:
        db_items: List[College] = (
            db.query(College)
            .filter(College.name == current_user.college_admin_college)
            .order_by(College.name.asc())
            .all()
        )
    else:
        db_items: List[College] = db.query(College).order_by(College.name.asc()).all()
    existing_norm = {normalize(c.name): c for c in db_items}

    dept_names = get_distinct_dept_colleges_norm(db)

    items: List[dict] = []
    for c in db_items:
        items.append({
            "id": c.id,
            "name": c.name,
            "name_en": getattr(c, "name_en", None),
            "name_print_ar": getattr(c, "name_print_ar", None),
            "dean_name": c.dean_name,
            "vp_students_name": c.vp_students_name,
            "vp_trainers_name": c.vp_trainers_name,
            "is_active": bool(c.is_active),
            "is_virtual": False,
            "dean_sign_path": getattr(c, "dean_sign_path", None),
            "vp_students_sign_path": getattr(c, "vp_students_sign_path", None),
            "students_affairs_stamp_path": getattr(c, "students_affairs_stamp_path", None),
        })

    if not (current_user and current_user.is_college_admin):
        for name in dept_names:
            if name not in existing_norm:
                items.append({
                    "id": None,
                    "name": name,
                    "name_en": None,
                    "name_print_ar": None,
                    "dean_name": None,
                    "vp_students_name": None,
                    "vp_trainers_name": None,
                    "is_active": False,
                    "is_virtual": True,
                    "dean_sign_path": None,
                    "vp_students_sign_path": None,
                    "students_affairs_stamp_path": None,
                })

    if q:
        ql = q.strip()
        items = [it for it in items if ql in it["name"]]

    items.sort(key=lambda x: normalize(x["name"]))
    dep_counts_norm = deps_count_map_norm(db)

    return templates.TemplateResponse(
        "admin/colleges_list.html",
        {
            "request": request,
            "items": items,
            "q": q or "",
            "dep_counts_norm": dep_counts_norm,
            "error": None,
        },
    )

@router.get("/new")
def college_new_form(
    request: Request,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):

    cu = get_current_user(request, db)
    if cu and cu.is_college_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="صلاحية إنشاء كلية للسوبر أدمن فقط")
    preset_name = request.query_params.get("name", "") or ""
    preset_name = normalize(preset_name)
    return templates.TemplateResponse(
        "admin/college_form.html",
        {"request": request, "mode": "create", "item": None, "preset_name": preset_name, "error": None},
    )

@router.post("/new")
def college_create(
    request: Request,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
    name: str = Form(...),
    name_en: Optional[str] = Form(None),
    name_print_ar: Optional[str] = Form(None),
    dean_name: Optional[str] = Form(None),
    vp_students_name: Optional[str] = Form(None),
    vp_trainers_name: Optional[str] = Form(None),
    is_active: Optional[str] = Form("on"),
    dean_sign: UploadFile = File(None),
    vp_students_sign: UploadFile = File(None),
    students_affairs_stamp: UploadFile = File(None),
):

    cu = get_current_user(request, db)
    if cu and cu.is_college_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="صلاحية إنشاء كلية للسوبر أدمن فقط")
    name_n = normalize(name)
    dean_n = normalize(dean_name) or None
    vp_st_n = normalize(vp_students_name) or None
    vp_tr_n = normalize(vp_trainers_name) or None
    name_en_n = normalize(name_en) or None
    name_print_ar_n = normalize(name_print_ar) or None

    if not name_n:
        return templates.TemplateResponse(
            "admin/college_form.html",
            {"request": request, "mode": "create", "item": None, "preset_name": name_n, "error": "اسم الكلية مطلوب."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if not ensure_unique_name(db, name_n):
        return templates.TemplateResponse(
            "admin/college_form.html",
            {"request": request, "mode": "create", "item": None, "preset_name": name_n, "error": "اسم الكلية موجود مسبقًا."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    active = fields_complete(name_n, dean_n, vp_st_n, vp_tr_n) and (str(is_active).lower() in ("on", "1", "true", "yes"))

    item = College(
        name=name_n,
        name_en=name_en_n,
        name_print_ar=(name_print_ar_n or name_n),
        dean_name=dean_n,
        vp_students_name=vp_st_n,
        vp_trainers_name=vp_tr_n,
        is_active=active,
    )
    db.add(item)
    db.commit()

    dean_sign_path = _safe_save(item.id, dean_sign, "dean-sign")
    vp_sign_path   = _safe_save(item.id, vp_students_sign, "vp-students-sign")
    stamp_path     = _safe_save(item.id, students_affairs_stamp, "students-affairs-stamp")

    if dean_sign_path: item.dean_sign_path = dean_sign_path
    if vp_sign_path:   item.vp_students_sign_path = vp_sign_path
    if stamp_path:     item.students_affairs_stamp_path = stamp_path

    db.commit()

    return RedirectResponse(url="/admin/?msg=تم+إنشاء+الكلية+بنجاح", status_code=status.HTTP_303_SEE_OTHER)

@router.get("/{cid}/edit")
def college_edit_form(
    cid: int,
    request: Request,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    item = db.get(College, cid)
    if not item:
        raise HTTPException(status_code=404, detail="الكلية غير موجودة")

    cu = get_current_user(request, db)
    if cu and cu.is_college_admin and cu.college_admin_college and normalize(item.name) != normalize(cu.college_admin_college):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="صلاحية التعديل مقتصرة على كليتك")
    return templates.TemplateResponse(
        "admin/college_form.html",
        {"request": request, "mode": "edit", "item": item, "preset_name": "", "error": None},
    )

@router.post("/{cid}/edit")
def college_update(
    cid: int,
    request: Request,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
    name: str = Form(...),
    name_en: Optional[str] = Form(None),
    name_print_ar: Optional[str] = Form(None),
    dean_name: Optional[str] = Form(None),
    vp_students_name: Optional[str] = Form(None),
    vp_trainers_name: Optional[str] = Form(None),
    is_active: Optional[str] = Form("on"),
    dean_sign: UploadFile = File(None),
    vp_students_sign: UploadFile = File(None),
    students_affairs_stamp: UploadFile = File(None),
):
    item = db.get(College, cid)
    if not item:
        raise HTTPException(status_code=404, detail="الكلية غير موجودة")

    cu = get_current_user(request, db)
    if cu and cu.is_college_admin and cu.college_admin_college and normalize(item.name) != normalize(cu.college_admin_college):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="صلاحية التعديل مقتصرة على كليتك")

    name_n = normalize(name)
    dean_n = normalize(dean_name) or None
    vp_st_n = normalize(vp_students_name) or None
    vp_tr_n = normalize(vp_trainers_name) or None
    name_en_n = normalize(name_en) or None
    name_print_ar_n = normalize(name_print_ar) or None

    if not name_n:
        return templates.TemplateResponse(
            "admin/college_form.html",
            {"request": request, "mode": "edit", "item": item, "preset_name": "", "error": "اسم الكلية مطلوب."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if not ensure_unique_name(db, name_n, exclude_id=item.id):
        return templates.TemplateResponse(
            "admin/college_form.html",
            {"request": request, "mode": "edit", "item": item, "preset_name": "", "error": "اسم الكلية موجود مسبقًا."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    item.name = name_n
    item.name_en = name_en_n
    item.name_print_ar = (name_print_ar_n or item.name_print_ar or name_n)
    item.dean_name = dean_n
    item.vp_students_name = vp_st_n
    item.vp_trainers_name = vp_tr_n
    item.is_active = fields_complete(name_n) and (str(is_active).lower() in ("on", "1", "true", "yes"))

    dean_sign_path = _safe_save(item.id, dean_sign, "dean-sign")
    if dean_sign_path:
        item.dean_sign_path = dean_sign_path

    vp_sign_path = _safe_save(item.id, vp_students_sign, "vp-students-sign")
    if vp_sign_path:
        item.vp_students_sign_path = vp_sign_path

    stamp_path = _safe_save(item.id, students_affairs_stamp, "students-affairs-stamp")
    if stamp_path:
        item.students_affairs_stamp_path = stamp_path

    db.commit()
    return RedirectResponse(url="/admin/colleges", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/{cid}/toggle$")
def college_toggle(
    cid: int,
    admin=Depends(require_admin),
    user: CurrentUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    item = db.get(College, cid)

    if item:
        if user.is_college_admin and user.college_admin_college and normalize(item.name) != normalize(user.college_admin_college):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="صلاحية التبديل مقتصرة على كليتك")

        if not fields_complete(item.name):
            item.is_active = False
        else:
            item.is_active = not bool(item.is_active)
        db.commit()
    return RedirectResponse(url="/admin/colleges", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/{cid}/delete")
def college_delete(
    cid: int,
    admin=Depends(require_admin),
    user: CurrentUser = Depends(require_user),
    db: Session = Depends(get_db),
):
    item = db.get(College, cid)
    if not item:
        return RedirectResponse(url="/admin/colleges", status_code=status.HTTP_303_SEE_OTHER)

    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="صلاحية الحذف للسوبر أدمن فقط")
    db.delete(item)
    db.commit()
    return RedirectResponse(url="/admin/colleges", status_code=status.HTTP_303_SEE_OTHER)