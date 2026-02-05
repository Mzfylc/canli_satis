import requests
import base64
import os

def login(api_base: str, email: str, password: str) -> str:
    r = requests.post(f"{api_base}/auth/login", json={"email": email, "password": password}, timeout=10)
    r.raise_for_status()
    return r.json()["access_token"]

def push_one(api_base: str, token: str, order: dict):
    headers = {"Authorization": f"Bearer {token}"}
    photo_b64 = None
    photo_path = order.get("photo_path") or ""
    if photo_path and os.path.exists(photo_path):
        try:
            with open(photo_path, "rb") as f:
                photo_b64 = base64.b64encode(f.read()).decode("utf-8")
        except Exception:
            photo_b64 = None
    payload = {
        "full_name": order["full_name"],
        "phone": order["phone"],
        "product": order["product"],
        "price": order["price"],
        "status": order["status"],
        "note": order.get("note",""),
        "photo_b64": photo_b64,
        "client_id": order["client_id"],
        "client_order_id": order["client_order_id"],
    }
    r = requests.post(f"{api_base}/orders/sync", json=payload, headers=headers, timeout=10)
    r.raise_for_status()
    return r.json()
