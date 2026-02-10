
from fastapi import APIRouter, Request, Depends, Form, HTTPException, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pydantic import BaseModel

from ..database import get_db
from ..deps_auth import require_user, CurrentUser
from ..models import User
from ..security import verify_password, hash_password

router = APIRouter(prefix="/profile", tags=["Profile"])
templates = Jinja2Templates(directory="app/templates")

def first_letter(text):
    if not text:
        return ""
    return str(text)[0].upper()

templates.env.filters["first_letter"] = first_letter

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str

@router.get("/")
def profile_page(
    request: Request,
    current_user: CurrentUser = Depends(require_user),
    db: Session = Depends(get_db)
):
    """عرض صفحة البروفايل الشخصي"""
    # جلب بيانات المستخدم الكاملة من قاعدة البيانات
    user = db.query(User).filter(User.id == current_user.id).first()
    
    return templates.TemplateResponse(
        "profile/index.html",
        {
            "request": request,
            "user": user,
            "current_user": current_user,
            "success": None,
            "error": None
        }
    )


@router.post("/change-password")
async def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    current_user: CurrentUser = Depends(require_user),
    db: Session = Depends(get_db)
):
    """تغيير كلمة المرور"""
    error = None
    success = None
    

    if not current_password or not new_password or not confirm_password:
        error = "جميع الحقول مطلوبة"
    elif new_password != confirm_password:
        error = "كلمات المرور الجديدة غير متطابقة"
    elif len(new_password) < 6:
        error = "كلمة المرور الجديدة يجب أن تكون 6 أحرف على الأقل"
    else:

        user = db.query(User).filter(User.id == current_user.id).first()
        

        if not verify_password(current_password, user.password_hash):
            error = "كلمة المرور الحالية غير صحيحة"
        else:

            user.password_hash = hash_password(new_password)
            db.commit()
            success = "تم تغيير كلمة المرور بنجاح"
    
    return templates.TemplateResponse(
        "profile/index.html",
        {
            "request": request,
            "user": current_user,
            "current_user": current_user,
            "success": success,
            "error": error
        }
    )

@router.post("/update-profile")
async def update_profile(
    request: Request,
    full_name: str = Form(...),
    current_user: CurrentUser = Depends(require_user),
    db: Session = Depends(get_db)
):
    """تحديث بيانات الملف الشخصي"""
    error = None
    success = None
    
    if not full_name or len(full_name.strip()) < 2:
        error = "الاسم الكامل يجب أن يكون 2 أحرف على الأقل"
    else:
        # تحديث الاسم
        user = db.query(User).filter(User.id == current_user.id).first()
        user.full_name = full_name.strip()
        db.commit()
        
        # تحديث الجلسة
        request.session["user"]["full_name"] = full_name.strip()
        success = "تم تحديث الملف الشخصي بنجاح"
    
    return templates.TemplateResponse(
        "profile/index.html",
        {
            "request": request,
            "user": current_user,
            "current_user": current_user,
            "success": success,
            "error": error
        }
    )