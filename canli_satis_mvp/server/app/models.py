from sqlalchemy import Column, Integer, String, DateTime, Numeric, Text, Boolean, UniqueConstraint
from sqlalchemy.sql import func
from .db import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), default="admin")

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    full_name = Column(String(255), nullable=False)
    phone = Column(String(50), nullable=False)
    product = Column(String(255), nullable=False)
    price = Column(Numeric(12, 2), nullable=False)
    status = Column(String(20), nullable=False)  # pending/paid/cancelled
    note = Column(Text, default="")

    client_id = Column(String(80), nullable=False)
    client_order_id = Column(String(80), nullable=False)

    __table_args__ = (
        UniqueConstraint("client_id", "client_order_id", name="uq_client_order"),
    )

class ReportLog(Base):
    __tablename__ = "report_logs"
    id = Column(Integer, primary_key=True)
    report_date = Column(String(10), unique=True, nullable=False)  # YYYY-MM-DD
    pdf_path = Column(String(500), nullable=False)
    mailed = Column(Boolean, default=False)
