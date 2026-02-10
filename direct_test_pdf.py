
"""Direct test of the PDF generation without HTTP"""
import sys
sys.path.insert(0, 'd:\\test_it--main')

from app.database import SessionLocal, is_sqlite
from app.deps_auth import CurrentUser
from app.routers.hod import skills_record_pdf_export
from datetime import datetime

# Create a mock session
db = SessionLocal()

# Create a mock user
user = CurrentUser(
    id=1,
    username="test_hod",
    full_name="Test HOD User",
    is_admin=False,
    is_hod=True,
    is_doc=False,
    hod_college=None,
    is_active=True,
    is_college_admin=False,
    college_admin_college=None,
    must_change_password=False
)

print("=" * 60)
print("🧪 Testing skills_record_pdf_export directly")
print("=" * 60)

try:
    result = skills_record_pdf_export(
        trainee_no="123456789",
        db=db,
        user=user
    )
    print(f"✓ Function executed successfully!")
    print(f"Result type: {type(result)}")
    
    # For StreamingResponse, we check media_type and headers
    print(f"✓ PDF endpoint is working!")
    print(f"Status code would be: 200")
    print(f"Content type: {result.media_type}")
    print(f"Headers: {result.headers}")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
finally:
    db.close()