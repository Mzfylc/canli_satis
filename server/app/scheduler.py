import os
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
from sqlalchemy.orm import Session
from .db import SessionLocal
from .models import Order, ReportLog
from .report import build_daily_pdf
from .mailer import send_mail

def compute_daily(db: Session, day: str):
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
            "status": o.status,
            "photo_path": o.photo_path or ""
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


def compute_range(db, start_day: str, end_day: str):
    # start_day/end_day: YYYY-MM-DD
    start_dt = datetime.fromisoformat(start_day + "T00:00:00")
    end_dt = datetime.fromisoformat(end_day + "T23:59:59")
    q = db.query(Order).filter(Order.created_at >= start_dt).filter(Order.created_at <= end_dt)
    rows = q.order_by(Order.created_at.asc()).all()

    total = 0.0
    paid = 0.0
    pending = 0.0
    cancelled = 0.0

    out = []
    for r in rows:
        price = float(r.price)
        total += price
        if r.status == "paid":
            paid += price
        elif r.status == "pending":
            pending += price
        elif r.status == "cancelled":
            cancelled += price

        out.append({
            "date": r.created_at.strftime("%Y-%m-%d"),
            "time": str(r.created_at)[11:16],
            "full_name": r.full_name,
            "phone": r.phone or "",
            "product": r.product,
            "price": price,
            "status": r.status,
            "photo_path": r.photo_path or "",
        })

    summary = {
        "count": len(out),
        "total": round(total, 2),
        "paid": round(paid, 2),
        "pending": round(pending, 2),
        "cancelled": round(cancelled, 2),
    }
    return summary, out
