import os
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from .db import Base, engine, get_db
from .models import User, Order
from .schemas import LoginIn, TokenOut, OrderIn, OrderOut
from .auth import hash_password, verify_password, create_token, require_user
from .scheduler import start_scheduler

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

app = FastAPI(title="Canli Satis API")

@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)

    # Admin seed
    from .db import SessionLocal
    db = SessionLocal()
    try:
        admin_email = os.getenv("ADMIN_EMAIL", "admin@firma.com")
        admin_pass = os.getenv("ADMIN_PASSWORD", "123456")
        u = db.query(User).filter(User.email == admin_email).first()
        if not u:
            u = User(email=admin_email, password_hash=hash_password(admin_pass), role="admin")
            db.add(u); db.commit()
    finally:
        db.close()

    # Scheduler
    start_scheduler()

@app.post("/auth/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.email == body.email).first()
    if not u or not verify_password(body.password, u.password_hash):
        raise HTTPException(status_code=401, detail="Bad credentials")
    return TokenOut(access_token=create_token(u.email))

@app.post("/orders/sync", response_model=OrderOut)
def sync_order(order: OrderIn, user: str = Depends(require_user), db: Session = Depends(get_db)):
    existing = db.query(Order).filter(
        Order.client_id == order.client_id,
        Order.client_order_id == order.client_order_id
    ).first()
    if existing:
        return existing

    o = Order(
        full_name=order.full_name,
        phone=order.phone,
        product=order.product,
        price=order.price,
        status=order.status,
        note=order.note or "",
        client_id=order.client_id,
        client_order_id=order.client_order_id
    )
    db.add(o); db.commit(); db.refresh(o)
    return o
