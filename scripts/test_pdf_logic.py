
import sys
import os
sys.path.append(os.getcwd())

from app.database import SessionLocal
from sqlalchemy import text
from app.models import User, Department, College

def test_logic():
    db = SessionLocal()
    trainee_no = "444116046"
    trainee_info = {"department": None, "college": None}

    try:
        print(f"Testing logic for trainee: {trainee_no}")

        trainee_user = db.query(User).filter(User.username == trainee_no).first()
        if trainee_user:
            user_dept = getattr(trainee_user, 'department', None)
            user_college = getattr(trainee_user, 'college', None)
            print(f"User found. Dept: {user_dept}, College: {user_college}")
        else:
            print("User not found.")

        if not trainee_info["department"]:
            print("Checking course_enrollments...")
            enrollment = db.execute(
                text("SELECT trainee_major FROM course_enrollments WHERE trainee_no = :tno AND trainee_major IS NOT NULL LIMIT 1"),
                {"tno": trainee_no}
            ).mappings().first()
            
            if enrollment and enrollment["trainee_major"]:
                major_str = enrollment["trainee_major"]
                print(f"Found major: {major_str}")
                
                if " - " in major_str:
                    parts = major_str.split(" - ")
                    if len(parts) >= 2:
                        trainee_info["department"] = parts[0].strip()
                        possible_college = parts[-1].strip()
                        if "كلية" in possible_college:
                            trainee_info["college"] = possible_college
                
                if not trainee_info["department"]:
                    trainee_info["department"] = major_str

        if trainee_info["department"] and not trainee_info["college"]:
            print(f"Looking up college for dept: {trainee_info['department']}")
            dept = db.query(Department).filter(Department.name == trainee_info["department"]).first()
            if dept and dept.college:
                college = db.query(College).filter(College.name == dept.college).first()
                trainee_info["college"] = college.name if college else dept.college

        print("\nFinal Result:")
        print(f"Department: {trainee_info['department']}")
        print(f"College: {trainee_info['college']}")
        
        if trainee_info["department"] == "تقنية الخدمات اللوجستية" and trainee_info["college"] == "كلية نجران":
            print("\nSUCCESS: Logic works as expected.")
        else:
            print("\nWARNING: Result differs from expectation.")

    finally:
        db.close()

if __name__ == "__main__":
    test_logic()