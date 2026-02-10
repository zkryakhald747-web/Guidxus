from typing import Optional, List
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from starlette import status

from ..database import get_db
from ..models import User, Department, College
from ..deps_auth import require_user_manager, get_current_user, require_admin
from ..security import hash_password

router = APIRouter(prefix="/admin/users", tags=["admin-users"])
templates = Jinja2Templates(directory="app/templates")

def to_bool(value: Optional[str]) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "on", "yes", "y"}

def normalize_text(s: Optional[str]) -> str:
    """يطبع النص: يقص الطرفين ويطوي المسافات الداخلية."""
    if not s:
        return ""
    return " ".join(str(s).strip().split())

def get_colleges(db: Session) -> List[str]:
    """يرجع قائمة الكليات من جدول colleges أولاً، ثم من Department.college كبديل"""

    colleges_from_table = db.query(College.name).filter(College.is_active == True).order_by(College.name.asc()).all()
    college_names = [normalize_text(c[0]) for c in colleges_from_table if c and c[0]]
    

    dept_colleges = (
        db.query(Department.college)
        .filter(Department.college.isnot(None))
        .filter(Department.college != "")
        .distinct()
        .all()
    )
    dept_names = [normalize_text(r[0]) for r in dept_colleges if r and r[0]]
    

    all_colleges = sorted(set(college_names + dept_names))
    return [c for c in all_colleges if c]

def get_all_departments(db: Session) -> List[Department]:
    """جلب جميع الأقسام النشطة من جميع الكليات"""
    return (
        db.query(Department)
        .filter(Department.is_active == True)
        .order_by(Department.college.asc(), Department.name.asc())
        .all()
    )

def get_departments_by_college(db: Session, college_name: str) -> List[Department]:
    """جلب جميع الأقسام من كلية معينة"""
    normalized_college = normalize_text(college_name)
    return (
        db.query(Department)
        .filter(Department.is_active == True)
        .all()
    )

@router.get("")
@router.get("/")
def users_list(
    request: Request,
    cu=Depends(require_user_manager),
    q: Optional[str] = None,
    db: Session = Depends(get_db),
):
    current_user = get_current_user(request, db)
    
    query = db.query(User)
    

    if current_user and current_user.is_college_admin and current_user.college_admin_college:

        college_name = normalize_text(current_user.college_admin_college)
        

        dept_ids = [d.id for d in db.query(Department).filter(
            func.trim(func.replace(Department.college, "  ", " ")) == college_name
        ).all()]
        

        head_user_ids = [d.head_user_id for d in db.query(Department).filter(
            Department.id.in_(dept_ids),
            Department.head_user_id.isnot(None)
        ).all() if d.head_user_id]
        

        query = query.filter(
            (User.college_admin_college == college_name) |
            (User.hod_college == college_name) |
            (User.id.in_(head_user_ids) if head_user_ids else False)
        )
    
    if q:
        q_like = f"%{q}%"
        query = query.filter(
            (User.username.ilike(q_like)) | (User.full_name.ilike(q_like))
        )
    users = query.order_by(User.created_at.desc()).all()
    return templates.TemplateResponse(
        "admin/users_list.html",
        {"request": request, "users": users, "q": q or ""},
    )

@router.get("/new")
def user_new_form(
    request: Request,
    cu=Depends(require_user_manager),
    db: Session = Depends(get_db),
):

    if cu.is_college_admin and cu.college_admin_college:
        colleges = [normalize_text(cu.college_admin_college)]
        departments = [
            d for d in get_all_departments(db)
            if normalize_text(d.college) == normalize_text(cu.college_admin_college)
        ]
    else:
        colleges = get_colleges(db)
        departments = get_all_departments(db)
    return templates.TemplateResponse(
        "admin/user_form.html",
        {
            "request": request,
            "mode": "create",
            "user": None,
            "colleges": colleges,
            "departments": departments,
            "current_user_role": {
                "is_admin": bool(cu.is_admin),
                "is_college_admin": bool(cu.is_college_admin),
                "is_hod": bool(cu.is_hod),
            },
            "error": None
        },
    )

@router.post("/new")
def user_create(
    request: Request,
    full_name: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    is_admin_f: Optional[str] = Form(None),
    is_college_admin_f: Optional[str] = Form(None),
    college_admin_college: Optional[str] = Form(None),
    is_hod_f: Optional[str] = Form(None),
    hod_college: Optional[str] = Form(None),
    is_doc_f: Optional[str] = Form(None),
    head_user_department_id: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    cu=Depends(require_user_manager),
):
    is_admin = to_bool(is_admin_f)
    is_college_admin = to_bool(is_college_admin_f)
    college_admin_college_norm = normalize_text(college_admin_college)
    is_hod = to_bool(is_hod_f)
    is_doc = to_bool(is_doc_f)
    colleges = get_colleges(db)
    departments = get_all_departments(db)
    selected_college = normalize_text(hod_college)

    if cu.is_hod:

        is_admin = False
        is_college_admin = False
        is_hod = False
        if not is_doc:
            return templates.TemplateResponse(
                "admin/user_form.html",
                {
                    "request": request,
                    "mode": "create",
                    "user": None,
                    "colleges": [],
                    "departments": [],
                    "error": "مسموح لرئيس القسم إضافة أطباء فقط",
                },
                status_code=status.HTTP_403_FORBIDDEN,
            )

    if cu.is_college_admin and not cu.is_admin:

        if is_admin or is_college_admin:
            return templates.TemplateResponse(
                "admin/user_form.html",
                {
                    "request": request,
                    "mode": "create",
                    "user": None,
                    "colleges": [normalize_text(cu.college_admin_college)] if cu.college_admin_college else colleges,
                    "departments": [
                        d for d in departments
                        if cu.college_admin_college and normalize_text(d.college) == normalize_text(cu.college_admin_college)
                    ],
                    "error": "غير مسموح بإضافة سوبر أدمن أو أدمن كلية",
                },
                status_code=status.HTTP_403_FORBIDDEN,
            )

        if is_hod:
            if not cu.college_admin_college:
                return templates.TemplateResponse(
                    "admin/user_form.html",
                    {
                        "request": request,
                        "mode": "create",
                        "user": None,
                        "colleges": colleges,
                        "departments": departments,
                        "error": "ملف أدمن الكلية غير مرتبط بكلية. راجع البيانات.",
                    },
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            if selected_college and normalize_text(selected_college) != normalize_text(cu.college_admin_college):
                return templates.TemplateResponse(
                    "admin/user_form.html",
                    {
                        "request": request,
                        "mode": "create",
                        "user": None,
                        "colleges": [normalize_text(cu.college_admin_college)],
                        "departments": [
                            d for d in departments
                            if normalize_text(d.college) == normalize_text(cu.college_admin_college)
                        ],
                        "selected_hod_college": normalize_text(cu.college_admin_college),
                        "error": "مسموح بإضافة رئيس قسم داخل كليتك فقط",
                    },
                    status_code=status.HTTP_403_FORBIDDEN,
                )
            selected_college = normalize_text(cu.college_admin_college)

    if is_college_admin:
        if not college_admin_college_norm:
            return templates.TemplateResponse(
                "admin/user_form.html",
                {
                    "request": request,
                    "mode": "create",
                    "user": None,
                    "colleges": colleges,
                    "departments": departments,
                    "error": "الرجاء اختيار الكلية لأدمن الكلية."
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        if college_admin_college_norm not in colleges:
            return templates.TemplateResponse(
                "admin/user_form.html",
                {
                    "request": request,
                    "mode": "create",
                    "user": None,
                    "colleges": colleges,
                    "departments": departments,
                    "error": "قيمة الكلية غير صحيحة. الرجاء الاختيار من القائمة."
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if is_admin:
            is_admin = False
    

    if is_college_admin and is_hod:
        return templates.TemplateResponse(
            "admin/user_form.html",
            {
                "request": request,
                "mode": "create",
                "user": None,
                "colleges": colleges,
                "departments": departments,
                "error": "لا يمكن أن يكون المستخدم أدمن كلية ورئيس قسم في نفس الوقت."
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if is_hod:
        if not selected_college:
            return templates.TemplateResponse(
                "admin/user_form.html",
                {
                    "request": request,
                    "mode": "create",
                    "user": None,
                    "colleges": colleges,
                    "departments": departments,
                    "selected_hod_college": selected_college,
                    "error": "الرجاء اختيار الكلية لرئيس القسم."
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        if selected_college not in colleges:
            return templates.TemplateResponse(
                "admin/user_form.html",
                {
                    "request": request,
                    "mode": "create",
                    "user": None,
                    "colleges": colleges,
                    "departments": departments,
                    "selected_hod_college": selected_college,
                    "error": "قيمة الكلية غير صحيحة. الرجاء الاختيار من القائمة."
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )
    else:
        selected_college = None

    head_department = None
    if head_user_department_id and head_user_department_id.strip():
        try:
            dept_id = int(head_user_department_id.strip())
            head_department = db.query(Department).filter(Department.id == dept_id).first()
            if not head_department:
                return templates.TemplateResponse(
                    "admin/user_form.html",
                    {
                        "request": request,
                        "mode": "create",
                        "user": None,
                        "colleges": colleges,
                        "departments": departments,
                        "selected_hod_college": selected_college,
                        "error": "القسم المحدد غير موجود."
                    },
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
        except (ValueError, TypeError):

            head_department = None
    
    try:
        u = User(
            full_name=full_name.strip(),
            username=username.strip(),
            password_hash=hash_password(password),
            is_admin=is_admin,
            is_college_admin=is_college_admin,
            college_admin_college=college_admin_college_norm if is_college_admin else None,
            is_hod=is_hod,
            is_doc=is_doc,
            hod_college=selected_college,
            is_active=True,
            must_change_password=True,
        )
        db.add(u)
        db.flush()
        

        if head_department:
            head_department.head_user_id = u.id
        
        db.commit()
    except IntegrityError:
        db.rollback()
        return templates.TemplateResponse(
            "admin/user_form.html",
            {
                "request": request,
                "mode": "create",
                "user": None,
                "colleges": colleges,
                "departments": departments,
                "selected_hod_college": selected_college,
                "error": "اسم المستخدم مستخدم مسبقًا. الرجاء اختيار اسم آخر."
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return RedirectResponse(url="/admin/?msg=تم+إنشاء+المستخدم+بنجاح", status_code=status.HTTP_303_SEE_OTHER)

@router.get("/{user_id}/edit")
def user_edit_form(
    user_id: int,
    request: Request,
    admin=Depends(require_user_manager),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")
    colleges = get_colleges(db)
    departments = get_all_departments(db)
    return templates.TemplateResponse(
        "admin/user_form.html",
        {
            "request": request,
            "mode": "edit",
            "user": user,
            "colleges": colleges,
            "departments": departments,
            "error": None
        },
    )

@router.post("/{user_id}/edit")
def user_update(
    user_id: int,
    request: Request,
    full_name: str = Form(...),
    username: str = Form(...),
    password: Optional[str] = Form(None),
    is_admin_f: Optional[str] = Form(None),
    is_college_admin_f: Optional[str] = Form(None),
    college_admin_college: Optional[str] = Form(None),
    is_hod_f: Optional[str] = Form(None),
    hod_college: Optional[str] = Form(None),
    head_user_department_id: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    admin=Depends(require_admin),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="المستخدم غير موجود")

    user.full_name = full_name.strip()
    user.username  = username.strip()
    if password:
        user.password_hash = hash_password(password)

    is_admin = to_bool(is_admin_f)
    is_college_admin = to_bool(is_college_admin_f)
    college_admin_college_norm = normalize_text(college_admin_college)
    is_hod   = to_bool(is_hod_f)
    
    colleges = get_colleges(db)
    departments = get_all_departments(db)
    selected_college = normalize_text(hod_college)
    

    if is_college_admin:
        if not college_admin_college_norm:
            return templates.TemplateResponse(
                "admin/user_form.html",
                {
                    "request": request,
                    "mode": "edit",
                    "user": user,
                    "colleges": colleges,
                    "departments": departments,
                    "error": "الرجاء اختيار الكلية لأدمن الكلية."
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        if college_admin_college_norm not in colleges:
            return templates.TemplateResponse(
                "admin/user_form.html",
                {
                    "request": request,
                    "mode": "edit",
                    "user": user,
                    "colleges": colleges,
                    "departments": departments,
                    "error": "قيمة الكلية غير صحيحة. الرجاء الاختيار من القائمة."
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if is_admin:
            is_admin = False
    

    if is_college_admin and is_hod:
        return templates.TemplateResponse(
            "admin/user_form.html",
            {
                "request": request,
                "mode": "edit",
                "user": user,
                "colleges": colleges,
                "departments": departments,
                "error": "لا يمكن أن يكون المستخدم أدمن كلية ورئيس قسم في نفس الوقت."
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    
    user.is_admin = is_admin
    user.is_college_admin = is_college_admin
    user.college_admin_college = college_admin_college_norm if is_college_admin else None
    user.is_hod   = is_hod

    if is_hod:
        if not selected_college:
            return templates.TemplateResponse(
                "admin/user_form.html",
                {
                    "request": request,
                    "mode": "edit",
                    "user": user,
                    "colleges": colleges,
                    "departments": departments,
                    "selected_hod_college": selected_college,
                    "error": "الرجاء اختيار الكلية لرئيس القسم."
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        if selected_college not in colleges:
            return templates.TemplateResponse(
                "admin/user_form.html",
                {
                    "request": request,
                    "mode": "edit",
                    "user": user,
                    "colleges": colleges,
                    "departments": departments,
                    "selected_hod_college": selected_college,
                    "error": "قيمة الكلية غير صحيحة. الرجاء الاختيار من القائمة."
                },
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        user.hod_college = selected_college
    else:
        user.hod_college = None
    

    db.query(Department).filter(Department.head_user_id == user_id).update({"head_user_id": None})
    

    if head_user_department_id and head_user_department_id.strip():
        try:
            dept_id = int(head_user_department_id.strip())
            head_department = db.query(Department).filter(Department.id == dept_id).first()
            if head_department:
                head_department.head_user_id = user_id
        except (ValueError, TypeError):

            pass

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return templates.TemplateResponse(
            "admin/user_form.html",
            {
                "request": request,
                "mode": "edit",
                "user": user,
                "colleges": colleges,
                "departments": departments,
                "selected_hod_college": selected_college,
                "error": "اسم المستخدم مستخدم مسبقًا. الرجاء اختيار اسم آخر."
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return RedirectResponse(url="/admin/users", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/{user_id}/delete")
def user_delete(
    user_id: int,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user:
        db.delete(user)
        db.commit()
    return RedirectResponse(url="/admin/?msg=تم+تحديث+المستخدم+بنجاح", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/{user_id}/toggle")
def user_toggle_active(
    user_id: int,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user:
        user.is_active = not bool(user.is_active)
        db.commit()
    return RedirectResponse(url="/admin/?msg=تم+تحديث+المستخدم+بنجاح", status_code=status.HTTP_303_SEE_OTHER)