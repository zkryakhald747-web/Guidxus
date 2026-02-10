
import bcrypt

def hash_password(password: str) -> str:
    """تهشير كلمة المرور باستخدام bcrypt"""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(plain_password: str, password_hash: str) -> bool:
    """التحقق من كلمة المرور"""
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), password_hash.encode('utf-8'))
    except:
        return False