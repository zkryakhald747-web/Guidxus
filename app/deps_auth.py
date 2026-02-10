
from typing import Optional
from fastapi import Request, HTTPException, status, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .database import get_db
from .models import User

class CurrentUser(BaseModel):
    id: int
    full_name: str
    username: str
    is_admin: bool = False
    is_college_admin: bool = False
    college_admin_college: Optional[str] = None
    is_hod: bool = False
    is_doc: bool = False
    hod_college: Optional[str] = None

def _map_user(u: User) -> CurrentUser:
    """تحويل ORM User إلى CurrentUser (Booleans مضمونة)."""
    return CurrentUser(
        id=u.id,
        full_name=u.full_name,
        username=u.username,
        is_admin=bool(u.is_admin),
        is_college_admin=bool(getattr(u, "is_college_admin", False)),
        college_admin_college=getattr(u, "college_admin_college", None),
        is_hod=bool(u.is_hod),
        is_doc=bool(getattr(u, "is_doc", False)),  # 👈 جديد
        hod_college=u.hod_college,
    )


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> Optional[CurrentUser]:
    """
    يقرأ المستخدم من الجلسة، ثم يعيد قراءته من قاعدة البيانات
    لضمان تحديث الصلاحيات مباشرة (بدون الاعتماد على بيانات قديمة في الجلسة).
    """
    sess = request.session.get("user")
    if not sess:
        # لا توجد جلسة
        request.state.current_user = None
        return None

    user_id = sess.get("id")
    if not user_id:
        request.state.current_user = None
        return None

    # ملاحظة: إن كنت على SQLAlchemy < 2.0 استخدم filter(...).first()
    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user or not db_user.is_active:
        # جلسة غير صالحة أو مستخدم غير فعّال
        request.state.current_user = None
        return None

    cu = _map_user(db_user)

    # خزن نسخة محدثة في request.state لاستخدامها داخل القوالب
    request.state.current_user = cu
    return cu


# ✅ الحمايات (تُستخدم كـ Depends في المسارات)
def require_user(user: Optional[CurrentUser] = Depends(get_current_user)) -> CurrentUser:
    if not user:
        # 401 → سيتم تحويلها لصفحة تسجيل الدخول عبر الـ exception_handler في main.py
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="الرجاء تسجيل الدخول",
        )
    if not user.username or not user.id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="جلسة غير صالحة",
        )
    return user


def require_admin(user: CurrentUser = Depends(require_user)) -> CurrentUser:
    """يتطلب سوبر أدمن أو أدمن كلية"""
    if not (user.is_admin or user.is_college_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="هذه الصفحة للأدمن فقط",
        )
    return user

def require_college_admin(user: CurrentUser = Depends(require_user)) -> CurrentUser:
    """يتطلب أدمن كلية فقط (صلاحيات مقتصرة على كليته)."""
    if not user.is_college_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="هذه الصفحة لأدمن الكلية فقط",
        )
    return user

def require_super_admin(user: CurrentUser = Depends(require_user)) -> CurrentUser:
    """يتطلب سوبر أدمن فقط (صلاحيات كاملة)"""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="هذه الصفحة للسوبر أدمن فقط",
        )
    return user

def require_hod(user: CurrentUser = Depends(require_user)) -> CurrentUser:
    if not user.is_hod:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="هذه الصفحة لرؤساء الأقسام فقط",
        )
    return user

def require_hod_or_admin(user: CurrentUser = Depends(require_user)) -> CurrentUser:
    """يسمح لرئيس القسم أو السوبر أدمن أو أدمن الكلية للوصول لمسارات القسم فقط."""
    if not (user.is_hod or user.is_admin or user.is_college_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="صلاحيات غير كافية",
        )
    return user


def require_doc(user: CurrentUser = Depends(require_user)) -> CurrentUser:
    """
    صلاحية طبيب الكلية أو أدمن الكلية أو السوبر أدمن.
    تُستخدم لحماية صفحات العيادة والصيدلية والمخزون.
    """
    if not (user.is_doc or user.is_college_admin or user.is_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="هذه الصفحة لأطباء الكلية أو أدمن الكلية",
        )
    return user


def require_user_manager(user: CurrentUser = Depends(require_user)) -> CurrentUser:
    """صلاحية إدارة المستخدمين: سوبر أدمن أو أدمن كلية أو رئيس قسم."""
    if not (user.is_admin or user.is_college_admin or user.is_hod):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="هذه الصفحة لإدارة المستخدمين (سوبر أدمن/أدمن كلية/رئيس قسم)",
        )
    return user