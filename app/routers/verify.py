
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime
from pathlib import Path
from ..database import get_db
from ..models import Course, CourseEnrollment, College, Department

router = APIRouter(prefix="/verify", tags=["Verify"])
templates = Jinja2Templates(directory="app/templates")

SQL_VERIFY = text("""
    SELECT
      cv.course_id, cv.trainee_no, cv.trainee_name, cv.course_title, cv.hours,
      cv.start_date, cv.end_date, cv.certificate_code, cv.copy_no, cv.barcode_path,
      cv.created_at AS issued_at,
      c.provider AS college_name
    FROM certificate_verifications cv
    LEFT JOIN courses c ON cv.course_id = c.id
    WHERE cv.certificate_code = :code
    ORDER BY cv.copy_no DESC
    LIMIT 1
""")

@router.get("/{code}")
def verify_page(code: str, request: Request, db: Session = Depends(get_db)):
    row = db.execute(SQL_VERIFY, {"code": code}).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="الشهادة غير موجودة")
    
    # الحصول على بيانات الدورة الكاملة
    course = db.query(Course).filter_by(id=row["course_id"]).first()
    if not course:
        raise HTTPException(status_code=404, detail="الدورة غير موجودة")
    
    # بناء كائن trainee مشابه لما يتوقعه template
    enrollment = CourseEnrollment(
        trainee_no=row["trainee_no"],
        trainee_name=row["trainee_name"]
    )
    
    # الحصول على كلية من استنتاج أهداف الدورة (مثل hod.py)
    college = None
    college_name_from_db = None
    
    # أولاً: حاول استنتاج الكلية من أسماء الأقسام المستهدفة للدورة
    try:
        target_dept_names = [t.department_name for t in course.targets] if getattr(course, "targets", None) else []
        for dept_name in target_dept_names:
            dept = db.query(Department).filter(Department.name == dept_name).first()
            if dept and dept.college:
                matched = db.query(College).filter(College.name == dept.college).first()
                if matched:
                    college = matched
                    college_name_from_db = matched.name
                    break
    except Exception:
        college = None
    
    # ثانياً: إذا لم نجد كلية من الأهداف، حاول البحث بـ provider من الدورة أو college_name
    if not college:
        college_name_from_db = row.get("college_name") or (course.provider if course else None)
        if college_name_from_db:
            college = db.query(College).filter_by(name=college_name_from_db).first()
    
    # استخراج البيانات من الكلية
    college_name = college_name_from_db or "الكلية التقنية"
    college_name_en = (getattr(college, "name_en", None) or "") if college else ""
    
    vp_name = college.vp_students_name if college and college.vp_students_name else ""
    dean_name = college.dean_name if college and college.dean_name else ""
    vp_sign_url = college.vp_students_sign_path if college and getattr(college, "vp_students_sign_path", None) else "/static/blank.png"
    dean_sign_url = college.dean_sign_path if college and getattr(college, "dean_sign_path", None) else "/static/blank.png"
    stamp_url = college.students_affairs_stamp_path if college and getattr(college, "students_affairs_stamp_path", None) else "/static/blank.png"
    
    # barcode URL
    barcode_url = row["barcode_path"] or f"/static/barcodes/{code}.png"
    
    # بناء السياق الكامل لـ template الشهادة
    context = {
        "request": request,
        "course": course,
        "trainee": enrollment,
        "college_name": college_name,
        "college_name_en": college_name_en,
        "vp_name": vp_name,
        "dean_name": dean_name,
        "vp_sign_url": vp_sign_url,
        "dean_sign_url": dean_sign_url,
        "stamp_url": stamp_url,
        "certificate_no": code,
        "copy_no": row["copy_no"],
        "barcode_url": barcode_url,
    }
    
    return templates.TemplateResponse("hod/certificate_template.html", context)

@router.get("/api/verify")
def verify_api(code: str, db: Session = Depends(get_db)):
    row = db.execute(SQL_VERIFY, {"code": code}).mappings().first()
    if not row:
        return {"valid": False, "code": code}
    return {
        "valid": True,
        "code": row["certificate_code"],
        "copy_no": row["copy_no"],
        "trainee_no": row["trainee_no"],
        "trainee_name": row["trainee_name"],
        "course_title": row["course_title"],
        "hours": row["hours"],
        "start_date": str(row["start_date"]) if row["start_date"] else None,
        "end_date": str(row["end_date"]) if row["end_date"] else None,
        "issued_at": str(row["issued_at"]) if row.get("issued_at") else None,
    }