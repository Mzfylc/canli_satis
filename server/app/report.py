import os
from decimal import Decimal
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader

def _try_register_tr_font() -> str:
    # Türkçe destekli fontları dene (macOS + Windows)
    candidates = [
        # macOS
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica.ttf",
        # Windows
        "C:\\Windows\\Fonts\\arial.ttf",
        "C:\\Windows\\Fonts\\arialuni.ttf",
        "C:\\Windows\\Fonts\\calibri.ttf",
        "C:\\Windows\\Fonts\\segoeui.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("TRFont", path))
                return "TRFont"
            except Exception:
                pass
    return "Helvetica"

def _reports_dir() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "reports"))


def build_daily_pdf(report_date: str, summary: dict, rows: list[dict]) -> str:
    # Günlük raporu, aralık şablonuyla aynı görünümde üret
    return build_range_pdf(
        report_date,
        report_date,
        summary,
        rows,
        title="Gunluk Satis Raporu",
    )


def build_range_pdf(start_day: str, end_day: str, summary: dict, rows: list, title: str = "Satis Raporu"):
    base_dir = _reports_dir()
    os.makedirs(base_dir, exist_ok=True)
    filename = f"range_{start_day}_to_{end_day}.pdf"
    path = os.path.join(base_dir, filename)
    c = canvas.Canvas(path, pagesize=A4)
    w, h = A4

    font_name = _try_register_tr_font()
    c.setFont(font_name, 18)
    c.drawString(50, h-60, f"FIRMA - {title}")
    c.setFont(font_name, 12)
    c.drawString(50, h-85, f"Tarih Araligi: {start_day} - {end_day}")

    c.setFont(font_name, 12)
    y = h-130
    c.drawString(50, y, f"Toplam Siparis: {summary.get('count',0)}"); y -= 18
    c.drawString(50, y, f"Toplam Satis: {summary.get('total',0):.2f}"); y -= 18
    c.drawString(50, y, f"Odenen: {summary.get('paid',0):.2f}"); y -= 18
    c.drawString(50, y, f"Bekleyen: {summary.get('pending',0):.2f}"); y -= 18
    c.drawString(50, y, f"Iptal: {summary.get('cancelled',0):.2f}"); y -= 28

    # baslik
    c.setLineWidth(1)
    c.line(50, y, w-50, y)
    y -= 18
    c.setFont(font_name, 11)
    # Kolon konumları (A4'e sığacak şekilde)
    x_date = 40
    x_time = 90
    x_photo = 125
    x_name = 155
    x_phone = 305
    x_product = 395
    x_price = 500
    x_status = 525

    c.drawString(x_date, y, "Tarih")
    c.drawString(x_time, y, "Saat")
    c.drawString(x_photo, y, "Foto")
    c.drawString(x_name, y, "Isim")
    c.drawString(x_phone, y, "Telefon")
    c.drawString(x_product, y, "Urun")
    c.drawRightString(x_price, y, "Fiyat")
    c.drawString(x_status, y, "Durum")
    y -= 12
    c.line(50, y, w-50, y)
    y -= 18

    def tr_status(s):
        return {"pending":"bekliyor","paid":"odendi","cancelled":"iptal"}.get(s, s)

    c.setFont(font_name, 10)
    for r in rows:
        if y < 80:
            c.showPage()
            y = h-60
            c.setFont(font_name, 10)

        c.drawString(x_date, y, str(r.get("date",""))[:10])
        c.drawString(x_time, y, str(r.get("time",""))[:5])

        photo_path = r.get("photo_path") or ""
        if photo_path and os.path.exists(photo_path):
            try:
                img = ImageReader(photo_path)
                c.drawImage(img, x_photo, y - 10, width=20, height=20, preserveAspectRatio=True, mask="auto")
            except Exception:
                pass

        c.drawString(x_name, y, str(r.get("full_name",""))[:18])
        c.drawString(x_phone, y, str(r.get("phone",""))[:13])
        c.drawString(x_product, y, str(r.get("product",""))[:14])
        c.drawRightString(x_price, y, f"{float(r.get('price',0)):.2f}")
        c.drawString(x_status, y, tr_status(r.get("status","")))
        y -= 18

    c.save()
    # API'ye relative dosya adı dönüyoruz; istemci /report-files/<filename> ile açacak
    return filename
