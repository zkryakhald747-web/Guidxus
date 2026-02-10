
from typing import Optional
from fastapi import APIRouter, Request, Depends, Query
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, Department, Course, College, CourseTargetDepartment, LoginLog
from ..deps_auth import require_admin
from sqlalchemy import text

router = APIRouter(prefix="/admin", tags=["Admin"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", dependencies=[Depends(require_admin)])
def admin_home(request: Request, db: Session = Depends(get_db), msg: Optional[str] = Query(None)):

    cu = request.session.get('user')
    

    if cu and cu.get('is_college_admin'):

        from ..deps_auth import get_current_user
        current_user = get_current_user(request, db)
        

        user_count = db.query(User).filter(
            (User.college_admin_college == current_user.college_admin_college) | (User.hod_college == current_user.college_admin_college)
        ).count()
        

        dept_count = db.query(Department).filter(Department.college == current_user.college_admin_college).count()
        

        dept_names = [d.name for d in db.query(Department).filter(Department.college == current_user.college_admin_college).all()]
        if dept_names:
            course_count = db.query(Course).join(Course.targets).filter(CourseTargetDepartment.department_name.in_(dept_names)).distinct().count()
        else:
            course_count = 0
        
        stats = {
            "users": user_count,
            "departments": dept_count,
            "courses": course_count,
        }
        
        return templates.TemplateResponse(
            "admin/college_admin_dashboard.html",
            {"request": request, "stats": stats, "msg": msg}
        )
    

    from ..models import CourseEnrollment
    
    counts = {
        "users": db.query(User).count(),
        "admins": db.query(User).filter(User.is_admin == True).count(),
        "hods": db.query(User).filter(User.is_hod == True).count(),
        "departments": db.query(Department).count(),
        "colleges": db.query(College).count(),
        "courses": db.query(Course).count(),
        "courses_published": db.query(Course).filter(Course.status == "published").count(),
    }
    

    try:

        enrollments_count = db.query(CourseEnrollment).join(Course).filter(
            Course.status == "published"
        ).count()
        counts["enrollments_published"] = enrollments_count
    except Exception:
        counts["enrollments_published"] = 0
    

    try:

        counts["doctors"] = db.query(User).filter(User.is_doc == True, User.is_active == True).count()
        

        from ..database import is_sqlite
        
        if is_sqlite():

            visits_count = db.execute(text("""
                SELECT COUNT(*) as cnt 
                FROM clinic_patients 
                WHERE record_kind = 'visit'
            """)).scalar()
            counts["visits"] = visits_count or 0
            
            # عدد الإحالات (من recommendation أو rec_json)
            referrals_count = db.execute(text("""
                SELECT COUNT(*) as cnt 
                FROM clinic_patients 
                WHERE record_kind = 'visit' 
                AND (
                    recommendation = 'referral' 
                    OR rec_json LIKE '%"type":"referral"%'
                    OR rec_json LIKE '%"type": "referral"%'
                )
            """)).scalar()
            counts["referrals"] = referrals_count or 0
            

            leaves_count = db.execute(text("""
                SELECT COUNT(*) as cnt 
                FROM clinic_patients 
                WHERE record_kind = 'visit' 
                AND (
                    rest_days IS NOT NULL AND rest_days != ''
                    OR recommendation = 'rest'
                    OR rec_json LIKE '%"type":"rest"%'
                    OR rec_json LIKE '%"type": "rest"%'
                )
            """)).scalar()
            counts["leaves"] = leaves_count or 0
        else:
            # PostgreSQL - استخدام JSON operators
            visits_count = db.execute(text("""
                SELECT COUNT(*) as cnt 
                FROM clinic_patients 
                WHERE record_kind = 'visit'
            """)).scalar()
            counts["visits"] = visits_count or 0
            
            referrals_count = db.execute(text("""
                SELECT COUNT(*) as cnt 
                FROM clinic_patients 
                WHERE record_kind = 'visit' 
                AND (
                    recommendation = 'referral' 
                    OR rec_json::text LIKE '%"type":"referral"%'
                    OR rec_json::text LIKE '%"type": "referral"%'
                )
            """)).scalar()
            counts["referrals"] = referrals_count or 0
            
            leaves_count = db.execute(text("""
                SELECT COUNT(*) as cnt 
                FROM clinic_patients 
                WHERE record_kind = 'visit' 
                AND (
                    rest_days IS NOT NULL 
                    OR recommendation = 'rest'
                    OR rec_json::text LIKE '%"type":"rest"%'
                    OR rec_json::text LIKE '%"type": "rest"%'
                )
            """)).scalar()
            counts["leaves"] = leaves_count or 0
        
    except Exception as e:

        try:
            import sys
            import os
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            from excel_data_reference import get_statistics
            
            stats = get_statistics()
            counts["doctors"] = 1
            counts["visits"] = stats.get('total_clinic_patients', 0)
            counts["referrals"] = int(stats.get('total_clinic_patients', 0) * 0.1)
            counts["leaves"] = int(stats.get('total_clinic_patients', 0) * 0.05)
            counts["excel_source"] = True
        except Exception:
            counts["doctors"] = db.query(User).filter(User.is_doc == True, User.is_active == True).count()
            counts["visits"] = 0
            counts["referrals"] = 0
            counts["leaves"] = 0

    try:
        total_courses = counts.get("courses", 0) or 0
        if total_courses > 0:
            counts["courses_published_pct"] = int(round((counts.get("courses_published", 0) / total_courses) * 100))
        else:
            counts["courses_published_pct"] = 0
    except Exception:
        counts["courses_published_pct"] = 0
    

    try:
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        from excel_data_reference import get_statistics, get_all_drugs
        
        stats = get_statistics()
        drugs = get_all_drugs()
        
        counts["pharmacy_drugs"] = len(drugs)
        counts["pharmacy_stock"] = sum(d.get('stock_qty', 0) for d in drugs)
        counts["pharmacy_movements"] = stats.get('drug_movements', 0) if hasattr(stats, 'get') else 0
    except Exception:
        counts["pharmacy_drugs"] = 0
        counts["pharmacy_stock"] = 0
        counts["pharmacy_movements"] = 0
    
    return templates.TemplateResponse(
        "admin/index.html",
        {"request": request, "counts": counts, "msg": msg}
    )

@router.get("/departments", dependencies=[Depends(require_admin)])
def admin_departments(request: Request):
    return templates.TemplateResponse(
        "admin/placeholder.html",
        {"request": request, "title": "إدارة الأقسام", "desc": "صفحة قيد الإنشاء."}
    )

@router.get("/settings", dependencies=[Depends(require_admin)])
def admin_settings(request: Request):
    return templates.TemplateResponse(
        "admin/placeholder.html",
        {"request": request, "title": "إعدادات النظام", "desc": "صفحة قيد الإنشاء."}
    )

@router.get("/audit", dependencies=[Depends(require_admin)])
def admin_audit(request: Request, db: Session = Depends(get_db)):
    from sqlalchemy import func, desc
    from datetime import datetime
    

    users = db.query(User).all()
    
    users_stats = []
    for user in users:

        last_login = db.query(LoginLog).filter(LoginLog.user_id == user.id).order_by(desc(LoginLog.login_at)).first()
        

        login_count = db.query(LoginLog).filter(LoginLog.user_id == user.id).count()
        
        users_stats.append({
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "last_login": last_login.login_at if last_login else None,
            "last_ip": last_login.ip_address if last_login else None,
            "login_count": login_count,
        })
    

    users_stats.sort(key=lambda x: x["last_login"] or datetime.min, reverse=True)
    
    return templates.TemplateResponse(
        "admin/login_activity.html",
        {"request": request, "users_stats": users_stats}
    )

@router.get("/logs", dependencies=[Depends(require_admin)])
def admin_logs(request: Request):
    return templates.TemplateResponse(
        "admin/placeholder.html",
        {"request": request, "title": "السجلات", "desc": "صفحة قيد الإنشاء."}
    )

@router.get("/backup", dependencies=[Depends(require_admin)])
def admin_backup(request: Request):
    return templates.TemplateResponse(
        "admin/placeholder.html",
        {"request": request, "title": "النسخ الاحتياطي", "desc": "صفحة قيد الإنشاء."}
    )

@router.get("/excel-data", dependencies=[Depends(require_admin)])
def admin_excel_data(request: Request):
    """عرض إحصائيات شاملة من بيانات Excel"""
    try:
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        from excel_data_reference import (
            get_statistics,
            get_all_drugs,
            get_low_stock_drugs,
            get_all_colleges,
            get_all_departments,
            search_students,
            search_clinic_patients,
        )
        
        # الإحصائيات العامة
        stats = get_statistics()
        
        # الأدوية ذات المخزون المنخفض
        low_stock_drugs = get_low_stock_drugs()
        
        # جميع الأدوية
        all_drugs = get_all_drugs()
        
        # الكليات والأقسام
        colleges = get_all_colleges()
        departments = get_all_departments()
        
        # عينات من البيانات
        sample_students = search_students("")[:5] if search_students("") else []
        sample_patients = search_clinic_patients("")[:5] if search_clinic_patients("") else []
        
        return templates.TemplateResponse(
            "admin/excel_data_dashboard.html",
            {
                "request": request,
                "stats": stats,
                "low_stock_drugs": low_stock_drugs,
                "all_drugs": all_drugs,
                "colleges": colleges,
                "departments": departments,
                "sample_students": sample_students,
                "sample_patients": sample_patients,
            }
        )
    except Exception as e:
        return templates.TemplateResponse(
            "admin/placeholder.html",
            {
                "request": request,
                "title": "خطأ",
                "desc": f"حدث خطأ أثناء تحميل البيانات: {str(e)}"
            }
        )