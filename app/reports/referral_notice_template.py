
REFERRAL_NOTICE_HTML = r"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8" />
  <title dir="rtl">
    {{ shape('بطاقة تحويل واستشارة') }} - {{ shape(patient.full_name or '') }}
  </title>

  <style>
    {{ font_ready_css|safe }}
    /* ألوان عامة: brand

    /* ================= صفحة وطباعة ================= */
    @page{
      size: A4 portrait;
      margin: 8mm;
    }

    html, body{
      direction: rtl;
      margin:0;
      padding: 4mm;
      padding-top: 4mm;
      padding-bottom: 4mm;
      -webkit-print-color-adjust: exact; print-color-adjust: exact;
      color:
      font-size:11pt; line-height:1.4;
      font-family:'MajallaAR','TradArabicAR','Majalla','Traditional Arabic','Arial Unicode MS','DejaVu Sans','Arial';
      display: flex;
      flex-direction: column;
      min-height: 100vh;
    }
    *{ font-family: inherit !important; }
    .ltr{ direction:ltr; unicode-bidi:bidi-override; }

    /* ================= هيدر (نظام الجداول لضمان الأماكن) ================= */

        width: 100%;
        border-collapse: collapse;
        margin-bottom: 8mm;
        table-layout: fixed; /* تثبيت العرض لمنع التحرك */
    }

        vertical-align: top;
        padding: 0;
    }

    /* تنسيق اللوجو */
    .logo-img { 
        height: 24mm;            
        width: auto;             
        object-fit: contain; 
        display: block;
        margin-top: 5mm; /* نزول بسيط للوجو ليكون موازي للعنوان */
    }

    /* تنسيق العنوان */
    .report-title{ 
        font-weight:800; 
        color:
        font-size:20pt; 
        line-height:1.1; 
        margin:0; 
        white-space: nowrap;     
    }
    
    .title-underline{ 
        height:3px; 
        width:180px; 
        background:
        border-radius:4px; 
        margin-top:5pt; 
        /* محاذاة الخط لليسار */
        margin-left: 0; 
        margin-right: auto; 
    }

    /* ================= بطاقات وعناوين ================= */

      flex: 1; 
      margin: 0;
      padding: 0 4mm 0 4mm;
    }
    .card{ background:
    .pad{ padding:6px 8px; }

    table.chipbox{
      width:100%;
      border-collapse:separate;
      border-spacing:0;
      background:
      color:
      border:1.2px solid
      border-radius:6px;
      margin:0 auto 6px;
      margin-left: 4mm;
      margin-right: 4mm;
      page-break-inside: avoid;
    }
    table.chipbox td{ text-align:center; padding:2px 8px; vertical-align:middle; }
    table.chipbox .ar{ display:block; font-weight:700; font-size:11pt; line-height:1.0; }
    table.chipbox .en{ display:block; font-size:9pt; font-weight:normal; line-height:0.85; margin-top:0px; direction:ltr; }

    /* ================= جداول أساسية (أزرق) ================= */
    table.meta, table.meta3{
      width:100%;
      border-collapse:collapse;
      border:1.2px solid
      margin: 0 auto 8px;
      margin-left: 4mm;
      margin-right: 4mm;
      table-layout:fixed;
    }
    table.meta th, table.meta td,
    table.meta3 th, table.meta3 td{
      border:1.2px solid
      padding:4px 6px;
      text-align:center;
      font-size:9pt;
    }
    table.meta td.label, table.meta3 td.label{
      font-weight:700; background:
    }
    table.meta td.value, table.meta3 td.value{
      word-wrap:break-word; overflow-wrap:break-word;
    }
    table.meta td.label div, table.meta3 td.label div{
      line-height:1.2; margin:0; padding:0;
    }
    table.meta td.label div.en, table.meta3 td.label div.en{
      font-size:80%; font-weight:normal;
    }

    /* ================= تخصيص جدول رد جهة الإحالة (برتقالي) ================= */
    table.meta3.resp{ border-color:
    table.meta3.resp th, table.meta3.resp td{ border-color:
    table.meta3.resp td.label{
      width:18%;
      background:
      color:
    }
    table.meta3.resp td.value{
      width:82%;
      background:
    }
    table.meta3.resp td.label div.en{ color:inherit; }

    /* ================= خطوط تعبئة ================= */
    .fill{
      display:inline-block;
      border-bottom:1px dotted
      min-width:40mm;
      height:1.2em;
      vertical-align:baseline;
    }
    .fill.short{ min-width:28mm; }
    .fill.med  { min-width:40mm; }
    .fill.long { min-width:90mm; }

    /* ================= جدول خيارات الإجراء ================= */
    table.opt-table{ width:100%; border-collapse:collapse; table-layout:fixed; }
    .opt-table td{ text-align:center; vertical-align:middle; padding:4px; }
    .cb{ width:4.2mm; height:4.2mm; border:1.2px solid
    .opt-lines .ar{ line-height:1.05; }
    .opt-lines .en{ direction:ltr; font-size:85%; font-weight:normal; line-height:1.0; }

    /* ================= فوتر ================= */

      position: absolute;
      left: 15mm;
      right: 15mm;
      bottom: 6mm;
      height: 26mm;
      margin-top: auto;
    }
    .footer-wrap{ text-align:center; }
    .footer-main{ font-size:10.5pt; color:
  </style>
</head>
<body>

<table id="header_table" role="presentation">
    <tr>
        <td style="text-align: right; width: 20%;">
            {% if logo_src %}
                <img class="logo-img" src="{{ logo_src }}" alt="logo">
            {% endif %}
        </td>

        <td style="text-align: right; width: 80%; padding-top: 2mm;">
            <div class="report-title">
                {{ shape('بطاقة تحويل و استشارة') }}<br/>
                {{ shape('REFERRAL FORM') }}
            </div>
            <div class="title-underline"></div>
        </td>
    </tr>
</table>

<div id="content_frame">

  <section class="card">
    <div class="pad">

      <table class="chipbox" role="presentation" aria-hidden="true">
        <tr>
          <td>
            <span class="ar">{{ shape('بيانات المراجع') }}</span>
            <span class="en" dir="ltr">{{ shape('Patient Information') }}</span>
          </td>
        </tr>
      </table>

      <table class="meta">
        <colgroup>
          <col style="width:32%"><col style="width:18%">
          <col style="width:32%"><col style="width:18%">
        </colgroup>

        <tr>
          <td class="value">{{ shape(patient.national_id or '') }}</td>
          <td class="label">
            <div>{{ shape('رقم الهوية') }}</div>
            <div dir="ltr" class="en">{{ shape('National ID') }}</div>
          </td>

          <td class="value">{{ shape(patient.full_name or '') }}</td>
          <td class="label">
            <div>{{ shape('الاسم') }}</div>
            <div dir="ltr" class="en">{{ shape("Patient's Name") }}</div>
          </td>
        </tr>

        <tr>
          <td class="value">{{ shape(patient.mobile or '') }}</td>
          <td class="label">
            <div>{{ shape('رقم الجوال') }}</div>
            <div dir="ltr" class="en">{{ shape('Mobile Number') }}</div>
          </td>

          <td class="value">{{ shape(patient.trainee_no or patient.employee_no or '') }}</td>
          <td class="label">
            <div>
              {{ shape('الرقم التدريبي') if patient.patient_type=='trainee' else shape('الرقم الوظيفي') }}
            </div>
            <div dir="ltr" class="en">
              {{ shape('Trainee No.') if patient.patient_type=='trainee' else shape('Employee No.') }}
            </div>
          </td>
        </tr>

        <tr>
          <td class="value ltr">{{ visit_date }}</td>
          <td class="label">
            <div>{{ shape('تاريخ الزيارة') }}</div>
            <div dir="ltr" class="en">{{ shape('Visit Date') }}</div>
          </td>

          <td class="value">
            {% if patient.birth_date %}
              <span class="ltr"><span class="ltr">{{ shape('سنة') }}</span> {{ patient.age }} / {{ patient.birth_date }}</span>{% if patient.age is not none %}{% endif %}
            {% else %}
              <span class="fill short"></span>
            {% endif %}
          </td>
          <td class="label">
            <div>{{ shape('تاريخ الميلاد / العمر') }}</div>
            <div dir="ltr" class="en">{{ shape('DOB / Age') }}</div>
          </td>
        </tr>

        {% if patient.patient_type=='trainee' %}
        <tr>
          <td class="value" colspan="3">{{ shape(patient.major or '') }}</td>
          <td class="label">
            <div>{{ shape('التخصص') }}</div>
            <div dir="ltr" class="en">{{ shape('Major') }}</div>
          </td>
        </tr>
        {% endif %}
      </table>
    </div>
  </section>

  <table class="chipbox" role="presentation" aria-hidden="true">
    <tr>
      <td>
        <span class="ar">{{ shape('الفحص السريري') }}</span>
        <span class="en" dir="ltr">{{ shape('PHYSICAL EXAMINATION') }}</span>
      </td>
    </tr>
  </table>

  <table class="meta3">
    <colgroup>
      <col style="width:21%"><col style="width:12%">
      <col style="width:21%"><col style="width:12%">
      <col style="width:22%"><col style="width:12%">
    </colgroup>

    <tr>
      <td class="value">
        {% if pulse_bpm is defined and pulse_bpm is not none %}
          <span class="ltr">{{ pulse_bpm }}</span>
        {% else %}
          <span class="fill short"></span>
        {% endif %}
      </td>
      <td class="label">
        <div>{{ shape('النبض') }}</div>
        <div class="en" dir="ltr">{{ shape('Pulse') }}</div>
      </td>

      <td class="value">
        {% if bp_systolic is defined and bp_systolic is not none and
              bp_diastolic is defined and bp_diastolic is not none %}
          <span class="ltr">{{ bp_systolic }}/{{ bp_diastolic }}</span>
        {% else %}
          <span class="fill short"></span>
        {% endif %}
      </td>
      <td class="label">
        <div>{{ shape('ضغط الدم') }}</div>
        <div class="en" dir="ltr">{{ shape('BP') }}</div>
      </td>

      <td class="value">
        {% if temp_c is defined and temp_c is not none %}
          <span class="ltr">{{ "%.1f"|format(temp_c) }}°C</span>
        {% else %}
          <span class="fill short"></span>
        {% endif %}
      </td>
      <td class="label">
        <div>{{ shape('الحرارة') }}</div>
        <div class="en" dir="ltr">{{ shape('Temp') }}</div>
      </td>
    </tr>

    <tr>
      <td class="value" colspan="5">
        {% if chronic_json is defined and chronic_json %}
          {% if chronic_json is iterable and (chronic_json is not string) %}
            {{ shape((chronic_json|join('، ')) or '') }}
          {% else %}
            {{ shape(chronic_json) }}
          {% endif %}
        {% else %}
          <span class="fill long"></span>
        {% endif %}
      </td>
      <td class="label">
        <div>{{ shape('الأمراض المزمنة') }}</div>
        <div class="en" dir="ltr">{{ shape('Chronic Diseases') }}</div>
      </td>
    </tr>

    <tr>
      <td class="value" colspan="5">
        {% if complaint is defined and complaint %}
          {{ shape(complaint) }}
        {% else %}
          <span class="fill long"></span>
        {% endif %}
      </td>
      <td class="label">
        <div>{{ shape('الشكوى ومدتها') }}</div>
        <div class="en" dir="ltr">{{ shape('Complaint & Duration') }}</div>
      </td>
    </tr>

    <tr>
      <td class="value" colspan="5">
        {% if treatment_given is defined and treatment_given %}
          {{ shape(treatment_given) }}
        {% elif notes is defined and notes %}
          {{ shape(notes) }}
        {% else %}
          <span class="fill long"></span>
        {% endif %}
      </td>
      <td class="label">
        <div>{{ shape('العلاج المعطى') }}</div>
        <div class="en" dir="ltr">{{ shape('Treatment given') }}</div>
      </td>
    </tr>

    <tr>
      <td class="value" colspan="5">
        {% if referral_summary is defined and referral_summary %}
          {{ shape(referral_summary) }}
        {% else %}
          <span class="fill long"></span>
        {% endif %}
      </td>
      <td class="label">
        <div>{{ shape('سبب الإحالة') }}</div>
        <div class="en" dir="ltr">{{ shape('Reason for referral') }}</div>
      </td>
    </tr>

    <tr>
      <td class="value" colspan="5">
        {% if referral_to is defined and referral_to %}
          {{ shape(referral_to) }}
        {% else %}
          <span class="fill long"></span>
        {% endif %}
      </td>
      <td class="label">
        <div>{{ shape('جهة الإحالة') }}</div>
        <div class="en" dir="ltr">{{ shape('Hospital / Center') }}</div>
      </td>
    </tr>

    <tr>
      <td class="value" colspan="5">
        {% if doctor_name is defined and doctor_name %}
          {{ shape(doctor_name) }}
        {% else %}
          <span class="fill long"></span>
        {% endif %}
      </td>
      <td class="label">
        <div>{{ shape('اسم الطبيب المعالج') }}</div>
        <div class="en" dir="ltr">{{ shape('Physician name') }}</div>
      </td>
    </tr>
  </table>

  <table class="chipbox" role="presentation" aria-hidden="true">
    <tr>
      <td>
        <span class="ar">{{ shape('رد جهة الإحالة') }}</span>
        <span class="en" dir="ltr">{{ shape('Receiving Facility Response') }}</span>
      </td>
    </tr>
  </table>

  <table class="meta3 resp">
    <colgroup>
      <col style="width:82%"><col style="width:18%">
    </colgroup>

    <tr>
      <td class="value"><span class="fill long"></span></td>
      <td class="label">
        <div>{{ shape('نتيجة الاستشارة والفحص') }}</div>
        <div class="en" dir="ltr">{{ shape('Finding & Diagnosis') }}</div>
      </td>
    </tr>

    <tr>
      <td class="value"><span class="fill long"></span></td>
      <td class="label">
        <div>{{ shape('العلاج والتوصيات') }}</div>
        <div class="en" dir="ltr">{{ shape('Treatment & Recommendations') }}</div>
      </td>
    </tr>

    </table>

</div> <div id="footer_content">
  <div style="margin-bottom:6mm;">
    <table class="meta3 resp" style="margin-bottom:6mm;">
      <colgroup>
        <col style="width:82%"><col style="width:18%">
      </colgroup>
      <tr>
        <td class="value">
          <table class="opt-table" role="presentation" aria-hidden="true">
            <colgroup><col><col><col></colgroup>
            <tr>
              <td>
                <span class="cb"></span>
                <div class="opt-lines">
                  <div class="ar">{{ shape('انتهاء الاستشارة') }}</div>
                  <div class="en" dir="ltr">{{ shape('Discharge') }}</div>
                </div>
              </td>
              <td>
                <span class="cb"></span>
                <div class="opt-lines">
                  <div class="ar">{{ shape('مراجعة العيادة') }}</div>
                  <div class="en" dir="ltr">{{ shape('Follow Up') }}</div>
                </div>
              </td>
              <td>
                <span class="cb"></span>
                <div class="opt-lines">
                  <div class="ar">{{ shape('دخول المستشفى') }}</div>
                  <div class="en" dir="ltr">{{ shape('Hospital Admission') }}</div>
                </div>
              </td>
            </tr>
          </table>
        </td>
        <td class="label">
          <div>{{ shape('الإجراء المتخذ') }}</div>
          <div class="en" dir="ltr">{{ shape('Action Taken') }}</div>
        </td>
      </tr>
    </table>
  </div>

  <div class="footer-wrap">
    <div class="footer-main">
      {{ shape('تم تصدير هذا النموذج من خلال نظام Guidxus لخدمة المتدربين - الكلية التقنية بنجران') }}
    </div>
  </div>
</div>

</body>
</html>
"""