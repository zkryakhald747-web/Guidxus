"""
Router للبحث في بيانات الإكسيل وعرض البيانات المرجعية
"""

from fastapi import APIRouter, Query, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.deps_auth import require_doc

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from excel_data_reference import (
    get_student_by_id,
    get_drug_by_name,
    get_clinic_patient_by_trainee_no,
    search_students,
    search_drugs,
    search_clinic_patients,
    get_all_drugs,
    get_drugs_by_status,
    get_low_stock_drugs,
    get_statistics,
    get_statistics_by_college,
    get_statistics_by_department,
    get_students_by_college,
    get_students_by_status,
    get_students_by_major,
    get_departments_by_college,
    get_courses_by_department,
    get_all_colleges,
    get_all_departments,
    get_all_drugs,
    load_excel_data,
)

router = APIRouter(prefix="/api/excel", tags=["excel_reference"])

load_excel_data()

@router.get("/students/search")
def search_students_endpoint(
    q: str = Query("", min_length=1),
    limit: int = Query(10, ge=1, le=100),
    user=Depends(require_doc),
):
    """البحث عن متدرب في بيانات الإكسيل"""
    try:
        results = search_students(q)
        return JSONResponse({
            "success": True,
            "count": len(results[:limit]),
            "results": results[:limit]
        })
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=400)

@router.get("/students/{student_id}")
def get_student_data(
    student_id: str,
    user=Depends(require_doc),
):
    """الحصول على بيانات المتدرب الكاملة من الإكسيل"""
    try:
        student = get_student_by_id(student_id)
        if student:
            return JSONResponse({
                "success": True,
                "data": {k: (None if str(v) == 'nan' else v) for k, v in student.items()}
            })
        else:
            return JSONResponse({
                "success": False,
                "error": "Student not found"
            }, status_code=404)
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=400)

@router.get("/drugs/all")
def get_drugs_list(
    user=Depends(require_doc),
):
    """الحصول على قائمة الأدوية من الإكسيل"""
    try:
        drugs = get_all_drugs()
        return JSONResponse({
            "success": True,
            "count": len(drugs),
            "drugs": drugs
        })
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=400)

@router.get("/drugs/search")
def search_drugs(
    name: str = Query("", min_length=1),
    user=Depends(require_doc),
):
    """البحث عن دواء"""
    try:
        drug = get_drug_by_name(name)
        if drug:
            return JSONResponse({
                "success": True,
                "data": {k: (None if str(v) == 'nan' else v) for k, v in drug.items()}
            })
        else:
            return JSONResponse({
                "success": False,
                "error": "Drug not found"
            }, status_code=404)
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=400)

@router.get("/clinic/patients/{trainee_no}")
def get_patient_data(
    trainee_no: str,
    user=Depends(require_doc),
):
    """الحصول على بيانات المريض من سجل العيادة"""
    try:
        patient = get_clinic_patient_by_trainee_no(trainee_no)
        if patient:
            return JSONResponse({
                "success": True,
                "data": {k: (None if str(v) == 'nan' else v) for k, v in patient.items()}
            })
        else:
            return JSONResponse({
                "success": False,
                "error": "Patient not found"
            }, status_code=404)
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=400)

# ===================== الإحصائيات =====================

@router.get("/statistics")
def get_excel_statistics(user=Depends(require_doc)):
    """الحصول على إحصائيات البيانات من الإكسيل"""
    try:
        stats = get_statistics()
        return JSONResponse({
            "success": True,
            "statistics": stats
        })
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=400)

@router.get("/drugs/search/advanced")
def search_drugs_advanced(
    query: str = Query("", min_length=1),
    user=Depends(require_doc),
):
    """البحث المتقدم عن الأدوية بالاسم التجاري أو الاسم العام"""
    try:
        results = search_drugs(query)
        return JSONResponse({
            "success": True,
            "count": len(results),
            "results": results
        })
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=400)

@router.get("/drugs/low-stock")
def get_low_stock(
    threshold: int = Query(None),
    user=Depends(require_doc),
):
    """الحصول على الأدوية ذات المخزون المنخفض"""
    try:
        drugs = get_low_stock_drugs(threshold)
        return JSONResponse({
            "success": True,
            "count": len(drugs),
            "drugs": drugs
        })
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=400)

@router.get("/drugs/status/{status}")
def get_drugs_by_status_endpoint(
    status: str,
    user=Depends(require_doc),
):
    """الحصول على الأدوية حسب الحالة (نشطة/غير نشطة)"""
    try:
        is_active = status.lower() in ["active", "true", "1"]
        drugs = get_drugs_by_status(is_active)
        return JSONResponse({
            "success": True,
            "count": len(drugs),
            "drugs": drugs
        })
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=400)

# ===================== المتدربين المتقدم =====================

@router.get("/students/by-college/{college_name}")
def get_students_by_college_endpoint(
    college_name: str,
    user=Depends(require_doc),
):
    """الحصول على جميع متدربي كلية معينة"""
    try:
        students = get_students_by_college(college_name)
        return JSONResponse({
            "success": True,
            "count": len(students),
            "students": students
        })
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=400)

@router.get("/students/by-major/{major_name}")
def get_students_by_major_endpoint(
    major_name: str,
    user=Depends(require_doc),
):
    """الحصول على جميع متدربي تخصص معين"""
    try:
        students = get_students_by_major(major_name)
        return JSONResponse({
            "success": True,
            "count": len(students),
            "students": students
        })
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=400)

@router.get("/students/by-status/{status}")
def get_students_by_status_endpoint(
    status: str,
    user=Depends(require_doc),
):
    """الحصول على المتدربين حسب الحالة (نشط/خريج/متقاعد)"""
    try:
        students = get_students_by_status(status)
        return JSONResponse({
            "success": True,
            "count": len(students),
            "students": students
        })
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=400)

@router.get("/clinic/search")
def search_clinic_patients_endpoint(
    query: str = Query("", min_length=1),
    limit: int = Query(10, ge=1, le=100),
    user=Depends(require_doc),
):
    """البحث عن مريض باسمه أو رقم متدربه"""
    try:
        results = search_clinic_patients(query)
        return JSONResponse({
            "success": True,
            "count": len(results[:limit]),
            "results": results[:limit]
        })
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=400)

# ===================== الأقسام والكليات =====================

@router.get("/colleges/all")
def get_colleges_endpoint(user=Depends(require_doc)):
    """الحصول على جميع الكليات"""
    try:
        colleges = get_all_colleges()
        return JSONResponse({
            "success": True,
            "count": len(colleges),
            "colleges": colleges
        })
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=400)

@router.get("/departments/all")
def get_departments_endpoint(user=Depends(require_doc)):
    """الحصول على جميع الأقسام"""
    try:
        departments = get_all_departments()
        return JSONResponse({
            "success": True,
            "count": len(departments),
            "departments": departments
        })
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=400)

@router.get("/departments/by-college/{college_name}")
def get_departments_by_college_endpoint(
    college_name: str,
    user=Depends(require_doc),
):
    """الحصول على أقسام كلية معينة"""
    try:
        departments = get_departments_by_college(college_name)
        return JSONResponse({
            "success": True,
            "count": len(departments),
            "departments": departments
        })
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=400)

@router.get("/courses/by-department/{department_name}")
def get_courses_by_department_endpoint(
    department_name: str,
    user=Depends(require_doc),
):
    """الحصول على دورات قسم معين"""
    try:
        courses = get_courses_by_department(department_name)
        return JSONResponse({
            "success": True,
            "count": len(courses),
            "courses": courses
        })
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=400)

# ===================== الإحصائيات المتقدمة =====================

@router.get("/statistics/by-college/{college_name}")
def get_stats_by_college(
    college_name: str,
    user=Depends(require_doc),
):
    """الحصول على إحصائيات كلية معينة"""
    try:
        stats = get_statistics_by_college(college_name)
        return JSONResponse({
            "success": True,
            "statistics": stats
        })
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=400)

@router.get("/statistics/by-department/{department_name}")
def get_stats_by_department(
    department_name: str,
    user=Depends(require_doc),
):
    """الحصول على إحصائيات قسم معين"""
    try:
        stats = get_statistics_by_department(department_name)
        return JSONResponse({
            "success": True,
            "statistics": stats
        })
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=400)