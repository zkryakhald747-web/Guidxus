from typing import Optional, List
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import RedirectResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from starlette import status

from ..database import get_db
from ..deps_auth import require_admin, get_current_user
from ..models import Department, User, College

router = APIRouter(prefix="/admin/departments", tags=["admin-departments"])
templates = Jinja2Templates(directory="app/templates")

def normalize(s: Optional[str]) -> str:
    """قص المسافات الزائدة وتطبيع النص للمقارنة والتخزين"""
    if not s:
        return ""
    return " ".join(str(s).strip().split())

def get_distinct_colleges(db: Session) -> List[str]:
    """جلب الكليات من جدول colleges أولاً، ثم من departments.college كبديل"""

    colleges_from_table = db.query(College.name).filter(College.is_active == True).order_by(College.name.asc()).all()
    college_names = [normalize(c[0]) for c in colleges_from_table if c and c[0]]
    

    dept_colleges = (
        db.query(Department.college)
        .filter(Department.college.isnot(None))
        .filter(Department.college != "")
        .distinct()
        .all()
    )
    dept_names = [normalize(r[0]) for r in dept_colleges if r and r[0]]
    

    all_colleges = sorted(set(college_names + dept_names))
    return [c for c in all_colleges if c]

def ensure_unique_name_in_college(
    db: Session, name: str, college: str, exclude_id: Optional[int] = None
) -> bool:
    q = db.query(Department).filter(
        func.trim(func.replace(Department.name, "  ", " ")) == normalize(name),
        func.trim(func.replace(Department.college, "  ", " ")) == normalize(college),
    )
    if exclude_id:
        q = q.filter(Department.id != exclude_id)
    return not db.query(q.exists()).scalar()

@router.get("")
@router.get("/")
def departments_list(
    request: Request,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
    college: Optional[str] = None,
    q: Optional[str] = None,
):

    current_user = get_current_user(request, db)
    if current_user and current_user.is_college_admin and current_user.college_admin_college:

        college = normalize(current_user.college_admin_college)
    
    colleges = get_distinct_colleges(db)

    query = (
        db.query(Department)
        .options(joinedload(Department.head_user))
        .order_by(Department.name.asc())
    )
    if college:
        query = query.filter(
            func.trim(func.replace(Department.college, "  ", " ")) == normalize(college)
        )
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(Department.name.ilike(like))

    deps = query.all()
    return templates.TemplateResponse(
        "admin/departments_list.html",
        {
            "request": request,
            "departments": deps,
            "colleges": colleges,
            "selected_college": college or "",
            "q": q or "",
        },
    )

@router.get("/new")
def department_new_form(
    request: Request,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
    college: Optional[str] = None,
):
    cu = get_current_user(request, db)
    if cu and cu.is_college_admin and cu.college_admin_college:
        colleges = [normalize(cu.college_admin_college)]
        college = normalize(cu.college_admin_college)
    else:
        colleges = get_distinct_colleges(db)
    return templates.TemplateResponse(
        "admin/department_form.html",
        {
            "request": request,
            "mode": "create",
            "dept": None,
            "colleges": colleges,
            "selected_college": college or "",
            "error": None,
        },
    )

@router.post("/new")
def department_create(
    request: Request,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
    name: str = Form(...),
    college: str = Form(...),
    hod_name: Optional[str] = Form(None),
    head_user_id: Optional[int] = Form(None),
    is_active: Optional[str] = Form("on"),
):
    name_n = normalize(name)
    college_n = normalize(college)
    hod_name_n = normalize(hod_name)

    cu = get_current_user(request, db)
    if cu and cu.is_college_admin and cu.college_admin_college and normalize(cu.college_admin_college) != college_n:
        return templates.TemplateResponse(
            "admin/department_form.html",
            {
                "request": request,
                "mode": "create",
                "dept": None,
                "colleges": [normalize(cu.college_admin_college)],
                "selected_college": normalize(cu.college_admin_college),
                "error": "مسموح بإضافة أقسام في كليتك فقط",
            },
            status_code=status.HTTP_403_FORBIDDEN,
        )

    if not name_n or not college_n:
        return templates.TemplateResponse(
            "admin/department_form.html",
            {
                "request": request,
                "mode": "create",
                "dept": None,
                "colleges": get_distinct_colleges(db),
                "selected_college": college_n,
                "error": "الاسم والكلية حقول مطلوبة.",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if not ensure_unique_name_in_college(db, name_n, college_n):
        return templates.TemplateResponse(
            "admin/department_form.html",
            {
                "request": request,
                "mode": "create",
                "dept": None,
                "colleges": get_distinct_colleges(db),
                "selected_college": college_n,
                "error": "اسم القسم موجود مسبقًا في نفس الكلية.",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    head_user = None
    if head_user_id:
        head_user = db.query(User).get(head_user_id)
        if not head_user:
            return PlainTextResponse("المستخدم المحدد غير موجود", status_code=400)

    dep = Department(
        name=name_n,
        college=college_n,
        hod_name=hod_name_n or None,
        head_user_id=head_user.id if head_user else None,
        is_active=True
        if (is_active and str(is_active).lower() in ("on", "1", "true", "yes"))
        else False,
    )
    db.add(dep)
    db.commit()

    return RedirectResponse(url="/admin/?msg=تم+إنشاء+القسم+بنجاح", status_code=status.HTTP_303_SEE_OTHER)

@router.get("/{dep_id}/edit")
def department_edit_form(
    dep_id: int,
    request: Request,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
):
    dep = db.get(Department, dep_id)
    if not dep:
        raise HTTPException(status_code=404, detail="القسم غير موجود")
    cu = get_current_user(request, db)
    if cu and cu.is_college_admin and cu.college_admin_college and normalize(dep.college) != normalize(cu.college_admin_college):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="صلاحية التعديل مقتصرة على أقسام كليتك")
    colleges = [normalize(cu.college_admin_college)] if (cu and cu.is_college_admin and cu.college_admin_college) else get_distinct_colleges(db)
    return templates.TemplateResponse(
        "admin/department_form.html",
        {
            "request": request,
            "mode": "edit",
            "dept": dep,
            "colleges": colleges,
            "selected_college": dep.college,
            "error": None,
        },
    )

@router.post("/{dep_id}/edit")
def department_update(
    dep_id: int,
    request: Request,
    admin=Depends(require_admin),
    db: Session = Depends(get_db),
    name: str = Form(...),
    college: str = Form(...),
    hod_name: Optional[str] = Form(None),
    head_user_id: Optional[int] = Form(None),
    is_active: Optional[str] = Form("on"),
):
    dep = db.get(Department, dep_id)
    if not dep:
        raise HTTPException(status_code=404, detail="القسم غير موجود")
    cu = get_current_user(request, db)

    if cu and cu.is_college_admin and cu.college_admin_college:
        if normalize(dep.college) != normalize(cu.college_admin_college):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="صلاحية التعديل مقتصرة على أقسام كليتك")

    name_n = normalize(name)
    college_n = normalize(college)
    hod_name_n = normalize(hod_name)

    if cu and cu.is_college_admin and cu.college_admin_college and college_n != normalize(cu.college_admin_college):
        return templates.TemplateResponse(
            "admin/department_form.html",
            {
                "request": request,
                "mode": "edit",
                "dept": dep,
                "colleges": [normalize(cu.college_admin_college)],
                "selected_college": normalize(cu.college_admin_college),
                "error": "غير مسموح بنقل القسم إلى كلية أخرى",
            },
            status_code=status.HTTP_403_FORBIDDEN,
        )

    if not name_n or not college_n:
        return templates.TemplateResponse(
            "admin/department_form.html",
            {
                "request": request,
                "mode": "edit",
                "dept": dep,
                "colleges": get_distinct_colleges(db),
                "selected_college": college_n,
                "error": "الاسم والكلية حقول مطلوبة.",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if not ensure_unique_name_in_college(db, name_n, college_n, exclude_id=dep.id):
        return templates.TemplateResponse(
            "admin/department_form.html",
            {
                "request": request,
                "mode": "edit",
                "dept": dep,
                "colleges": get_distinct_colleges(db),
                "selected_college": college_n,
                "error": "اسم القسم موجود مسبقًا في نفس الكلية.",
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    head_user = None
    if head_user_id:
        head_user = db.query(User).get(head_user_id)
        if not head_user:
            return PlainTextResponse("المستخدم المحدد غير موجود", status_code=400)

    dep.name = name_n
    dep.college = college_n
    dep.hod_name = hod_name_n or None
    dep.head_user_id = head_user.id if head_user else None
    dep.is_active = (
        True
        if (is_active and str(is_active).lower() in ("on", "1", "true", "yes"))
        else False
    )

    db.commit()
    return RedirectResponse(
        url=f"/admin/departments?college={college_n}",
        status_code=status.HTTP_303_SEE_OTHER,
    )

@router.post("/{dep_id}/toggle")
def department_toggle(
    dep_id: int, admin=Depends(require_admin), db: Session = Depends(get_db), request: Request = None
):
    dep = db.get(Department, dep_id)
    if dep:

        if request:
            cu = get_current_user(request, db)
            if cu and cu.is_college_admin and cu.college_admin_college and normalize(dep.college) != normalize(cu.college_admin_college):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="صلاحية التبديل مقتصرة على أقسام كليتك")
        dep.is_active = not bool(dep.is_active)
        db.commit()
    return RedirectResponse(
        url=f"/admin/departments?college={dep.college if dep else ''}",
        status_code=status.HTTP_303_SEE_OTHER,
    )

@router.post("/{dep_id}/delete")
def department_delete(
    dep_id: int, admin=Depends(require_admin), db: Session = Depends(get_db), request: Request = None
):
    dep = db.get(Department, dep_id)
    if dep:

        if request:
            cu = get_current_user(request, db)
            if cu and cu.is_college_admin and cu.college_admin_college and normalize(dep.college) != normalize(cu.college_admin_college):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="صلاحية الحذف مقتصرة على أقسام كليتك")

        db.delete(dep)
        db.commit()
    return RedirectResponse(
        url="/admin/departments", status_code=status.HTTP_303_SEE_OTHER
    )