
import sys
import os
sys.path.append(os.getcwd())

from app.database import SessionLocal
from sqlalchemy import text
from app.models import User, Department

def check_data():
    db = SessionLocal()
    try:
        trainee_no = "444116046"
        

        print("Checking sf01...")
        try:
            row = db.execute(
                text('SELECT * FROM sf01 WHERE student_id = :sid'),
                {"sid": int(trainee_no)}
            ).mappings().first()
            if row:
                print(f"Found in sf01: {dict(row)}")
            else:
                print("Not found in sf01")
        except Exception as e:
            print(f"Error checking sf01: {e}")

        print("\nChecking User...")
        user = db.query(User).filter(User.username == trainee_no).first()
        if user:
            print(f"Found User: {user.username}")
            try:
                print(f"User.department: {user.department}")
            except AttributeError:
                print("User has no attribute 'department'")
            
            try:
                print(f"User.college: {user.college}")
            except AttributeError:
                print("User has no attribute 'college'")
        else:
            print("User not found")

        print("\nChecking CourseEnrollments...")
        enrollments = db.execute(
            text("SELECT DISTINCT trainee_major FROM course_enrollments WHERE trainee_no = :tno"),
            {"tno": trainee_no}
        ).mappings().all()
        print(f"Enrollment Majors: {[r['trainee_major'] for r in enrollments]}")
        

        if row and row.get('Major'):
            major = row['Major']
            print(f"\nChecking Department for Major: {major}")
            dept = db.query(Department).filter(Department.name == major).first()
            if dept:
                print(f"Found Department: {dept.name}, College: {dept.college}")
            else:
                print("Department not found in departments table")

    finally:
        db.close()

if __name__ == "__main__":
    check_data()