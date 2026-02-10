"""
سكريبت متقدم لتحميل بيانات ملف الإكسيل وربطها بقاعدة البيانات
يوفر دالات للبحث عن بيانات المتدربين والأدوية والمرضى من الإكسيل
"""

import pandas as pd
import json
from datetime import datetime
from typing import Optional, Dict, Any

# قراءة ملف الإكسيل مرة واحدة
EXCEL_FILE = 'used_tables_export.xlsx'

# تخزين البيانات في الذاكرة
_excel_data_cache = {}

def load_excel_data():
    """تحميل جميع بيانات الإكسيل في الذاكرة"""
    global _excel_data_cache
    
    if _excel_data_cache:
        return _excel_data_cache
    
    try:
        sheets = {
            'students': 'sf01',
            'drugs': 'drugs',
            'clinic_patients': 'clinic_patients',
            'courses': 'courses',
            'departments': 'departments',
            'colleges': 'colleges',
            'users': 'users',
            'drug_movements': 'drug_movements',
            'locations': 'locations',
        }
        
        for key, sheet_name in sheets.items():
            try:
                _excel_data_cache[key] = pd.read_excel(EXCEL_FILE, sheet_name=sheet_name)
                print(f"[+] Loaded {key}: {len(_excel_data_cache[key])} records")
            except Exception as e:
                print(f"[-] Failed to load {key}: {str(e)}")
                _excel_data_cache[key] = pd.DataFrame()
        
        return _excel_data_cache
    except Exception as e:
        print(f"[-] Error loading Excel file: {str(e)}")
        return {}

def get_student_by_id(student_id: str) -> Optional[Dict[str, Any]]:
    """
    البحث عن بيانات المتدرب من خلال رقمه
    
    Args:
        student_id: رقم المتدرب
    
    Returns:
        قاموس ببيانات المتدرب أو None
    """
    if 'students' not in _excel_data_cache:
        load_excel_data()
    
    students = _excel_data_cache.get('students', pd.DataFrame())
    
    # البحث عن المتدرب
    result = students[students['student_id'].astype(str).str.strip() == str(student_id).strip()]
    
    if len(result) > 0:
        return result.iloc[0].to_dict()
    
    return None

def get_student_data_as_json(student_id: str) -> Optional[str]:
    """الحصول على بيانات المتدرب بصيغة JSON"""
    student = get_student_by_id(student_id)
    if student:
        # تحويل NaN و NaT إلى None
        student = {k: (None if pd.isna(v) else v) for k, v in student.items()}
        return json.dumps(student, ensure_ascii=False, default=str)
    return None

def get_students_by_college(college_name: str) -> list:
    """الحصول على جميع متدربي كلية معينة"""
    if 'students' not in _excel_data_cache:
        load_excel_data()
    
    students = _excel_data_cache.get('students', pd.DataFrame())
    
    if 'College' not in students.columns:
        return []
    
    result = students[students['College'].astype(str).str.strip() == college_name.strip()]
    return [row.to_dict() for _, row in result.iterrows()]

def get_students_by_major(major_name: str) -> list:
    """الحصول على جميع المتدربين ذوي تخصص معين"""
    if 'students' not in _excel_data_cache:
        load_excel_data()
    
    students = _excel_data_cache.get('students', pd.DataFrame())
    
    if 'Major' not in students.columns:
        return []
    
    result = students[students['Major'].astype(str).str.strip() == major_name.strip()]
    return [row.to_dict() for _, row in result.iterrows()]

def get_drug_by_name(trade_name: str) -> Optional[Dict[str, Any]]:
    """
    البحث عن دواء باسمه التجاري
    
    Args:
        trade_name: الاسم التجاري للدواء
    
    Returns:
        قاموس ببيانات الدواء أو None
    """
    if 'drugs' not in _excel_data_cache:
        load_excel_data()
    
    drugs = _excel_data_cache.get('drugs', pd.DataFrame())
    
    result = drugs[drugs['trade_name'].astype(str).str.strip().str.lower() == trade_name.strip().lower()]
    
    if len(result) > 0:
        return result.iloc[0].to_dict()
    
    return None

def get_drug_by_generic_name(generic_name: str) -> Optional[Dict[str, Any]]:
    """البحث عن دواء باسمه العام"""
    if 'drugs' not in _excel_data_cache:
        load_excel_data()
    
    drugs = _excel_data_cache.get('drugs', pd.DataFrame())
    
    result = drugs[drugs['generic_name'].astype(str).str.strip().str.lower() == generic_name.strip().lower()]
    
    if len(result) > 0:
        return result.iloc[0].to_dict()
    
    return None

def get_all_drugs() -> list:
    """الحصول على قائمة جميع الأدوية"""
    if 'drugs' not in _excel_data_cache:
        load_excel_data()
    
    drugs = _excel_data_cache.get('drugs', pd.DataFrame())
    return [row.to_dict() for _, row in drugs.iterrows()]

def get_drug_by_code(drug_code: str) -> Optional[Dict[str, Any]]:
    """
    الحصول على بيانات الدواء من خلال الكود
    
    Args:
        drug_code: كود الدواء
    
    Returns:
        قاموس ببيانات الدواء أو None
    """
    if 'drugs' not in _excel_data_cache:
        load_excel_data()
    
    drugs = _excel_data_cache.get('drugs', pd.DataFrame())
    
    # البحث عن الدواء - المحاولة عن طريق id أولاً
    result = drugs[drugs['id'].astype(str).str.strip() == str(drug_code).strip()]
    
    if len(result) > 0:
        return result.iloc[0].to_dict()
    
    return None

def get_drug_stock(drug_code: str) -> Optional[Dict[str, Any]]:
    """
    الحصول على معلومات المخزون للدواء
    
    Args:
        drug_code: كود الدواء
    
    Returns:
        قاموس يحتوي على معلومات المخزون أو None
    """
    drug = get_drug_by_code(drug_code)
    
    if drug:
        return {
            'id': drug.get('id'),
            'trade_name': drug.get('trade_name'),
            'generic_name': drug.get('generic_name'),
            'stock_qty': drug.get('stock_qty', 0),
            'unit': drug.get('unit'),
            'reorder_level': drug.get('reorder_level', 0),
            'is_active': drug.get('is_active', True),
        }
    
    return None

def get_clinic_patient_by_trainee_no(trainee_no: str) -> Optional[Dict[str, Any]]:
    """
    الحصول على بيانات مريض العيادة باستخدام رقم المتدرب
    
    Args:
        trainee_no: رقم المتدرب
    
    Returns:
        قاموس ببيانات المريض أو None
    """
    if 'clinic_patients' not in _excel_data_cache:
        load_excel_data()
    
    patients = _excel_data_cache.get('clinic_patients', pd.DataFrame())
    
    result = patients[patients['trainee_no'].astype(str).str.strip() == str(trainee_no).strip()]
    
    if len(result) > 0:
        return result.iloc[0].to_dict()
    
    return None

def get_clinic_patients_by_college(college: str) -> list:
    """الحصول على جميع مرضى كلية معينة"""
    if 'clinic_patients' not in _excel_data_cache:
        load_excel_data()
    
    patients = _excel_data_cache.get('clinic_patients', pd.DataFrame())
    
    result = patients[patients['college'].astype(str).str.strip() == college.strip()]
    return [row.to_dict() for _, row in result.iterrows()]

def get_drug_movements_for_drug(drug_id: int) -> list:
    """الحصول على حركات الأدوية لدواء معين"""
    if 'drug_movements' not in _excel_data_cache:
        load_excel_data()
    
    movements = _excel_data_cache.get('drug_movements', pd.DataFrame())
    
    result = movements[movements['drug_id'] == drug_id]
    return [row.to_dict() for _, row in result.iterrows()]

def get_course_by_id(course_id: int) -> Optional[Dict[str, Any]]:
    """الحصول على بيانات الدورة"""
    if 'courses' not in _excel_data_cache:
        load_excel_data()
    
    courses = _excel_data_cache.get('courses', pd.DataFrame())
    
    result = courses[courses['id'] == course_id]
    
    if len(result) > 0:
        return result.iloc[0].to_dict()
    
    return None

def search_students(query: str) -> list:
    """
    البحث في بيانات المتدربين (بالاسم أو رقم المتدرب)
    
    Args:
        query: نص البحث
    
    Returns:
        قائمة بنتائج البحث
    """
    if 'students' not in _excel_data_cache:
        load_excel_data()
    
    students = _excel_data_cache.get('students', pd.DataFrame())
    query = query.strip().lower()
    
    # البحث في الاسم أو رقم المتدرب
    results = students[
        (students['student_Name'].astype(str).str.lower().str.contains(query)) |
        (students['student_id'].astype(str).str.contains(query))
    ]
    
    return [row.to_dict() for _, row in results.iterrows()]

def search_drugs(query: str) -> list:
    """
    البحث عن أدوية بالاسم التجاري أو الاسم العام
    
    Args:
        query: نص البحث
    
    Returns:
        قائمة بالأدوية المطابقة
    """
    if 'drugs' not in _excel_data_cache:
        load_excel_data()
    
    drugs = _excel_data_cache.get('drugs', pd.DataFrame())
    query = query.strip().lower()
    
    result = drugs[
        (drugs['trade_name'].astype(str).str.lower().str.contains(query, na=False)) |
        (drugs['generic_name'].astype(str).str.lower().str.contains(query, na=False))
    ]
    
    return [row.to_dict() for _, row in result.iterrows()]

def get_drugs_by_status(is_active: bool = True) -> list:
    """
    الحصول على الأدوية حسب حالتها (نشطة/غير نشطة)
    
    Args:
        is_active: True للأدوية النشطة، False للأدوية غير النشطة
    
    Returns:
        قائمة بالأدوية
    """
    if 'drugs' not in _excel_data_cache:
        load_excel_data()
    
    drugs = _excel_data_cache.get('drugs', pd.DataFrame())
    
    result = drugs[drugs['is_active'] == is_active]
    return [row.to_dict() for _, row in result.iterrows()]

def get_low_stock_drugs(threshold: int = None) -> list:
    """
    الحصول على الأدوية التي انخفض مخزونها عن الحد الأدنى
    
    Args:
        threshold: الحد الأدنى (إذا لم يتم تحديده، يستخدم reorder_level)
    
    Returns:
        قائمة بالأدوية ذات المخزون المنخفض
    """
    if 'drugs' not in _excel_data_cache:
        load_excel_data()
    
    drugs = _excel_data_cache.get('drugs', pd.DataFrame())
    
    if threshold is not None:
        result = drugs[drugs['stock_qty'] <= threshold]
    else:
        result = drugs[drugs['stock_qty'] <= drugs['reorder_level']]
    
    return [row.to_dict() for _, row in result.iterrows()]

def search_clinic_patients(query: str) -> list:
    """
    البحث عن مرضى العيادة بالاسم أو رقم المتدرب
    
    Args:
        query: نص البحث
    
    Returns:
        قائمة بنتائج البحث
    """
    if 'clinic_patients' not in _excel_data_cache:
        load_excel_data()
    
    patients = _excel_data_cache.get('clinic_patients', pd.DataFrame())
    query = query.strip().lower()
    
    result = patients[
        (patients['full_name'].astype(str).str.lower().str.contains(query, na=False)) |
        (patients['trainee_no'].astype(str).str.contains(query, na=False))
    ]
    
    return [row.to_dict() for _, row in result.iterrows()]

def get_students_by_status(status: str) -> list:
    """
    الحصول على المتدربين حسب حالتهم (نشط/خريج/متقاعد)
    
    Args:
        status: حالة المتدرب
    
    Returns:
        قائمة بالمتدربين
    """
    if 'students' not in _excel_data_cache:
        load_excel_data()
    
    students = _excel_data_cache.get('students', pd.DataFrame())
    
    result = students[students['Status'].astype(str).str.strip().str.lower() == status.strip().lower()]
    return [row.to_dict() for _, row in result.iterrows()]

def get_departments_by_college(college_name: str) -> list:
    """
    الحصول على جميع أقسام كلية معينة
    
    Args:
        college_name: اسم الكلية
    
    Returns:
        قائمة بالأقسام
    """
    if 'departments' not in _excel_data_cache:
        load_excel_data()
    
    departments = _excel_data_cache.get('departments', pd.DataFrame())
    
    result = departments[departments['college_id'].astype(str) == college_name.strip()]
    return [row.to_dict() for _, row in result.iterrows()]

def get_courses_by_department(department_name: str) -> list:
    """
    الحصول على جميع الدورات التابعة لقسم معين
    
    Args:
        department_name: اسم القسم
    
    Returns:
        قائمة بالدورات
    """
    if 'courses' not in _excel_data_cache:
        load_excel_data()
    
    courses = _excel_data_cache.get('courses', pd.DataFrame())
    
    result = courses[courses['department_id'].astype(str).str.strip().str.lower() == department_name.strip().lower()]
    return [row.to_dict() for _, row in result.iterrows()]

def get_all_colleges() -> list:
    """الحصول على جميع الكليات"""
    if 'colleges' not in _excel_data_cache:
        load_excel_data()
    
    colleges = _excel_data_cache.get('colleges', pd.DataFrame())
    return [row.to_dict() for _, row in colleges.iterrows()]

def get_all_departments() -> list:
    """الحصول على جميع الأقسام"""
    if 'departments' not in _excel_data_cache:
        load_excel_data()
    
    departments = _excel_data_cache.get('departments', pd.DataFrame())
    return [row.to_dict() for _, row in departments.iterrows()]

def get_statistics() -> Dict[str, int]:
    """الحصول على إحصائيات البيانات الموجودة في الإكسيل"""
    load_excel_data()
    
    drugs_df = _excel_data_cache.get('drugs', pd.DataFrame())
    
    return {
        'total_students': len(_excel_data_cache.get('students', pd.DataFrame())),
        'total_drugs': len(drugs_df),
        'total_active_drugs': len(drugs_df[drugs_df['is_active'] == True]),
        'total_low_stock_drugs': len(drugs_df[drugs_df['stock_qty'] <= drugs_df['reorder_level']]),
        'total_clinic_patients': len(_excel_data_cache.get('clinic_patients', pd.DataFrame())),
        'total_courses': len(_excel_data_cache.get('courses', pd.DataFrame())),
        'total_departments': len(_excel_data_cache.get('departments', pd.DataFrame())),
        'total_colleges': len(_excel_data_cache.get('colleges', pd.DataFrame())),
        'total_users': len(_excel_data_cache.get('users', pd.DataFrame())),
    }

def get_statistics_by_college(college_name: str) -> Dict[str, int]:
    """الحصول على إحصائيات حسب الكلية"""
    students = _excel_data_cache.get('students', pd.DataFrame())
    clinic_patients = _excel_data_cache.get('clinic_patients', pd.DataFrame())
    
    college_students = students[students['College'].astype(str).str.strip() == college_name.strip()]
    college_patients = clinic_patients[clinic_patients['college'].astype(str).str.strip() == college_name.strip()]
    
    return {
        'students_count': len(college_students),
        'clinic_patients_count': len(college_patients),
        'majors': college_students['Major'].unique().tolist() if len(college_students) > 0 else [],
    }

def get_statistics_by_department(department_name: str) -> Dict[str, int]:
    """الحصول على إحصائيات حسب القسم"""
    students = _excel_data_cache.get('students', pd.DataFrame())
    clinic_patients = _excel_data_cache.get('clinic_patients', pd.DataFrame())
    
    dept_students = students[students['Department'].astype(str).str.strip() == department_name.strip()]
    dept_patients = clinic_patients[clinic_patients['department'].astype(str).str.strip() == department_name.strip()]
    
    return {
        'students_count': len(dept_students),
        'clinic_patients_count': len(dept_patients),
    }

if __name__ == "__main__":
    print("=" * 60)
    print("Excel Data Reference Module")
    print("=" * 60)
    
    # تحميل البيانات
    load_excel_data()
    
    # عرض الإحصائيات
    stats = get_statistics()
    print("\nStatistics:")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    # أمثلة على الاستخدام
    print("\n\nExample Queries:")
    
    # البحث عن متدرب
    student = get_student_by_id("2101024")
    if student:
        print(f"\n✓ Found student: {student.get('student_Name')}")
    else:
        print("\n✗ Student not found")
    
    # البحث عن دواء
    drug = get_drug_by_name("Amoxicillin")
    if drug:
        print(f"✓ Found drug: {drug.get('trade_name')}")
    else:
        print("✗ Drug not found")
