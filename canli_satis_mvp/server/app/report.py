import os
from decimal import Decimal
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

def build_daily_pdf(report_date: str, summary: dict, rows: list[dict]) -> str:
    os.makedirs("reports", exist_ok=True)
    path = f"reports/daily_{report_date}.pdf"
    c = canvas.Canvas(path, pagesize=A4)
    w, h = A4

    company = os.getenv("COMPANY_NAME", "FIRMA")
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, h - 50, f"{company} - Gunluk Satis Raporu")
    c.setFont("Helvetica", 11)
    c.drawString(40, h - 70, f"Tarih: {report_date}")

    y = h - 105
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, y, f"Toplam Siparis: {summary['count']}")
    y -= 16
    c.drawString(40, y, f"Toplam Satis: {summary['total']:.2f}")
    y -= 16
    c.drawString(40, y, f"Odenen: {summary['paid']:.2f}")
    y -= 16
    c.drawString(40, y, f"Bekleyen: {summary['pending']:.2f}")
    y -= 16
    c.drawString(40, y, f"Iptal: {summary['cancelled']:.2f}")

    y -= 25
    c.setFont("Helvetica-Bold", 10)
    c.drawString(40, y, "Saat")
    c.drawString(85, y, "Isim")
    c.drawString(230, y, "Telefon")
    c.drawString(320, y, "Urun")
    c.drawRightString(515, y, "Fiyat")
    c.drawString(525, y, "Durum")
    y -= 12
    c.line(40, y, 555, y)
    y -= 14

    c.setFont("Helvetica", 9)
    for r in rows:
        if y < 60:
            c.showPage()
            y = h - 60
            c.setFont("Helvetica", 9)

        c.drawString(40, y, r["time"])
        c.drawString(85, y, r["full_name"][:22])
        c.drawString(230, y, r["phone"][:14])
        c.drawString(320, y, r["product"][:20])
        c.drawRightString(515, y, f"{Decimal(r['price']):.2f}")
        c.drawString(525, y, r["status"])
        y -= 12

    c.save()
    return path
