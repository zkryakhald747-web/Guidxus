from app.database import SessionLocal
from sqlalchemy import text

db = SessionLocal()

try:
    result = db.execute(text("SELECT student_id, name_ar FROM students WHERE student_id = '123456789' LIMIT 1")).fetchone()
    if result:
        print(f'From students table:')
        print(f'  student_id: {result[0]}')
        print(f'  name_ar: {result[1]}')
    else:
        print('No student found')
except Exception as e:
    print(f'Students table error: {e}')

print()

try:
    result = db.execute(text("SELECT id, username, full_name FROM users WHERE username = '123456789' LIMIT 1")).fetchone()
    if result:
        print(f'From users table:')
        print(f'  id: {result[0]}')
        print(f'  username: {result[1]}')
        print(f'  full_name: {result[2]}')
    else:
        print('No user found')
except Exception as e:
    print(f'Users table error: {e}')

db.close()