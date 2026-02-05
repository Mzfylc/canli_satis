import os
import base64
import uuid
from sqlalchemy import text
from datetime import datetime, timedelta
from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from .db import Base, engine, get_db
from .models import User, Order
from .schemas import LoginIn, TokenOut, OrderIn, OrderOut, RangeReportIn
from .auth import hash_password, verify_password, create_token, require_user
from .scheduler import start_scheduler, compute_daily, compute_range
from .report import build_daily_pdf, build_range_pdf

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

app = FastAPI(title="Canli Satis API")

# PDF raporlarını servis et (mutlak yol)
REPORTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "reports"))
os.makedirs(REPORTS_DIR, exist_ok=True)
# Not: /reports endpoint'leri POST kullandığı için statik servis farklı bir yol olmalı
app.mount("/report-files", StaticFiles(directory=REPORTS_DIR), name="report-files")

@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)

    from .db import SessionLocal
    db = SessionLocal()
    try:
        # sqlite schema update: photo_path column
        cols = db.execute(text("PRAGMA table_info(orders)")).fetchall()
        col_names = [c[1] for c in cols]
        if "photo_path" not in col_names:
            db.execute(text("ALTER TABLE orders ADD COLUMN photo_path TEXT"))
            db.commit()

        admin_email = os.getenv("ADMIN_EMAIL", "admin@firma.com")
        admin_pass = os.getenv("ADMIN_PASSWORD", "123456")
        u = db.query(User).filter(User.email == admin_email).first()
        if not u:
            u = User(email=admin_email, password_hash=hash_password(admin_pass), role="admin")
            db.add(u)
            db.commit()
    finally:
        db.close()

    start_scheduler()

@app.post("/auth/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.email == body.email).first()
    if not u or not verify_password(body.password, u.password_hash):
        raise HTTPException(status_code=401, detail="Bad credentials")
    return TokenOut(access_token=create_token(u.email))

@app.post("/orders/sync", response_model=OrderOut)
def sync_order(order: OrderIn, user: str = Depends(require_user), db: Session = Depends(get_db)):
    def _save_photo(photo_b64: str) -> str:
        if not photo_b64:
            return ""
        try:
            data = base64.b64decode(photo_b64.encode("utf-8"))
        except Exception:
            return ""
        os.makedirs("uploads", exist_ok=True)
        path = os.path.join("uploads", f"{uuid.uuid4()}.jpg")
        with open(path, "wb") as f:
            f.write(data)
        return path

    existing = db.query(Order).filter(
        Order.client_id == order.client_id,
        Order.client_order_id == order.client_order_id
    ).first()
    if existing:
        # existing kaydı güncelle (status, fiyat, not vb.)
        existing.full_name = order.full_name
        existing.phone = order.phone
        existing.product = order.product
        existing.price = order.price
        existing.status = order.status
        existing.note = order.note or ""
        if order.photo_b64:
            existing.photo_path = _save_photo(order.photo_b64)
        db.commit()
        db.refresh(existing)
        return existing

    photo_path = _save_photo(order.photo_b64) if order.photo_b64 else ""
    o = Order(
        full_name=order.full_name,
        phone=order.phone,
        product=order.product,
        price=order.price,
        status=order.status,
        note=order.note or "",
        photo_path=photo_path,
        client_id=order.client_id,
        client_order_id=order.client_order_id
    )
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


@app.post("/reports/daily")
def manual_daily_report(user: str = Depends(require_user), db: Session = Depends(get_db)):
    day = datetime.now().strftime("%Y-%m-%d")
    summary, rows = compute_daily(db, day)
    path = build_daily_pdf(day, summary, rows)
    return {"pdf": path, "count": summary["count"], "total": summary["total"]}


@app.get("/stats/today")
def stats_today(user: str = Depends(require_user), db: Session = Depends(get_db)):
    day = datetime.now().strftime("%Y-%m-%d")
    summary, _ = compute_daily(db, day)
    return summary


@app.post("/reports/weekly")
def report_weekly(user: str = Depends(require_user), db: Session = Depends(get_db)):
    end = datetime.now().date()
    start = end - timedelta(days=6)
    summary, rows = compute_range(db, str(start), str(end))
    path = build_range_pdf(str(start), str(end), summary, rows, title="Haftalik Satis Raporu")
    return {"pdf": path, "start": str(start), "end": str(end), "count": summary["count"], "total": summary["total"]}


@app.post("/reports/monthly")
def report_monthly(user: str = Depends(require_user), db: Session = Depends(get_db)):
    today = datetime.now().date()
    start = today.replace(day=1)
    end = today
    summary, rows = compute_range(db, str(start), str(end))
    path = build_range_pdf(str(start), str(end), summary, rows, title="Aylik Satis Raporu")
    return {"pdf": path, "start": str(start), "end": str(end), "count": summary["count"], "total": summary["total"]}


@app.post("/reports/range")
def report_range(body: RangeReportIn, user: str = Depends(require_user), db: Session = Depends(get_db)):
    start = (body.start or "").strip()
    end = (body.end or "").strip()
    if not start or not end:
        raise HTTPException(status_code=400, detail="start/end required")
    try:
        dt_start = datetime.strptime(start, "%Y-%m-%d").date()
        dt_end = datetime.strptime(end, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")
    if dt_end < dt_start:
        raise HTTPException(status_code=400, detail="end must be >= start")

    summary, rows = compute_range(db, str(dt_start), str(dt_end))
    path = build_range_pdf(str(dt_start), str(dt_end), summary, rows, title="Tarih Araligi Satis Raporu")
    return {"pdf": path, "start": str(dt_start), "end": str(dt_end), "count": summary["count"], "total": summary["total"]}


@app.patch("/orders/{order_id}/status")
def update_order_status(order_id: int, payload: dict, user: str = Depends(require_user), db: Session = Depends(get_db)):
    status = (payload.get("status") or "").strip()
    if status not in ("pending", "paid", "cancelled"):
        raise HTTPException(status_code=400, detail="Invalid status")
    o = db.get(Order, order_id)
    if not o:
        raise HTTPException(status_code=404, detail="Order not found")
    o.status = status
    db.commit()
    db.refresh(o)
    return {"id": o.id, "status": o.status}
