from fastapi import APIRouter, Request, Depends, Form, HTTPException, Query
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime
import base64
from io import BytesIO
import qrcode

from ..database import get_db
from ..deps_auth import require_doc
from ..models import FirstAidBox, FirstAidBoxItem

router = APIRouter(prefix="/first-aid", tags=["FirstAid"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/boxes/{box_id}/public", include_in_schema=False)
def box_public_detail(request: Request, box_id: int, db: Session = Depends(get_db)):
    """صفحة عامة تعرض محتويات الصندوق وسجلات الإضافة وتواريخ الصلاحية بدون تسجيل دخول"""
    from datetime import date
    
    box = db.query(FirstAidBox).filter(FirstAidBox.id == box_id).first()
    if not box:
        raise HTTPException(status_code=404, detail="الصندوق غير موجود")
    
    # توليد QR code يشير للصفحة العامة
    qr_url = f"{request.base_url}first-aid/boxes/{box_id}/public"
    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(qr_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    
    # تحويل الصورة إلى base64 لعرضها في HTML
    img_io = BytesIO()
    qr_img.save(img_io, format='PNG')
    img_io.seek(0)
    qr_base64 = base64.b64encode(img_io.getvalue()).decode()
    qr_data_url = f"data:image/png;base64,{qr_base64}"
    
    return templates.TemplateResponse("first_aid/box_public.html", {
        "request": request,
        "box": box,
        "items": box.items,
        "today": date.today(),
        "public": True,
        "qr_code": qr_data_url
    })

# ===================== الداشبورد الرئيسي =====================
@router.get("/", include_in_schema=False)
def fa_index(request: Request, user=Depends(require_doc), db: Session = Depends(get_db)):
    """الصفحة الرئيسية للإسعافات"""
    boxes = db.query(FirstAidBox).all()
    return templates.TemplateResponse("first_aid/index.html", {
        "request": request,
        "boxes": boxes,
        "box_count": len(boxes)
    })

@router.get("/boxes")
def boxes_list(request: Request, user=Depends(require_doc), db: Session = Depends(get_db)):
    """قائمة جميع صناديق الإسعافات"""
    boxes = db.query(FirstAidBox).all()
    return templates.TemplateResponse("first_aid/boxes_list.html", {
        "request": request,
        "boxes": boxes
    })

# ===================== إنشاء صندوق جديد =====================
@router.get("/boxes/create")
def boxes_create_form(request: Request, user=Depends(require_doc)):
    """نموذج إنشاء صندوق جديد"""
    return templates.TemplateResponse("first_aid/box_form.html", {
        "request": request,
        "mode": "create"
    })

@router.post("/boxes/create")
def boxes_create(
    request: Request,
    user=Depends(require_doc),
    db: Session = Depends(get_db),
    box_name: str = Form(...),
    location: str = Form(...)
):
    """إنشاء صندوق إسعافات جديد"""
    try:
        new_box = FirstAidBox(
            box_name=box_name,
            location=location,
            created_by_user_id=user.id
        )
        db.add(new_box)
        db.commit()
        db.refresh(new_box)
        return RedirectResponse(url=f"/first-aid/boxes/{new_box.id}", status_code=303)
    except Exception as ex:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(ex))

# ===================== عرض تفاصيل الصندوق =====================
@router.get("/boxes/{box_id}")
def box_detail(
    request: Request,
    box_id: int,
    msg: str = Query(default=None),
    user=Depends(require_doc),
    db: Session = Depends(get_db)
):
    """عرض تفاصيل صندوق معين"""
    from datetime import date
    import base64
    from io import BytesIO
    import qrcode
    
    box = db.query(FirstAidBox).filter(FirstAidBox.id == box_id).first()
    if not box:
        raise HTTPException(status_code=404, detail="الصندوق غير موجود")
    

    box.last_reviewed_at = datetime.now()
    db.commit()
    

    qr_url = f"{request.base_url}first-aid/boxes/{box_id}/public"
    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(qr_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    

    img_io = BytesIO()
    qr_img.save(img_io, format='PNG')
    img_io.seek(0)
    qr_base64 = base64.b64encode(img_io.getvalue()).decode()
    qr_data_url = f"data:image/png;base64,{qr_base64}"
    
    return templates.TemplateResponse("first_aid/box_detail.html", {
        "request": request,
        "box": box,
        "items": box.items,
        "today": date.today(),
        "msg": msg,
        "qr_code": qr_data_url
    })

@router.get("/boxes/{box_id}/add-item")
def add_item_form(
    request: Request,
    box_id: int,
    error: str = Query(default=None),
    user=Depends(require_doc),
    db: Session = Depends(get_db)
):
    """نموذج إضافة دواء للصندوق"""
    box = db.query(FirstAidBox).filter(FirstAidBox.id == box_id).first()
    if not box:
        raise HTTPException(status_code=404, detail="الصندوق غير موجود")
    
    # جلب قائمة الأدوية من الصيدلية (من Excel) مع الكميات المتوفرة
    try:
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        from excel_data_reference import get_all_drugs, get_drug_stock
        
        drugs = get_all_drugs()
        
        # إضافة كمية المتوفر لكل دواء
        for drug in drugs:
            try:
                stock = get_drug_stock(str(drug.get('id')))
                drug['available_quantity'] = stock.get('stock_qty', 0) if stock else 0
            except Exception:
                drug['available_quantity'] = 0
    except Exception:
        drugs = []
    
    return templates.TemplateResponse("first_aid/add_item.html", {
        "request": request,
        "box": box,
        "drugs": drugs,
        "error": error
    })

@router.post("/boxes/{box_id}/add-item")
def add_item(
    request: Request,
    box_id: int,
    user=Depends(require_doc),
    db: Session = Depends(get_db),
    drug_name: str = Form(...),
    drug_code: str = Form(default=None),
    quantity: int = Form(...),
    unit: str = Form(default="عدد"),
    expiry_date: str = Form(default=None),
    notes: str = Form(default=None)
):
    """إضافة دواء للصندوق"""
    try:
        box = db.query(FirstAidBox).filter(FirstAidBox.id == box_id).first()
        if not box:
            raise HTTPException(status_code=404, detail="الصندوق غير موجود")
        

        if drug_code:
            try:
                import sys
                import os
                sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
                from excel_data_reference import get_drug_by_code, get_drug_stock
                

                drug_stock = get_drug_stock(drug_code)
                
                if drug_stock:
                    available_quantity = drug_stock.get('stock_qty', 0)
                    if quantity > available_quantity:
                        error_msg = f"الكمية المطلوبة ({quantity}) تتجاوز المتاح في المخزون ({available_quantity}). الرجاء اختيار كمية أقل."
                        return RedirectResponse(
                            url=f"/first-aid/boxes/{box_id}/add-item?error={error_msg}",
                            status_code=303
                        )
            except Exception:

                pass
        
        expiry_date_obj = None
        if expiry_date:
            try:
                expiry_date_obj = datetime.strptime(expiry_date, "%Y-%m-%d").date()
            except Exception:
                pass
        
        new_item = FirstAidBoxItem(
            box_id=box_id,
            drug_name=drug_name,
            drug_code=drug_code,
            quantity=quantity,
            unit=unit,
            expiry_date=expiry_date_obj,
            notes=notes
        )
        db.add(new_item)
        db.commit()
        db.refresh(new_item)
        

        if drug_code:
            try:
                from sqlalchemy.orm import Session
                

                drug_row = db.execute(text(
                    'SELECT id FROM drugs WHERE drug_code = :code'
                ), {'code': drug_code}).fetchone()
                
                if drug_row:
                    drug_id = drug_row[0]
                    

                    db.execute(text('''
                        UPDATE warehouse_stock
                        SET balance_qty = balance_qty - :qty,
                            last_updated = CURRENT_TIMESTAMP
                        WHERE drug_id = :did
                    '''), {'qty': quantity, 'did': drug_id})
                    
                    # 3. خصم من رصيد الصيدلية (pharmacy) أيضاً
                    db.execute(text('''
                        UPDATE pharmacy_stock
                        SET balance_qty = balance_qty - :qty,
                            last_updated = CURRENT_TIMESTAMP
                        WHERE drug_id = :did
                    '''), {'qty': quantity, 'did': drug_id})
                    

                    db.execute(text('''
                        INSERT INTO drug_transactions 
                        (drug_id, drug_code, transaction_type, quantity_change, 
                         source, destination, notes, created_by)
                        VALUES (:did, :code, :type, :qty, :src, :dst, :notes, :uid)
                    '''), {
                        'did': drug_id,
                        'code': drug_code,
                        'type': 'warehouse_to_box',
                        'qty': -quantity,
                        'src': 'warehouse',
                        'dst': f'box_{box_id}',
                        'notes': f'إضافة للصندوق: {box.box_name}',
                        'uid': user.id
                    })
                    
                    db.commit()
                    print(f"✓ تم خصم {quantity} من الرصيد")
            except Exception as e:
                print(f"Warning: Failed to update stock: {e}")
                # لا نتوقف عن العملية حتى لو فشل الخصم
        
        return RedirectResponse(url=f"/first-aid/boxes/{box_id}?msg=item_added_stock_deducted", status_code=303)
    except Exception as ex:
        db.rollback()
        error_msg = str(ex)
        return RedirectResponse(
            url=f"/first-aid/boxes/{box_id}/add-item?error={error_msg}",
            status_code=303
        )

# ===================== حذف عنصر من الصندوق =====================
@router.post("/boxes/{box_id}/items/{item_id}/delete")
def delete_item(
    box_id: int,
    item_id: int,
    user=Depends(require_doc),
    db: Session = Depends(get_db)
):
    """حذف دواء من الصندوق وإرجاع الكمية للمخزن"""
    try:
        item = db.query(FirstAidBoxItem).filter(
            FirstAidBoxItem.id == item_id,
            FirstAidBoxItem.box_id == box_id
        ).first()
        
        if not item:
            raise HTTPException(status_code=404, detail="العنصر غير موجود")
        

        drug_code = item.drug_code
        quantity = item.quantity
        drug_name = item.drug_name
        

        db.delete(item)
        db.commit()
        

        if drug_code:
            try:

                drug_row = db.execute(text(
                    'SELECT id FROM drugs WHERE drug_code = :code'
                ), {'code': drug_code}).fetchone()
                
                if drug_row:
                    drug_id = drug_row[0]
                    

                    db.execute(text('''
                        UPDATE warehouse_stock
                        SET balance_qty = balance_qty + :qty,
                            last_updated = CURRENT_TIMESTAMP
                        WHERE drug_id = :did
                    '''), {'qty': quantity, 'did': drug_id})
                    
                    # 3. أرجع الكمية لرصيد الصيدلية (pharmacy)
                    db.execute(text('''
                        UPDATE pharmacy_stock
                        SET balance_qty = balance_qty + :qty,
                            last_updated = CURRENT_TIMESTAMP
                        WHERE drug_id = :did
                    '''), {'qty': quantity, 'did': drug_id})
                    

                    db.execute(text('''
                        INSERT INTO drug_transactions 
                        (drug_id, drug_code, transaction_type, quantity_change, 
                         source, destination, notes, created_by)
                        VALUES (:did, :code, :type, :qty, :src, :dst, :notes, :uid)
                    '''), {
                        'did': drug_id,
                        'code': drug_code,
                        'type': 'box_return',
                        'qty': quantity,
                        'src': f'box_{box_id}',
                        'dst': 'warehouse',
                        'notes': f'إرجاع من صندوق - حذف عنصر',
                        'uid': user.id
                    })
                    
                    db.commit()
            except Exception as e:
                print(f"Warning: Failed to restore stock on delete: {e}")
        
        return RedirectResponse(url=f"/first-aid/boxes/{box_id}?msg=item_deleted_stock_restored", status_code=303)
    except Exception as ex:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(ex))