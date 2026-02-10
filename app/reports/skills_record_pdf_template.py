
SKILLS_RECORD_PDF_HTML = r"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8" />
  <title>{{ shape('سجل المهارات الشخصية') }} - {{ shape(trainee.trainee_name or '') }}</title>
  <style>
    {{ font_ready_css|safe }}
    /* brand:

    @page{
      size: A4 portrait;
      margin: 0;
      @frame header_frame  { -pdf-frame-content: header_content; left: 10mm; right: 10mm; top: 6mm;  height: 35mm; }
      @frame content_frame { left: 10mm; right: 10mm; top: 42mm; bottom: 90mm; }
      @frame footer_frame  { -pdf-frame-content: footer_content; left: 10mm; right: 10mm; bottom: 6mm; height: 85mm; }
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
    /* تعديل اللوجو: تقليل العرض للخانة */
    .logo-cell{ text-align:right; width:50mm; } 
    /* تعديل اللوجو: زيادة الارتفاع */
    .logo{ max-height:50mm; width:auto; height: 40mm; display:block; object-fit:contain; margin-top: 2mm; }
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

    /* ===== التوقيعات ===== */
    .signatures-section {
      width: 100%;
      margin-top: 20px;
      border-collapse: collapse;
    }
    .sig-cell {
      width: 33.33%;
      text-align: center;
      padding: 0;
      border: none;
    }
    .sig-name {
      font-weight: 700;
      font-size: 11pt;
      margin-bottom: 20px;
      display: block;
    }
    .sig-line {
      border-top: 1px solid
      height: 20px;
      width: 90%;
      margin: 0 auto;
      display: block;
    }
    .sig-title {
      font-size: 10pt;
      margin-top: 3px;
      display: block;
    }

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
        <td class="logo-cell">
          {% if logo_src %}
            <img class="logo" src="{{ logo_src }}" alt="logo">
          {% endif %}
        </td>

        <td style="text-align: right; padding-top: 2mm;">
          <div class="report-title">{{ shape('سجل المهارات الشخصية') }}</div>
          <div class="title-underline"></div>
        </td>
      </tr>
    </table>
  </div>

  <div id="content_frame">
    <section class="card"><div class="pad">
      <span class="chip">{{ shape('بيانات المتدرب والإحصائيات') }}</span>
      <table class="meta">
        <colgroup>
          <col style="width:18%"><col style="width:32%"><col style="width:18%"><col style="width:32%">
        </colgroup>

        <tr>
          <td class="value">{{ shape(trainee.trainee_no or '') }}</td>
          <td class="label">{{ shape('الرقم التدريبي') }}</td>
          <td class="value">{{ shape(trainee.trainee_name or '') }}</td>
          <td class="label">{{ shape('الاسم الكامل') }}</td>
        </tr>

        <tr>
          <td class="value">{{ trainee.total_hours|int }}</td>
          <td class="label">{{ shape('إجمالي الساعات') }}</td>
          <td class="value">{{ trainee.completed_courses }}</td>
          <td class="label">{{ shape('عدد الدورات') }}</td>
        </tr>

        <tr>
          <td class="value">{{ shape(trainee.department or '---') }}</td>
          <td class="label">{{ shape('القسم') }}</td>
          <td class="value">{{ shape(trainee.total_certificates) }}</td>
          <td class="label">{{ shape('عدد الشهادات') }}</td>
        </tr>

        <tr>
          <td class="value">{{ shape(trainee.college or '---') }}</td>
          <td class="label">{{ shape('الكلية') }}</td>
          <td class="value ltr">{{ generated_date }}</td>
          <td class="label">{{ shape('تاريخ الإصدار') }}</td>
        </tr>
      </table>

      {% if trainee.courses %}
      <span class="chip" style="margin-top:12px;">{{ shape('الدورات التدريبية') }}</span>
      <table class="meta" style="margin-bottom:12px;">
        <colgroup>
          <col style="width:15%"><col style="width:60%"><col style="width:25%">
        </colgroup>
        <thead>
          <tr>
            <th style="background:#0f7d89; color:#fff; font-weight:700; padding:8px;">{{ shape('عدد الساعات') }}</th>
            <th style="background:#0f7d89; color:#fff; font-weight:700; padding:8px;">{{ shape('اسم الدورة') }}</th>
            <th style="background:#0f7d89; color:#fff; font-weight:700; padding:8px;">{{ shape('م') }}</th>
          </tr>
        </thead>
        <tbody>
          {% for course in trainee.courses %}
          <tr>
            <td style="border:1.2px solid #c5d6de; padding:6px 8px; text-align:center;">{{ course.hours|int }}</td>
            <td style="border:1.2px solid #c5d6de; padding:6px 8px; text-align:right;">{{ shape(course.course_title or '') }}</td>
            <td style="border:1.2px solid #c5d6de; padding:6px 8px; text-align:center;">{{ loop.index }}</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
      {% endif %}

    </div></section>
  </div>

  <div id="footer_content">
    {% if colleges and colleges|length > 0 %}
      {% for col in colleges %}
        <table class="signatures-section" style="margin-top:12px;">
          <tr>
            <td class="sig-cell">
              <span class="sig-title" style="font-size:11pt; font-weight:700;">{{ shape('عميد الكلية - ' + (col.name or '') + ((' - ' + col.dean_name) if col.dean_name else '')) }}</span>
            </td>
            <td class="sig-cell">
              <span class="sig-title" style="font-size:11pt; font-weight:700;">{{ shape('وكيل شؤون المتدربين - ' + (col.vp_name or '')) }}</span>
            </td>
            <td class="sig-cell">
              <span class="sig-title" style="font-size:11pt; font-weight:700;">{{ shape('الختم') }}</span>
            </td>
          </tr>
          <tr style="height: 85px;">
            <td class="sig-cell" style="vertical-align: top; text-align: center; padding: 0 5px;">
              {% if col.dean_sign_url and col.dean_sign_url != '/static/blank.png' %}
                <img src="{{ col.dean_sign_url }}" alt="توقيع العميد" style="max-height: 70px; width: auto; display: inline-block; margin: 0 auto 0 auto;">
              {% else %}
                <div style="border-top:2px solid #2b2d31; display:block; height:50px; margin-top:15px;"></div>
              {% endif %}
            </td>
            <td class="sig-cell" style="vertical-align: top; text-align: center; padding: 0 5px;">
              {% if col.vp_sign_url and col.vp_sign_url != '/static/blank.png' %}
                <img src="{{ col.vp_sign_url }}" alt="توقيع الوكيل" style="max-height: 70px; width: auto; display: inline-block; margin: 0 auto 0 auto;">
              {% else %}
                <div style="border-top:2px solid #2b2d31; display:block; height:50px; margin-top:15px;"></div>
              {% endif %}
            </td>
            <td class="sig-cell" style="vertical-align: top; text-align: center; padding: 0 5px;">
              {% if col.stamp_url and col.stamp_url != '/static/blank.png' %}
                <img src="{{ col.stamp_url }}" alt="ختم شؤون المتدربين" style="max-height: 70px; width: auto; display: inline-block; margin: 0 auto 0 auto;">
              {% else %}
                <div style="border-top:2px solid #2b2d31; display:block; height:50px; margin-top:15px;"></div>
              {% endif %}
            </td>
          </tr>
        </table>
      {% endfor %}
    {% else %}
      <table class="signatures-section">
        <tr>
          <td class="sig-cell">
            <span class="sig-title" style="font-size:11pt; font-weight:700;">{{ shape('عميد الكلية - ' + (dean_name or '')) }}</span>
          </td>
          <td class="sig-cell">
            <span class="sig-title" style="font-size:11pt; font-weight:700;">{{ shape('وكيل شؤون المتدربين - ' + (delegate_name or '')) }}</span>
          </td>
          <td class="sig-cell">
            <span class="sig-title" style="font-size:11pt; font-weight:700;">{{ shape('الختم') }}</span>
          </td>
        </tr>
        <tr style="height: 85px;">
          <td class="sig-cell" style="vertical-align: top; text-align: center; padding: 0 5px;">
            {% if dean_sign_url and dean_sign_url != '/static/blank.png' %}
              <img src="{{ dean_sign_url }}" alt="توقيع العميد" style="max-height: 70px; width: auto; display: inline-block; margin: 0 auto 0 auto;">
            {% else %}
              <div style="border-top:2px solid #2b2d31; display:block; height:50px; margin-top:15px;"></div>
            {% endif %}
          </td>
          <td class="sig-cell" style="vertical-align: top; text-align: center; padding: 0 5px;">
            {% if vp_sign_url and vp_sign_url != '/static/blank.png' %}
              <img src="{{ vp_sign_url }}" alt="توقيع الوكيل" style="max-height: 70px; width: auto; display: inline-block; margin: 0 auto 0 auto;">
            {% else %}
              <div style="border-top:2px solid #2b2d31; display:block; height:50px; margin-top:15px;"></div>
            {% endif %}
          </td>
          <td class="sig-cell" style="vertical-align: top; text-align: center; padding: 0 5px;">
            {% if stamp_url and stamp_url != '/static/blank.png' %}
              <img src="{{ stamp_url }}" alt="ختم شؤون المتدربين" style="max-height: 70px; width: auto; display: inline-block; margin: 0 auto 0 auto;">
            {% else %}
              <div style="border-top:2px solid #2b2d31; display:block; height:50px; margin-top:15px;"></div>
            {% endif %}
          </td>
        </tr>

      </table>
    {% endif %}
    
    <div style="margin-top:30px; text-align:center;">
      <div class="footer-note">{{ shape('سجل المهارات الشخصية للمتدربين - نسخة معتمدة') }}</div>
      <div class="footer-main">{{ shape('تم إصدار هذا السجل من خلال نظام Guidxus - الكلية التقنية بنجران') }}</div>
    </div>
  </div>

</body>
</html>
"""