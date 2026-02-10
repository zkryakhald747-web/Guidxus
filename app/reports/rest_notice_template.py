
REST_NOTICE_HTML = r"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8" />
  <title>{{ shape('إشعار إجازة مرضية') }} - {{ shape(patient.full_name or '') }}</title>
  <style>
    {{ font_ready_css|safe }}
    /* brand:

    @page{
      size: A4 portrait;
      margin: 0;
      @frame header_frame  { -pdf-frame-content: header_content; left: 10mm; right: 10mm; top: 6mm;  height: 22mm; }
      @frame content_frame { left: 10mm; right: 10mm; top: 32mm; bottom: 28mm; }
      @frame footer_frame  { -pdf-frame-content: footer_content; left: 10mm; right: 10mm; bottom: 6mm; height: 20mm; }
    }

    html, body{
      direction: rtl; margin:0; padding:0;
      -webkit-print-color-adjust: exact; print-color-adjust: exact;
      color:
      font-family:'MajallaAR','TradArabicAR','Majalla','Traditional Arabic','Arial Unicode MS','DejaVu Sans','Arial';
    }
    * { font-family: inherit !important; }

    .ltr { direction:ltr; unicode-bidi:bidi-override; }

    /* ===== الهيدر المثبّت ===== */
    .hdr{ width:100%; border-collapse:collapse; table-layout:fixed; }
    .hdr td{ vertical-align:middle; padding:0; }
    .title-cell{ text-align:left; padding-right:6mm; }
    .logo-cell{ text-align:right; width:50mm; }
    .logo{ max-height:28mm; width:auto; height: 24mm; display:block; object-fit:contain; margin-top: 5mm; }
    .report-title{ font-weight:800; color:
    .title-underline{ height:3px; width:180px; background:

    /* ===== البطاقة ===== */
    .card{ background:
    .pad{ padding:10px 12px; }
    .chip{
      display:block; text-align:center; padding:2px 10px; margin:0 auto 8px;
      background:
    }
    table.meta{ width:100%; border-collapse:collapse; border:1.2px solid
    table.meta th, table.meta td{ border:1.2px solid
    table.meta td.label{ width:18%; font-weight:700; background:
    table.meta td.value{ width:32%; word-wrap:break-word; overflow-wrap:break-word; }

    /* ===== نص الخطاب ===== */
    .body-text{
      direction: rtl; unicode-bidi: embed;
      text-align: right; margin-top:12px; line-height:1.3;
    }
    .body-text p{ margin:0 0 10px 0; }

    .sign-row{ margin-top:28px; display:flex; justify-content:space-between; gap:20px; }
    .sign-box{ flex:1; min-height:42mm; border:1.2px dashed
    .sign-title{ color:
    .rtl-left{ text-align:left; }

    /* ===== الفوترة ===== */
    .footer-wrap { text-align:center; }
    .footer-note{ font-size:9pt; color:
    .footer-main{ font-size:10.5pt; color:
  </style>
</head>
<body>

  <div id="header_content">
    <table class="hdr" role="presentation" aria-hidden="true">
      <tr>
        <td style="text-align: right; width: 20%;">
          {% if logo_src %}
            <img class="logo" src="{{ logo_src }}" alt="logo">
          {% endif %}
        </td>

        <td style="text-align: right; width: 80%; padding-top: 2mm;">
          <div class="report-title">{{ shape('إشعار إجازة مرضية') }}</div>
          <div class="title-underline"></div>
        </td>
      </tr>
    </table>
  </div>

  <div id="content_frame">
    <section class="card"><div class="pad">
      <span class="chip">{{ shape('بيانات المراجع') }}</span>
      <table class="meta">
        <colgroup>
          <col style="width:18%"><col style="width:32%"><col style="width:18%"><col style="width:32%">
        </colgroup>

        <tr>
          <td class="value">{{ shape(patient.national_id or '') }}</td>
          <td class="label">{{ shape('رقم الهوية') }}</td>
          <td class="value">{{ shape(patient.full_name or '') }}</td>
          <td class="label">{{ shape('الاسم') }}</td>
        </tr>

        <tr>
          <td class="value">{{ shape(patient.mobile or '') }}</td>
          <td class="label">{{ shape('رقم الجوال') }}</td>
          <td class="value">{{ shape(patient.trainee_no or patient.employee_no or '') }}</td>
          <td class="label">{{ shape('الرقم التدريبي') if patient.patient_type=='trainee' else shape('الرقم الوظيفي') }}</td>
        </tr>

        <tr>
          <td class="value ltr">{{ visit_date }}</td>
          <td class="label">{{ shape('تاريخ الزيارة') }}</td>
          <td class="value">{{ shape('يوم') }} {{ shape(rest_days) }}</td>
          <td class="label">{{ shape('عدد أيام الراحة') }}</td>
        </tr>

        <tr>
          <td class="value" colspan="3">
            {% if visit.chronic_json %}
              {% set chronic_list = visit.chronic_json|safe %}
              {{ shape(chronic_list) }}
            {% else %}
              <span>—</span>
            {% endif %}
          </td>
          <td class="label">{{ shape('الأمراض المزمنة') }}</td>
        </tr>

        {% if patient.patient_type=='trainee' %}
        <tr>
          <td class="value" colspan="3">{{ shape(patient.major or '') }}</td>
          <td class="label">{{ shape('التخصص') }}</td>
        </tr>
        {% endif %}
      </table>

      <div class="body-text">
        <p>{{ shape('الزملاء الكرام بالكلية وفقهم الله') }}</p>
        <p>{{ shape('السلام عليكم ورحمة الله وبركاته، وبعد:') }}</p>
        <p>{{ shape('تفيدكم العيادة الطبية بأن المراجع قد حضر للعيادة في التاريخ الموضح في الجدول أعلاه،') }}</p>
        <p>{{ shape('وقد تقرر منحه راحة بعدد الأيام المبين فيه بدءًا من يوم الزيارة.') }}</p>
        <p>{{ shape('مع تمنياتنا له بالشفاء العاجل،') }}</p>
        <p>{{ shape('وتقبلوا خالص التحية والتقدير.') }}</p>
      </div>

<div style="margin-top:28px; text-align:left; direction:rtl; margin-left:25mm;">
  <p style="margin:0 0 5px 0; font-size:13pt;">
    {{ shape(doctor_name or '') }} {{ shape('طبيب الكلية :') }}
  </p>
  <p style="margin:0; font-size:13pt;">
    ____________________ {{ shape('التوقيع :') }}
  </p>
</div>

    </div></section>
  </div>

  <div id="footer_content" class="footer-wrap">
    <div class="footer-note">{{ shape('تنبيه: هذه الإجازة صالحة للاستخدام داخل الكلية فقط') }}</div>
    <div class="footer-main">{{ shape('تم تصدير هذا النموذج من خلال نظام Guidxus لخدمة المتدربين - الكلية التقنية بنجران') }}</div>
  </div>

</body>
</html>
"""