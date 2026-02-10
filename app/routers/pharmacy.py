
from __future__ import annotations

from fastapi import APIRouter, Request, Depends, Query, Form
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, Any, Dict, List
from ..database import get_db, is_sqlite
from ..deps_auth import require_doc
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/clinic/pharmacy", tags=["Clinic-Pharmacy"])
templates = Jinja2Templates(directory="app/templates")

def _clean(s: Optional[str]) -> Optional[str]:
    if s is None: return None
    t = str(s).strip()
    return t if t else None

def _uid(request: Request) -> Optional[int]:
    try:
        return (request.session.get("user") or {}).get("id")
    except Exception:
        return None

def _fail(msg: str, code: int = 400):
    return JSONResponse({"error": msg}, status_code=code)

def _find_drug_by_query(db: Session, q: str) -> Dict[str, Any]:
    """
    بحث ذكي بالاسم التجاري/العلمي/الشركة/الجرعة/الشكل.
    - يقسم النص إلى رموز (مسافات / سلاش / فاصلة / شرطة)
    - إن وُجدت نتيجة واحدة يرجعها، وإلا يرفع خطأ مع اقتراحات.
    """
    import re

    s = _clean(q)
    if not s:
        raise ValueError("الرجاء إدخال اسم الدواء.")

    if s.isdigit():
        table_name = "public.drugs" if not is_sqlite() else "drugs"
        row = db.execute(text(f"""
            SELECT id, trade_name, generic_name, strength, form
            FROM {table_name}
            WHERE is_active=TRUE AND id=:id
            LIMIT 1
        """), {"id": int(s)}).mappings().first()
        if row:
            return row

    # تفكيك النص لرموز قصيرة >= 2
    tokens = [t for t in re.split(r"[\s/,\-]+", s.strip()) if len(t) >= 2]
    params = {}
    conds = []
    for i, t in enumerate(tokens):
        k = f"t{i}"
        params[k] = f"%{t}%"
        # استخدام LIKE مع UPPER في SQLite، أو ILIKE في PostgreSQL
        if is_sqlite():
            conds.append(
                f"(UPPER(COALESCE(trade_name,'')) LIKE UPPER(:{k}) "
                f"OR UPPER(COALESCE(generic_name,'')) LIKE UPPER(:{k}) "
                f"OR UPPER(COALESCE(manufacturer,'')) LIKE UPPER(:{k}) "
                f"OR UPPER(COALESCE(strength,'')) LIKE UPPER(:{k}) "
                f"OR UPPER(COALESCE(form,'')) LIKE UPPER(:{k}))"
            )
        else:
            conds.append(
                f"(COALESCE(trade_name,'') ILIKE :{k} "
                f"OR COALESCE(generic_name,'') ILIKE :{k} "
                f"OR COALESCE(manufacturer,'') ILIKE :{k} "
                f"OR COALESCE(strength,'') ILIKE :{k} "
                f"OR COALESCE(form,'') ILIKE :{k})"
            )

    where_extra = (" AND " + " AND ".join(conds)) if conds else ""

    table_name = "public.drugs" if not is_sqlite() else "drugs"
    rows = db.execute(text(f"""
        SELECT id, trade_name, generic_name, strength, form, COALESCE(manufacturer,'') AS manufacturer
        FROM {table_name}
        WHERE is_active=TRUE {where_extra}
        ORDER BY id
        LIMIT 20
    """), params).mappings().all()

    if not rows:
        raise ValueError("لم يتم العثور على دواء مطابق.")
    if len(rows) == 1:
        return rows[0]

    opts = " | ".join(" / ".join(filter(None, [
        r["trade_name"], r.get("generic_name"), r.get("strength"), r.get("form")
    ])) for r in rows)
    raise ValueError(f"الرجاء تحديد بدقة أكثر. اقتراحات: {opts}")

def _main_pharma_id(db: Session) -> int:
    row = db.execute(text("SELECT id FROM public.locations WHERE code='MAIN-PHARMA' LIMIT 1")).mappings().first()
    if not row:
        raise RuntimeError("الموقع MAIN-PHARMA غير موجود. شغّل سكربت التهيئة.")
    return int(row["id"])

@router.get("/",
            dependencies=[Depends(require_doc)])
def pharmacy_home(request: Request, db: Session = Depends(get_db)):
    try:

        drug_table = "public.drugs" if not is_sqlite() else "drugs"
        stock_table = "public.v_drug_stock" if not is_sqlite() else "v_drug_stock"
        loc_table = "public.locations" if not is_sqlite() else "locations"
        totals = db.execute(text(f"""
            SELECT
              (SELECT COUNT(*) FROM {drug_table} WHERE is_active) AS active_drugs,
              COALESCE((
                SELECT SUM(stock_qty)
                FROM {stock_table}
                WHERE location_id=(
                  SELECT id FROM {loc_table} WHERE code='MAIN-PHARMA' LIMIT 1
                )
              ),0) AS total_stock
        """)).mappings().first()
    except Exception:
        # إذا فشل الاستعلام، جرّب من الإكسيل
        try:
            import sys
            import os
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            from excel_data_reference import get_all_drugs, get_statistics
            
            all_drugs = get_all_drugs()
            stats = get_statistics()
            
            totals = {
                "active_drugs": len([d for d in all_drugs if d.get('is_active', True)]),
                "total_stock": sum(d.get('stock_qty', 0) for d in all_drugs),
                "excel_source": True
            }
        except Exception:
            # قيم افتراضية
            totals = {"active_drugs": 0, "total_stock": 0}
    
    return templates.TemplateResponse("clinic/pharmacy_index.html",
                                      {"request": request, "totals": totals})

# ================== الأصناف ==================
@router.get("/drugs",
            dependencies=[Depends(require_doc)])
def drugs_list(request: Request,
               q: Optional[str] = Query(default=None),
               db: Session = Depends(get_db)):
    rows = []
    
    try:
        # محاولة من قاعدة البيانات أولاً
        where = "WHERE d.is_active=TRUE"
        params = {}
        if q:
            if is_sqlite():
                where += " AND (UPPER(d.trade_name) LIKE UPPER(:q) OR UPPER(d.generic_name) LIKE UPPER(:q) OR UPPER(COALESCE(d.manufacturer,'')) LIKE UPPER(:q))"
            else:
                where += " AND (d.trade_name ILIKE :q OR d.generic_name ILIKE :q OR COALESCE(d.manufacturer,'') ILIKE :q)"
            params["q"] = f"%{q.strip()}%"
        rows = db.execute(text(f"""
            SELECT d.id, d.trade_name, d.generic_name, d.strength, d.form, d.unit,
                   '' AS manufacturer,
                   COALESCE(ps.balance_qty,0) AS stock_main
            FROM drugs d
            LEFT JOIN pharmacy_stock ps
              ON ps.drug_id = d.id
            {where}
            ORDER BY d.id
            LIMIT 400
        """), params).mappings().all()
    except Exception:
        pass
    

    if not rows:
        try:
            import sys
            import os
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            from excel_data_reference import get_all_drugs
            
            all_drugs = get_all_drugs()
            rows = []
            
            for drug in all_drugs:
                if q and q.strip():
                    query_lower = q.lower()
                    if not (query_lower in str(drug.get('trade_name', '')).lower() or
                           query_lower in str(drug.get('generic_name', '')).lower() or
                           query_lower in str(drug.get('manufacturer', '')).lower()):
                        continue
                
                rows.append({
                    "id": drug.get('id', 0),
                    "trade_name": drug.get('trade_name', ''),
                    "generic_name": drug.get('generic_name', ''),
                    "strength": drug.get('strength', ''),
                    "form": drug.get('form', ''),
                    "manufacturer": drug.get('manufacturer', ''),
                    "stock_main": drug.get('stock_qty', 0),
                    "excel_source": True
                })
        except Exception:
            rows = []
    
    return templates.TemplateResponse("clinic/pharmacy_drugs.html",
                                      {"request": request, "rows": rows, "q": q or ""})

@router.post("/drugs/create",
             dependencies=[Depends(require_doc)])
def drugs_create(request: Request,
                 trade_name: str = Form(...),
                 generic_name: Optional[str] = Form(default=None),
                 strength: Optional[str] = Form(default=None),
                 form: Optional[str] = Form(default=None),
                 manufacturer: Optional[str] = Form(default=None),
                 unit: Optional[str] = Form(default=None),
                 db: Session = Depends(get_db)):
    try:
        table_name = "public.drugs" if not is_sqlite() else "drugs"

        import uuid
        drug_code = f"DRUG-{uuid.uuid4().hex[:8].upper()}"
        
        db.execute(text(f"""
            INSERT INTO {table_name} (drug_code, trade_name, generic_name, strength, form, manufacturer, unit, is_active, created_by)
            VALUES (:dc, :tn, :gn, :st, :fm, :m, :u, TRUE, :uid)
        """), {"dc": drug_code, "tn": trade_name.strip(), "gn": _clean(generic_name), "st": _clean(strength),
               "fm": _clean(form), "m": _clean(manufacturer), "u": _clean(unit), "uid": _uid(request)})
        db.commit()
        return RedirectResponse(url="/clinic/pharmacy/drugs?msg=added", status_code=303)
    except Exception as ex:
        db.rollback()
        return _fail(str(ex))

@router.post("/drugs/update",
             dependencies=[Depends(require_doc)])
def drugs_update(request: Request,
                 drug_id: int = Form(...),
                 trade_name: str = Form(...),
                 generic_name: Optional[str] = Form(default=None),
                 strength: Optional[str] = Form(default=None),
                 form: Optional[str] = Form(default=None),
                 manufacturer: Optional[str] = Form(default=None),
                 unit: Optional[str] = Form(default=None),
                 db: Session = Depends(get_db)):
    try:
        table_name = "public.drugs" if not is_sqlite() else "drugs"
        timestamp_col = "now()" if not is_sqlite() else "CURRENT_TIMESTAMP"
        db.execute(text(f"""
            UPDATE {table_name}
               SET trade_name=:tn,
                   generic_name=:gn,
                   strength=:st,
                   form=:fm,
                   manufacturer=:m,
                   unit=:u,
                   updated_at={timestamp_col},
                   updated_by=:uid
             WHERE id=:id AND is_active=TRUE
        """), {"id": drug_id, "tn": trade_name.strip(), "gn": _clean(generic_name),
               "st": _clean(strength), "fm": _clean(form), "m": _clean(manufacturer),
               "u": _clean(unit), "uid": _uid(request)})
        db.commit()
        return RedirectResponse(url="/clinic/pharmacy/drugs?msg=updated", status_code=303)
    except Exception as ex:
        db.rollback()
        return _fail(str(ex))

@router.get("/movements/log", dependencies=[Depends(require_doc)])
def movements_log(
    request: Request,
    drug_id: Optional[str] = Query(default=None),
    drug_q: Optional[str] = Query(default=None),
    move_type: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    export: Optional[str] = Query(default=None),
    db: Session = Depends(get_db)
):
    try:
        import re

        def _to_int(s: Optional[str]) -> Optional[int]:
            if s is None: return None
            s = s.strip()
            if not s: return None
            try: return int(s)
            except: return None

        d_id = _to_int(drug_id)

        df, dt = (date_from or None), (date_to or None)
        if df and dt and df > dt:
            df, dt = dt, df

        export_csv = (export or "").lower() == "csv"
        limit_sql = "" if export_csv else "LIMIT 500"

        def token_where(q: str, params: dict) -> str:
            if not q: return ""
            tokens = [t for t in re.split(r"[\s/,\-]+", q.strip()) if len(t) >= 2]
            if not tokens: return ""
            conds = []
            for i, t in enumerate(tokens):
                key = f"tok{i}"
                params[key] = f"%{t}%"
                if is_sqlite():
                    conds.append(
                        f"(UPPER(COALESCE(d.trade_name,'')) LIKE UPPER(:{key}) "
                        f"OR UPPER(COALESCE(d.generic_name,'')) LIKE UPPER(:{key}) "
                        f"OR UPPER(COALESCE(d.manufacturer,'')) LIKE UPPER(:{key}) "
                        f"OR UPPER(COALESCE(d.strength,'')) LIKE UPPER(:{key}) "
                        f"OR UPPER(COALESCE(d.form,'')) LIKE UPPER(:{key}))"
                    )
                else:
                    conds.append(
                        f"(COALESCE(d.trade_name,'') ILIKE :{key} "
                        f"OR COALESCE(d.generic_name,'') ILIKE :{key} "
                        f"OR COALESCE(d.manufacturer,'') ILIKE :{key} "
                        f"OR COALESCE(d.strength,'') ILIKE :{key} "
                        f"OR COALESCE(d.form,'') ILIKE :{key})"
                    )
            return " AND " + " AND ".join(conds)

        def build_base_where() -> tuple[str, dict]:
            where = "WHERE 1=1"
            params: dict = {}
            if move_type:
                where += " AND m.movement_type=:t"
                params["t"] = move_type
            if df:
                if is_sqlite():
                    where += " AND DATE(m.created_at) >= :df"
                else:
                    where += " AND m.created_at::date >= :df"
                params["df"] = df
            if dt:
                if is_sqlite():
                    where += " AND DATE(m.created_at) <= :dt"
                else:
                    where += " AND m.created_at::date <= :dt"
                params["dt"] = dt
            return where, params

        def run_query(where: str, params: dict):

            drugs_table = "drugs" if is_sqlite() else "public.drugs"
            movements_table = "drug_stock_movements" if is_sqlite() else "public.drug_stock_movements"
            transactions_table = "drug_transactions" if is_sqlite() else "public.drug_transactions"
            users_table = "users" if is_sqlite() else "public.users"
            
            sql = f"""
                SELECT * FROM (
                    SELECT
                      m.id, m.created_at, m.movement_type as move_type, m.quantity_change as qty, m.notes as ref_note,
                      d.id AS drug_id,
                      COALESCE(d.trade_name, '') AS trade_name,
                      COALESCE(d.generic_name, '') AS generic_name,
                      COALESCE(d.strength, '') AS strength,
                      COALESCE(d.form, '') AS form,
                      m.drug_name AS drug_name,
                      u.full_name AS user_name,
                      CASE
                        WHEN m.movement_type='out' THEN CASE WHEN m.quantity_change>0 THEN -m.quantity_change ELSE m.quantity_change END
                        WHEN m.movement_type='in'  THEN CASE WHEN m.quantity_change<0 THEN -m.quantity_change ELSE m.quantity_change END
                        ELSE m.quantity_change
                      END AS effective_qty
                    FROM {movements_table} m
                    LEFT JOIN {drugs_table} d ON (d.id = m.drug_code OR UPPER(d.drug_code) = UPPER(CAST(m.drug_code AS TEXT)))
                    LEFT JOIN {users_table} u ON u.id = m.created_by
                    
                    UNION ALL
                    
                    SELECT
                      t.id, t.created_at, t.transaction_type as move_type, t.quantity_change as qty, t.notes as ref_note,
                      d.id AS drug_id,
                      COALESCE(d.trade_name, '') AS trade_name,
                      COALESCE(d.generic_name, '') AS generic_name,
                      COALESCE(d.strength, '') AS strength,
                      COALESCE(d.form, '') AS form,
                      d.trade_name AS drug_name,
                      u.full_name AS user_name,
                      t.quantity_change AS effective_qty
                    FROM {transactions_table} t
                    LEFT JOIN {drugs_table} d ON d.id = t.drug_id
                    LEFT JOIN {users_table} u ON u.id = t.created_by
                ) AS combined
                {where}
                ORDER BY created_at DESC
                {limit_sql}
            """
            return db.execute(text(sql), params).mappings().all()

        # === الحالات ===
        base_where, base_params = build_base_where()

        # 0) بدون أي فلاتر -> رجّع السجل كامل (آخر 500)
        if d_id is None and not (drug_q and drug_q.strip()):
            rows = run_query(base_where, base_params)

        else:
            rows = []

            # 1) جرّب بالـID
            if d_id is not None:
                where_id  = base_where + " AND m.drug_id=:d"
            params_id = {**base_params, "d": d_id}
            rows = run_query(where_id, params_id)

        # 2) لو ما فيه نتيجة، جرّب بالنص (token search)
        if not rows and (drug_q or "").strip():
            where_txt, params_txt = build_base_where()
            where_txt += token_where(drug_q, params_txt)
            rows = run_query(where_txt, params_txt)

        # 3) لو ما فيه نتيجة ولسه فيه ID، ابنِ نص من بطاقة الدواء وبحث به
        if not rows and d_id is not None:
            try:
                table_name = "public.drugs" if not is_sqlite() else "drugs"
                name_row = db.execute(text(f"""
                    SELECT trade_name, generic_name, COALESCE(manufacturer,'') AS manufacturer,
                           COALESCE(strength,'') AS strength, COALESCE(form,'') AS form
                    FROM {table_name} WHERE id=:d
                """), {"d": d_id}).mappings().first()
                if name_row:
                    q2 = " ".join(x for x in [
                        name_row["trade_name"], name_row["generic_name"],
                        name_row["manufacturer"], name_row["strength"], name_row["form"]
                    ] if x)
                    where_txt2, params_txt2 = build_base_where()
                    where_txt2 += token_where(q2, params_txt2)
                    rows = run_query(where_txt2, params_txt2)
            except Exception:
                pass

        if export_csv:
            import io, csv, datetime
            from fastapi.responses import Response
            buf = io.StringIO(newline="")
            w = csv.writer(buf)
            w.writerow(["movement_id","date_time","drug_id","trade_name","generic_name",
                        "strength","form","move_type","qty","effective_qty","note","user"])
            for r in rows:
                w.writerow([
                    r["id"],
                    r["created_at"].strftime("%Y-%m-%d %H:%M:%S") if r["created_at"] else "",
                    r["drug_id"] if r["drug_id"] is not None else "",
                    r["trade_name"], r["generic_name"], r["strength"], r["form"],
                    r["move_type"], r["qty"], r["effective_qty"],
                    (r["ref_note"] or "").replace("\n"," ").strip(),
                    r["user_name"] or "",
                ])
            csv_text = "\ufeff" + buf.getvalue()
            fname = f"movements_{datetime.date.today():%Y%m%d}.csv"
            return Response(
                content=csv_text,
                media_type="text/csv; charset=utf-8",
                headers={"Content-Disposition": f'attachment; filename="{fname}"'}
            )

        return templates.TemplateResponse("clinic/pharmacy_movements.html", {
            "request": request,
            "rows": rows,
            "drug_id": d_id,
            "drug_q": drug_q or "",
            "move_type": move_type,
            "date_from": df or "",
            "date_to": dt or "",
        })
    
    except Exception:

        try:
            import sys
            import os
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            from excel_data_reference import get_all_drugs, get_drug_movements_for_drug
            
            all_drugs = get_all_drugs()
            all_movements = []
            

            if drug_id:
                try:
                    drug_id_int = int(drug_id)
                    movements = get_drug_movements_for_drug(drug_id_int)
                    all_movements = movements
                except:
                    pass
            else:

                for drug in all_drugs:
                    try:
                        movements = get_drug_movements_for_drug(drug.get('id', 0))
                        all_movements.extend(movements)
                    except:
                        pass
            

            rows = []
            for m in all_movements:
                row = {
                    "id": m.get('id', 0),
                    "drug_id": m.get('drug_id', 0),
                    "move_kind": m.get('move_kind', ''),
                    "move_type": m.get('move_type', ''),
                    "qty": m.get('qty', 0),
                    "created_at": m.get('created_at', ''),
                    "created_by": m.get('created_by', ''),
                    "excel_source": True
                }
                rows.append(row)
        except Exception:
            rows = []
        
        return templates.TemplateResponse("clinic/pharmacy_movements.html", {
            "request": request,
            "rows": rows,
            "drug_id": None,
            "drug_q": drug_q or "",
            "move_type": move_type,
            "date_from": date_from or "",
            "date_to": date_to or "",
        })

@router.post("/movements/in", dependencies=[Depends(require_doc)])
def movement_in(request: Request,
                drug_q: str = Form(...),
                qty: int = Form(..., ge=1),
                ref_note: Optional[str] = Form(default=None),
                db: Session = Depends(get_db)):
    try:
        drug = _find_drug_by_query(db, drug_q)
        loc_id = _main_pharma_id(db)
        db.execute(text("""
            INSERT INTO public.drug_movements
              (drug_id, location_id, move_kind, move_type, qty, ref_note, created_by)
            VALUES
              (:d, :l, 'in', 'in', :q, :n, :u)
        """), {"d": drug["id"], "l": loc_id, "q": qty, "n": _clean(ref_note), "u": _uid(request)})
        db.commit()
        return RedirectResponse(url="/clinic/pharmacy/drugs?msg=in_ok", status_code=303)
    except Exception as ex:
        db.rollback()
        return _fail(str(ex))

@router.post("/movements/out", dependencies=[Depends(require_doc)])
def movement_out(request: Request,
                 drug_q: str = Form(...),
                 qty: int = Form(..., ge=1),
                 ref_note: Optional[str] = Form(default=None),
                 db: Session = Depends(get_db)):
    try:
        drug = _find_drug_by_query(db, drug_q)
        loc_id = _main_pharma_id(db)

        # الرصيد الحالي
        cur = db.execute(text("""
            SELECT COALESCE(SUM(qty),0) AS stock_qty
            FROM public.drug_movements
            WHERE drug_id=:d AND location_id=:l
        """), {"d": drug["id"], "l": loc_id}).mappings().first()
        current_qty = int(cur["stock_qty"] or 0)

        if qty > current_qty:

            url = f"/clinic/pharmacy/drugs?msg=err_insufficient&need={qty}&have={current_qty}"
            return RedirectResponse(url=url, status_code=303)

        db.execute(text("""
            INSERT INTO public.drug_movements
              (drug_id, location_id, move_kind, move_type, qty, ref_note, created_by)
            VALUES
              (:d, :l, 'out', 'out', :qneg, :n, :u)
        """), {"d": drug["id"], "l": loc_id, "qneg": -abs(qty),
               "n": _clean(ref_note), "u": _uid(request)})
        db.commit()
        return RedirectResponse(url="/clinic/pharmacy/drugs?msg=out_ok", status_code=303)

    except Exception:
        db.rollback()
        # أي خطأ غير متوقع -> رسالة عامة بنفس مكان التنبيه
        return RedirectResponse(url="/clinic/pharmacy/drugs?msg=err_unknown", status_code=303)

@router.post("/movements/adjust", dependencies=[Depends(require_doc)])
def movement_adjust(request: Request,
                    drug_q: str = Form(...),
                    counted_qty: int = Form(..., ge=0),
                    ref_note: Optional[str] = Form(default=None),
                    db: Session = Depends(get_db)):
    try:
        drug = _find_drug_by_query(db, drug_q)
        loc_id = _main_pharma_id(db)

        cur = db.execute(text("""
            SELECT COALESCE(SUM(qty),0) AS cur_qty
            FROM public.drug_movements
            WHERE drug_id=:d AND location_id=:l
        """), {"d": drug["id"], "l": loc_id}).mappings().first()

        diff = counted_qty - (cur["cur_qty"] or 0)
        if diff == 0:
            return RedirectResponse(url="/clinic/pharmacy/drugs?msg=no_change", status_code=303)

        db.execute(text("""
            INSERT INTO public.drug_movements
              (drug_id, location_id, move_kind, move_type, qty, ref_note, created_by)
            VALUES
              (:d, :l, 'adjust', 'adjust', :q, :n, :u)
        """), {"d": drug["id"], "l": loc_id, "q": diff,
               "n": _clean(ref_note) or "جرد", "u": _uid(request)})
        db.commit()
        return RedirectResponse(url="/clinic/pharmacy/drugs?msg=adjust_ok", status_code=303)
    except Exception as ex:
        db.rollback()
        return _fail(str(ex))

# ================== Autocomplete / Dropdown ==================
@router.get("/drugs/search", dependencies=[Depends(require_doc)])
def drugs_search(q: str = "", db: Session = Depends(get_db)):
    s = (q or "").strip()
    
    # إذا كانت الـ query فارغة، أرجع كل الأدوية النشطة
    if not s:
        rows = db.execute(text(f"""
            SELECT id, trade_name, generic_name, strength, form,
                   COALESCE(manufacturer,'') AS manufacturer
            FROM {'public.drugs' if not is_sqlite() else 'drugs'}
            WHERE is_active=TRUE
            ORDER BY trade_name
            LIMIT 100
        """)).mappings().all()
    else:

        if is_sqlite():
            like_clause = """
                UPPER(trade_name) LIKE UPPER(:q) OR
                UPPER(generic_name) LIKE UPPER(:q) OR
                UPPER(COALESCE(manufacturer,'')) LIKE UPPER(:q)
            """
        else:
            like_clause = """
                trade_name ILIKE :q OR
                generic_name ILIKE :q OR
                COALESCE(manufacturer,'') ILIKE :q
            """
        rows = db.execute(text(f"""
            SELECT id, trade_name, generic_name, strength, form,
                   COALESCE(manufacturer,'') AS manufacturer
            FROM {'public.drugs' if not is_sqlite() else 'drugs'}
            WHERE is_active=TRUE
              AND ({like_clause})
            ORDER BY trade_name
            LIMIT 20
        """), {"q": f"%{s}%"}).mappings().all()
    
    items = []
    for r in rows:
        label = " / ".join(filter(None, [r["trade_name"], r["generic_name"], r["strength"], r["form"]]))
        items.append({
            "id": r["id"],
            "label": label,
            "manufacturer": r["manufacturer"]  # سطر ثانٍ اختياري للعرض
        })
    return JSONResponse({"items": items})