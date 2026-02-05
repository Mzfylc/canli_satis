import os
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from .db import SessionLocal
from .models import Order, ReportLog
from .report import build_daily_pdf
from .mailer import send_mail

def compute_daily(db: Session, day: str):
    # day: YYYY-MM-DD
    start = datetime.fromisoformat(day + "T00:00:00")
    end = datetime.fromisoformat(day + "T23:59:59")

    q = db.query(Order).filter(Order.created_at >= start, Order.created_at <= end).order_by(Order.created_at.asc())
    orders = q.all()

    total = sum([float(o.price) for o in orders if o.status != "cancelled"])
    paid = sum([float(o.price) for o in orders if o.status == "paid"])
    pending = sum([float(o.price) for o in orders if o.status == "pending"])
    cancelled = sum([float(o.price) for o in orders if o.status == "cancelled"])

    rows = []
    for o in orders:
        rows.append({
            "time": o.created_at.strftime("%H:%M"),
            "full_name": o.full_name,
            "phone": o.phone,
            "product": o.product,
            "price": str(o.price),
            "status": o.status
        })

    summary = {
        "count": len(orders),
        "total": total,
        "paid": paid,
        "pending": pending,
        "cancelled": cancelled
    }
    return summary, rows

def run_daily_job():
    db = SessionLocal()
    try:
        day = datetime.now().strftime("%Y-%m-%d")
        existing = db.query(ReportLog).filter(ReportLog.report_date == day).first()
        if existing and existing.mailed:
            return

        summary, rows = compute_daily(db, day)
        pdf_path = build_daily_pdf(day, summary, rows)

        if not existing:
            existing = ReportLog(report_date=day, pdf_path=pdf_path, mailed=False)
            db.add(existing)
            db.commit()

        subject = f"Gunluk Satis Raporu - {day}"
        body = (
            f"Tarih: {day}\n"
            f"Toplam Siparis: {summary['count']}\n"
            f"Toplam Satis: {summary['total']:.2f}\n"
            f"Odenen: {summary['paid']:.2f}\n"
            f"Bekleyen: {summary['pending']:.2f}\n"
            f"Iptal: {summary['cancelled']:.2f}\n"
        )
        ok, _ = send_mail(subject, body, [pdf_path])
        if ok:
            existing.mailed = True
            existing.pdf_path = pdf_path
            db.commit()
    finally:
        db.close()

def start_scheduler():
    hour = int(os.getenv("REPORT_HOUR", "23"))
    minute = int(os.getenv("REPORT_MINUTE", "0"))
    sched = BackgroundScheduler()
    sched.add_job(run_daily_job, "cron", hour=hour, minute=minute)
    sched.start()
    return sched
