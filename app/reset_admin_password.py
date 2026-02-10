from app.database import SessionLocal, engine, Base
from app.models import User
from app.security import hash_password

Base.metadata.create_all(bind=engine)
db = SessionLocal()

username = "admin"
new_password = "admin123"

user = db.query(User).filter(User.username == username).first()
if not user:
    raise SystemExit("❌ لا يوجد مستخدم admin. أنشئه أولاً.")

user.password_hash = hash_password(new_password)
user.is_active = True
user.is_admin = True
db.commit()
db.close()

print("✅ تم تحديث كلمة مرور admin بنجاح -> admin / admin123")