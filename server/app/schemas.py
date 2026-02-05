from pydantic import BaseModel, EmailStr
from typing import Optional, Literal
from decimal import Decimal
from datetime import datetime

Status = Literal["pending", "paid", "cancelled"]

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"

class OrderIn(BaseModel):
    full_name: str
    phone: str
    product: str
    price: Decimal
    status: Status = "pending"
    note: Optional[str] = ""
    photo_b64: Optional[str] = None
    client_id: str
    client_order_id: str

class OrderOut(BaseModel):
    id: int
    created_at: datetime
    full_name: str
    phone: str
    product: str
    price: Decimal
    status: Status
    note: str
    photo_path: Optional[str] = ""
    client_id: str
    client_order_id: str

    class Config:
        from_attributes = True


class RangeReportIn(BaseModel):
    start: str  # YYYY-MM-DD
    end: str    # YYYY-MM-DD
