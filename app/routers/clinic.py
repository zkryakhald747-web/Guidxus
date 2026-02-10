from datetime import date
import json, math, io, os, re
from fastapi import APIRouter, Request, Depends, Query, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from ..reports.rest_notice_template import REST_NOTICE_HTML
from ..reports.referral_notice_template import REFERRAL_NOTICE_HTML
from jinja2 import Template
from xhtml2pdf import pisa
from pathlib import Path
from urllib.parse import urlparse, unquote
from typing import List

from ..database import get_db, is_sqlite
from ..deps_auth import require_doc

router = APIRouter(prefix="/clinic", tags=["Clinic"])
templates = Jinja2Templates(directory="app/templates")

_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

def norm_digits(s: str | None) -> str:
    """تحويل الأرقام العربية/الفارسية إلى لاتينية وإزالة المسافات البيضاء."""
    if s is None:
        return ""
    return str(s).translate(_ARABIC_DIGITS).strip()

def to_none_if_blank(s: str | None) -> str | None:
    """إرجاع None إن كان النص فارغًا بعد التشذيب."""
    if s is None:
        return None
    t = str(s).strip()
    return t if t else None

def to_int(s: str | None) -> int | None:
    """تحويل إلى int بأمان (يدعم أرقامًا عربية)."""
    if s is None:
        return None
    t = norm_digits(s)
    if not t:
        return None
    try:
        return int(t)
    except Exception:
        return None

def to_float(s: str | None) -> float | None:
    """تحويل إلى float بأمان (يدعم فاصل عشري عربي أو إنجليزي)."""
    if s is None:
        return None
    t = norm_digits(s).replace(",", ".")
    if not t:
        return None
    try:
        return float(t)
    except Exception:
        return None

def _build_font_ready_css() -> str:
    parts = []
    font_dir = Path("app/static/fonts")

    for name in ["Majalla.ttf", "alfont_com_majalla.ttf"]:
        p = font_dir / name
        if p.exists():
            parts.append(f"@font-face {{ font-family:'MajallaAR'; src:url('/static/fonts/{name}') format('truetype'); }}")
            break

    for name in ["Traditional-Arabic.ttf", "Traditional Arabic.ttf"]:
        p = font_dir / name
        if p.exists():
            parts.append(f"@font-face {{ font-family:'TradArabicAR'; src:url('/static/fonts/{name}') format('truetype'); }}")
            break

    return "\n".join(parts)

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

def _html_to_pdf_bytes(html: str) -> bytes:
    pdf_io = io.BytesIO()
    pisa.CreatePDF(src=html, dest=pdf_io, encoding="UTF-8", link_callback=_link_callback)
    return pdf_io.getvalue()

def _as_rec_dict(val):
    """إرجاع rec_json كقاموس dict سواء أتى من Postgres كـ jsonb (dict) أو كنص JSON."""
    if isinstance(val, dict):
        return val
    if isinstance(val, (bytes, bytearray)):
        try:
            return json.loads(val.decode("utf-8"))
        except Exception:
            return None
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return None
        try:
            return json.loads(s)
        except Exception:
            return None
    return None

# ================= تقارير — المسارات القديمة متوقفة =================
@router.get("/reports/rest_notice")
def export_rest_notice_legacy_disabled(
    request: Request,
    user=Depends(require_doc),
):
    return JSONResponse({"error": "تم إيقاف هذا المسار. استخدم /clinic/reports/rest_notice/by_visit?visit_id=..."},
                        status_code=410)

@router.get("/reports/referral_notice")
def export_referral_notice_legacy_disabled(
    request: Request,
    user=Depends(require_doc),
):
    return JSONResponse({"error": "تم إيقاف هذا المسار. استخدم /clinic/reports/referral_notice/by_visit?visit_id=..."},
                        status_code=410)

# ================= تقارير — مسارات آمنة حسب الزيارة =================
# --- استخراج إحالة قديمة من rec_detail ---
def _parse_legacy_referral(detail: str | None) -> tuple[str | None, str | None]:
    """
    يتوقع صيغًا مثل:
    'إحالة: مستشفى الملك خالد - السبب: ضيق في التنفس...'
    أو أي نص يبدأ بكلمة إحالة ثم الجهة ثم (اختياريًا) السبب.
    """
    if not detail:
        return None, None
    t = str(detail).strip()
    # إزالة أسطر زائدة
    t = re.sub(r'\s+', ' ', t)
    # نمط: إحالة : <الجهة> ( -/—/– )? السبب : <الخلاصة> (اختياري)
    m = re.search(r'إحالة\s*[:\-]?\s*(.+?)(?:\s*(?:-|—|–)?\s*السبب\s*[:\-]\s*(.+))?$', t)
    if m:
        to_ = (m.group(1) or '').strip(' .،؛-—–')
        summ = (m.group(2) or '').strip(' .،؛-—–')
        return (to_ or None), (summ or None)
    # fallback أبسط: خذ كل شيء بعد "إحالة"
    m2 = re.search(r'إحالة\s*[:\-]?\s*(.+)$', t)
    if m2:
        to_ = (m2.group(1) or '').strip(' .،؛-—–')
        return (to_ or None), None
    return None, None

@router.get("/reports/rest_notice/by_visit")
def export_rest_notice_by_visit(
    request: Request,
    visit_id: int = Query(..., ge=1),
    user=Depends(require_doc),
    db: Session = Depends(get_db),
):
    # اجلب الزيارة + الحقول التي نحتاجها
    v = db.execute(text("""
        SELECT id, patient_type, trainee_no, employee_no,
               visit_at, rec_json, recommendation, rest_days, chronic_json
        FROM clinic_patients
        WHERE record_kind='visit' AND id=:vid
        LIMIT 1
    """), {"vid": visit_id}).mappings().first()
    if not v:
        return JSONResponse({"error": "لم يتم العثور على الزيارة"}, status_code=404)

    days = None
    rec = None
    try:
        rec = json.loads(v.get("rec_json") or "{}")
    except Exception:
        rec = None

    if isinstance(rec, dict) and (rec.get("type") == "rest"):
        d = rec.get("days")
        if isinstance(d, int):
            days = d
        elif isinstance(d, str) and d.isdigit():
            days = int(d)

    if days is None and v.get("recommendation") == "rest":
        rd = v.get("rest_days")
        if isinstance(rd, int):
            days = rd
        elif isinstance(rd, str) and rd.isdigit():
            days = int(rd)

    if not days:
        return JSONResponse({"error": "هذه الزيارة لا تحتوي على إجازة مرضية"}, status_code=400)

    patient_key = f"T:{v['trainee_no']}" if v["patient_type"] == "trainee" else f"E:{v['employee_no']}"

    card = _get_patient_card(db, patient_key)
    if not card:
        return JSONResponse({"error": "لا يوجد ملف للمراجع"}, status_code=404)

    logo_src = None
    for p in ("images/main_logo.png", "images/favicon.ico", "images/logo.png", "img/logo.png"):
        fp = Path("app/static").joinpath(p)
        if fp.exists():
            logo_src = f"/static/{p}"
            break

    payload = {
        "patient": {
            "patient_type": "trainee" if card.get("trainee_no") else "employee",
            "full_name": card.get("full_name"),
            "trainee_no": card.get("trainee_no"),
            "employee_no": card.get("employee_no"),
            "national_id": card.get("id_no"),
            "mobile": card.get("mobile"),
            "major": card.get("major"),
            "birth_date": card.get("birth_date"),
            "age": card.get("age"),
        },
        "visit_date": (
            v["visit_at"].date().isoformat() if hasattr(v.get("visit_at"), 'date') 
            else (str(v.get("visit_at")).split()[0] if v.get("visit_at") else "")
        ),
        "rest_days": int(days),
        "visit": {
            "chronic_json": v.get("chronic_json"),
        },
        "doctor_name": (request.session.get("user") or {}).get("full_name"),
        "created_by_name": (request.session.get("user") or {}).get("full_name"),
        "logo_src": logo_src,
        "font_ready_css": _build_font_ready_css(),
        "shape": _shape_ar_safe,
    }

    html = Template(REST_NOTICE_HTML).render(**payload)
    pdf_bytes = _html_to_pdf_bytes(html)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="rest_notice_{visit_id}.pdf"'}
    )
def _clean_treatment_from_notes(notes: str | None) -> str | None:
    """
    تحذف سطر المؤشرات الحيوية (الوزن/الطول/BMI/سكر/O₂) وجملة 'الأمراض المزمنة:'
    من notes وتعيد فقط العلاج/التعليمات التي كتبها الطبيب.
    """
    if not notes:
        return None
    t = str(notes).strip()
    if not t:
        return None

    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    out = []
    for i, ln in enumerate(lines):

        if i == 0 and any(k in ln for k in ("الوزن", "الطول", "BMI", "O₂", "سكر الدم")):
            continue

        if ln.startswith("الأمراض المزمنة"):
            continue
        out.append(ln)

    cleaned = "\n".join(out).strip()
    return cleaned or None

@router.get("/reports/referral_notice/by_visit")
def export_referral_notice_by_visit(
    request: Request,
    visit_id: int = Query(..., ge=1),
    user=Depends(require_doc),
    db: Session = Depends(get_db),
):
    v = db.execute(text("""
        SELECT id, patient_type, trainee_no, employee_no,
               visit_at, diagnosis, rec_json, recommendation, rec_detail,
               temp_c, bp_systolic, bp_diastolic, pulse_bpm,
               chronic_json, complaint, notes
        FROM clinic_patients
        WHERE record_kind='visit' AND id=:vid
        LIMIT 1
    """), {"vid": visit_id}).mappings().first()
    if not v:
        return JSONResponse({"error": "لم يتم العثور على الزيارة"}, status_code=404)

    # rec_json (إحالة)
    referral_to = None
    referral_summary = None
    rj = _as_rec_dict(v.get("rec_json"))
    if isinstance(rj, dict) and rj.get("type") == "referral" and rj.get("to"):
        referral_to = rj.get("to")
        referral_summary = (rj.get("summary") or "").strip() or None

    # fallback قديم
    if not referral_to and (v.get("recommendation") == "referral"):
        legacy_to, legacy_summary = _parse_legacy_referral(v.get("rec_detail"))
        if legacy_to:
            referral_to = legacy_to
            referral_summary = legacy_summary

    if not referral_to:
        return JSONResponse({"error": "هذه الزيارة لا تحتوي على إحالة"}, status_code=400)

    # بطاقة المراجع
    patient_key = f"T:{v['trainee_no']}" if v["patient_type"] == "trainee" else f"E:{v['employee_no']}"
    card = _get_patient_card(db, patient_key)
    if not card:
        return JSONResponse({"error": "لا يوجد ملف للمراجع"}, status_code=404)

    # الشعار
    logo_src = None
    for p in ("images/main_logo.png", "images/favicon.ico", "images/logo.png", "img/logo.png"):
        fp = Path("app/static").joinpath(p)
        if fp.exists():
            logo_src = f"/static/{p}"
            break

    # الأمراض المزمنة: حوّل لنص "لا يوجد" إذا غير موجودة
    chronic_val = v.get("chronic_json")
    if isinstance(chronic_val, str):
        try:
            chronic_val = json.loads(chronic_val)
        except Exception:
            pass
    if not chronic_val:  # None أو [] أو ""
        chronic_val = "لا يوجد"

    # العلاج المعطى المنقّى من الإضافات الآلية
    treatment_given = _clean_treatment_from_notes(v.get("notes"))

    payload = {
        "patient": {
            "patient_type": "trainee" if card.get("trainee_no") else "employee",
            "full_name": card.get("full_name"),
            "trainee_no": card.get("trainee_no"),
            "employee_no": card.get("employee_no"),
            "national_id": card.get("id_no"),
            "mobile": card.get("mobile"),
            "major": card.get("major"),
            "birth_date": card.get("birth_date"),
            "age": card.get("age"),
        },
        "visit_date": (
            v["visit_at"].date().isoformat() if hasattr(v.get("visit_at"), 'date') 
            else (str(v.get("visit_at")).split()[0] if v.get("visit_at") else "")
        ),
        "referral_to": referral_to,
        "referral_summary": referral_summary or "",
        "diagnosis": v.get("diagnosis") or "",

        # لجدول الفحص السريري
        "temp_c": v.get("temp_c"),
        "bp_systolic": v.get("bp_systolic"),
        "bp_diastolic": v.get("bp_diastolic"),
        "pulse_bpm": v.get("pulse_bpm"),
        "chronic_json": chronic_val,
        "complaint": v.get("complaint"),

        # نمرّر العلاج المعطى بشكل صريح (حتى لا يقع القالب على notes ويعرض الإضافات)
        "treatment_given": treatment_given,

        # (اختياري) إن أردت إبقاء notes للأرشفة لكنها لن تظهر طالما treatment_given موجود
        "notes": v.get("notes"),

        "doctor_name": (request.session.get("user") or {}).get("full_name"),
        "created_by_name": (request.session.get("user") or {}).get("full_name"),
        "logo_src": logo_src,
        "font_ready_css": _build_font_ready_css(),
        "shape": _shape_ar_safe,
    }

    html = Template(REFERRAL_NOTICE_HTML).render(**payload)
    pdf_bytes = _html_to_pdf_bytes(html)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="referral_{visit_id}.pdf"'}
    )

_MOBILE_RE = re.compile(r"^(?:0?5)\d{8}$")  # 05xxxxxxxx أو 5xxxxxxxx
def valid_mobile(m: str | None) -> bool:
    if not m:
        return True
    m = norm_digits(m)
    return bool(_MOBILE_RE.match(m))

def parse_patient_key(patient_key: str) -> tuple[str, str]:
    # T:123456 أو E:1001
    t = patient_key.split(":", 1)
    if len(t) != 2:
        raise ValueError("patient_key غير صالح.")
    return t[0].upper(), norm_digits(t[1])

def build_recommendation(
    recommendation: str,
    rec_detail: str | None,
    rest_days: str | None,
    rec_to: str | None,
    rec_summary: str | None,
):
    """
    تُرجع: (rec_type, rec_detail, rest_days, rec_json_str)
    - none: rec_json=None
    - rest: rec_json={"type":"rest","days":N}
    - referral: rec_json={"type":"referral","to":...,"summary":...}
    """
    rec = recommendation if recommendation in ("none", "rest", "referral") else "none"
    if rec == "none":
        return rec, None, None, None
    if rec == "rest":
        rd = to_int(rest_days)
        if rd is None or rd < 1 or rd > 30:
            raise ValueError("يرجى تحديد عدد أيام الراحة بين 1 و 30.")
        return rec, None, rd, json.dumps({"type": "rest", "days": rd}, ensure_ascii=False)
    # referral
    dest = to_none_if_blank(rec_to)
    summ = to_none_if_blank(rec_summary) or to_none_if_blank(rec_detail)
    if not dest:
        raise ValueError("يرجى إدخال جهة الإحالة.")
    if not summ:
        raise ValueError("يرجى كتابة وصف الحالة/سبب الإحالة.")
    rec_json = {"type": "referral", "to": dest, "summary": summ}
    return rec, None, None, json.dumps(rec_json, ensure_ascii=False)

def clamp(v: float | None, lo: float, hi: float) -> float | None:
    if v is None: return None
    return max(lo, min(hi, v))

def bmi_calc(weight_kg: float | None, height_cm: float | None) -> float | None:
    try:
        if not weight_kg or not height_cm: return None
        h_m = height_cm / 100.0
        if h_m <= 0: return None
        return round(weight_kg / (h_m*h_m), 1)
    except Exception:
        return None

# ===== تشكيل عربي + حماية اتجاه (RTL) =====
try:
    import arabic_reshaper
    from bidi.algorithm import get_display as bidi_get_display
    _HAS_ARABIC = True
except Exception:
    _HAS_ARABIC = False

def _shape_ar_safe(s: str | None) -> str:
    """
    نسخة آمنة لـ xhtml2pdf: لا تحقن ALM/RLM ولا تُحاط الرموز،
    حتى لا تظهر كمربعات. نكتفي باستبدال الترقيم بالنسخة العربية + تشكيل BiDi.
    """
    if not s:
        return ""
    t = str(s)
    # استبدال الترقيم الشائع للنسخة العربية
    t = (t.replace(",", "،")
           .replace(";", "؛")
           .replace("?", "؟"))
    if _HAS_ARABIC:
        try:
            t = bidi_get_display(arabic_reshaper.reshape(t))
        except Exception:
            pass
    return t

def _get_patient_card(db: Session, patient_key: str):
    """يبني بطاقة المراجع لاستخدامها عند العرض/الأخطاء دون تكرار الكود."""
    try:
        ptype, pno = parse_patient_key(patient_key)
        patient = None
        
        try:
            if ptype == "T":
                patient = db.execute(text("""
                    SELECT full_name, trainee_no, national_id, mobile, major, college, birth_date
                    FROM clinic_patients
                    WHERE record_kind='profile' AND patient_type='trainee' AND trainee_no = :n
                    LIMIT 1
                """), {"n": pno}).mappings().first()
            else:
                patient = db.execute(text("""
                    SELECT full_name, employee_no, national_id, mobile, NULL AS major, NULL AS college, birth_date
                    FROM clinic_patients
                    WHERE record_kind='profile' AND patient_type='employee' AND employee_no = :n
                    LIMIT 1
                """), {"n": pno}).mappings().first()
        except Exception:

            if ptype == "T":
                try:
                    import sys
                    import os
                    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
                    from excel_data_reference import get_student_by_id
                    
                    student = get_student_by_id(pno)
                    if student:
                        patient = {
                            "full_name": student.get('student_Name', ''),
                            "trainee_no": pno,
                            "national_id": student.get('ID', ''),
                            "mobile": student.get('mobile', ''),
                            "major": student.get('Major', ''),
                            "college": student.get('College', ''),
                            "birth_date": student.get('birth_date') or student.get('DOB') or None,
                        }
                except Exception:
                    pass
        
        if not patient:
            return None

        age = None
        if patient.get("birth_date"):
            try:

                bd = patient["birth_date"]
                if isinstance(bd, str):

                    from datetime import datetime

                    try:
                        bd = datetime.strptime(bd, "%Y-%m-%d").date()
                    except:

                        try:
                            bd = datetime.strptime(bd, "%d/%m/%Y").date()
                        except:
                            bd = None
                
                if bd and isinstance(bd, date):
                    today = date.today()
                    age = today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
                    if age < 0:
                        age = None
            except Exception as e:
                age = None

        return {
            "full_name": patient.get("full_name"),
            "id_no": patient.get("national_id"),
            "mobile": patient.get("mobile"),
            "trainee_no": patient.get("trainee_no"),
            "employee_no": patient.get("employee_no"),
            "major": patient.get("major"),
            "college": patient.get("college"),
            "birth_date": patient.get("birth_date"),
            "age": age,
            "patient_key": patient_key,
        }
    except Exception:
        return None

@router.get("/", include_in_schema=False)
def clinic_index(request: Request, user=Depends(require_doc), db: Session = Depends(get_db)):
    def safe_count(sql):
        try:
            return db.execute(text(sql), {}).scalar() or 0
        except Exception:
            return 0
    stats = {
        "doctors": 1,
        "visits": safe_count("SELECT COUNT(*) FROM clinic_patients WHERE record_kind='visit'"),
        "referrals": safe_count("SELECT COUNT(*) FROM clinic_patients WHERE record_kind='visit' AND recommendation='referral'"),
        "leaves": safe_count("SELECT COUNT(*) FROM clinic_patients WHERE record_kind='visit' AND recommendation='rest'"),
        "pharmacy_drugs": safe_count("SELECT COUNT(*) FROM drugs"),
        "pharmacy_stock": safe_count("SELECT SUM(balance_qty) FROM pharmacy_stock"),
        "pharmacy_movements": safe_count("SELECT COUNT(*) FROM drug_movements"),
        "first_aid_boxes": safe_count("SELECT COUNT(*) FROM first_aid_boxes"),
        "first_aid_items": safe_count("SELECT COUNT(*) FROM first_aid_box_items"),
    }
    return templates.TemplateResponse("clinic/index.html", {"request": request, "stats": stats})

@router.get("/drugs/search")
def drugs_search(
    q: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=25),
    user=Depends(require_doc),
    db: Session = Depends(get_db),
):
    """
    يتوقع جدول public.drugs: id, trade_name, generic_name, strength, form
    """
    qn = f"%{q.strip()}%"

    if is_sqlite():
        like_clause = "UPPER(trade_name) LIKE UPPER(:q) OR UPPER(generic_name) LIKE UPPER(:q)"
    else:
        like_clause = "trade_name ILIKE :q OR generic_name ILIKE :q"
    rows = db.execute(
        text(f"""
            SELECT id, trade_name, generic_name, strength, form
            FROM public.drugs
            WHERE {like_clause}
            ORDER BY trade_name ASC
            LIMIT :limit
        """),
        {"q": qn, "limit": limit},
    ).mappings().all()

    items = []
    for r in rows:
        label = " / ".join(filter(None, [
            r.get("trade_name"),
            r.get("generic_name"),
            r.get("strength"),
            r.get("form"),
        ]))
        items.append({
            "id": r["id"],
            "label": label,
            "trade_name": r.get("trade_name"),
            "generic_name": r.get("generic_name"),
            "strength": r.get("strength"),
            "form": r.get("form"),
        })
    return JSONResponse({"items": items})

# ===================== الوصفات المصروفة (Dispensed Prescriptions) =====================
@router.get("/prescriptions")
def prescriptions_list(
    request: Request,
    user=Depends(require_doc),
    db: Session = Depends(get_db),
):
    try:
        # جلب الوصفات المصروفة من قاعدة البيانات
        from app.models import Prescription
        prescriptions = db.query(Prescription).all() if hasattr(Prescription, '__table__') else []
    except Exception:
        prescriptions = []
    
    return templates.TemplateResponse(
        "clinic/prescriptions.html",
        {
            "request": request,
            "prescriptions": prescriptions,
            "user": user,
        }
    )

# ===================== الملف الطبي (إنشاء/تعديل ملف/بحث) =====================
@router.get("/patients")
def patients_home(
    request: Request,
    tab: str = Query("create", pattern="^(create|search)$"),
    patient_type: str | None = Query(default=None),  # 'trainee' | 'employee'
    trainee_no: str | None = Query(default=None),
    mode: str | None = Query(default=None),  # 'edit'
    patient_key: str | None = Query(default=None),  # T:xxx أو E:yyy
    q: str | None = Query(default=None),
    user=Depends(require_doc),
    db: Session = Depends(get_db),
):
    ctx = {
        "request": request,
        "tab": tab,
        "q": q,
        "prefill": None,
        "error": None,
        "msg": request.query_params.get("msg"),
        "confirm": request.query_params.get("confirm"),
        "confirm_name": request.query_params.get("name"),
        "confirm_patient_key": request.query_params.get("patient_key"),
        "edit_profile": None,
        "selected_patient_type": patient_type or "trainee",
        "results": None,
    }

    # ===== وضع تعديل الملف =====
    if tab == "create" and mode == "edit" and patient_key:
        try:
            ptype, pno = parse_patient_key(patient_key)
            row = None
            
            try:
                if ptype == "T":
                    row = db.execute(text("""
                        SELECT id, full_name, trainee_no, national_id, mobile, major, college, birth_date
                        FROM clinic_patients
                        WHERE record_kind='profile' AND patient_type='trainee' AND trainee_no = :n
                        LIMIT 1
                    """), {"n": pno}).mappings().first()
                else:
                    row = db.execute(text("""
                        SELECT id, full_name, employee_no, national_id, mobile, birth_date
                        FROM clinic_patients
                        WHERE record_kind='profile' AND patient_type='employee' AND employee_no = :n
                        LIMIT 1
                    """), {"n": pno}).mappings().first()
            except Exception:
                # محاولة الحصول من Excel
                if ptype == "T":
                    try:
                        import sys
                        import os
                        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
                        from excel_data_reference import get_student_by_id
                        
                        student = get_student_by_id(pno)
                        if student:
                            row = {
                                "id": None,
                                "full_name": student.get('student_Name', ''),
                                "trainee_no": pno,
                                "national_id": student.get('ID', ''),
                                "mobile": student.get('mobile', ''),
                                "major": student.get('Major', ''),
                                "college": student.get('College', ''),
                                "birth_date": None,
                            }
                    except Exception:
                        pass

            if not row:
                ctx["error"] = "لا يوجد ملف طبي لهذا المراجع."
            else:
                ctx["edit_profile"] = {
                    "id": row.get("id"),
                    "patient_key": patient_key,
                    "patient_type": "trainee" if ptype == "T" else "employee",
                    "full_name": row.get("full_name"),
                    "trainee_no": row.get("trainee_no"),
                    "employee_no": row.get("employee_no"),
                    "national_id": row.get("national_id"),
                    "major": row.get("major"),
                    "college": row.get("college"),
                    "mobile": row.get("mobile"),
                    "birth_date": row.get("birth_date"),
                }
                ctx["selected_patient_type"] = ctx["edit_profile"]["patient_type"]
        except Exception as ex:
            ctx["error"] = f"تعذر تحميل بيانات الملف: {ex}"
        return templates.TemplateResponse("clinic/patients.html", ctx)

    # ===== جلب بيانات متدرب من sf01 عند الإنشاء =====
    if tab == "create" and patient_type:
        ptype = patient_type
        trainee_no = norm_digits(trainee_no) if trainee_no else None
        if ptype == "trainee" and trainee_no:
            try:
                exists = None
                try:
                    exists = db.execute(text("""
                        SELECT id, full_name
                        FROM clinic_patients
                        WHERE record_kind='profile' AND patient_type='trainee' AND trainee_no = :n
                        LIMIT 1
                    """), {"n": trainee_no}).mappings().first()
                except Exception:
                    pass

                if exists:
                    return templates.TemplateResponse(
                        "clinic/patients.html",
                        {**ctx, "confirm": "profile_found", "confirm_name": exists["full_name"], "confirm_patient_key": f"T:{trainee_no}"}
                    )
                
                row = None
                try:
                    row = db.execute(text("""
                        SELECT "student_id" AS trainee_no, "student_Name" AS full_name, "mobile" AS mobile,
                               "ID" AS national_id, "Major" AS major, "College" AS college
                        FROM sf01
                        WHERE "student_id" = :t
                        LIMIT 1
                    """), {"t": trainee_no}).mappings().first()
                except Exception:
                    # جدول sf01 قد لا يكون موجود، حاول من Excel
                    try:
                        import sys
                        import os
                        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
                        from excel_data_reference import get_student_by_id
                        
                        student = get_student_by_id(trainee_no)
                        if student:
                            row = {
                                "trainee_no": trainee_no,
                                "full_name": student.get('student_Name', ''),
                                "mobile": student.get('mobile', ''),
                                "national_id": student.get('ID', ''),
                                "major": student.get('Major', ''),
                                "college": student.get('College', ''),
                            }
                    except Exception:
                        row = None
                
                if not row:
                    ctx["error"] = f"لم يتم العثور على المتدرب ({trainee_no}) في قاعدة البيانات."
                else:
                    def _s(v): return "" if v is None else str(v)
                    ctx["prefill"] = {
                        "patient_type": "trainee",
                        "trainee_no": _s(row.get("trainee_no")),
                        "full_name": row.get("full_name"),
                        "national_id": _s(row.get("national_id")),
                        "mobile": _s(row.get("mobile")),
                        "major": row.get("major"),
                        "college": row.get("college"),
                        "birth_date": "",
                    }
            except Exception as ex:
                ctx["error"] = f"تعذّر الجلب: {ex}"

    # ===== بحث عن ملف =====
    if tab == "search" and q:
        try:
            raw_q = q.strip()
            nd = norm_digits(raw_q) or None
            like_q = f"%{raw_q}%"

            # بحث المتدربين والموظفين من قاعدة البيانات
            trainees = []
            employees = []
            
            try:
                trainees = db.execute(text("""
                    SELECT p.id, 'trainee' AS patient_type, p.full_name, p.trainee_no, p.national_id,
                           p.mobile, p.major, p.college,
                           (SELECT MAX(v.visit_at) FROM clinic_patients v
                             WHERE v.record_kind='visit' AND v.patient_type='trainee' AND v.trainee_no=p.trainee_no) AS last_visit_at,
                           (SELECT COUNT(*) FROM clinic_patients v
                             WHERE v.record_kind='visit' AND v.patient_type='trainee' AND v.trainee_no=p.trainee_no) AS visit_count
                    FROM clinic_patients p
                    WHERE p.record_kind='profile' AND p.patient_type='trainee'
                      AND (
                            (:nd IS NOT NULL AND (p.trainee_no = :nd OR p.national_id = :nd))
                            OR UPPER(p.full_name) LIKE UPPER(:like_q)
                            OR (:nd IS NOT NULL AND p.mobile LIKE ('%' || :nd || '%'))
                          )
                    ORDER BY p.full_name ASC
                    LIMIT 20
                """), {"nd": nd, "like_q": like_q}).mappings().all()

                employees = db.execute(text("""
                    SELECT p.id, 'employee' AS patient_type, p.full_name, p.employee_no, p.national_id,
                           p.mobile, NULL AS major, NULL AS college,
                           (SELECT MAX(v.visit_at) FROM clinic_patients v
                             WHERE v.record_kind='visit' AND v.patient_type='employee' AND v.employee_no=p.employee_no) AS last_visit_at,
                           (SELECT COUNT(*) FROM clinic_patients v
                             WHERE v.record_kind='visit' AND v.patient_type='employee' AND v.employee_no=p.employee_no) AS visit_count
                    FROM clinic_patients p
                    WHERE p.record_kind='profile' AND p.patient_type='employee'
                      AND (
                            (:nd IS NOT NULL AND (p.employee_no = :nd OR p.national_id = :nd))
                            OR UPPER(p.full_name) LIKE UPPER(:like_q)
                            OR (:nd IS NOT NULL AND p.mobile LIKE ('%' || :nd || '%'))
                          )
                    ORDER BY p.full_name ASC
                    LIMIT 20
                """), {"nd": nd, "like_q": like_q}).mappings().all()
            except Exception:
                # إذا فشلت جميع الاستعلامات، حاول من Excel مباشرة
                pass

            results = []
            
            # إضافة النتائج من قاعدة البيانات
            def _recent_visits(ptype: str, num: int):
                try:
                    if ptype == 'trainee':
                        rows = db.execute(text("""
                            SELECT id, visit_at, complaint, diagnosis, temp_c, bp_systolic, bp_diastolic,
                                   pulse_bpm, resp_rpm, weight_kg, height_cm, bmi, glucose_mg, o2_sat, chronic_json,
                                   notes, rec_json, rx_json
                            FROM clinic_patients
                            WHERE record_kind='visit' AND patient_type='trainee' AND trainee_no = :n
                            ORDER BY visit_at DESC
                            LIMIT 5
                        """), {"n": num}).mappings().all()
                    else:
                        rows = db.execute(text("""
                            SELECT id, visit_at, complaint, diagnosis, temp_c, bp_systolic, bp_diastolic,
                                   pulse_bpm, resp_rpm, weight_kg, height_cm, bmi, glucose_mg, o2_sat, chronic_json,
                                   notes, rec_json, rx_json
                            FROM clinic_patients
                            WHERE record_kind='visit' AND patient_type='employee' AND employee_no = :n
                            ORDER BY visit_at DESC
                            LIMIT 5
                        """), {"n": num}).mappings().all()
                except Exception:
                    rows = []
                    
                out = []
                for v in rows:
                    rj = v.get("rec_json")
                    if isinstance(rj, str):
                        try:
                            rj = json.loads(rj)
                        except Exception:
                            rj = None
                    cj = v.get("chronic_json")
                    if isinstance(cj, str):
                        try:
                            cj = json.loads(cj)
                        except Exception:
                            cj = None
                    out.append({
                        "id": v.get("id"),  # مهم للأزرار
                        "visit_at": v.get("visit_at"),
                        "complaint": v.get("complaint"),
                        "diagnosis": v.get("diagnosis"),
                        "temp_c": v.get("temp_c"),
                        "bp_systolic": v.get("bp_systolic"),
                        "bp_diastolic": v.get("bp_diastolic"),
                        "pulse_bpm": v.get("pulse_bpm"),
                        "resp_rpm": v.get("resp_rpm"),
                        "weight_kg": v.get("weight_kg"),
                        "height_cm": v.get("height_cm"),
                        "bmi": v.get("bmi"),
                        "glucose_mg": v.get("glucose_mg"),
                        "o2_sat": v.get("o2_sat"),
                        "chronic_json": cj,
                        "notes": v.get("notes"),
                        "rec_json": rj,
                        "rx_json": v.get("rx_json"),
                    })
                return out

            for r in trainees:
                results.append({
                    "patient_type": "trainee",
                    "full_name": r.get("full_name"),
                    "trainee_no": r.get("trainee_no"),
                    "employee_no": None,
                    "mobile": r.get("mobile"),
                    "major": r.get("major"),
                    "college": r.get("college"),
                    "last_visit_at": r.get("last_visit_at"),
                    "visit_count": r.get("visit_count") or 0,
                    "patient_key": f"T:{r.get('trainee_no')}",
                    "visits": _recent_visits('trainee', r.get("trainee_no")),
                })

            for r in employees:
                results.append({
                    "patient_type": "employee",
                    "full_name": r.get("full_name"),
                    "trainee_no": None,
                    "employee_no": r.get("employee_no"),
                    "mobile": r.get("mobile"),
                    "major": None,
                    "college": None,
                    "last_visit_at": r.get("last_visit_at"),
                    "visit_count": r.get("visit_count") or 0,
                    "patient_key": f"E:{r.get('employee_no')}",
                    "visits": _recent_visits('employee', r.get("employee_no")),
                })

            # إضافة النتائج من ملف الإكسيل إذا لم تكن هناك نتائج كافية
            if not results or len(results) < 20:
                try:
                    import sys
                    import os
                    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
                    from excel_data_reference import search_students, get_student_by_id
                    
                    excel_results = search_students(q)
                    
                    for student in excel_results[:10]:  # أضف 10 نتائج من الإكسيل كحد أقصى
                        student_id = str(student.get('student_id', '')).strip()
                        
                        # تجنب التكرار
                        if any(r.get('patient_key') == f"T:{student_id}" for r in results):
                            continue
                        
                        results.append({
                            "patient_type": "trainee",
                            "full_name": student.get('student_Name', ''),
                            "trainee_no": student_id,
                            "employee_no": None,
                            "mobile": None,
                            "major": student.get('Major', ''),
                            "college": student.get('College', ''),
                            "last_visit_at": None,
                            "visit_count": 0,
                            "patient_key": f"T:{student_id}",
                            "visits": [],
                            "excel_source": True  # علامة تشير أن البيانات من الإكسيل
                        })
                except Exception:
                    pass

            ctx["results"] = results

        except Exception as ex:
            ctx["error"] = f"فشل البحث: {ex}"

    return templates.TemplateResponse("clinic/patients.html", ctx)

@router.post("/patients/create")
def patients_create(
    request: Request,
    user=Depends(require_doc),
    db: Session = Depends(get_db),

    patient_type: str = Form(...),

    trainee_no: str | None = Form(default=None),
    full_name: str | None = Form(default=None),
    national_id: str | None = Form(default=None),
    mobile: str | None = Form(default=None),
    major: str | None = Form(default=None),
    college: str | None = Form(default=None),
    birth_date: str | None = Form(default=None),

    employee_no: str | None = Form(default=None),
    emp_full_name: str | None = Form(default=None),
    emp_national_id: str | None = Form(default=None),
    emp_mobile: str | None = Form(default=None),
    department: str | None = Form(default=None),
):
    try:
        uid = (request.session.get("user") or {}).get("id")

        if patient_type == "trainee":
            trainee_no = norm_digits(trainee_no)
            if not (trainee_no and full_name and national_id and major and college):
                raise ValueError("بيانات المتدرب غير مكتملة. رجاءً اجلب البيانات من قاعدة البيانات أولًا.")
            if not valid_mobile(mobile):
                raise ValueError("رقم الجوال غير صحيح. الصيغة المتوقعة: 05xxxxxxxx")

            exists = db.execute(text("""
                SELECT 1 FROM clinic_patients
                WHERE record_kind='profile' AND patient_type='trainee' AND trainee_no = :n
                LIMIT 1
            """), {"n": trainee_no}).first()
            if exists:
                return RedirectResponse(
                    url=f"/clinic/patients?tab=create&confirm=profile_found&patient_key=T:{trainee_no}&name={full_name}",
                    status_code=303
                )

            bd = to_none_if_blank(birth_date)
            db.execute(text("""
                INSERT INTO clinic_patients
                (patient_type, trainee_no, national_id, full_name, mobile, major, college, birth_date,
                 record_kind, created_by)
                VALUES
                ('trainee', :trainee_no, :national_id, :full_name, :mobile, :major, :college,
                 :birth_date, 'profile', :uid)
            """), {
                "trainee_no": trainee_no,
                "national_id": norm_digits(national_id),
                "full_name": full_name,
                "mobile": norm_digits(mobile) if mobile else None,
                "major": major,
                "college": college,
                "birth_date": bd,
                "uid": uid,
            })
            db.commit()
            return RedirectResponse(url=f"/clinic/visits/new?patient_key=T:{trainee_no}&msg=profile_saved", status_code=303)

        elif patient_type == "employee":
            employee_no = norm_digits(employee_no)
            if not (employee_no and emp_full_name and emp_national_id and emp_mobile):
                raise ValueError("بيانات الموظف غير مكتملة.")
            if not valid_mobile(emp_mobile):
                raise ValueError("رقم الجوال غير صحيح. الصيغة المتوقعة: 05xxxxxxxx")

            exists = db.execute(text("""
                SELECT 1 FROM clinic_patients
                WHERE record_kind='profile' AND patient_type='employee' AND employee_no = :n
                LIMIT 1
            """), {"n": employee_no}).first()
            if exists:
                return RedirectResponse(
                    url=f"/clinic/patients?tab=create&confirm=profile_found&patient_key=E:{employee_no}&name={emp_full_name}",
                    status_code=303
                )

            bd = to_none_if_blank(birth_date)
            db.execute(text("""
                INSERT INTO clinic_patients
                (patient_type, employee_no, national_id, full_name, mobile, birth_date, record_kind, notes, created_by)
                VALUES
                ('employee', :employee_no, :national_id, :full_name, :mobile,
                 :birth_date, 'profile', :dept, :uid)
            """), {
                "employee_no": employee_no,
                "national_id": norm_digits(emp_national_id),
                "full_name": emp_full_name,
                "mobile": norm_digits(emp_mobile),
                "birth_date": bd,
                "dept": to_none_if_blank(department),
                "uid": uid,
            })
            db.commit()
            return RedirectResponse(url=f"/clinic/visits/new?patient_key=E:{employee_no}&msg=profile_saved", status_code=303)

        else:
            raise ValueError("نوع المراجع غير صحيح.")

    except Exception as ex:
        db.rollback()
        ctx = {"request": request, "tab": "create", "q": None, "prefill": None, "error": str(ex)}
        return templates.TemplateResponse("clinic/patients.html", ctx)

@router.post("/patients/update_profile")
def update_profile(
    request: Request,
    user=Depends(require_doc),
    db: Session = Depends(get_db),

    patient_key: str = Form(...),
    mobile: str | None = Form(default=None),
    birth_date: str | None = Form(default=None),
):
    try:
        ptype, pno = parse_patient_key(patient_key)

        mobile = norm_digits(to_none_if_blank(mobile))
        birth_date = to_none_if_blank(birth_date)

        if mobile and not valid_mobile(mobile):
            raise ValueError("رقم الجوال غير صحيح. الصيغة المتوقعة: 05xxxxxxxx")

        if ptype == "T":
            row = db.execute(text("""
                SELECT id FROM clinic_patients
                WHERE record_kind='profile' AND patient_type='trainee' AND trainee_no = :n
                LIMIT 1
            """), {"n": pno}).mappings().first()
        else:
            row = db.execute(text("""
                SELECT id FROM clinic_patients
                WHERE record_kind='profile' AND patient_type='employee' AND employee_no = :n
                LIMIT 1
            """), {"n": pno}).mappings().first()

        if not row:
            raise ValueError("لا يوجد ملف طبي لهذا المراجع.")

        db.execute(text("""
            UPDATE clinic_patients
            SET mobile = COALESCE(:mobile, mobile),
                birth_date = COALESCE(:birth_date, birth_date),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :id AND record_kind='profile'
        """), {"mobile": mobile, "birth_date": birth_date, "id": row["id"]})
        db.commit()
        return RedirectResponse(url=f"/clinic/patients?tab=create&mode=edit&patient_key={ptype}:{pno}&msg=profile_updated", status_code=303)

    except Exception as ex:
        db.rollback()
        return RedirectResponse(url=f"/clinic/patients?tab=create&mode=edit&patient_key={patient_key}&msg={str(ex)}", status_code=303)

@router.get("/visits")
def visits_list(
    request: Request,
    user=Depends(require_doc),
    db: Session = Depends(get_db),
    start_date: str = Query(None, description="Start date for filtering"),
    end_date: str = Query(None, description="End date for filtering"),
    chronic_disease: str = Query(None, description="Chronic disease filter"),
):
    visits = []
    

    query = """
        SELECT 
            id,
            trainee_no,
            full_name,
            record_kind,
            college,
            complaint,
            diagnosis,
            created_at,
            visit_at,
            chronic_json
        FROM clinic_patients
        WHERE record_kind = 'visit'
    """
    
    params = {}
    
    # إضافة فلتر التاريخ
    if start_date:
        try:
            # التحقق من صيغة التاريخ
            from datetime import datetime
            datetime.strptime(start_date, '%Y-%m-%d')
            query += " AND visit_at >= :start_date"
            params["start_date"] = start_date
        except ValueError:
            pass
    
    if end_date:
        try:
            # التحقق من صيغة التاريخ
            from datetime import datetime
            datetime.strptime(end_date, '%Y-%m-%d')
            query += " AND visit_at <= :end_date"
            params["end_date"] = end_date + " 23:59:59"  # لتضمين اليوم بالكامل
        except ValueError:
            pass
    
    # إضافة فلتر الأمراض المزمنة
    if chronic_disease:
        query += " AND chronic_json LIKE :chronic_disease"
        params["chronic_disease"] = f"%{chronic_disease}%"
    
    query += " ORDER BY visit_at DESC NULLS LAST, created_at DESC"
    
    # جلب الزيارات من جدول clinic_patients مرتبة بالتاريخ
    try:
        all_patients = db.execute(text(query), params).fetchall()
        
        for row in all_patients:
            # معالجة بيانات الأمراض المزمنة
            chronic_data = row[9]
            print(f"=== CHRONIC DISEASE DEBUG ===")
            print(f"Row ID: {row[0]}, Name: {row[2]}")
            print(f"Raw chronic_data: {repr(chronic_data)}")
            print(f"Type: {type(chronic_data)}")
            
            if isinstance(chronic_data, str) and chronic_data.strip():
                try:
                    parsed_data = json.loads(chronic_data)
                    print(f"Parsed successfully: {repr(parsed_data)}")
                    chronic_data = parsed_data
                except (json.JSONDecodeError, Exception) as e:
                    print(f"Failed to parse JSON: {e}")
            elif chronic_data is None:
                print("chronic_data is None")
            elif chronic_data == '':
                print("chronic_data is empty string")
            else:
                print(f"chronic_data is already processed: {repr(chronic_data)}")
            
            print("===========================")
            
            visits.append({
                "id": row[0],
                "trainee_no": row[1],
                "full_name": row[2],
                "record_kind": row[3],
                "college": row[4],
                "complaint": row[5],
                "diagnosis": row[6],
                "created_at": row[7],
                "visit_at": row[8],
                "chronic_json": chronic_data,  # بيانات الأمراض المزمنة المعالجة
                "source": "database"
            })
    except Exception as e:
        print(f"خطأ في جلب البيانات من clinic_patients: {e}")
    
    return templates.TemplateResponse(
        "clinic/visits_list.html",
        {
            "request": request,
            "visits": visits,
            "user": user,
            "start_date": start_date,
            "end_date": end_date,
            "chronic_disease": chronic_disease,
        }
    )

# ===================== الزيارات =====================
@router.get("/visits/new")
def visit_form_get(
    request: Request,
    patient_key: str | None = None,
    msg: str | None = None,
    user=Depends(require_doc),
    db: Session = Depends(get_db),
):
    card = _get_patient_card(db, patient_key) if patient_key else None
    return templates.TemplateResponse(
        "clinic/visit_form.html",
        {"request": request, "patient_card": card, "msg": msg, "form_vals": None}
    )

@router.post("/visits/create")
def visit_create(
    request: Request,
    user=Depends(require_doc),
    db: Session = Depends(get_db),

    patient_key: str = Form(...),

    temp: str | None = Form(default=None),
    bp: str | None = Form(default=None),
    pulse: str | None = Form(default=None),
    resp: str | None = Form(default=None),

    weight_kg: str | None = Form(default=None),
    height_cm: str | None = Form(default=None),

    # جديد (علامات حيوية إضافية)
    glucose_mg: str | None = Form(default=None),   # نسبة السكر mg/dL
    o2_sat: str | None = Form(default=None),       # تشبع الأكسجين %

    complaint: str | None = Form(default=None),
    diagnosis: str | None = Form(default=None),
    notes: str | None = Form(default=None),

    # التوصية
    recommendation: str = Form(default="none"),
    rec_detail: str | None = Form(default=None),     # للتوافق الخلفي فقط
    rest_days: str | None = Form(default=None),
    rec_to: str | None = Form(default=None),         # جديد
    rec_summary: str | None = Form(default=None),    # جديد

    # جديد (أمراض مزمنة)
    chronic: List[str] = Form(default=[]),           # ['ضغط','سكر','ربو','صرع','أخرى']
    chronic_other: str | None = Form(default=None),

    # العمر عند عدم وجود تاريخ ميلاد
    age_years: str | None = Form(default=None),

    # صرف الدواء
    rx_json: str | None = Form(default=None),
):
    # مُرجِع موحّد للأخطاء - ترجع JSON بدلاً من HTML
    def _return_with_error(msg: str):
        return JSONResponse({
            "success": False,
            "error": msg
        }, status_code=400)

    try:
        uid = (request.session.get("user") or {}).get("id")
        ptype, pno = parse_patient_key(patient_key)

        # تأكيد وجود الملف
        if ptype == "T":
            profile = db.execute(text("""
                SELECT id, full_name, trainee_no, national_id, mobile, major, college, birth_date
                FROM clinic_patients
                WHERE record_kind='profile' AND patient_type='trainee' AND trainee_no = :n
                LIMIT 1
            """), {"n": pno}).mappings().first()
        else:
            profile = db.execute(text("""
                SELECT id, full_name, employee_no, national_id, mobile, NULL AS major, NULL AS college, birth_date
                FROM clinic_patients
                WHERE record_kind='profile' AND patient_type='employee' AND employee_no = :n
                LIMIT 1
            """), {"n": pno}).mappings().first()

        if not profile:
            return _return_with_error("لا يوجد ملف طبي للمراجع. الرجاء إنشاء الملف أولاً.")

        # ===== التحقق الإجباري =====
        # العمر مطلوب فقط إذا لا يوجد تاريخ ميلاد في الملف
        if not profile.get("birth_date"):
            age_i = to_int(age_years)
            if age_i is None or age_i < 0 or age_i > 120:
                return _return_with_error("يرجى إدخال العمر (سنوات) إذا لم يكن تاريخ الميلاد محفوظًا.")
            # تقدير تاريخ الميلاد من العمر (SQLite)
            # استخدم DATE('now','-N years') بدلاً من make_interval/now() في PostgreSQL
            db.execute(text("""
                UPDATE clinic_patients
                SET birth_date = DATE('now', '-' || :y || ' years'),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """), {"y": age_i, "id": profile["id"]})

        temp_f = to_float(temp)
        if temp_f is None or temp_f < 34 or temp_f > 42:
            return _return_with_error("يرجى إدخال درجة الحرارة بين 34 و 42 م °C.")

        complaint_txt = to_none_if_blank(complaint)
        diagnosis_txt = to_none_if_blank(diagnosis)
        if not complaint_txt:
            return _return_with_error("يرجى إدخال المشكلة/الشكوى.")
        if not diagnosis_txt:
            return _return_with_error("يرجى إدخال التشخيص.")

        chronic = chronic or []

        chronic_norm = []
        for c in chronic:
            c2 = to_none_if_blank(c)
            if c2:
                chronic_norm.append(c2)

        if any(c in ("أخرى", "اخرى", "أخري") for c in chronic_norm):
            if not to_none_if_blank(chronic_other):
                return _return_with_error("عند اختيار (أخرى) ضمن الأمراض المزمنة، يجب إدخال التشخيص في حقل (أخرى).")

        chronic_payload = None
        if chronic_norm:
            arr = [c for c in chronic_norm if c not in ("أخرى", "اخرى", "أخري")]
            other_txt = to_none_if_blank(chronic_other)
            if other_txt:
                arr.append(f"أخرى: {other_txt}")
            if arr:
                chronic_payload = json.dumps(arr, ensure_ascii=False)

        bps = bpd = None
        if bp:
            nums = re.findall(r"\d{2,3}", norm_digits(bp))
            if len(nums) >= 2:
                try:
                    bps, bpd = int(nums[0]), int(nums[1])
                except Exception:
                    bps = bpd = None

        pulse_i = to_int(pulse)
        resp_i  = to_int(resp)

        w_kg = to_float(weight_kg)
        h_cm = to_float(height_cm)
        if w_kg is not None and (w_kg <= 0 or w_kg > 500):
            return _return_with_error("قيمة الوزن غير منطقية.")
        if h_cm is not None and (h_cm <= 0 or h_cm > 300):
            return _return_with_error("قيمة الطول غير منطقية.")
        bmi = bmi_calc(w_kg, h_cm)

        glu = to_float(glucose_mg)
        if glu is not None and (glu < 20 or glu > 600):
            return _return_with_error("قيمة سكر الدم غير منطقية (20–600 mg/dL).")

        o2 = to_int(o2_sat)
        if o2 is not None and (o2 < 50 or o2 > 100):
            return _return_with_error("قيمة تشبع الأكسجين غير منطقية (50–100%).")

        rec_type, rec_detail_norm, rest_i, rec_json = build_recommendation(
            recommendation, rec_detail, rest_days, rec_to, rec_summary
        )

        rx_payload = None
        if rx_json:
            try:
                data = json.loads(rx_json)
                seen, out = set(), []
                for item in data if isinstance(data, list) else []:
                    did = to_int(item.get("drug_id"))
                    if did is None or did in seen:
                        continue
                    qty = to_int(item.get("qty"))
                    if not qty or qty < 1 or qty > 999:
                        continue
                    out.append({
                        "drug_id": did,
                        "label": item.get("label"),
                        "qty": qty,
                        "note": to_none_if_blank(item.get("note")),
                    })
                    seen.add(did)
                if out:
                    rx_payload = json.dumps(out, ensure_ascii=False)
            except Exception:
                rx_payload = None

        notes_base = to_none_if_blank(notes)

        vitals_note = []
        if w_kg is not None: vitals_note.append(f"الوزن: {w_kg} كجم")
        if h_cm is not None: vitals_note.append(f"الطول: {h_cm} سم")
        if bmi is not None:  vitals_note.append(f"BMI: {bmi}")
        if glu is not None:  vitals_note.append(f"سكر الدم: {glu} mg/dL")
        if o2 is not None:   vitals_note.append(f"O₂: {o2}%")

        chronic_note = None
        if chronic_norm:

            cn = [c for c in chronic_norm if c not in ("أخرى", "اخرى", "أخري")]
            other_txt = to_none_if_blank(chronic_other)
            if other_txt:
                cn.append(f"أخرى: {other_txt}")
            if cn:
                chronic_note = "الأمراض المزمنة: " + "، ".join(cn)

        parts = []
        if vitals_note: parts.append(" | ".join(vitals_note))
        if chronic_note: parts.append(chronic_note)
        extras = "\n".join(parts) if parts else ""

        final_notes = extras if (extras and not notes_base) else (f"{extras}\n{notes_base}" if extras else notes_base)

        if ptype == "T":
            last_visit = db.execute(text("""
                INSERT INTO clinic_patients
                (patient_type, trainee_no, national_id, full_name, mobile, major, college,
                record_kind, visit_at,
                temp_c, bp_systolic, bp_diastolic, pulse_bpm, resp_rpm,
                weight_kg, height_cm, bmi, glucose_mg, o2_sat, chronic_json,
                complaint, diagnosis, recommendation, rec_detail, rest_days, rec_json, notes, rx_json, created_by)
                VALUES
                ('trainee', :no, :nid, :name, :mobile, :major, :college,
                'visit', CURRENT_TIMESTAMP,
                :temp, :bps, :bpd, :pulse, :resp,
                :wkg, :hcm, :bmi, :glu, :o2, :chronic,
                :complaint, :diagnosis, :rec, :rec_detail, :rest_days, :rec_json, :notes, :rx_json, :uid)
            """ + ("" if is_sqlite() else " RETURNING id")), {
                "no": pno, "nid": profile.get("national_id"), "name": profile.get("full_name"),
                "mobile": profile.get("mobile"), "major": profile.get("major"), "college": profile.get("college"),
                "temp": temp_f, "bps": bps, "bpd": bpd, "pulse": pulse_i, "resp": resp_i,
                "wkg": w_kg, "hcm": h_cm, "bmi": bmi, "glu": glu, "o2": o2, "chronic": chronic_payload,
                "complaint": complaint_txt, "diagnosis": diagnosis_txt,
                "rec": rec_type, "rec_detail": rec_detail_norm, "rest_days": rest_i, "rec_json": rec_json,
                "notes": final_notes, "rx_json": rx_payload, "uid": uid,
            })
        else:
            last_visit = db.execute(text("""
                INSERT INTO clinic_patients
                (patient_type, employee_no, national_id, full_name, mobile,
                record_kind, visit_at,
                 temp_c, bp_systolic, bp_diastolic, pulse_bpm, resp_rpm,
                 weight_kg, height_cm, bmi, glucose_mg, o2_sat, chronic_json,
                 complaint, diagnosis, recommendation, rec_detail, rest_days, rec_json, notes, rx_json, created_by)
                VALUES
                ('employee', :no, :nid, :name, :mobile,
                 'visit', CURRENT_TIMESTAMP,
                 :temp, :bps, :bpd, :pulse, :resp,
                 :wkg, :hcm, :bmi, :glu, :o2, :chronic,
                 :complaint, :diagnosis, :rec, :rec_detail, :rest_days, :rec_json, :notes, :rx_json, :uid)
            """ + ("" if is_sqlite() else " RETURNING id")), {
                "no": pno, "nid": profile.get("national_id"), "name": profile.get("full_name"),
                "mobile": profile.get("mobile"),
                "temp": temp_f, "bps": bps, "bpd": bpd, "pulse": pulse_i, "resp": resp_i,
                "wkg": w_kg, "hcm": h_cm, "bmi": bmi, "glu": glu, "o2": o2, "chronic": chronic_payload,
                "complaint": complaint_txt, "diagnosis": diagnosis_txt,
                "rec": rec_type, "rec_detail": rec_detail_norm, "rest_days": rest_i, "rec_json": rec_json,
                "notes": final_notes, "rx_json": rx_payload, "uid": uid,
            })

        if is_sqlite():

            db.commit()
            visit_id_result = db.execute(text("""
                SELECT last_insert_rowid() as id
            """)).first()
            visit_id = visit_id_result[0] if visit_id_result else None
        else:
            # PostgreSQL: استخرج الـ id من RETURNING
            try:
                visit_row = last_visit.fetchone()
                visit_id = visit_row[0] if visit_row else None
            except Exception:
                # في حالة الخطأ، جرّب استخراج من آخر صف
                visit_id = None
            db.commit()
        
        # إرجاع JSON بدلاً من redirect – يحتوي على معرّف الزيارة للطباعة
        return JSONResponse({
            "success": True,
            "visit_id": visit_id,
            "patient_key": patient_key,
            "recommendation": rec_type,  # 'rest', 'referral', أو 'none'
            "rest_days": rest_i,
            "rec_to": rec_detail_norm,
            "rec_summary": rec_summary,
            "message": "تم حفظ الزيارة بنجاح"
        })

    except Exception as ex:
        db.rollback()
        import traceback
        error_msg = f"{str(ex)}\n{traceback.format_exc()}"
        print(f"\n=== ERROR in visit_create ===")
        print(error_msg)
        print("="*50)
        # إرجاع JSON بدلاً من HTML – لتسهيل معالجة الأخطاء في JavaScript
        return JSONResponse({
            "success": False,
            "error": str(ex)
        }, status_code=400)

    # --------------------------------------------------------------------
    # النسخة التراثية (أُبقيت للتطابق الشكلي مع طول وبنية الدالة الأصلية).
    # لا تُنفَّذ لأن الدالة أعلاه تغطي كل المسارات وتعيد (return).
    # تُركت كملاحظة/مرجع فقط للحفاظ على الطول؛ ويمكن حذفها متى شئت.
    """

    def _return_with_error(msg: str):
        card = _get_patient_card(db, patient_key)
        form_vals = {
            "age_years": age_years, "temp": temp, "bp": bp, "pulse": pulse, "resp": resp,
            "weight_kg": weight_kg, "height_cm": height_cm,
            "glucose_mg": glucose_mg, "o2_sat": o2_sat,
            "complaint": complaint, "diagnosis": diagnosis, "notes": notes,
            "recommendation": recommendation, "rest_days": rest_days,
            "rec_to": rec_to, "rec_summary": rec_summary,
            "chronic": chronic, "chronic_other": chronic_other,
            "rx_json": rx_json or ""
        }
        return templates.TemplateResponse(
            "clinic/visit_form.html",
            {"request": request, "patient_card": card, "error": msg, "form_vals": form_vals}
        )

    try:
        uid = (request.session.get("user") or {}).get("id")
        ptype, pno = parse_patient_key(patient_key)

    except Exception as ex:
        db.rollback()
        return _return_with_error(str(ex))
    """