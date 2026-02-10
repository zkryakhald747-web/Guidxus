from pathlib import Path
import os, tempfile, io, traceback
from datetime import date, datetime
from typing import List, Optional, Dict
from urllib.parse import urlparse, unquote, quote
from ..models import Course, CourseTargetDepartment, Department, College, User
from pathlib import Path
import qrcode
from app.services.settings import PUBLIC_BASE_URL
from ..reports.skills_record_pdf_template import SKILLS_RECORD_PDF_HTML

BARCODES_DIR = Path("app/static/barcodes")
BARCODES_DIR.mkdir(parents=True, exist_ok=True)

def ensure_barcode_png(code: str) -> str:
    """
    توليد QR code قابل للمسح يحتوي على رابط التحقق من الشهادة.
    عند مسح QR code، سيتم فتح صفحة التحقق من الشهادة (verify page).
    
    - كل شهادة لها رمز فريد (certificate_code)
    - جميع النسخ المطبوعة من نفس الشهادة تحتوي على نفس QR code
    - عند مسح QR code، يتم فتح رابط: {PUBLIC_BASE_URL}/verify/{code}
    
    Args:
        code: رمز الشهادة (مثال: "1-123456789-5")
    
    Returns:
        مسار صورة QR code (مثال: "/static/barcodes/1-123456789-5.png")
    """
    png_path = BARCODES_DIR / f"{code}.png"
    verify_url = f"{PUBLIC_BASE_URL}/verify/{code}"
    

    if png_path.exists():

        return f"/static/barcodes/{code}.png"
    

    img = qrcode.make(verify_url)
    img.save(png_path)
    return f"/static/barcodes/{code}.png"

if os.name == "nt":
    _FORCE_TMP = r"C:\x2p_tmp"
    try:
        Path(_FORCE_TMP).mkdir(parents=True, exist_ok=True)
    except Exception:
        _FORCE_TMP = tempfile.gettempdir()
else:
    _FORCE_TMP = "/tmp"

os.environ["TMPDIR"] = _FORCE_TMP
os.environ["TMP"]    = _FORCE_TMP
os.environ["TEMP"]   = _FORCE_TMP
tempfile.tempdir     = _FORCE_TMP

_old_mkstemp = tempfile.mkstemp
def _mkstemp_forced(*args, **kwargs):
    kwargs.setdefault("dir", _FORCE_TMP)
    return _old_mkstemp(*args, **kwargs)
tempfile.mkstemp = _mkstemp_forced

os.environ["PISA_TEMP_DIR"] = _FORCE_TMP

_old_ntf = tempfile.NamedTemporaryFile
def _NamedTemporaryFile_forced(*args, **kwargs):
    kwargs.setdefault("dir", _FORCE_TMP)
    if os.name == "nt":
        kwargs["delete"] = False
    return _old_ntf(*args, **kwargs)
tempfile.NamedTemporaryFile = _NamedTemporaryFile_forced

from fastapi import APIRouter, Depends, Request, Form, HTTPException, status, Query
from fastapi import Path as FastAPIPath
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, and_, text
from sqlalchemy.orm import Session, selectinload
from jinja2 import Template

try:
    from xhtml2pdf import pisa
    HAS_XHTML2PDF = True
except Exception:
    HAS_XHTML2PDF = False

try:
    import arabic_reshaper
    from bidi.algorithm import get_display as bidi_get_display
    _HAS_ARABIC_SHAPING = True
except Exception:
    _HAS_ARABIC_SHAPING = False

from ..database import get_db
from ..models import Course, CourseTargetDepartment, Department, College, User
from ..schemas import CourseCreate
from ..deps_auth import require_hod_or_admin, require_user, CurrentUser

templates = Jinja2Templates(directory="app/templates")
import itertools

def _flatten_filter(value):
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
router = APIRouter(prefix="/hod", tags=["HOD"])

def _assert_can_manage_course(user: CurrentUser, course: Course, db: Session = None):
    if user.is_admin:
        return
    if course.created_by_user_id == user.id:
        return

    if user.is_college_admin and user.college_admin_college and db:
        college_name = user.college_admin_college
        college_departments = db.query(Department).filter(Department.college == college_name).all()
        dept_names = {d.name for d in college_departments}
        course_targets = {t.department_name for t in course.targets}
        if dept_names & course_targets:
            return
    raise HTTPException(status_code=403, detail="لا تملك صلاحية إدارة هذه الدورة")

def _ctd_uses_name() -> bool:
    return hasattr(CourseTargetDepartment, "department_name")

def _link_callback(uri: str, rel: str) -> str:
    if not uri:
        return uri
    if uri.startswith("file://"):
        parsed = urlparse(uri)
        p = parsed.netloc if (parsed.netloc and not parsed.path) else parsed.path
        p = unquote(p)
        if os.name == "nt" and len(p) >= 3 and p[0] == "/" and p[2] == ":":
            p = p[1:]
        return str(Path(p).resolve())
    if uri.startswith("/static/"):
        return str(Path("app").joinpath(uri.lstrip("/")).resolve())
    return uri

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

_FONTS_REGISTERED = False
def _register_arabic_fonts_once() -> str:
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return "'ARMain','ARAlt','Arial Unicode MS','DejaVu Sans','Arial'"

    def _try(name: str, relpath: str) -> bool:
        p = Path("app/static/fonts").joinpath(relpath)
        if not p.exists():
            return False
        pdfmetrics.registerFont(TTFont(name, str(p.resolve())))
        return True

    main_candidates = ["NotoNaskhArabic-Regular.ttf","Traditional-Arabic.ttf","Amiri.ttf","Majalla.ttf","Cairo.ttf"]
    alt_candidates  = ["Amiri.ttf","Majalla.ttf","Cairo.ttf","Traditional-Arabic.ttf","NotoNaskhArabic-Regular.ttf"]
    any(_try("ARMain", fn) for fn in main_candidates)
    any(_try("ARAlt",  fn) for fn in alt_candidates)
    _FONTS_REGISTERED = True
    return "'ARMain','ARAlt','Arial Unicode MS','DejaVu Sans','Arial'"

def _shape_ar(s: Optional[str]) -> str:
    if s is None: return ""
    if not str(s).strip(): return ""
    if not _HAS_ARABIC_SHAPING: return str(s)
    try:
        return bidi_get_display(arabic_reshaper.reshape(str(s)))
    except Exception:
        return str(s)

_ROSTER_PRETTY_HTML = r"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8" />
  <title>{{ shape('كشف حضور دورة تدريبية') }} - {{ shape(course.title or '') }}</title>
  <style>
    {{ font_ready_css|safe }}
    /* brand:

    @page{
      size: A4 portrait;
      margin: 0;
      @frame header_frame  { -pdf-frame-content: header_content; left: 10mm; right: 10mm; top: 6mm;  height: 22mm; }
      @frame content_frame { left: 10mm; right: 10mm; top: 32mm; bottom: 18mm; }
      @frame footer_frame  { -pdf-frame-content: footer_content; left: 10mm; right: 10mm; bottom: 6mm; height: 10mm; }
    }

    html, body{
      direction: rtl; margin:0; padding:0;
      -webkit-print-color-adjust: exact; print-color-adjust: exact;
      color:
      font-family:'MajallaAR','TradArabicAR','Majalla','Traditional Arabic','Arial Unicode MS','DejaVu Sans','Arial';
    }
    * { font-family: inherit !important; }

    .ltr { direction:ltr; unicode-bidi:bidi-override; }

    /* ===== الهيدر المثبّت ===== */
    .hdr{ width:100%; border-collapse:collapse; table-layout:fixed; }
    .hdr td{ vertical-align:middle; padding:0; }
    .title-cell{ text-align:left; padding-right:6mm; }
    .logo-cell{ text-align:right; width:50mm; }
    .logo{ max-height:28mm; width:auto; height:auto; display:block; object-fit:contain; }
    .report-title{ font-weight:800; color:
    .title-underline{ height:3px; width:180px; background:

    /* ===== البطاقة ===== */
    .card{ background:
    .pad{ padding:10px 12px; }
    .chip{
      display:block; text-align:center; padding:2px 10px; margin:0 auto 8px;
      background:
      font-weight:700; font-size:14pt;
    }

    /* ===== جدول بيانات الدورة ===== */
    table.meta{
      width:100%; border-collapse:collapse; table-layout:fixed; border:1.2px solid
    }
    table.meta th, table.meta td{
      border:1.2px solid
      text-align:center; vertical-align:middle; font-size:11pt;
      white-space:normal; word-wrap:break-word; overflow-wrap:break-word;
      line-height:1.25;
    }
    table.meta th{ background:
    table.meta td.label{ width:12%; font-weight:700; }
    table.meta td.value{ width:38%; }

    /* ===== جدول كشف الحضور ===== */
    table.roster{
      width:100%; border-collapse:collapse; table-layout:fixed; margin-top:8px;
      border:1.2px solid
    }
    table.roster thead th{
      border:1.2px solid
      background:
      white-space:normal; word-wrap:break-word; overflow-wrap:break-word;
    }
    table.roster tbody td{
      border:1.2px solid
      font-size:11pt; white-space:normal; word-wrap:break-word; overflow-wrap:break-word; line-height:1.25;
    }

    thead{ display:table-header-group; }
    tr{ page-break-inside:avoid; }
  </style>
</head>
<body>

  <!-- الهيدر المثبّت -->
  <div id="header_content">
    <table class="hdr" dir="ltr" role="presentation" aria-hidden="true">
      <colgroup><col><col style="width:50mm"></colgroup>
      <tr>
        <td class="title-cell">
          <div class="report-title">{{ shape('كشف حضور دورة تدريبية') }}</div>
          <div class="title-underline"></div>
        </td>
        <td class="logo-cell">
          {% if logo_src %}
            <img class="logo" src="{{ logo_src }}" alt="logo">
          {% endif %}
        </td>
      </tr>
    </table>
  </div>

  <!-- المحتوى -->
  <div id="content_frame">
    <section class="card">
      <div class="pad">
        <span class="chip">{{ shape('بيانات الدورة') }}</span>

        <!-- جدول البيانات -->
        <table class="meta" role="presentation" aria-hidden="true">
          <!-- ثبّت العرض: العمود 1 و3 (label) = 10%، العمود 2 و4 (value) = 40% -->
          <colgroup>
            <col style="width:10%"><col style="width:40%">
            <col style="width:10%"><col style="width:40%">
          </colgroup>
          <tbody>
            <!-- الصف 1 -->
            <tr>
              
              <td class="value">{{ shape(((course.hours|string) if course.hours else '0') if course.hours else '0') }}</td>
              <td class="label">{{ shape('عدد الساعات') }}</td>
              
              <td class="value">{{ shape(course.title or '---') }}</td>
              <td class="label">{{ shape('اسم الدورة') }}</td>
              
            </tr>

            <!-- الصف 2 -->
            <tr>
              <td class="value">{{ shape(course.provider or '---') }}</td>
              <td class="label">{{ shape('الجهة المنفذة') }}</td>
              
              <td class="value">{{ shape(course.provider_name or '---') }}</td>
              <td class="label">{{ shape('اسم المنفذ') }}</td>

              
            </tr>

            <!-- الصف 3: التواريخ -->
            <tr>
              <td class="value ltr">{% if course.end_date %}{{ course.end_date.strftime('%d-%m-%Y') }}{% else %}---{% endif %}</td>
              <td class="label">{{ shape('تاريخ النهاية') }}</td>
              
              <td class="value ltr">{% if course.start_date %}{{ course.start_date.strftime('%d-%m-%Y') }}{% else %}---{% endif %}</td>
              <td class="label">{{ shape('تاريخ البداية') }}</td>
              
              
            </tr>
          </tbody>
        </table>

        <!-- جدول الحضور (مع عمود التخصص) -->
        <table class="roster" dir="ltr" role="table" aria-label="{{ shape('كشف حضور الدورة') }}">
          <colgroup>
            <col style="width:40mm">
            <col style="width:58mm">
            <col style="width:28mm">
            <col style="width:55mm">
            <col style="width:9mm">
          </colgroup>
          <thead>
            <tr>
              <th style="width:40mm;min-height:20px">{{ shape('توقيع المتدرب') }}</th>
              <th style="width:58mm;min-height:20px">{{ shape('التخصص') }}</th>
              <th style="width:28mm;min-height:20px">{{ shape('الرقم التدريبي') }}</th>
              <th style="width:55mm;min-height:20px">{{ shape('اسم المتدرب') }}</th>
              <th style="width:9mm;min-height:20px">{{ shape('م') }}</th>
            </tr>
          </thead>
          <tbody>
            {% if enrollments and enrollments|length > 0 %}
              {% for r in enrollments %}
                <tr>
                  <td style="min-height:20px">&nbsp;</td>
                  <td style="min-height:20px">{{ shape(r.trainee_major or '') or '&nbsp;' }}</td>
                  <td style="min-height:20px">{{ shape(r.trainee_no or '') or '&nbsp;' }}</td>
                  <td style="min-height:20px">{{ shape(r.trainee_name or '') or '&nbsp;' }}</td>
                  <td style="min-height:20px">{{ loop.index }}</td>
                </tr>
              {% endfor %}
            {% else %}
              <tr><td colspan="5" style="min-height:20px">&nbsp;</td></tr>
            {% endif %}
          </tbody>
        </table>
      </div>
    </section>
  </div>

  <!-- الفوتر المثبّت -->
  <div id="footer_content" style="text-align:center; font-size:10.5pt; color:#6b7280; border-top:1px dashed #c5d6de; padding-top:6px;">
    {{ shape('تم تصدير هذا الكشف عبر نظام خدمات المتدربين التفاعلية Guidxus') }}
  </div>

</body>
</html>
"""

# ===================== لوحة HOD =====================

@router.get("/")
def hod_home(request: Request, user: CurrentUser = Depends(require_user)):
    return templates.TemplateResponse("hod/dashboard.html", {"request": request, "current_user": user})

# ===================== إنشاء دورة =====================

@router.get("/courses/new")
def create_course_form(
    request: Request,
    edit: Optional[int] = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_hod_or_admin),
):
    if edit:
        return RedirectResponse(url=f"/hod/courses/{edit}/edit", status_code=status.HTTP_302_FOUND)

    q = db.query(Department)
    if user.is_hod and user.hod_college:
        q = q.filter(Department.college == user.hod_college)
    elif user.is_college_admin and user.college_admin_college:
        q = q.filter(Department.college == user.college_admin_college)
    departments = q.order_by(Department.name.asc()).all()

    return templates.TemplateResponse(
        "hod/create_course.html",
        {"request": request, "departments": departments, "current_user": user},
    )

@router.post("/courses/new")
def create_course_submit(
    request: Request,
    title: str = Form(...),
    description: Optional[str] = Form(None),
    provider: Optional[str] = Form(None),
    provider_name: Optional[str] = Form(None),
    hours: float = Form(...),
    mode: str = Form(...),
    start_date: date = Form(...),
    end_date: date = Form(...),
    capacity: int = Form(...),
    registration_policy: str = Form(...),
    prevent_duplicates: Optional[bool] = Form(False),
    attendance_verification: str = Form("paper"),
    completion_threshold: int = Form(80),
    create_expected_roster: Optional[bool] = Form(False),
    auto_issue_certificates: Optional[bool] = Form(False),
    target_department_ids: Optional[List[int]] = Form(None),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_hod_or_admin),
):
    payload = CourseCreate(
        title=title,
        description=description,
        provider=provider,
        provider_name=provider_name,
        hours=hours,
        mode=mode,
        start_date=start_date,
        end_date=end_date,
        capacity=capacity,
        registration_policy=registration_policy,
        prevent_duplicates=bool(prevent_duplicates),
        attendance_verification=attendance_verification,
        completion_threshold=completion_threshold,
        create_expected_roster=bool(create_expected_roster),
        auto_issue_certificates=bool(auto_issue_certificates),
        target_department_ids=[int(i) for i in (target_department_ids or [])],
    )

    if user.is_hod and user.hod_college and payload.target_department_ids:
        count_allowed = (
            db.query(Department)
            .filter(Department.id.in_(payload.target_department_ids))
            .filter(Department.college == user.hod_college)
            .count()
        )
        if count_allowed != len(payload.target_department_ids):
            raise HTTPException(status_code=403, detail="لا تملك صلاحية لاستهداف أقسام خارج كليتك")

    course = Course(
        title=payload.title,
        description=payload.description,
        provider=payload.provider,
        provider_name=payload.provider_name,
        hours=payload.hours,
        mode=payload.mode,
        start_date=payload.start_date,
        end_date=payload.end_date,
        capacity=payload.capacity,
        registration_policy=payload.registration_policy,
        prevent_duplicates=payload.prevent_duplicates,
        attendance_verification=payload.attendance_verification,
        completion_threshold=payload.completion_threshold,
        create_expected_roster=payload.create_expected_roster,
        auto_issue_certificates=payload.auto_issue_certificates,
        status="published",
        created_by_user_id=user.id,
    )
    db.add(course)
    db.flush()

    if _ctd_uses_name():
        id_to_name = {
            d.id: d.name
            for d in db.query(Department).filter(Department.id.in_(payload.target_department_ids or [])).all()
        }
        for dep_id in payload.target_department_ids or []:
            dep_name = id_to_name.get(dep_id)
            if dep_name:
                db.add(CourseTargetDepartment(course_id=course.id, department_name=dep_name))
    else:
        for dep_id in payload.target_department_ids or []:
            db.add(CourseTargetDepartment(course_id=course.id, department_id=dep_id))

    db.commit()
    return RedirectResponse(url="/hod/courses?msg=تمت+إضافة+الدورة+بنجاح", status_code=status.HTTP_303_SEE_OTHER)

# ===================== تعديل دورة =====================

@router.get("/courses/{course_id}/edit")
def edit_course_form(
    course_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_hod_or_admin),
):
    course: Course = (
        db.query(Course)
        .options(selectinload(Course.targets))
        .filter(Course.id == course_id)
        .first()
    )
    if not course:
        raise HTTPException(status_code=404, detail="الدورة غير موجودة")
    _assert_can_manage_course(user, course, db)

    q = db.query(Department)
    if user.is_hod and user.hod_college:
        q = q.filter(Department.college == user.hod_college)
    elif user.is_college_admin and user.college_admin_college:
        q = q.filter(Department.college == user.college_admin_college)
    departments = q.order_by(Department.name.asc()).all()

    if _ctd_uses_name():
        selected_names = {t.department_name for t in course.targets}
        selected_department_ids = [d.id for d in departments if d.name in selected_names]
    else:
        selected_department_ids = [t.department_id for t in course.targets]

    return templates.TemplateResponse(
        "hod/create_course.html",
        {"request": request, "current_user": user, "departments": departments, "edit_mode": True, "course": course, "selected_department_ids": selected_department_ids},
    )

@router.post("/courses/{course_id}/edit")
def edit_course_submit(
    course_id: int,
    request: Request,
    title: str = Form(...),
    description: Optional[str] = Form(None),
    provider: Optional[str] = Form(None),
    provider_name: Optional[str] = Form(None),
    hours: float = Form(...),
    mode: str = Form(...),
    start_date: date = Form(...),
    end_date: date = Form(...),
    capacity: int = Form(...),
    registration_policy: str = Form(...),
    prevent_duplicates: Optional[bool] = Form(False),
    attendance_verification: str = Form("paper"),
    completion_threshold: int = Form(80),
    create_expected_roster: Optional[bool] = Form(False),
    auto_issue_certificates: Optional[bool] = Form(False),
    target_department_ids: Optional[List[int]] = Form(None),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_hod_or_admin),
):
    course: Course = (
        db.query(Course)
        .options(selectinload(Course.targets))
        .filter(Course.id == course_id)
        .first()
    )
    if not course:
        raise HTTPException(status_code=404, detail="الدورة غير موجودة")
    _assert_can_manage_course(user, course, db)

    course.title = title
    course.description = description
    course.provider = provider
    course.provider_name = provider_name
    course.hours = hours
    course.mode = mode
    course.start_date = start_date
    course.end_date = end_date
    course.capacity = capacity
    course.registration_policy = registration_policy
    course.prevent_duplicates = bool(prevent_duplicates)
    course.attendance_verification = attendance_verification
    course.completion_threshold = completion_threshold
    course.create_expected_roster = bool(create_expected_roster)
    course.auto_issue_certificates = bool(auto_issue_certificates)

    for t in list(course.targets):
        db.delete(t)
    if _ctd_uses_name():
        if target_department_ids:
            id_to_name = {d.id: d.name for d in db.query(Department).filter(Department.id.in_(target_department_ids)).all()}
            for dep_id in target_department_ids:
                dep_name = id_to_name.get(dep_id)
                if dep_name:
                    db.add(CourseTargetDepartment(course_id=course.id, department_name=dep_name))
    else:
        for dep_id in target_department_ids or []:
            db.add(CourseTargetDepartment(course_id=course.id, department_id=dep_id))

    db.commit()
    return RedirectResponse(url="/hod/courses?updated=1", status_code=status.HTTP_303_SEE_OTHER)

# ===================== قائمة الدورات =====================

@router.get("/courses")
def course_list(
    request: Request,
    q: str = Query("", description="بحث بعنوان الدورة"),
    status_filter: Optional[str] = Query(None, pattern=r"^(published|closed|finished)$"),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_hod_or_admin),
):
    q_courses = db.query(Course).options(selectinload(Course.targets))
    if not user.is_admin:
        if user.is_college_admin and user.college_admin_college:
            # College admin sees only courses targeting their college's departments
            college_name = user.college_admin_college
            college_departments = db.query(Department).filter(Department.college == college_name).all()
            dept_names = [d.name for d in college_departments]
            if dept_names:
                q_courses = q_courses.join(CourseTargetDepartment).filter(CourseTargetDepartment.department_name.in_(dept_names)).distinct()
            else:
                # College has no departments, show no courses
                q_courses = q_courses.filter(Course.id == -1)
        else:
            # HOD sees only their own courses
            q_courses = q_courses.filter(Course.created_by_user_id == user.id)

    if status_filter:
        q_courses = q_courses.filter(Course.status == status_filter)
    if date_from:
        q_courses = q_courses.filter(Course.start_date >= date_from)
    if date_to:
        q_courses = q_courses.filter(Course.end_date <= date_to)
    if q.strip():
        q_courses = q_courses.filter(Course.title.ilike(f"%{q.strip()}%"))

    q_courses = q_courses.order_by(Course.start_date.desc(), Course.id.desc())
    courses = q_courses.all()

    course_targets: Dict[int, List[str]] = {}
    if _ctd_uses_name():
        for c in courses:
            names = [t.department_name for t in c.targets if t.department_name]
            seen = set()
            course_targets[c.id] = [n for n in names if not (n in seen or seen.add(n))]
    else:
        dep_map = {d.id: d.name for d in db.query(Department).all()}
        for c in courses:
            names = [dep_map.get(t.department_id, "") for t in c.targets]
            seen = set()
            course_targets[c.id] = [n for n in names if n and not (n in seen or seen.add(n))]

    counts_rows = db.execute(text("""SELECT course_id, COUNT(*) AS cnt FROM course_enrollments GROUP BY course_id""")).fetchall()
    counts_map = {row[0]: int(row[1]) for row in counts_rows}
    for c in courses:
        setattr(c, "registered_count", counts_map.get(c.id, 0))

    dep_query = db.query(Department)
    if user.is_hod and user.hod_college:
        dep_query = dep_query.filter(Department.college == user.hod_college)
    elif user.is_college_admin and user.college_admin_college:
        dep_query = dep_query.filter(Department.college == user.college_admin_college)
    departments = dep_query.order_by(Department.name.asc()).all()

    owner_scope = db.query(Course)
    if not user.is_admin:
        owner_scope = owner_scope.filter(Course.created_by_user_id == user.id)
    kpis = {
        "total_active": owner_scope.filter(Course.status == "published").count(),
        "running_now": owner_scope.filter(and_(Course.start_date <= func.current_date(), Course.end_date >= func.current_date())).count(),
        "pending_attendance": 0,
    }

    return templates.TemplateResponse(
        "hod/course_list.html",
        {"request": request, "current_user": user, "courses": courses, "course_targets": course_targets, "departments": departments, "filters": {"q": q, "status_filter": status_filter, "date_from": date_from, "date_to": date_to}, "kpis": kpis},
    )

# ===================== الحضور =====================

@router.get("/attendance/{course_id}")
def attendance_page(
    course_id: int,
    request: Request,
    trainee_no: Optional[str] = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_hod_or_admin),
):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="الدورة غير موجودة")
    _assert_can_manage_course(user, course, db)

    enrollments = db.execute(
        text("""
            SELECT e.trainee_no, e.trainee_name, e.trainee_major, e.status, e.present
            FROM course_enrollments e
            WHERE e.course_id = :cid
            ORDER BY CASE WHEN e.trainee_name IS NULL THEN 1 ELSE 0 END, e.trainee_name, e.trainee_no
        """),
        {"cid": course.id},
    ).mappings().all()

    student = None
    if trainee_no:
        try:
            row = db.execute(
                text("""
                    SELECT student_id, "student_Name" AS student_name, "Major" AS major
                    FROM sf01 WHERE student_id = :sid LIMIT 1
                """),
                {"sid": int(trainee_no)},
            ).mappings().first()
            if row:
                student = dict(row)
        except Exception:
            # جدول sf01 قد لا يكون موجود
            student = None

    return templates.TemplateResponse(
        "hod/attendance.html",
        {"request": request, "current_user": user, "course": course, "enrollments": enrollments, "trainee_no": trainee_no or "", "student": student},
    )

@router.post("/attendance/{course_id}/add-trainee")
def attendance_add_trainee(
    course_id: int,
    trainee_no: str = Form(...),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_hod_or_admin),
):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="الدورة غير موجودة")
    _assert_can_manage_course(user, course, db)

    # الحصول على البيانات من ملف الإكسيل فقط
    stu = None
    try:
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        from excel_data_reference import get_student_by_id
        
        student_data = get_student_by_id(trainee_no)
        if student_data:
            stu = {
                "student_id": student_data.get('student_id', trainee_no),
                "student_name": student_data.get('student_Name', '') or student_data.get('student_name', ''),
                "major": student_data.get('Major', '') or student_data.get('major', '')
            }
    except Exception as e:
        pass
    
    # إذا لم نجد من الإكسيل، حاول من جدول sf01 مباشرة
    if not stu:
        try:
            stu = db.execute(
                text("""
                    SELECT student_id, "student_Name" AS student_name, "Major" AS major
                    FROM sf01 WHERE student_id = :sid LIMIT 1
                """),
                {"sid": int(trainee_no)},
            ).mappings().first()
        except Exception:
            stu = None

    if not stu:
        error_msg = f"لا يوجد متدرب برقم {trainee_no} في قاعدة البيانات"
        encoded_error = quote(error_msg, safe='')
        return RedirectResponse(url=f"/hod/attendance/{course.id}?trainee_no={trainee_no}&error={encoded_error}", status_code=status.HTTP_303_SEE_OTHER)

    current_count = db.execute(text("SELECT COUNT(*) FROM course_enrollments WHERE course_id = :cid"), {"cid": course.id}).scalar() or 0
    if course.capacity and current_count >= course.capacity:
        raise HTTPException(status_code=400, detail="تم الوصول للسعة القصوى لهذه الدورة")

    db.execute(
        text("""
            INSERT INTO course_enrollments (course_id, trainee_no, trainee_name, trainee_major, status, present)
            VALUES (:cid, :tno, :tname, :tmajor, 'registered', 0)
            ON CONFLICT (course_id, trainee_no) DO UPDATE
              SET trainee_name  = EXCLUDED.trainee_name,
                  trainee_major = EXCLUDED.trainee_major
        """),
        {"cid": course.id, "tno": str(stu["student_id"]), "tname": stu["student_name"], "tmajor": stu["major"]},
    )
    db.commit()
    return RedirectResponse(url=f"/hod/attendance/{course.id}?trainee_no={trainee_no}&ok=1", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/attendance/{course_id}/mark")
def attendance_mark_toggle(
    course_id: int,
    trainee_no: str = Form(...),
    present: str = Form("false"),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_hod_or_admin),
):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="الدورة غير موجودة")
    _assert_can_manage_course(user, course, db)

    present_val = str(present).strip().lower() in {"1", "true", "t", "yes", "on"}
    db.execute(
        text("UPDATE course_enrollments SET present = :p, updated_at = CURRENT_TIMESTAMP WHERE course_id = :cid AND trainee_no = :tno"),
        {"p": present_val, "cid": course.id, "tno": str(trainee_no)},
    )
    db.commit()
    return RedirectResponse(url=f"/hod/attendance/{course.id}", status_code=status.HTTP_303_SEE_OTHER)

# ===================== تسجيل يدوي =====================

@router.get("/courses/{course_id}/enroll-manual")
def enroll_manual_form(
    course_id: int,
    request: Request,
    trainee_no: Optional[str] = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_hod_or_admin),
):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="الدورة غير موجودة")
    _assert_can_manage_course(user, course, db)

    student = None
    error_message = None
    if trainee_no:
        try:
            import sys
            import os
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            from excel_data_reference import get_student_by_id
            
            student_data = get_student_by_id(trainee_no)
            if student_data:
                student = {
                    "student_id": student_data.get('student_id', trainee_no),
                    "student_name": student_data.get('student_Name', '') or student_data.get('student_name', ''),
                    "major": student_data.get('Major', '') or student_data.get('major', '')
                }
            else:
                # محاولة من جدول sf01 كحل بديل
                try:
                    row = db.execute(
                        text("""
                            SELECT student_id, COALESCE("student_Name", student_name) AS student_name,
                                   COALESCE("Major", major) AS major
                            FROM sf01 WHERE student_id = :sid LIMIT 1
                        """),
                        {"sid": int(trainee_no)},
                    ).mappings().first()
                    if row:
                        student = dict(row)
                    else:
                        error_message = f"لا يوجد متدرب برقم {trainee_no} في قاعدة البيانات"
                except Exception:
                    error_message = f"لا يوجد متدرب برقم {trainee_no} في قاعدة البيانات"
        except Exception:

            try:
                row = db.execute(
                    text("""
                        SELECT student_id, COALESCE("student_Name", student_name) AS student_name,
                               COALESCE("Major", major) AS major
                        FROM sf01 WHERE student_id = :sid LIMIT 1
                    """),
                    {"sid": int(trainee_no)},
                ).mappings().first()
                if row:
                    student = dict(row)
                else:
                    error_message = f"لا يوجد متدرب برقم {trainee_no} في قاعدة البيانات"
            except Exception:
                error_message = f"لا يوجد متدرب برقم {trainee_no} في قاعدة البيانات"

    return templates.TemplateResponse(
        "hod/manual_enroll.html",
        {"request": request, "current_user": user, "course": course, "trainee_no": trainee_no or "", "student": student, "error_message": error_message},
    )

@router.post("/courses/{course_id}/enroll-manual")
def enroll_manual_submit(
    course_id: int,
    trainee_no: str = Form(...),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_hod_or_admin),
):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="الدورة غير موجودة")
    _assert_can_manage_course(user, course, db)

    stu = None
    try:
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        from excel_data_reference import get_student_by_id
        
        student_data = get_student_by_id(trainee_no)
        if student_data:
            stu = {
                "student_id": student_data.get('student_id', trainee_no),
                "student_name": student_data.get('student_Name', '') or student_data.get('student_name', ''),
                "major": student_data.get('Major', '') or student_data.get('major', '')
            }
    except Exception:
        pass
    
    if not stu:
        try:
            stu = db.execute(
                text("""
                    SELECT student_id, "student_Name" AS student_name, "Major" AS major
                    FROM sf01 WHERE student_id = :sid LIMIT 1
                """),
                {"sid": int(trainee_no)},
            ).mappings().first()
        except Exception:
            stu = None
    
    if not stu:

        raise HTTPException(status_code=400, detail=f"لا يوجد متدرب برقم {trainee_no} في قاعدة البيانات")

    current_count = db.execute(text("SELECT COUNT(*) FROM course_enrollments WHERE course_id = :cid"), {"cid": course.id}).scalar() or 0
    if course.capacity and current_count >= course.capacity:
        raise HTTPException(status_code=400, detail="تم الوصول للسعة القصوى لهذه الدورة")

    db.execute(
        text("""
            INSERT INTO course_enrollments (course_id, trainee_no, trainee_name, trainee_major, status, present)
            VALUES (:cid, :tno, :tname, :tmajor, 'registered', 0)
            ON CONFLICT (course_id, trainee_no) DO UPDATE
              SET trainee_name  = EXCLUDED.trainee_name,
                  trainee_major = EXCLUDED.trainee_major
        """),
        {"cid": course.id, "tno": str(stu["student_id"]), "tname": stu["student_name"], "tmajor": stu["major"]},
    )
    db.commit()
    return RedirectResponse(url=f"/hod/courses/{course.id}/enroll-manual?trainee_no={trainee_no}&ok=1", status_code=status.HTTP_303_SEE_OTHER)

@router.get("/certificates/issue")
def certificates_issue_page(
    course_id: Optional[int] = None,
    search: Optional[str] = None,
    request: Request = None,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_hod_or_admin),
):
    back_url = request.headers.get("referer") or "/hod/courses"

    # إذا لم يتم تحديد course_id، عرض صفحة البحث
    if not course_id:
        certificates = []
        trainee_info = None
        
        if search:
            # البحث عن المتدرب برقمه أو اسمه
            search_param = f"%{search}%"
            
            # البحث: نجد جميع الشهادات الفريدة للمتدرب (نسخة واحدة من كل دورة - النسخة الأولى)
            certificates = db.execute(
                text("""
                    SELECT DISTINCT
                        cv.id,
                        cv.trainee_no,
                        cv.trainee_name,
                        cv.course_title,
                        cv.hours,
                        cv.start_date,
                        cv.end_date,
                        cv.certificate_code,
                        cv.created_at,
                        c.id as course_id,
                        cv.copy_no
                    FROM certificate_verifications cv
                    LEFT JOIN courses c ON cv.course_id = c.id
                    WHERE (cv.trainee_no LIKE :search OR cv.trainee_name LIKE :search)
                      AND cv.copy_no = 1
                    ORDER BY cv.created_at DESC, cv.trainee_name
                """),
                {"search": search_param},
            ).mappings().all()
            

            processed_certificates = []
            for cert in certificates:
                cert_dict = dict(cert)

                if cert_dict.get('start_date') and isinstance(cert_dict['start_date'], str):
                    try:
                        cert_dict['start_date'] = datetime.strptime(cert_dict['start_date'], '%Y-%m-%d').date()
                    except:
                        pass
                if cert_dict.get('end_date') and isinstance(cert_dict['end_date'], str):
                    try:
                        cert_dict['end_date'] = datetime.strptime(cert_dict['end_date'], '%Y-%m-%d').date()
                    except:
                        pass
                if cert_dict.get('created_at') and isinstance(cert_dict['created_at'], str):
                    try:
                        cert_dict['created_at'] = datetime.fromisoformat(cert_dict['created_at'])
                    except:
                        pass
                processed_certificates.append(cert_dict)
            
            certificates = processed_certificates
            

            if certificates:
                trainee_info = {
                    'trainee_no': certificates[0]['trainee_no'],
                    'trainee_name': certificates[0]['trainee_name'],
                    'total_certificates': len(certificates),
                    'total_hours': sum(c['hours'] or 0 for c in certificates) if certificates else 0,
                }

        return templates.TemplateResponse(
            "hod/certificates_search.html",
            {
                "request": request,
                "current_user": user,
                "search": search or "",
                "certificates": certificates,
                "trainee_info": trainee_info,
                "back_url": back_url,
            },
        )

    course = db.query(Course).filter(Course.id == course_id).first()

    if not course:
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "message": "الدورة غير موجودة",
                "back_url": back_url
            },
            status_code=404,
        )

    _assert_can_manage_course(user, course, db)

    if course.status != "closed":
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "message": "لا يمكن إصدار الشهادات إلا بعد إغلاق الدورة",
                "back_url": back_url
            },
            status_code=400,
        )

    attendees = db.execute(
        text("""
            SELECT e.trainee_no, e.trainee_name, e.trainee_major
            FROM course_enrollments e
            WHERE e.course_id = :cid AND e.present = true
            ORDER BY CASE WHEN e.trainee_name IS NULL THEN 1 ELSE 0 END, e.trainee_name
        """),
        {"cid": course.id},
    ).mappings().all()

    return templates.TemplateResponse(
        "hod/certificates_issue.html",
        {
            "request": request,
            "current_user": user,
            "course": course,
            "attendees": attendees,
        },
    )

# ===================== إصدار جميع الشهادات =====================
@router.get("/certificates/issue-all")
def certificates_issue_all(
    course_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_hod_or_admin),
):
    """إصدار شهادات لجميع الحاضرين في الدورة"""
    back_url = request.headers.get("referer") or "/hod/courses"
    

    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="الدورة غير موجودة")
    _assert_can_manage_course(user, course, db)

    if course.status != "closed":
        raise HTTPException(
            status_code=400, 
            detail="لا يمكن إصدار الشهادات إلا بعد إغلاق الدورة"
        )

    attendees = db.execute(
        text("""
            SELECT e.trainee_no, e.trainee_name, e.trainee_major, e.certificate_code
            FROM course_enrollments e
            WHERE e.course_id = :cid AND e.present = true
            ORDER BY CASE WHEN e.trainee_name IS NULL THEN 1 ELSE 0 END, e.trainee_name
        """),
        {"cid": course.id},
    ).mappings().all()

    issued_count = 0
    skipped_count = 0
    
    # إصدار شهادة لكل حاضر
    for enrollment in attendees:
        trainee_no = enrollment["trainee_no"]
        
        # تخطي إذا كانت الشهادة مصدرة بالفعل
        if enrollment.get("certificate_code") is not None:
            skipped_count += 1
            continue
        
        try:
            # إنشاء كود الشهادة
            try:
                seq_val = db.execute(text("SELECT nextval('certificate_seq')")).scalar()
            except Exception:
                seq_val = (db.execute(text("SELECT COALESCE(MAX(id),0)+1 FROM certificate_verifications")).scalar() or 1)
            
            cert_code = f"{seq_val}-{trainee_no}-{course_id}"
            
            # تحديث كود الشهادة في course_enrollments
            db.execute(
                text("""
                    UPDATE course_enrollments
                    SET certificate_code = :code, certificate_issued_at = CURRENT_TIMESTAMP
                    WHERE course_id = :cid AND trainee_no = :tno
                """),
                {"code": cert_code, "cid": course_id, "tno": trainee_no},
            )
            db.commit()
            

            barcode_url = ensure_barcode_png(cert_code)
            db.execute(
                text("""
                    INSERT INTO certificate_verifications (
                      course_id, trainee_no, trainee_name, course_title, hours,
                      start_date, end_date, certificate_code, copy_no, barcode_path
                    )
                    VALUES (
                      :cid, :tno, :tname, :ctitle, :hours,
                      :sdate, :edate, :code,
                      COALESCE((SELECT MAX(copy_no) FROM certificate_verifications WHERE certificate_code = :code), 0) + 1,
                      :barcode
                    )
                """),
                {
                    "cid": course.id,
                    "tno": trainee_no,
                    "tname": enrollment["trainee_name"],
                    "ctitle": course.title,
                    "hours": course.hours,
                    "sdate": course.start_date,
                    "edate": course.end_date,
                    "code": cert_code,
                    "barcode": barcode_url,
                },
            )
            db.commit()
            issued_count += 1
            
        except Exception as e:
            # تسجيل الخطأ والمتابعة
            print(f"خطأ في إصدار شهادة {trainee_no}: {str(e)}")
            traceback.print_exc()
            continue
    
    # إعادة التوجيه مع رسالة نجاح
    return RedirectResponse(
        url=f"/hod/certificates/issue?course_id={course_id}&issued={issued_count}&skipped={skipped_count}",
        status_code=status.HTTP_303_SEE_OTHER
    )

@router.get("/certificates/print/{course_id}/{trainee_no}")
def certificate_print(
    course_id: int,
    trainee_no: str,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_hod_or_admin),
):
    # 1) الدورة
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(404, "الدورة غير موجودة")
    _assert_can_manage_course(user, course, db)

    # 2) المتدرب (حاضر فقط)
    enrollment = db.execute(
        text("""
            SELECT e.trainee_no, e.trainee_name, e.trainee_major,
                   e.certificate_code, e.certificate_issued_at
            FROM course_enrollments e
            WHERE e.course_id = :cid AND e.trainee_no = :tno AND e.present = true
        """),
        {"cid": course_id, "tno": trainee_no},
    ).mappings().first()
    if not enrollment:
        raise HTTPException(404, "المتدرب غير موجود أو غير حاضر")

    cert_code = enrollment.get("certificate_code")
    if not cert_code:
        try:
            seq_val = db.execute(text("SELECT nextval('certificate_seq')")).scalar()
        except Exception:
            seq_val = (db.execute(text("SELECT COALESCE(MAX(id),0)+1 FROM certificate_verifications")).scalar() or 1)
        cert_code = f"{seq_val}-{trainee_no}-{course_id}"
        db.execute(
            text("""
                UPDATE course_enrollments
                SET certificate_code = :code, certificate_issued_at = CURRENT_TIMESTAMP
                WHERE course_id = :cid AND trainee_no = :tno
            """),
            {"code": cert_code, "cid": course_id, "tno": trainee_no},
        )
        db.commit()

    # 4) توليد الباركود + إدراج سجلّ التحقق مع copy_no = آخر نسخة + 1
    barcode_url = ensure_barcode_png(cert_code)
    row = db.execute(
        text("""
            INSERT INTO certificate_verifications (
              course_id, trainee_no, trainee_name, course_title, hours,
              start_date, end_date, certificate_code, copy_no, barcode_path
            )
            VALUES (
              :cid, :tno, :tname, :ctitle, :hours,
              :sdate, :edate, :code,
              COALESCE((SELECT MAX(copy_no) FROM certificate_verifications WHERE certificate_code = :code), 0) + 1,
              :barcode
            )
            RETURNING copy_no
        """),
        {
            "cid": course.id,
            "tno": enrollment["trainee_no"],
            "tname": enrollment["trainee_name"],
            "ctitle": course.title,
            "hours": course.hours,
            "sdate": course.start_date,
            "edate": course.end_date,
            "code": cert_code,
            "barcode": barcode_url,
        },
    ).first()
    copy_no = int(row[0]) if row else 1
    db.commit()

    def _norm(s): return " ".join((s or "").strip().split())
    college = None

    try:
        target_dept_names = [t.department_name for t in course.targets] if getattr(course, "targets", None) else []
        for dept_name in target_dept_names:
            dept = db.query(Department).filter(Department.name == dept_name).first()
            if dept and dept.college:
                matched = db.query(College).filter(College.name == dept.college).first()
                if matched:
                    college = matched
                    break
    except Exception:
        college = None

    if not college and getattr(user, "hod_college", None):
        normalized_user_college = _norm(user.hod_college)
        all_colleges = db.query(College).filter(College.is_active == True).all()
        for c in all_colleges:
            if _norm(c.name) == normalized_user_college:
                college = c
                break

    college_name    = (college.name or user.hod_college or "الكلية التقنية") if college else (user.hod_college or "الكلية التقنية")
    college_name_en = (getattr(college, "name_en", None) or "") if college else ""

    vp_name       = college.vp_students_name if college and college.vp_students_name else ""
    dean_name     = college.dean_name         if college and college.dean_name         else ""
    vp_sign_url   = college.vp_students_sign_path if college and getattr(college, "vp_students_sign_path", None) else "/static/blank.png"
    dean_sign_url = college.dean_sign_path       if college and getattr(college, "dean_sign_path", None)       else "/static/blank.png"
    stamp_url     = college.students_affairs_stamp_path if college and getattr(college, "students_affairs_stamp_path", None) else "/static/blank.png"

    logo_src = None
    for p in ("images/main_logo.png", "images/favicon.ico", "images/logo.png", "img/logo.png"):
        fp = Path("app/static").joinpath(p)
        if fp.exists():
            logo_src = f"/static/{p}"
            break

    start_s = course.start_date.strftime("%d-%m-%Y") if course.start_date else ""
    end_s   = course.end_date.strftime("%d-%m-%Y")   if course.end_date else ""

    return templates.TemplateResponse(
        "hod/certificate_template.html",
        {
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
            "logo_src": logo_src,
            "certificate_no": cert_code,
            "copy_no": copy_no,
            "barcode_url": barcode_url,
            "start_date": start_s,
            "end_date": end_s,
        },
    )

@router.get("/certificates/print.pdf/{course_id}/{trainee_no}")
def certificate_print_pdf(
    course_id: int,
    trainee_no: str,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_hod_or_admin),
    download: int = 1,
):

    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(404, "الدورة غير موجودة")
    _assert_can_manage_course(user, course, db)

    enrollment = db.execute(
        text("""
            SELECT e.trainee_no, e.trainee_name, e.trainee_major,
                   e.certificate_code, e.certificate_issued_at
            FROM course_enrollments e
            WHERE e.course_id = :cid AND e.trainee_no = :tno AND e.present = true
        """),
        {"cid": course_id, "tno": trainee_no},
    ).mappings().first()
    if not enrollment:
        raise HTTPException(404, "المتدرب غير موجود أو غير حاضر")

    # 3) إنشاء/تثبيت كود الشهادة
    cert_code = enrollment.get("certificate_code")
    if not cert_code:
        try:
            seq_val = db.execute(text("SELECT nextval('certificate_seq')")).scalar()
        except Exception:
            seq_val = (db.execute(text("SELECT COALESCE(MAX(id),0)+1 FROM certificate_verifications")).scalar() or 1)
        cert_code = f"{seq_val}-{trainee_no}-{course_id}"
        db.execute(
            text("""
                UPDATE course_enrollments
                SET certificate_code = :code, certificate_issued_at = CURRENT_TIMESTAMP
                WHERE course_id = :cid AND trainee_no = :tno
            """),
            {"code": cert_code, "cid": course_id, "tno": trainee_no},
        )
        db.commit()

    barcode_url = ensure_barcode_png(cert_code)
    row = db.execute(
        text("""
            INSERT INTO certificate_verifications (
              course_id, trainee_no, trainee_name, course_title, hours,
              start_date, end_date, certificate_code, copy_no, barcode_path
            )
            VALUES (
              :cid, :tno, :tname, :ctitle, :hours,
              :sdate, :edate, :code,
              COALESCE((SELECT MAX(copy_no) FROM certificate_verifications WHERE certificate_code = :code), 0) + 1,
              :barcode
            )
            RETURNING copy_no
        """),
        {
            "cid": course.id,
            "tno": enrollment["trainee_no"],
            "tname": enrollment["trainee_name"],
            "ctitle": course.title,
            "hours": course.hours,
            "sdate": course.start_date,
            "edate": course.end_date,
            "code": cert_code,
            "barcode": barcode_url,
        },
    ).first()
    copy_no = int(row[0]) if row else 1
    db.commit()

    # 5) بيانات الكلية والتواقيع (استنتاج من أهداف الدورة إن توفرت)
    def _norm(s): return " ".join((s or "").strip().split())
    college = None

    # أولًا: حاول استنتاج الكلية من أسماء الأقسام المستهدفة للدورة
    try:
        target_dept_names = [t.department_name for t in course.targets] if getattr(course, "targets", None) else []
        for dept_name in target_dept_names:
            dept = db.query(Department).filter(Department.name == dept_name).first()
            if dept and dept.college:
                matched = db.query(College).filter(College.name == dept.college).first()
                if matched:
                    college = matched
                    break
    except Exception:
        college = None

    # ثانياً: لو لم يتم العثور، جرب استخدام كلية المستخدم (hod_college)
    if not college and getattr(user, "hod_college", None):
        normalized_user_college = _norm(user.hod_college)
        all_colleges = db.query(College).filter(College.is_active == True).all()
        for c in all_colleges:
            if _norm(c.name) == normalized_user_college:
                college = c
                break

    college_name    = (college.name or user.hod_college or "الكلية التقنية") if college else (user.hod_college or "الكلية التقنية")
    college_name_en = (getattr(college, "name_en", None) or "") if college else ""

    vp_name       = college.vp_students_name if college and college.vp_students_name else ""
    dean_name     = college.dean_name         if college and college.dean_name         else ""
    vp_sign_url   = college.vp_students_sign_path if college and getattr(college, "vp_students_sign_path", None) else "/static/blank.png"
    dean_sign_url = college.dean_sign_path       if college and getattr(college, "dean_sign_path", None)       else "/static/blank.png"
    stamp_url     = college.students_affairs_stamp_path if college and getattr(college, "students_affairs_stamp_path", None) else "/static/blank.png"

    # 6) جهّز القالب إلى HTML (كسلسلة نصية)
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
        "certificate_no": cert_code,
        "copy_no": copy_no,
        "barcode_url": barcode_url,
        # إن رغبت في استخدام start/end جاهزة بالنص:
        # "start_date": course.start_date.strftime("%Y-%m-%d") if course.start_date else "",
        # "end_date":   course.end_date.strftime("%Y-%m-%d") if course.end_date else "",
    }

    tpl = templates.env.get_template("hod/certificate_template.html")
    html_str = tpl.render(**context)

    # 7) تحويل HTML إلى PDF عبر xhtml2pdf
    if not HAS_XHTML2PDF:
        raise HTTPException(500, "xhtml2pdf غير مثبتة، ثبّت: pip install xhtml2pdf")

    pdf_io = io.BytesIO()
    doc = pisa.CreatePDF(src=html_str, dest=pdf_io, encoding="UTF-8", link_callback=_link_callback)
    if doc.err:
        raise HTTPException(500, f"تعذّر توليد PDF للشهادة عبر xhtml2pdf: {doc.err}")
    pdf_io.seek(0)

    # 8) ترويسة تنزيل باسم واضح
    pretty_name = f"شهادة-{cert_code}-نسخة-{copy_no}.pdf"
    ascii_fallback = f"certificate_{course_id}_{trainee_no}_copy_{copy_no}.pdf"
    disposition = 'attachment' if str(download).lower() not in {'0', 'false'} else 'inline'
    content_disp = (
        f'{disposition}; '
        f'filename="{ascii_fallback}"; '
        f"filename*=UTF-8''{quote(pretty_name)}"
    )

    return StreamingResponse(
        pdf_io,
        media_type="application/pdf",
        headers={
            "Content-Disposition": content_disp,
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/verify/{code}")
def verify_page(code: str, request: Request, db: Session = Depends(get_db)):
    row = db.execute(text("""
        SELECT trainee_name, trainee_no, course_title, hours, start_date, end_date, copy_no
        FROM certificate_verifications
        WHERE certificate_code = :c
        ORDER BY copy_no DESC
        LIMIT 1
    """), {"c": code}).mappings().first()
    if not row:
        raise HTTPException(404, "لم يتم العثور على الشهادة")
    return templates.TemplateResponse("verify.html", {"request": request, "code": code, "rec": row})

def _render_roster_html_pretty(course, enrollments):

    logo_src = None
    for p in ("images/main_logo.png", "images/logo.png", "img/logo.png"):
        fp = Path("app/static").joinpath(p)
        if fp.exists():
            logo_src = f"/static/{p}"
            break

    font_url_majalla = None
    for name in ["Majalla.ttf", "alfont_com_majalla.ttf"]:
        p = Path("app/static/fonts") / name
        if p.exists():
            font_url_majalla = f"/static/fonts/{name}"
            break

    font_url_traditional = None
    for name in ["Traditional-Arabic.ttf", "Traditional Arabic.ttf"]:
        p = Path("app/static/fonts") / name
        if p.exists():
            font_url_traditional = f"/static/fonts/{name}"
            break

    parts = []
    if font_url_majalla:
        parts.append(f"@font-face {{ font-family:'MajallaAR'; src:url('{font_url_majalla}') format('truetype'); }}")
    if font_url_traditional:
        parts.append(f"@font-face {{ font-family:'TradArabicAR'; src:url('{font_url_traditional}') format('truetype'); }}")
    font_ready_css = "\n".join(parts)

    cleaned_enrollments = []
    if enrollments:
        for row in enrollments:
            cleaned_row = {
                'trainee_name': row.get('trainee_name') or '',
                'trainee_no': row.get('trainee_no') or '',
                'trainee_major': row.get('trainee_major') or '',
            }
            cleaned_enrollments.append(cleaned_row)

    tpl = Template(_ROSTER_PRETTY_HTML)
    return tpl.render(
        course=course,
        enrollments=cleaned_enrollments,
        logo_src=logo_src,
        font_ready_css=font_ready_css,
        shape=_shape_ar,
    )

@router.get("/courses/{course_id}/roster.pdf")
def course_roster_pdf(
    course_id: int,
    request: Request,
    download: int = 1,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_hod_or_admin),
):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(404, "الدورة غير موجودة")
    _assert_can_manage_course(user, course, db)

    if not HAS_XHTML2PDF:
        raise HTTPException(500, "xhtml2pdf غير مثبتة، ثبّت: pip install xhtml2pdf")

    rows = db.execute(
        text("""
            SELECT trainee_name, trainee_no, trainee_major
            FROM course_enrollments
            WHERE course_id = :cid
            ORDER BY CASE WHEN trainee_name IS NULL THEN 1 ELSE 0 END, trainee_name, trainee_no
        """),
        {"cid": course.id},
    ).mappings().all()

    # توليد HTML الاحترافي ثم تحويله إلى PDF
    html = _render_roster_html_pretty(course, rows)
    pdf_io = io.BytesIO()
    doc = pisa.CreatePDF(src=html, dest=pdf_io, encoding="UTF-8", link_callback=_link_callback)
    if doc.err:
        raise HTTPException(500, f"تعذّر توليد PDF (pretty) عبر xhtml2pdf: {doc.err}")
    pdf_io.seek(0)

    # ===== اسم ملف عربي صحيح + احتياطي ASCII لمنع انقلاب/ترميز خاطئ =====
    # تنظيف العنوان من محارف قد تُربك المتصفحات في الترويسة
    raw_title = (course.title or "").strip()
    safe_title = "".join(ch if ch not in "\\/:*?\"<>|\r\n\t" else " " for ch in raw_title)
    safe_title = " ".join(safe_title.split())  # طيّ المسافات
    if not safe_title:
        safe_title = f"الدورة {course.id}"
    # حد طول الاسم حتى لا يتجاوز حدود الترويسة
    if len(safe_title) > 120:
        safe_title = safe_title[:117] + "..."

    pretty_name = f"كشف حضور - {safe_title}.pdf"
    ascii_fallback = f"roster_course_{course.id}.pdf"

    disposition = 'attachment' if str(download).lower() not in {'0', 'false'} else 'inline'
    # ضع filename (ASCII) ثم filename* (UTF-8) لضمان دعم أوسع للمتصفحات
    content_disp = (
        f'{disposition}; '
        f'filename="{ascii_fallback}"; '
        f"filename*=UTF-8''{quote(pretty_name)}"
    )

    return StreamingResponse(
        pdf_io,
        media_type="application/pdf",
        headers={
            "Content-Disposition": content_disp,
            "X-Content-Type-Options": "nosniff",
        },
    )

# ألياس يوجّه لنفس المسار الاحترافي
@router.get("/attendance/{course_id}/roster2.pdf")
def attendance_roster_pdf_pretty_alias(
    course_id: int,
    request: Request,
    download: int = 1,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_hod_or_admin),
):
    return RedirectResponse(
        url=f"/hod/courses/{course_id}/roster.pdf?download={int(download)}",
        status_code=status.HTTP_307_TEMPORARY_REDIRECT
    )

# ===================== إغلاق الدورة =====================

@router.get("/courses/{course_id}/close")
def close_course(
    course_id: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_hod_or_admin),
):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(404, "الدورة غير موجودة")
    _assert_can_manage_course(user, course, db)

    # ✅ تحقق من الحضور
    unmarked = db.execute(
        text("""
            SELECT COUNT(*) FROM course_enrollments
            WHERE course_id = :cid AND present IS NULL
        """),
        {"cid": course.id},
    ).scalar()

    if unmarked > 0:
        raise HTTPException(
            status_code=400,
            detail="لا يمكن إغلاق الدورة قبل تأكيد حالة الحضور لجميع المتدربين"
        )

    course.status = "closed"
    db.commit()
    return RedirectResponse(url="/hod/courses?closed=1", status_code=status.HTTP_303_SEE_OTHER)

@router.get("/courses/{course_id}/reopen")
def reopen_course(
    course_id: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_hod_or_admin),
):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(404, "الدورة غير موجودة")

    _assert_can_manage_course(user, course, db)

    if course.status != "closed":
        raise HTTPException(400, "لا يمكن إعادة فتح إلا الدورات المغلقة")

    course.status = "published"
    db.commit()

    return RedirectResponse(
        url="/hod/courses?reopened=1",
        status_code=status.HTTP_303_SEE_OTHER
    )

@router.get("/skills-record")
@router.get("/skills/record")
def skills_record(
    request: Request,
    db: Session = Depends(get_db)
):
    """صفحة البحث عن سجل مهارات المتدرب

    تم إضافة مسار بديل `/skills/record` ليتوافق مع روابط المتصفح القديمة.
    """
    return templates.TemplateResponse("hod/skills_record.html", {"request": request})

@router.get("/skills-record/pdf/{trainee_no}")
def skills_record_pdf_export(
    trainee_no: str = FastAPIPath(...),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_hod_or_admin)
):
    """تصدير تقرير مهارات المتدرب كملف PDF احترافي"""
    
    # If college_admin, only show records for their college's courses
    if user.is_college_admin and user.college_admin_college:
        college_name = user.college_admin_college
        college_departments = db.query(Department).filter(Department.college == college_name).all()
        dept_names = [d.name for d in college_departments]
        
        if not dept_names:
            raise HTTPException(status_code=403, detail="لم يتم العثور على أقسام في كليتك")
        
        sql = """
            SELECT DISTINCT
                e.trainee_no,
                e.trainee_name,
                c.id as course_id,
                c.title as course_title,
                c.description,
                c.hours,
                c.start_date,
                c.end_date,
                c.provider,
                cv.certificate_code,
                cv.copy_no,
                cv.created_at as certificate_date
            FROM course_enrollments e
            INNER JOIN courses c ON e.course_id = c.id
            INNER JOIN course_target_departments ctd ON c.id = ctd.course_id
            LEFT JOIN certificate_verifications cv ON 
                e.course_id = cv.course_id AND 
                e.trainee_no = cv.trainee_no AND
                cv.copy_no = 1
            WHERE e.trainee_no = :trainee_no AND ctd.department_name IN ({})
            ORDER BY c.start_date DESC
        """.format(','.join([f"'{d}'" for d in dept_names]))
    else:
        sql = """
            SELECT DISTINCT
                e.trainee_no,
                e.trainee_name,
                c.id as course_id,
                c.title as course_title,
                c.description,
                c.hours,
                c.start_date,
                c.end_date,
                c.provider,
                cv.certificate_code,
                cv.copy_no,
                cv.created_at as certificate_date
            FROM course_enrollments e
            INNER JOIN courses c ON e.course_id = c.id
            LEFT JOIN certificate_verifications cv ON 
                e.course_id = cv.course_id AND 
                e.trainee_no = cv.trainee_no AND
                cv.copy_no = 1
            WHERE e.trainee_no = :trainee_no
            ORDER BY c.start_date DESC
        """
    
    query = text(sql)
    results = db.execute(query, {"trainee_no": trainee_no}).mappings().all()
    
    if not results:
        raise HTTPException(status_code=404, detail="لم يتم العثور على المتدرب")
    
    # تجميع البيانات
    trainee_info = {
        "trainee_no": results[0]["trainee_no"],
        "trainee_name": results[0]["trainee_name"],
        "courses": [],
        "total_hours": 0,
        "total_certificates": 0,
        "completed_courses": 0,
        "department": None,
        "college": None
    }
    
    # البحث عن بيانات المتدرب (القسم والكلية)
    # 1. محاولة البحث في جدول المستخدمين
    trainee_user = db.query(User).filter(User.username == trainee_no).first()
    if trainee_user:
        # استخدام getattr لتجنب الأخطاء إذا لم تكن الحقول موجودة في Model
        user_dept = getattr(trainee_user, 'department', None)
        user_college = getattr(trainee_user, 'college', None)

        if user_dept:
            dept = db.query(Department).filter(Department.name == user_dept).first()
            if dept:
                trainee_info["department"] = dept.name
                if dept.college:
                    college = db.query(College).filter(College.name == dept.college).first()
                    if college:
                        trainee_info["college"] = college.name
            else:
                trainee_info["department"] = user_dept
        
        if not trainee_info["college"] and user_college:
            college = db.query(College).filter(College.name == user_college).first()
            if college:
                trainee_info["college"] = college.name
            else:
                trainee_info["college"] = user_college

    # 2. محاولة البحث في جدول التسجيلات (course_enrollments) إذا لم نجد البيانات
    # هذا مفيد للمتدربين الذين ليس لديهم حساب مستخدم ولكن لديهم بيانات في التسجيل
    if not trainee_info["department"]:
        enrollment = db.execute(
            text("SELECT trainee_major FROM course_enrollments WHERE trainee_no = :tno AND trainee_major IS NOT NULL LIMIT 1"),
            {"tno": trainee_no}
        ).mappings().first()
        
        if enrollment and enrollment["trainee_major"]:
            major_str = enrollment["trainee_major"]
            
            # محاولة استخراج الكلية والقسم من النص (مثال: "قسم الحاسب - كلية التقنية")
            if " - " in major_str:
                parts = major_str.split(" - ")
                if len(parts) >= 2:
                    trainee_info["department"] = parts[0].strip()
                    # نفترض أن الجزء الأخير هو الكلية
                    possible_college = parts[-1].strip()
                    if "كلية" in possible_college:
                        trainee_info["college"] = possible_college
            
            # إذا لم يتم استخراج القسم (لم نجد " - ") نستخدم النص كاملاً
            if not trainee_info["department"]:
                trainee_info["department"] = major_str

    # 3. محاولة استنتاج الكلية من القسم إذا وجدت
    if trainee_info["department"] and not trainee_info["college"]:
        dept = db.query(Department).filter(Department.name == trainee_info["department"]).first()
        if dept and dept.college:
            college = db.query(College).filter(College.name == dept.college).first()
            trainee_info["college"] = college.name if college else dept.college
    
    for row in results:
        course_info = {
            "course_id": row["course_id"],
            "course_title": row["course_title"],
            "description": row["description"],
            "hours": row["hours"] or 0,
            "start_date": row["start_date"],
            "end_date": row["end_date"],
            "provider": row["provider"],
            "certificate_code": row["certificate_code"],
            "certificate_date": row["certificate_date"],
            # defaults for college-specific signing data
            "college_name": None,
            "college": None,
        }

        # حاول إيجاد الكلية المرتبطة بهذه الدورة إن وُجدت عبر Course.targets -> Department -> College
        try:
            course_obj = db.query(Course).filter(Course.id == row["course_id"]).first()
            found_college = None
            if course_obj and getattr(course_obj, "targets", None):
                for t in course_obj.targets:
                    dept_name = t.department_name
                    if dept_name:
                        dept = db.query(Department).filter(Department.name == dept_name).first()
                        if dept and dept.college:
                            matched_col = db.query(College).filter(College.name == dept.college).first()
                            if matched_col:
                                found_college = matched_col
                                break
            if found_college:
                course_info["college_name"] = found_college.name
                course_info["college"] = {
                    "name": found_college.name,
                    "dean_name": found_college.dean_name or "",
                    "vp_name": found_college.vp_students_name or "",
                    "dean_sign_url": found_college.dean_sign_path if getattr(found_college, "dean_sign_path", None) else "/static/blank.png",
                    "vp_sign_url": found_college.vp_students_sign_path if getattr(found_college, "vp_students_sign_path", None) else "/static/blank.png",
                    "stamp_url": found_college.students_affairs_stamp_path if getattr(found_college, "students_affairs_stamp_path", None) else "/static/blank.png",
                }
        except Exception:
            pass

        trainee_info["courses"].append(course_info)
        trainee_info["total_hours"] += course_info["hours"]
        if row["certificate_code"]:
            trainee_info["total_certificates"] += 1
        trainee_info["completed_courses"] = len(trainee_info["courses"])

    # البحث عن اللوجو
    logo_src = None
    for p in ("images/main_logo.png", "images/favicon.ico", "images/logo.png", "img/logo.png"):
        fp = Path("app/static").joinpath(p)
        if fp.exists():
            logo_src = f"/static/{p}"
            break

    # بناء الخطوط
    font_url_majalla = None
    for name in ["Majalla.ttf", "alfont_com_majalla.ttf"]:
        p = Path("app/static/fonts") / name
        if p.exists():
            font_url_majalla = f"/static/fonts/{name}"
            break

    font_url_traditional = None
    for name in ["Traditional-Arabic.ttf", "Traditional Arabic.ttf"]:
        p = Path("app/static/fonts") / name
        if p.exists():
            font_url_traditional = f"/static/fonts/{name}"
            break

    parts = []
    if font_url_majalla:
        parts.append(f"@font-face {{ font-family:'MajallaAR'; src:url('{font_url_majalla}') format('truetype'); }}")
    if font_url_traditional:
        parts.append(f"@font-face {{ font-family:'TradArabicAR'; src:url('{font_url_traditional}') format('truetype'); }}")
    font_ready_css = "\n".join(parts)

    # الحصول على أسماء المسؤولين من بيانات الكلية والقسم
    dean_name = ""
    delegate_name = ""  # وكيل شؤون المتدربين
    dept_head_name = ""
    
    # جلب بيانات الكلية للحصول على اسم العميد (admin الكلية) والوكيل والتوقيعات
    dean_sign_url = "/static/blank.png"
    vp_sign_url = "/static/blank.png"
    stamp_url = "/static/blank.png"
    
    if trainee_info["college"]:
        college = db.query(College).filter(College.name == trainee_info["college"]).first()
        if college:
            # جرب الحصول على اسم العميد من dean_name أولاً، ثم من admin الكلية
            if college.dean_name:
                dean_name = college.dean_name
            else:
                # ابحث عن admin الكلية
                college_admin = db.query(User).filter(
                    User.college_admin_college == college.name,
                    User.is_college_admin == True
                ).first()
                if college_admin:
                    dean_name = college_admin.full_name or college_admin.username
            
            delegate_name = college.vp_students_name or ""
            
            # جلب التوقيعات من بيانات الكلية
            dean_sign_url = college.dean_sign_path if college.dean_sign_path else "/static/blank.png"
            vp_sign_url = college.vp_students_sign_path if college.vp_students_sign_path else "/static/blank.png"
            stamp_url = college.students_affairs_stamp_path if college.students_affairs_stamp_path else "/static/blank.png"
    
    # جلب بيانات القسم للحصول على اسم رئيس القسم
    if trainee_info["department"]:
        dept = db.query(Department).filter(Department.name == trainee_info["department"]).first()
        if dept:
            # جرب الحصول على الاسم من المستخدم المرتبط أو من hod_name
            if dept.head_user:
                dept_head_name = dept.head_user.full_name or dept.head_user.username or ""
            else:
                dept_head_name = dept.hod_name or ""


    # بناء قائمة الكليات الفريدة مع بيانات التوقيعات (تجميع من كل دورة)
    colleges_map = {}
    for c in trainee_info.get("courses", []):
        col = c.get("college")
        if col and col.get("name"):
            name = col.get("name")
            if name not in colleges_map:
                colleges_map[name] = {
                    "name": name,
                    "dean_name": col.get("dean_name", ""),
                    "vp_name": col.get("vp_name", ""),
                    "dean_sign_url": col.get("dean_sign_url", "/static/blank.png"),
                    "vp_sign_url": col.get("vp_sign_url", "/static/blank.png"),
                    "stamp_url": col.get("stamp_url", "/static/blank.png"),
                }

    # إذا لم نحدّد أية كلية من الدورات، استعمل بيانات الكلية المستنتجة سابقًا إن وُجدت
    if not colleges_map and trainee_info.get("college"):
        col = db.query(College).filter(College.name == trainee_info.get("college")).first()
        if col:
            colleges_map[col.name] = {
                "name": col.name,
                "dean_name": col.dean_name or "",
                "vp_name": col.vp_students_name or "",
                "dean_sign_url": col.dean_sign_path if getattr(col, "dean_sign_path", None) else "/static/blank.png",
                "vp_sign_url": col.vp_students_sign_path if getattr(col, "vp_students_sign_path", None) else "/static/blank.png",
                "stamp_url": col.students_affairs_stamp_path if getattr(col, "students_affairs_stamp_path", None) else "/static/blank.png",
            }

    # جهز مصفوفة الكليات للتمرير إلى القالب
    colleges = list(colleges_map.values())

    # احتفظ بمتغيرات التوافق العكسي (أول كلية إن وُجدت)
    if colleges:
        dean_name = dean_name or colleges[0].get("dean_name", "")
        delegate_name = delegate_name or colleges[0].get("vp_name", "")
        dean_sign_url = dean_sign_url if dean_sign_url else colleges[0].get("dean_sign_url", "/static/blank.png")
        vp_sign_url = vp_sign_url if vp_sign_url else colleges[0].get("vp_sign_url", "/static/blank.png")
        stamp_url = stamp_url if stamp_url else colleges[0].get("stamp_url", "/static/blank.png")

    # تحضير البيانات للـ template
    payload = {
        "trainee": trainee_info,
        "logo_src": logo_src,
        "generated_date": date.today().isoformat(),
        "generated_by": user.full_name or user.username,
        "dean_name": dean_name,
        "delegate_name": delegate_name,
        "dept_head_name": dept_head_name,
        "dean_sign_url": dean_sign_url,
        "vp_sign_url": vp_sign_url,
        "stamp_url": stamp_url,
        "font_ready_css": font_ready_css,
        "shape": _shape_ar,
        "colleges": colleges,
    }

    # تصيير الـ HTML
    try:
        tpl = Template(SKILLS_RECORD_PDF_HTML)
        html = tpl.render(**payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"خطأ في إنشاء التقرير: {str(e)}")

    # توليد PDF
    if not HAS_XHTML2PDF:
        raise HTTPException(status_code=500, detail="مكتبة PDF غير متاحة")

    try:
        pdf_bytes = io.BytesIO()
        pisa.CreatePDF(html.encode('utf-8'), dest=pdf_bytes, link_callback=_link_callback)
        pdf_bytes.seek(0)
        
        # Use RFC 2231 encoding for Arabic filename
        filename_utf8 = f"تقرير_مهارات_{trainee_no}.pdf"
        filename_encoded = filename_utf8.encode('utf-8')
        filename_rfc2231 = f"UTF-8''{quote(filename_utf8)}"
        
        return StreamingResponse(
            pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename*={filename_rfc2231}; filename={trainee_no}_skills_report.pdf"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"خطأ في توليد PDF: {str(e)}")

@router.get("/skills-record/report/{trainee_no}")
def skills_record_report(
    trainee_no: str,
    request: Request,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_hod_or_admin)
):
    """تقرير شامل عن سجل مهارات المتدرب"""
    

    if user.is_college_admin and user.college_admin_college:
        college_name = user.college_admin_college
        college_departments = db.query(Department).filter(Department.college == college_name).all()
        dept_names = [d.name for d in college_departments]
        
        if not dept_names:
            raise HTTPException(status_code=403, detail="لم يتم العثور على أقسام في كليتك")
        

        sql = """
            SELECT DISTINCT
                e.trainee_no,
                e.trainee_name,
                c.id as course_id,
                c.title as course_title,
                c.description,
                c.hours,
                c.start_date,
                c.end_date,
                c.provider,
                cv.certificate_code,
                cv.copy_no,
                cv.created_at as certificate_date
            FROM course_enrollments e
            INNER JOIN courses c ON e.course_id = c.id
            INNER JOIN course_target_departments ctd ON c.id = ctd.course_id
            LEFT JOIN certificate_verifications cv ON 
                e.course_id = cv.course_id AND 
                e.trainee_no = cv.trainee_no AND
                cv.copy_no = 1
            WHERE e.trainee_no = :trainee_no AND ctd.department_name IN ({})
            ORDER BY c.start_date DESC
        """.format(','.join([f"'{d}'" for d in dept_names]))
    else:
        # البحث عن بيانات المتدرب بدون تصفية (للأدمن والمستخدمين العاديين)
        sql = """
            SELECT DISTINCT
                e.trainee_no,
                e.trainee_name,
                c.id as course_id,
                c.title as course_title,
                c.description,
                c.hours,
                c.start_date,
                c.end_date,
                c.provider,
                cv.certificate_code,
                cv.copy_no,
                cv.created_at as certificate_date
            FROM course_enrollments e
            INNER JOIN courses c ON e.course_id = c.id
            LEFT JOIN certificate_verifications cv ON 
                e.course_id = cv.course_id AND 
                e.trainee_no = cv.trainee_no AND
                cv.copy_no = 1
            WHERE e.trainee_no = :trainee_no
            ORDER BY c.start_date DESC
        """
    
    query = text(sql)
    results = db.execute(query, {"trainee_no": trainee_no}).mappings().all()
    
    if not results:
        raise HTTPException(status_code=404, detail="لم يتم العثور على المتدرب")
    

    trainee_info = {
        "trainee_no": results[0]["trainee_no"],
        "trainee_name": results[0]["trainee_name"],
        "courses": [],
        "total_hours": 0,
        "total_certificates": 0,
        "completed_courses": 0,
        "department": None,
        "college": None
    }

    trainee_user = db.query(User).filter(User.username == trainee_no).first()
    if trainee_user:
        user_dept = getattr(trainee_user, 'department', None)
        user_college = getattr(trainee_user, 'college', None)

        if user_dept:
            dept = db.query(Department).filter(Department.name == user_dept).first()
            if dept:
                trainee_info["department"] = dept.name
                if dept.college:
                    college = db.query(College).filter(College.name == dept.college).first()
                    if college:
                        trainee_info["college"] = college.name
            else:
                trainee_info["department"] = user_dept
        
        if not trainee_info["college"] and user_college:
            college = db.query(College).filter(College.name == user_college).first()
            if college:
                trainee_info["college"] = college.name
            else:
                trainee_info["college"] = user_college

    if not trainee_info["department"]:
        enrollment = db.execute(
            text("SELECT trainee_major FROM course_enrollments WHERE trainee_no = :tno AND trainee_major IS NOT NULL LIMIT 1"),
            {"tno": trainee_no}
        ).mappings().first()
        
        if enrollment and enrollment["trainee_major"]:
            major_str = enrollment["trainee_major"]
            if " - " in major_str:
                parts = major_str.split(" - ")
                if len(parts) >= 2:
                    trainee_info["department"] = parts[0].strip()
                    possible_college = parts[-1].strip()
                    if "كلية" in possible_college:
                        trainee_info["college"] = possible_college
            
            if not trainee_info["department"]:
                trainee_info["department"] = major_str

    if trainee_info["department"] and not trainee_info["college"]:
        dept = db.query(Department).filter(Department.name == trainee_info["department"]).first()
        if dept and dept.college:
            college = db.query(College).filter(College.name == dept.college).first()
            trainee_info["college"] = college.name if college else dept.college
    
    for row in results:
        course_info = {
            "course_id": row["course_id"],
            "course_title": row["course_title"],
            "description": row["description"],
            "hours": row["hours"] or 0,
            "start_date": row["start_date"],
            "end_date": row["end_date"],
            "provider": row["provider"],
            "certificate_code": row["certificate_code"],
            "certificate_date": row["certificate_date"]
        }
        
        trainee_info["courses"].append(course_info)
        trainee_info["total_hours"] += course_info["hours"]
        if row["certificate_code"]:
            trainee_info["total_certificates"] += 1
        trainee_info["completed_courses"] = len(trainee_info["courses"])
    

    colleges_map = {}
    for c in trainee_info.get("courses", []):
        col = c.get("college")
        if col and col.get("name"):
            name = col.get("name")
            if name not in colleges_map:
                colleges_map[name] = {
                    "name": name,
                    "dean_name": col.get("dean_name", ""),
                    "vp_name": col.get("vp_name", ""),
                    "dean_sign_url": col.get("dean_sign_url", "/static/blank.png"),
                    "vp_sign_url": col.get("vp_sign_url", "/static/blank.png"),
                    "stamp_url": col.get("stamp_url", "/static/blank.png"),
                }

    if not colleges_map and trainee_info.get("college"):
        col = db.query(College).filter(College.name == trainee_info.get("college")).first()
        if col:
            colleges_map[col.name] = {
                "name": col.name,
                "dean_name": col.dean_name or "",
                "vp_name": col.vp_students_name or "",
                "dean_sign_url": col.dean_sign_path if getattr(col, "dean_sign_path", None) else "/static/blank.png",
                "vp_sign_url": col.vp_students_sign_path if getattr(col, "vp_students_sign_path", None) else "/static/blank.png",
                "stamp_url": col.students_affairs_stamp_path if getattr(col, "students_affairs_stamp_path", None) else "/static/blank.png",
            }

    colleges = list(colleges_map.values())

    return templates.TemplateResponse(
        "hod/skills_record_report.html",
        {
            "request": request,
            "trainee": trainee_info,
            "colleges": colleges,
        }
    )

@router.get("/skills-record/search")
def skills_record_search(
    request: Request,
    trainee_no: str = Query("", min_length=0),
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_hod_or_admin)
):
    """البحث عن سجل مهارات المتدرب برقمه فقط"""
    if not trainee_no:
        return templates.TemplateResponse(
            "hod/skills_record.html",
            {"request": request, "error": "يرجى إدخال رقم المتدرب", "current_user": user}
        )
    
    # Build the query - filter by college if user is college_admin
    if user.is_college_admin and user.college_admin_college:
        college_name = user.college_admin_college
        college_departments = db.query(Department).filter(Department.college == college_name).all()
        dept_names = [d.name for d in college_departments]
        
        if not dept_names:
            # No departments for this college
            return templates.TemplateResponse(
                "hod/skills_record.html",
                {"request": request, "not_found": True, "search_query": trainee_no, "current_user": user}
            )
        
        # بناء الـ query مع تصفية حسب الكلية
        sql = """
            SELECT DISTINCT
                e.trainee_no,
                e.trainee_name,
                c.id as course_id,
                c.title as course_title,
                c.description,
                c.hours,
                c.start_date,
                c.end_date,
                c.provider,
                cv.certificate_code,
                cv.copy_no,
                cv.created_at as certificate_date
            FROM course_enrollments e
            INNER JOIN courses c ON e.course_id = c.id
            INNER JOIN course_target_departments ctd ON c.id = ctd.course_id
            LEFT JOIN certificate_verifications cv ON 
                e.course_id = cv.course_id AND 
                e.trainee_no = cv.trainee_no AND
                cv.copy_no = 1
            WHERE e.trainee_no LIKE :no AND ctd.department_name IN ({})
            ORDER BY e.trainee_no, c.start_date DESC
        """.format(','.join([f"'{d}'" for d in dept_names]))
    else:

        sql = """
            SELECT DISTINCT
                e.trainee_no,
                e.trainee_name,
                c.id as course_id,
                c.title as course_title,
                c.description,
                c.hours,
                c.start_date,
                c.end_date,
                c.provider,
                cv.certificate_code,
                cv.copy_no,
                cv.created_at as certificate_date
            FROM course_enrollments e
            INNER JOIN courses c ON e.course_id = c.id
            LEFT JOIN certificate_verifications cv ON 
                e.course_id = cv.course_id AND 
                e.trainee_no = cv.trainee_no AND
                cv.copy_no = 1
            WHERE e.trainee_no LIKE :no
            ORDER BY e.trainee_no, c.start_date DESC
        """
    
    params = {"no": f"%{trainee_no}%"}
    
    query = text(sql)
    results = db.execute(query, params).mappings().all()
    
    if not results:
        return templates.TemplateResponse(
            "hod/skills_record.html",
            {"request": request, "not_found": True, "search_query": trainee_no, "current_user": user}
        )
    
    # تجميع البيانات حسب المتدرب
    trainee_data = {}
    
    for row in results:
        key = row["trainee_no"]
        if key not in trainee_data:
            trainee_data[key] = {
                "trainee_no": row["trainee_no"],
                "trainee_name": row["trainee_name"],
                "courses": [],
                "total_hours": 0,
                "total_certificates": 0
            }
        
        course_info = {
            "course_id": row["course_id"],
            "course_title": row["course_title"],
            "description": row["description"],
            "hours": row["hours"] or 0,
            "start_date": row["start_date"],
            "end_date": row["end_date"],
            "provider": row["provider"],
            "certificate_code": row["certificate_code"],
            "certificate_date": row["certificate_date"]
        }
        
        trainee_data[key]["courses"].append(course_info)
        trainee_data[key]["total_hours"] += course_info["hours"]
        if row["certificate_code"]:
            trainee_data[key]["total_certificates"] += 1
    
    # تحويل إلى قائمة
    trainees = list(trainee_data.values())
    
    # حساب الإجماليات
    total_hours = sum(t["total_hours"] for t in trainees)
    total_certificates = sum(t["total_certificates"] for t in trainees)
    total_courses = sum(len(t["courses"]) for t in trainees)
    
    return templates.TemplateResponse(
        "hod/skills_record.html",
        {
            "request": request,
            "trainees": trainees,
            "total_hours": total_hours,
            "total_certificates": total_certificates,
            "total_courses": total_courses,
            "search_query": trainee_no,
            "results_count": len(trainees),
            "current_user": user
        }
    )