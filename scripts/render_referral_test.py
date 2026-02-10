import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app.reports.referral_notice_template import REFERRAL_NOTICE_HTML
from jinja2 import Template

payload = {
    'patient': {'full_name': 'Test Name', 'national_id':'123', 'mobile':'0591234567', 'trainee_no':'123', 'employee_no':'', 'major':'', 'birth_date':'1990-01-01', 'age': 35, 'patient_type':'trainee'},
    'visit_date': '2025-12-02',
    'referral_to': 'King Fahad Hospital',
    'referral_summary': 'Summary',
    'diagnosis': 'Diagnose',
    'temp_c': 37.0,
    'bp_systolic': 120,
    'bp_diastolic': 80,
    'pulse_bpm': 75,
    'chronic_json': 'لا يوجد',
    'complaint': 'Headache',
    'treatment_given': 'Ibuprofen',
    'notes': 'example notes',
    'doctor_name': 'Dr. Smith',
    'created_by_name': 'Dr. Smith',
    'logo_src': None,
    'font_ready_css':'',
    'shape': lambda x: x,
}

html = Template(REFERRAL_NOTICE_HTML).render(**payload)
out_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'rendered_referral_test.html')
open(out_path,'w',encoding='utf-8').write(html)
print('Wrote d:\\project\\rendered_referral_test.html')