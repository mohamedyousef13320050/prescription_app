"""توليد وحفظ الروشتة الطبية بصيغة HTML و PDF جاهزة للطباعة بحجم A4."""
import html
from pathlib import Path
from typing import Dict, List, Any, Tuple
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle


def build_prescription_html(
    metadata: Dict[str, str],
    items: List[Dict[str, Any]],
    prescription_id: int = 0,
) -> str:
    """توليد صفحة روشتة A4 احترافية باللغة العربية والإنجليزية جاهزة للطباعة المباشرة."""
    rows_html = []
    for idx, it in enumerate(items, start=1):
        rows_html.append(f"""
        <tr>
          <td style="padding:10px;border-bottom:1px solid #cbd5e1;text-align:center;font-weight:700;">{idx}</td>
          <td style="padding:10px;border-bottom:1px solid #cbd5e1;text-align:right;">
            <div style="font-weight:700;font-size:15px;color:#0f172a;">{html.escape(str(it.get('medicine_name', '')))}</div>
            <div style="font-size:12px;color:#475569;">التركيز: <strong>{html.escape(str(it.get('concentration', '')))}</strong> | الشكل: {html.escape(str(it.get('dosage_form', '')))}</div>
          </td>
          <td style="padding:10px;border-bottom:1px solid #cbd5e1;text-align:center;">{html.escape(str(it.get('dose', '—')))}</td>
          <td style="padding:10px;border-bottom:1px solid #cbd5e1;text-align:center;">{html.escape(str(it.get('frequency', '—')))}</td>
          <td style="padding:10px;border-bottom:1px solid #cbd5e1;text-align:center;">{html.escape(str(it.get('duration', '—')))}</td>
          <td style="padding:10px;border-bottom:1px solid #cbd5e1;text-align:right;">{html.escape(str(it.get('instructions', '—')))}</td>
        </tr>
        """)

    body_rows = "".join(rows_html) if rows_html else '<tr><td colspan="6" style="padding:20px;text-align:center;">لا توجد أدوية مضافة بعد</td></tr>'
    rx_num_label = f"#{prescription_id}" if prescription_id else "مسودة جديدة"

    return f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<title>روشتة طبية - {html.escape(metadata.get('patient_name', ''))}</title>
<style>
  @page {{ size: A4 portrait; margin: 14mm; }}
  body {{ font-family: 'Tahoma', 'Segoe UI', Arial, sans-serif; background: #f8fafc; color: #0f172a; margin: 0; padding: 16px; direction: rtl; }}
  .sheet {{ max-width: 210mm; margin: 0 auto; background: #ffffff; padding: 18mm; border: 1px solid #cbd5e1; border-radius: 8px; }}
  .header {{ display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 3px solid #0f4c5c; padding-bottom: 14px; margin-bottom: 16px; }}
  .patient-bar {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; background: #f1f5f9; padding: 12px 16px; border-radius: 6px; margin-bottom: 18px; font-size: 14px; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 24px; font-size: 13.5px; }}
  th {{ background: #0f4c5c; color: #ffffff; padding: 10px; text-align: center; }}
  .footer {{ margin-top: 32px; display: flex; justify-content: space-between; align-items: flex-end; border-top: 1px solid #cbd5e1; padding-top: 16px; font-size: 13px; }}
  @media print {{
    body {{ background: #ffffff; padding: 0; }}
    .sheet {{ border: none; padding: 0; }}
    .no-print {{ display: none !important; }}
  }}
</style>
</head>
<body>
<div class="sheet">
  <div class="header">
    <div>
      <h1 style="margin:0;font-size:22px;color:#0f4c5c;">{html.escape(metadata.get('clinic_name', 'عيادة طبية'))}</h1>
      <div style="font-size:14px;font-weight:700;margin-top:4px;">د. {html.escape(metadata.get('doctor_name', '________________'))}</div>
      <div style="font-size:12px;color:#475569;">{html.escape(metadata.get('doctor_specialty', ''))} | قيد نقابة: {html.escape(metadata.get('doctor_reg_no', '—'))}</div>
    </div>
    <div style="text-align:left;font-size:13px;">
      <div><strong>رقم الروشتة:</strong> {rx_num_label}</div>
      <div><strong>التاريخ:</strong> {html.escape(metadata.get('prescription_date', ''))}</div>
      <div style="font-size:12px;color:#475569;">{html.escape(metadata.get('clinic_address', ''))}</div>
    </div>
  </div>

  <div class="patient-bar">
    <div><strong>اسم المريض:</strong> {html.escape(metadata.get('patient_name', '________________'))}</div>
    <div><strong>السن / النوع:</strong> {html.escape(metadata.get('patient_age', '—'))} / {html.escape(metadata.get('patient_gender', '—'))}</div>
    <div><strong>التشخيص:</strong> {html.escape(metadata.get('diagnosis_notes', '—'))}</div>
  </div>

  <div style="font-size:20px;font-weight:700;color:#0f4c5c;margin-bottom:10px;">&#8478; الأدوية الموصوفة والمؤكدة من الطبيب</div>

  <table>
    <thead>
      <tr>
        <th style="width:36px;">#</th>
        <th style="text-align:right;">اسم الدواء والتركيز</th>
        <th>الجرعة</th>
        <th>التكرار</th>
        <th>المدة</th>
        <th style="text-align:right;">تعليمات الاستخدام</th>
      </tr>
    </thead>
    <tbody>
      {body_rows}
    </tbody>
  </table>

  <div class="footer">
    <div>تم التأكيد والمراجعة بواسطة الطبيب المعالج.</div>
    <div style="width:200px;border-top:1px solid #0f172a;text-align:center;padding-top:6px;font-weight:700;">توقيع وختم الطبيب</div>
  </div>
</div>
</body>
</html>"""


def save_prescription_files(
    saved_dir: Path,
    prescription_id: int,
    metadata: Dict[str, str],
    items: List[Dict[str, Any]],
) -> Tuple[Path, Path]:
    """حفظ نسخة HTML ونسخة PDF للروشتة في مجلد saved_prescriptions."""
    saved_dir = Path(saved_dir)
    saved_dir.mkdir(parents=True, exist_ok=True)
    html_path = saved_dir / f"prescription_{prescription_id:04d}.html"
    pdf_path = saved_dir / f"prescription_{prescription_id:04d}.pdf"

    html_content = build_prescription_html(metadata, items, prescription_id=prescription_id)
    html_path.write_text(html_content, encoding="utf-8")

    # توليد ملف PDF قياسي A4
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )
    styles = getSampleStyleSheet()
    cell_style = ParagraphStyle("RxCell", parent=styles["Normal"], fontSize=9, leading=12)
    story = [
        Paragraph(f"<b>Prescription #{prescription_id:04d}</b> | Date: {html.escape(metadata.get('prescription_date', ''))}", styles["Heading2"]),
        Spacer(1, 4 * mm),
    ]
    tbl_data = [["#", "Medicine (EN)", "Conc.", "Dose", "Frequency", "Duration", "Status"]]
    for idx, it in enumerate(items, start=1):
        en_name = str(it.get("medicine_name", "")).split("(")[0].strip() or str(it.get("medicine_name", ""))
        tbl_data.append([
            str(idx),
            Paragraph(f"<b>{html.escape(en_name)}</b>", cell_style),
            Paragraph(html.escape(str(it.get("concentration", ""))), cell_style),
            Paragraph(html.escape(str(it.get("dose", ""))), cell_style),
            Paragraph(html.escape(str(it.get("frequency", ""))), cell_style),
            Paragraph(html.escape(str(it.get("duration", ""))), cell_style),
            "CONFIRMED",
        ])
    tbl = Table(tbl_data, colWidths=[10 * mm, 52 * mm, 26 * mm, 24 * mm, 28 * mm, 20 * mm, 24 * mm], repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f4c5c")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(tbl)
    doc.build(story)
    return html_path, pdf_path
