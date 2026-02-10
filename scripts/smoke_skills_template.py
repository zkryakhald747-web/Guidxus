from jinja2 import Template
from app.reports.skills_record_pdf_template import SKILLS_RECORD_PDF_HTML

def run_check():
    tpl = Template(SKILLS_RECORD_PDF_HTML)
    payload = {
        'trainee': {'trainee_no': 'X', 'trainee_name': 'Y', 'courses': []},
        'logo_src': None,
        'generated_date': '2025-12-26',
        'generated_by': 'tester',
        'dean_name': '',
        'delegate_name': '',
        'dept_head_name': '',
        'dean_sign_url': '/static/blank.png',
        'vp_sign_url': '/static/blank.png',
        'stamp_url': '/static/blank.png',
        'font_ready_css': '',
        'shape': lambda x: x,
        'colleges': [
            {
                'name': 'كلية أ',
                'dean_name': 'د. أحمد',
                'vp_name': 'أ. فاطمة',
                'dean_sign_url': '/static/dean_a.png',
                'vp_sign_url': '/static/vp_a.png',
                'stamp_url': '/static/stamp_a.png',
            },
            {
                'name': 'كلية ب',
                'dean_name': 'د. سعيد',
                'vp_name': 'أ. ليلى',
                'dean_sign_url': '/static/dean_b.png',
                'vp_sign_url': '/static/vp_b.png',
                'stamp_url': '/static/stamp_b.png',
            },
        ],
    }
    html = tpl.render(**payload)
    assert '/static/dean_a.png' in html, 'missing dean_a'
    assert 'د. أحمد' in html, 'missing dean name'
    assert '/static/stamp_b.png' in html, 'missing stamp_b'
    print('OK: template includes college signatures')

if __name__ == '__main__':
    run_check()