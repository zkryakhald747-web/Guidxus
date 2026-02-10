from fastapi import APIRouter, Request, Depends, Query, HTTPException, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import text

from ..database import get_db
from ..deps_auth import require_doc
from ..models import FirstAidBox

router = APIRouter(prefix="/inventory", tags=["Inventory"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", include_in_schema=False)
def inv_index(request: Request, user=Depends(require_doc)):
    return templates.TemplateResponse("inventory/index.html", {"request": request})

@router.get("/stock-levels")
def stock_levels(request: Request, user=Depends(require_doc), db: Session = Depends(get_db)):
    return templates.TemplateResponse("inventory/stock_levels.html", {"request": request})

@router.get("/alerts")
def alerts_page(request: Request, user=Depends(require_doc), db: Session = Depends(get_db)):
    """صفحة عرض تنبيهات الأدوية قريبة الانتهاء"""
    from datetime import datetime, timedelta
    
    # الحصول على الأدوية قريبة الانتهاء أو المنتهية الصلاحية
    today = datetime.now().date()
    soon = today + timedelta(days=30)  # تنبيه للأدوية التي تنتهي خلال 30 يوم
    
    expiring_drugs = db.execute(text('''
        SELECT DISTINCT
            d.id,
            d.trade_name,
            d.generic_name,
            d.strength,
            d.form,
            dt.expiry_date,
            dt.created_at,
            CASE WHEN dt.expiry_date < DATE('now') THEN 1 ELSE 0 END as is_expired
        FROM drugs d
        LEFT JOIN drug_transactions dt ON d.id = dt.drug_id
        WHERE dt.expiry_date IS NOT NULL
        AND (dt.expiry_date < DATE('now') OR dt.expiry_date <= DATE(:soon))
        ORDER BY dt.expiry_date ASC
    '''), {'soon': soon}).fetchall()
    
    expiring_list = [
        {
            'id': row[0],
            'trade_name': row[1],
            'generic_name': row[2],
            'strength': row[3],
            'form': row[4],
            'expiry_date': row[5],
            'added_date': row[6],
            'is_expired': bool(row[7])
        }
        for row in expiring_drugs
    ]
    
    return templates.TemplateResponse("inventory/alerts.html", {
        "request": request,
        "expiring_drugs": expiring_list
    })

@router.get("/dispense-drugs")
def dispense_drugs_page(
    request: Request,
    user=Depends(require_doc),
    db: Session = Depends(get_db)
):
    """صفحة صرف الأدوية من المستودع لصناديق الإسعافات"""
    # جلب جميع الأدوية مع أرصدتها
    drugs_data = db.execute(text('''
        SELECT 
            d.id,
            d.drug_code,
            d.trade_name,
            d.generic_name,
            d.strength,
            d.form,
            d.unit,
            ws.balance_qty as warehouse_qty,
            ps.balance_qty as pharmacy_qty
        FROM drugs d
        LEFT JOIN warehouse_stock ws ON d.id = ws.drug_id
        LEFT JOIN pharmacy_stock ps ON d.id = ps.drug_id
        ORDER BY d.trade_name
    ''')).fetchall()
    

    drugs = [
        {
            'id': row[0],
            'drug_code': row[1],
            'trade_name': row[2],
            'generic_name': row[3],
            'strength': row[4],
            'form': row[5],
            'unit': row[6],
            'warehouse_qty': row[7] or 0,
            'pharmacy_qty': row[8] or 0,
        }
        for row in drugs_data
    ]
    

    boxes = db.query(FirstAidBox).all()
    
    return templates.TemplateResponse("inventory/stock_moves.html", {
        "request": request,
        "drugs": drugs,
        "boxes": boxes
    })

@router.post("/dispense-drugs/process")
def process_drug_dispense(
    request: Request,
    drug_id: int = Query(...),
    box_id: int = Query(...),
    quantity: int = Query(...),
    user=Depends(require_doc),
    db: Session = Depends(get_db)
):
    """معالجة صرف الدواء إلى صندوق"""
    
    # التحقق من وجود الدواء
    drug = db.execute(text('''
        SELECT id, drug_code, trade_name, unit FROM drugs WHERE id = :did
    '''), {'did': drug_id}).fetchone()
    
    if not drug:
        raise HTTPException(status_code=404, detail="الدواء غير موجود")
    

    box = db.query(FirstAidBox).filter(FirstAidBox.id == box_id).first()
    if not box:
        raise HTTPException(status_code=404, detail="الصندوق غير موجود")
    

    warehouse_stock = db.execute(text('''
        SELECT balance_qty FROM warehouse_stock WHERE drug_id = :did
    '''), {'did': drug_id}).fetchone()
    
    available_qty = warehouse_stock[0] if warehouse_stock else 0
    if available_qty < quantity:
        raise HTTPException(
            status_code=400, 
            detail=f"الكمية المتاحة في المستودع: {available_qty} فقط"
        )
    
    # خصم من المستودع
    db.execute(text('''
        UPDATE warehouse_stock
        SET balance_qty = balance_qty - :qty
        WHERE drug_id = :did
    '''), {'qty': quantity, 'did': drug_id})
    

    db.execute(text('''
        UPDATE pharmacy_stock
        SET balance_qty = balance_qty - :qty
        WHERE drug_id = :did
    '''), {'qty': quantity, 'did': drug_id})
    
    # إضافة الدواء إلى الصندوق
    db.execute(text('''
        INSERT INTO first_aid_box_items (box_id, drug_code, drug_name, quantity, unit)
        VALUES (:bid, :code, :name, :qty, :unit)
    '''), {
        'bid': box_id,
        'code': drug[1],
        'name': drug[2],
        'qty': quantity,
        'unit': drug[3]
    })
    

    db.execute(text('''
        INSERT INTO drug_transactions 
        (drug_id, transaction_type, quantity_change, source, destination, notes, created_at)
        VALUES (:did, :type, :qty, :src, :dst, :notes, datetime('now'))
    '''), {
        'did': drug_id,
        'type': 'warehouse_to_box',
        'qty': -quantity,
        'src': 'warehouse_pharmacy',
        'dst': f'box_{box_id}',
        'notes': f'صرف إلى صندوق: {box.box_name}'
    })
    
    db.commit()
    
    return RedirectResponse(
        url=f"/inventory/stock-moves?msg=drug_dispensed_successfully&box_id={box_id}",
        status_code=303
    )

# ===================== توريد الأدوية إلى المستودع =====================
@router.get("/stock-moves")
def stock_moves_page(
    request: Request,
    msg: str = Query(default=None),
    user=Depends(require_doc),
    db: Session = Depends(get_db)
):
    """صفحة موحدة لصرف وتوريد الأدوية"""

    drugs_data = db.execute(text('''
        SELECT 
            d.id,
            d.drug_code,
            d.trade_name,
            d.generic_name,
            d.strength,
            d.form,
            d.unit,
            ws.balance_qty as warehouse_qty,
            ps.balance_qty as pharmacy_qty
        FROM drugs d
        LEFT JOIN warehouse_stock ws ON d.id = ws.drug_id
        LEFT JOIN pharmacy_stock ps ON d.id = ps.drug_id
        ORDER BY d.trade_name
    ''')).fetchall()
    
    # تحويل النتائج إلى قائمة من القواميس
    drugs = [
        {
            'id': row[0],
            'drug_code': row[1],
            'trade_name': row[2],
            'generic_name': row[3],
            'strength': row[4],
            'form': row[5],
            'unit': row[6],
            'warehouse_qty': row[7] or 0,
            'pharmacy_qty': row[8] or 0,
        }
        for row in drugs_data
    ]
    
    # جلب جميع صناديق الإسعافات
    boxes = db.query(FirstAidBox).all()
    
    return templates.TemplateResponse("inventory/stock_moves.html", {
        "request": request,
        "drugs": drugs,
        "boxes": boxes,
        "msg": msg
    })

@router.post("/stock-moves", dependencies=[Depends(require_doc)])
def stock_moves_process(
    request: Request,
    user=Depends(require_doc),
    db: Session = Depends(get_db)
):
    """معالجة طلب التوريد"""

    return RedirectResponse(url="/inventory/stock-moves?msg=supply_ok", status_code=303)

@router.get("/supply-drugs/process")
@router.post("/supply-drugs/process")
def process_drug_supply(
    request: Request,
    drug_id: int = Query(...),
    quantity: int = Query(...),
    notes: str = Query(default=""),
    expiry_date: str = Query(default=""),
    user=Depends(require_doc),
    db: Session = Depends(get_db)
):
    """معالجة توريد الدواء إلى المستودع والصيدلية"""
    
    # التحقق من وجود الدواء
    drug = db.execute(text('''
        SELECT id, drug_code, trade_name FROM drugs WHERE id = :did
    '''), {'did': drug_id}).fetchone()
    
    if not drug:
        raise HTTPException(status_code=404, detail="الدواء غير موجود")
    

    expiry_date_obj = None
    if expiry_date:
        try:
            from datetime import datetime
            expiry_date_obj = datetime.strptime(expiry_date, "%Y-%m-%d").date()
        except Exception:
            pass
    

    warehouse_exists = db.execute(text('''
        SELECT id FROM warehouse_stock WHERE drug_id = :did
    '''), {'did': drug_id}).fetchone()
    
    if warehouse_exists:
        db.execute(text('''
            UPDATE warehouse_stock
            SET balance_qty = balance_qty + :qty
            WHERE drug_id = :did
        '''), {'qty': quantity, 'did': drug_id})
    else:
        db.execute(text('''
            INSERT INTO warehouse_stock (drug_id, balance_qty)
            VALUES (:did, :qty)
        '''), {'did': drug_id, 'qty': quantity})
    
    # إضافة أو تحديث في الصيدلية - التحقق أولاً
    pharmacy_exists = db.execute(text('''
        SELECT id FROM pharmacy_stock WHERE drug_id = :did
    '''), {'did': drug_id}).fetchone()
    
    if pharmacy_exists:
        db.execute(text('''
            UPDATE pharmacy_stock
            SET balance_qty = balance_qty + :qty
            WHERE drug_id = :did
        '''), {'qty': quantity, 'did': drug_id})
    else:
        db.execute(text('''
            INSERT INTO pharmacy_stock (drug_id, balance_qty)
            VALUES (:did, :qty)
        '''), {'did': drug_id, 'qty': quantity})
    

    supply_notes = f"توريد: {notes}" if notes else "توريد إلى المستودع"
    db.execute(text('''
        INSERT INTO drug_transactions 
        (drug_id, transaction_type, quantity_change, source, destination, notes, expiry_date, created_at)
        VALUES (:did, :type, :qty, :src, :dst, :notes, :exp, datetime('now'))
    '''), {
        'did': drug_id,
        'type': 'supply_received',
        'qty': quantity,
        'src': 'external_supplier',
        'dst': 'warehouse_pharmacy',
        'notes': supply_notes,
        'exp': expiry_date_obj
    })
    
    db.commit()
    
    return RedirectResponse(
        url=f"/inventory/stock-moves?msg=drug_supplied_successfully",
        status_code=303
    )

# ===================== إضافة أدوية لصناديق الإسعافات =====================
@router.get("/supply-to-boxes")
def supply_to_boxes_page(
    request: Request,
    msg: str = Query(default=None),
    drug_id: int = Query(default=None),
    drug_name: str = Query(default=None),
    user=Depends(require_doc),
    db: Session = Depends(get_db)
):
    """صفحة إضافة أدوية لصناديق الإسعافات مباشرة من المستودع"""

    drugs_data = db.execute(text('''
        SELECT 
            d.id,
            d.drug_code,
            d.trade_name,
            d.generic_name,
            d.strength,
            d.form,
            d.unit,
            ws.balance_qty as warehouse_qty,
            ps.balance_qty as pharmacy_qty,
            MAX(fi.expiry_date) as expiry_date
        FROM drugs d
        LEFT JOIN warehouse_stock ws ON d.id = ws.drug_id
        LEFT JOIN pharmacy_stock ps ON d.id = ps.drug_id
        LEFT JOIN first_aid_box_items fi ON d.id = CAST(fi.drug_code AS INTEGER)
        GROUP BY d.id, d.drug_code, d.trade_name, d.generic_name, d.strength, d.form, d.unit
        ORDER BY d.trade_name
    ''')).fetchall()
    
    # تحويل النتائج إلى قائمة من القواميس
    drugs = [
        {
            'id': row[0],
            'drug_code': row[1],
            'trade_name': row[2],
            'generic_name': row[3],
            'strength': row[4],
            'form': row[5],
            'unit': row[6],
            'warehouse_qty': row[7] or 0,
            'pharmacy_qty': row[8] or 0,
            'expiry_date': str(row[9]) if row[9] else None,
        }
        for row in drugs_data
    ]
    
    # جلب جميع صناديق الإسعافات
    boxes = db.query(FirstAidBox).all()
    
    # تاريخ اليوم لمقارنة الصلاحية
    from datetime import date
    today = str(date.today())
    
    return templates.TemplateResponse("inventory/supply_to_boxes.html", {
        "request": request,
        "drugs": drugs,
        "boxes": boxes,
        "msg": msg,
        "preselected_drug_id": drug_id,
        "preselected_drug_name": drug_name,
        "today": today
    })

@router.post("/supply-to-boxes/process")
def process_supply_to_boxes(
    drug_id: int = Form(...),
    box_id: int = Form(...),
    quantity: int = Form(...),
    expiry_date: str = Form(default=None),
    user=Depends(require_doc),
    db: Session = Depends(get_db)
):
    """معالجة إضافة دواء مباشرة للصندوق من المستودع"""
    

    drug = db.execute(text('''
        SELECT id, drug_code, trade_name, unit FROM drugs WHERE id = :did
    '''), {'did': drug_id}).fetchone()
    
    if not drug:
        raise HTTPException(status_code=404, detail="الدواء غير موجود")
    
    # التحقق من وجود الصندوق
    box = db.query(FirstAidBox).filter(FirstAidBox.id == box_id).first()
    if not box:
        raise HTTPException(status_code=404, detail="الصندوق غير موجود")
    
    # التحقق من الكمية المتاحة في المستودع
    warehouse_stock = db.execute(text('''
        SELECT balance_qty FROM warehouse_stock WHERE drug_id = :did
    '''), {'did': drug_id}).fetchone()
    
    available_qty = warehouse_stock[0] if warehouse_stock else 0
    if available_qty < quantity:
        raise HTTPException(
            status_code=400, 
            detail=f"الكمية المتاحة في المستودع: {available_qty} فقط"
        )
    

    db.execute(text('''
        UPDATE warehouse_stock
        SET balance_qty = balance_qty - :qty
        WHERE drug_id = :did
    '''), {'qty': quantity, 'did': drug_id})
    
    # خصم من الصيدلية
    db.execute(text('''
        UPDATE pharmacy_stock
        SET balance_qty = balance_qty - :qty
        WHERE drug_id = :did
    '''), {'qty': quantity, 'did': drug_id})
    

    if expiry_date:
        db.execute(text('''
            INSERT INTO first_aid_box_items (box_id, drug_code, drug_name, quantity, unit, expiry_date)
            VALUES (:bid, :code, :name, :qty, :unit, :expiry)
        '''), {
            'bid': box_id,
            'code': drug[1],
            'name': drug[2],
            'qty': quantity,
            'unit': drug[3],
            'expiry': expiry_date
        })
    else:
        db.execute(text('''
            INSERT INTO first_aid_box_items (box_id, drug_code, drug_name, quantity, unit)
            VALUES (:bid, :code, :name, :qty, :unit)
        '''), {
            'bid': box_id,
            'code': drug[1],
            'name': drug[2],
            'qty': quantity,
            'unit': drug[3]
        })
    

    db.execute(text('''
        INSERT INTO drug_transactions 
        (drug_id, transaction_type, quantity_change, source, destination, notes, created_at)
        VALUES (:did, :type, :qty, :src, :dst, :notes, datetime('now'))
    '''), {
        'did': drug_id,
        'type': 'warehouse_to_box',
        'qty': -quantity,
        'src': 'warehouse_pharmacy',
        'dst': f'box_{box_id}',
        'notes': f'إضافة مباشرة للصندوق: {box.box_name}'
    })
    
    db.commit()
    
    return {
        "success": True,
        "message": "تم إضافة الدواء للصندوق بنجاح",
        "drug_name": drug[2],
        "box_name": box.box_name,
        "quantity": quantity
    }