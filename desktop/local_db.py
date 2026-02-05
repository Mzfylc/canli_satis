import sqlite3
from pathlib import Path
from datetime import datetime
import os

APP_DIR = Path.home() / "Library" / "Application Support" / "CanliSatis"
APP_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = APP_DIR / "local_data.db"

def _connect():
    return sqlite3.connect(DB_PATH)

def init_db():
    with sqlite3.connect(DB_PATH) as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            full_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            product TEXT NOT NULL,
            price REAL NOT NULL,
            status TEXT NOT NULL,
            note TEXT,
            photo_path TEXT,
            client_id TEXT NOT NULL,
            client_order_id TEXT NOT NULL,
            synced INTEGER NOT NULL DEFAULT 0
        )
        """)
        cols = [r[1] for r in con.execute("PRAGMA table_info(orders)").fetchall()]
        if "photo_path" not in cols:
            con.execute("ALTER TABLE orders ADD COLUMN photo_path TEXT")
        con.commit()

def add_order(row: dict):
    with sqlite3.connect(DB_PATH) as con:
        con.execute("""
        INSERT INTO orders(created_at, full_name, phone, product, price, status, note, photo_path, client_id, client_order_id, synced)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """, (
            datetime.now().isoformat(timespec="seconds"),
            row["full_name"], row["phone"], row["product"],
            float(row["price"]), row["status"], row.get("note",""),
            row.get("photo_path",""),
            row["client_id"], row["client_order_id"]
        ))
        con.commit()

def list_orders(limit=200):
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute("SELECT * FROM orders ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

def pending_sync():
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute("SELECT * FROM orders WHERE synced=0 ORDER BY id ASC").fetchall()
        return [dict(r) for r in rows]

def mark_synced(local_id: int):
    with sqlite3.connect(DB_PATH) as con:
        con.execute("UPDATE orders SET synced=1 WHERE id=?", (local_id,))
        con.commit()

def count_unsynced() -> int:
    with sqlite3.connect(DB_PATH) as con:
        (n,) = con.execute("SELECT COUNT(*) FROM orders WHERE synced=0").fetchone()
        return int(n)


def update_status_local(local_id: int, status: str):
    with sqlite3.connect(DB_PATH) as con:
        con.execute("UPDATE orders SET status=?, synced=0 WHERE id=?", (status, local_id))
        con.commit()


def update_status(order_id: int, status: str):
    con = _connect()
    try:
        con.execute("UPDATE orders SET status=?, synced=0 WHERE id=?", (status, order_id))
        con.commit()
    finally:
        con.close()


def mark_unsynced(order_id: int):
    con = _connect()
    try:
        con.execute("UPDATE orders SET synced=0 WHERE id=?", (order_id,))
        con.commit()
    finally:
        con.close()
