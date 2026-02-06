import flet as ft

STATUS_OPTIONS = [
    ("paid", "Ödendi"),
    ("pending", "Bekliyor"),
    ("cancelled", "İptal"),
]

import requests
import uuid
import subprocess
import os
import webbrowser
import threading
import sys
import time
import shutil
import platform
from datetime import timedelta
from datetime import datetime

from local_db import init_db, add_order, list_orders, list_orders_filtered, pending_sync, mark_synced, count_unsynced, update_status_local, APP_DIR, DB_PATH
from sync import login, push_one

CLIENT_ID = str(uuid.uuid4())

STATUS_LABEL = {
    "pending": "Bekliyor",
    "paid": "Ödendi",
    "cancelled": "İptal",
}
LABEL_STATUS = {v: k for k, v in STATUS_LABEL.items()}

def main(page: ft.Page):

    # Windows paketinde FilePicker desteklenmeyebilir; güvenli fallback
    supports_file_picker = platform.system().lower() != "windows"
    file_picker = None
    if supports_file_picker:
        try:
            file_picker = ft.FilePicker()
            page.overlay.append(file_picker)
        except Exception:
            file_picker = None
            supports_file_picker = False

    page.title = "Canli Satis - Siparis"
    page.window_width = 1200
    page.window_height = 780
    page.window_resizable = True
    page.scroll = ft.ScrollMode.AUTO

    init_db()

    api_base = ft.TextField(
        label="API Base",
        value="http://51.195.25.69:8000",
        width=360,
        read_only=True,
    )
    email = ft.TextField(label="E-posta", value="admin@firma.com", width=240)
    password = ft.TextField(label="Şifre", value="123456", password=True, can_reveal_password=True, width=200)

    token_text = ft.Text("Bulut: Bağlı değil", color="red")
    unsynced_text = ft.Text("")
    token_holder = {"token": None}

    # Üst özet (server’dan)
    kpi_total = ft.Text("Günlük Satış: -", size=14, weight="bold")
    kpi_paid = ft.Text("Ödenen: -", size=14, weight="bold")
    kpi_pending = ft.Text("Bekleyen: -", size=14, weight="bold")
    kpi_cancel = ft.Text("İptal: -", size=14, weight="bold")

    full_name = ft.TextField(label="İsim Soyisim", width=260)
    phone = ft.TextField(label="Telefon (opsiyonel)", width=180)
    product = ft.TextField(label="Ürün", width=280)
    price = ft.TextField(label="Fiyat", width=140)

    status = ft.Dropdown(
        label="Durum",
        width=170,
        options=[
            ft.dropdown.Option("pending", "Bekliyor"),
            ft.dropdown.Option("paid", "Ödendi"),
            ft.dropdown.Option("cancelled", "İptal"),
        ],
        value="pending",
    )

    note = ft.TextField(label="Not", width=520)

    range_start = ft.TextField(label="Başlangıç (YYYY-AA-GG)", width=190)
    range_end = ft.TextField(label="Bitiş (YYYY-AA-GG)", width=190)

    # Görünüm / sıralama
    sort_dd = ft.Dropdown(
        label="Sıralama",
        width=190,
        options=[
            ft.dropdown.Option("date_desc", "Tarih (Yeni→Eski)"),
            ft.dropdown.Option("date_asc", "Tarih (Eski→Yeni)"),
            ft.dropdown.Option("name_asc", "İsim (A→Z)"),
            ft.dropdown.Option("name_desc", "İsim (Z→A)"),
        ],
        value="date_desc",
        on_change=lambda e: refresh_table(),
    )

    history_date = ft.TextField(label="Geçmiş Tarih (YYYY-AA-GG)", width=190, on_change=lambda e: refresh_table())
    search_text = ft.TextField(label="Ara (isim/ürün/telefon)", width=260, on_change=lambda e: refresh_table())

    # Takvim (DatePicker) - destek yoksa fallback manuel tarih
    date_picker = ft.DatePicker()
    page.overlay.append(date_picker)

    def _on_date_picked(e):
        if date_picker.value:
            history_date.value = date_picker.value.strftime("%Y-%m-%d")
            refresh_table()
            page.update()

    date_picker.on_change = _on_date_picked

    def open_calendar(e):
        try:
            date_picker.open = True
            page.update()
        except Exception:
            pass

    calendar_btn = ft.OutlinedButton("Takvim", on_click=open_calendar)

    def _set_history(days_ago: int):
        history_date.value = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        refresh_table()

    btn_today = ft.OutlinedButton("Bugün", on_click=lambda e: _set_history(0))
    btn_yesterday = ft.OutlinedButton("Dün", on_click=lambda e: _set_history(1))
    btn_10days = ft.OutlinedButton("10 Gün Önce", on_click=lambda e: _set_history(10))

    # Seçili kayıt için durum değiştirme
    selected_id = {"local_id": None}
    supports_row_select = platform.system().lower() != "windows"
    manual_id = ft.TextField(
        label="Kayıt ID (Windows)",
        width=140,
        visible=platform.system().lower() == "windows",
    )
    edit_status = ft.Dropdown(
        label="Seçili Kayıt Durumu",
        width=220,
        options=[
            ft.dropdown.Option("pending", "Bekliyor"),
            ft.dropdown.Option("paid", "Ödendi"),
            ft.dropdown.Option("cancelled", "İptal"),
        ],
        value="pending",
        disabled=False,
    )
    edit_btn = ft.ElevatedButton("Durumu Güncelle", disabled=False)

    table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("ID")),
            ft.DataColumn(ft.Text("İsim")),
            ft.DataColumn(ft.Text("Ürün")),
            ft.DataColumn(ft.Text("Fiyat")),
            ft.DataColumn(ft.Text("Telefon")),
            ft.DataColumn(ft.Text("Foto")),
            ft.DataColumn(ft.Text("Durum")),
            ft.DataColumn(ft.Text("Sync")),
            ft.DataColumn(ft.Text("Tarih")),
        ],
        rows=[],
    )

    def refresh_kpis():
        tok = token_holder["token"]
        if not tok:
            return
        try:
            r = requests.get(api_base.value.strip() + "/stats/today", headers={"Authorization": f"Bearer {tok}"}, timeout=10)
            s = r.json()
            kpi_total.value = f"Günlük Satış: {s.get('total','-')}"
            kpi_paid.value = f"Ödenen: {s.get('paid','-')}"
            kpi_pending.value = f"Bekleyen: {s.get('pending','-')}"
            kpi_cancel.value = f"İptal: {s.get('cancelled','-')}"
        except:
            pass
        page.update()

    
    def _apply_row_status(order_id: int, new_status: str):
        # 1) local db güncelle
        try:
            update_status_local(order_id, new_status)
        except Exception as ex:
            print("UPDATE_STATUS_ERR:", ex)
            return

        # 2) sunucuya yolla (varsa) + UI yenile
        try:
            try_sync()
            refresh_table()
            refresh_kpis()
        except Exception as ex:
            print("REFRESH_ERR:", ex)

    def refresh_table():
        def _photo_cell(path: str):
            if path:
                return ft.DataCell(ft.Image(src=path, width=60, height=40, fit="contain"))
            return ft.DataCell(ft.Text("-"))

        active_tab = tabs.selected_index if tabs else 0
        date_filter = None
        if active_tab == 0:
            date_filter = datetime.now().strftime("%Y-%m-%d")
        else:
            date_filter = (history_date.value or "").strip() or None

        rows = list_orders_filtered(300, date_filter, sort_dd.value, (search_text.value or "").strip())
        table.rows.clear()

        def on_row_select(local_id, st):
            def _inner(e):
                selected_id["local_id"] = local_id
                edit_status.value = st
                edit_btn.disabled = False
                page.update()
            return _inner

        for r in rows:
            st = r["status"]
            cells = [
                ft.DataCell(ft.Text(str(r["id"]))),
                ft.DataCell(ft.Text(r["full_name"])),
                ft.DataCell(ft.Text(r["product"])),
                ft.DataCell(ft.Text(f"{r['price']:.2f}")),
                ft.DataCell(ft.Text(r["phone"] or "")),
                _photo_cell(r.get("photo_path") or ""),
                ft.DataCell(ft.Text(STATUS_LABEL.get(st, st))),
                ft.DataCell(ft.Text("✅" if r["synced"] else "⏳")),
                ft.DataCell(ft.Text(r["created_at"])),
            ]
            if supports_row_select:
                row = ft.DataRow(on_select_changed=on_row_select(r["id"], st), cells=cells)
            else:
                row = ft.DataRow(cells=cells)
            table.rows.append(row)

        uns = count_unsynced()
        unsynced_text.value = f"Bekleyen senkron: {uns}"
        unsynced_text.color = "green" if uns == 0 else "orange"
        page.update()

    def do_login(e):
        try:
            tok = login(api_base.value.strip(), email.value.strip(), password.value)
            token_holder["token"] = tok
            token_text.value = "Bulut: Bağlı ✅"
            token_text.color = "green"
            refresh_kpis()
        except:
            token_holder["token"] = None
            token_text.value = "Bulut: Bağlanamadı"
            token_text.color = "red"
        refresh_table()

    def try_sync():
        tok = token_holder["token"]
        if not tok:
            return
        for r in pending_sync():
            try:
                push_one(api_base.value.strip(), tok, r)
                mark_synced(r["id"])
            except:
                break

    def backup_db():
        try:
            bdir = APP_DIR / "backups"
            bdir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            shutil.copy2(DB_PATH, bdir / f"local_data_{stamp}.db")
        except:
            pass

    def background_loop():
        # 60 sn’de bir: yedek + sync + kpi güncelle
        while True:
            time.sleep(60)
            backup_db()
            try_sync()
            refresh_kpis()
            refresh_table()

    def save_order(e):
        if not full_name.value or not product.value or not price.value:
            page.snack_bar = ft.SnackBar(ft.Text("İsim, ürün ve fiyat zorunlu."), open=True)
            page.update()
            return

        saved_photo = ""
        if photo_path.value:
            try:
                img_dir = APP_DIR / "images"
                img_dir.mkdir(parents=True, exist_ok=True)
                ext = os.path.splitext(photo_path.value)[1] or ".jpg"
                saved_photo = str(img_dir / f"{uuid.uuid4()}{ext}")
                shutil.copy2(photo_path.value, saved_photo)
            except Exception as ex:
                print("PHOTO_SAVE_ERR:", ex)

        add_order(
            {
                "full_name": full_name.value.strip(),
                "phone": (phone.value or "").strip(),
                "product": product.value.strip(),
                "price": float(price.value.replace(",", ".")),
                "status": status.value,
                "note": note.value.strip(),
                "photo_path": saved_photo,
                "client_id": CLIENT_ID,
                "client_order_id": str(uuid.uuid4()),
            }
        )

        full_name.value = ""
        phone.value = ""
        product.value = ""
        price.value = ""
        status.value = "pending"
        note.value = ""
        photo_path.value = ""
        photo_preview.src = None
        photo_preview.visible = False

        try_sync()
        refresh_kpis()
        refresh_table()

    def update_selected_status(e):
        lid = selected_id["local_id"]
        if not lid and manual_id.visible:
            try:
                lid = int((manual_id.value or "").strip())
            except Exception:
                lid = None
        if not lid:
            return
        new_status = edit_status.value
        update_status_local(lid, new_status)   # local değiş
        try_sync()                             # server’a anında yolla (upsert)
        refresh_kpis()
        refresh_table()

    def run_report(path):
        # Raporu API üzerinden aç (uzak sunucu için güvenli)
        try:
            base = api_base.value.strip().rstrip("/")
            url = f"{base}/report-files/{path.lstrip('/')}"
            webbrowser.open(url)
        except Exception as ex:
            print("OPEN_REPORT_ERR:", ex)

    def report_daily(e):
        tok = token_holder["token"]
        if not tok:
            return
        r = requests.post(api_base.value.strip() + "/reports/daily", headers={"Authorization": f"Bearer {tok}"}, timeout=20)
        j = r.json()
        page.snack_bar = ft.SnackBar(ft.Text(f"PDF hazır: {j['pdf']} | Adet:{j['count']} | Toplam:{j['total']}"), open=True)
        page.update()
        run_report(j["pdf"])

    def report_weekly(e):
        tok = token_holder["token"]
        if not tok:
            return
        r = requests.post(api_base.value.strip() + "/reports/weekly", headers={"Authorization": f"Bearer {tok}"}, timeout=30)
        if r.status_code != 200:
            try:
                msg = r.json().get("detail", "Hata")
            except Exception:
                msg = "Hata"
            page.snack_bar = ft.SnackBar(ft.Text(f"Rapor alınamadı: {msg}"), open=True)
            page.update()
            return
        j = r.json()
        page.snack_bar = ft.SnackBar(ft.Text(f"Haftalık PDF: {j['pdf']} | {j['start']} - {j['end']}"), open=True)
        page.update()
        run_report(j["pdf"])

    def report_monthly(e):
        tok = token_holder["token"]
        if not tok:
            return
        r = requests.post(api_base.value.strip() + "/reports/monthly", headers={"Authorization": f"Bearer {tok}"}, timeout=30)
        if r.status_code != 200:
            try:
                msg = r.json().get("detail", "Hata")
            except Exception:
                msg = "Hata"
            page.snack_bar = ft.SnackBar(ft.Text(f"Rapor alınamadı: {msg}"), open=True)
            page.update()
            return
        j = r.json()
        page.snack_bar = ft.SnackBar(ft.Text(f"Aylık PDF: {j['pdf']} | {j['start']} - {j['end']}"), open=True)
        page.update()
        run_report(j["pdf"])

    def report_range(e):
        tok = token_holder["token"]
        if not tok:
            return
        payload = {"start": range_start.value.strip(), "end": range_end.value.strip()}
        r = requests.post(api_base.value.strip() + "/reports/range", json=payload, headers={"Authorization": f"Bearer {tok}"}, timeout=30)
        if r.status_code != 200:
            try:
                msg = r.json().get("detail", "Hata")
            except Exception:
                msg = "Hata"
            page.snack_bar = ft.SnackBar(ft.Text(f"Rapor alınamadı: {msg}"), open=True)
            page.update()
            return
        j = r.json()
        page.snack_bar = ft.SnackBar(ft.Text(f"Tarih Aralığı PDF: {j['pdf']} | {j['start']} - {j['end']}"), open=True)
        page.update()
        run_report(j["pdf"])

    login_btn = ft.ElevatedButton("Buluta Bağlan", on_click=do_login)
    photo_path = ft.Text("")
    photo_preview = ft.Image(src="", width=220, height=140, fit="contain", visible=False)
    def pick_photo(e):
        if file_picker:
            file_picker.pick_files(allow_multiple=False)
            return
        # Windows fallback: tkinter file dialog
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            try:
                root.attributes("-topmost", True)
                root.lift()
                root.focus_force()
                root.update()
            except Exception:
                pass
            path = filedialog.askopenfilename(
                parent=root,
                title="Fotoğraf Seç",
                filetypes=[("Image files", "*.png;*.jpg;*.jpeg;*.webp;*.bmp"), ("All files", "*.*")]
            )
            root.destroy()
            if path:
                photo_path.value = path
                photo_preview.src = path
                photo_preview.visible = True
                page.update()
        except Exception as ex:
            print("TK_FILEPICKER_ERR:", ex)

    def _on_photo_result(e):
        if e.files:
            path = e.files[0].path
            photo_path.value = path
            photo_preview.src = path
            photo_preview.visible = True
        else:
            photo_path.value = ""
            photo_preview.src = None
            photo_preview.visible = False
        page.update()

    if file_picker:
        file_picker.on_result = _on_photo_result

    photo_btn = ft.OutlinedButton("Foto Seç", on_click=pick_photo)

    save_btn = ft.ElevatedButton("Kaydet", on_click=save_order)
    sync_btn = ft.OutlinedButton("Senkronla", on_click=lambda e: (try_sync(), refresh_kpis(), refresh_table()))
    edit_btn.on_click = update_selected_status

    daily_btn = ft.OutlinedButton("Günlük PDF", on_click=report_daily)
    weekly_btn = ft.OutlinedButton("Haftalık PDF", on_click=report_weekly)
    monthly_btn = ft.OutlinedButton("Aylık PDF", on_click=report_monthly)
    range_btn = ft.OutlinedButton("Aralık PDF", on_click=report_range)

    tabs = ft.Tabs(
        selected_index=0,
        tabs=[
            ft.Tab(text="Bugün"),
            ft.Tab(text="Geçmiş"),
        ],
        on_change=lambda e: refresh_table(),
    )

    page.add(
        ft.Row([api_base, email, password, login_btn, token_text], wrap=True),
        ft.Row([kpi_total, kpi_paid, kpi_pending, kpi_cancel], wrap=True),
        ft.Row([unsynced_text, sync_btn, daily_btn, weekly_btn, monthly_btn], wrap=True),
        ft.Row([range_start, range_end, range_btn], wrap=True),
        ft.Divider(),
        ft.Row([full_name, phone, product, price, status, photo_btn, save_btn], wrap=True),
        photo_path,
        ft.Row([note], wrap=True),
        photo_preview,
        ft.Divider(),
        ft.Text("Son Kayıtlar"),
        tabs,
        ft.Row([sort_dd, search_text], wrap=True),
        ft.Row([history_date, calendar_btn, btn_today, btn_yesterday, btn_10days], wrap=True),
        ft.Row([ft.Text("Seçili Kayıt Durumu:"), edit_status, edit_btn, manual_id], wrap=True),
        ft.Container(table, expand=True),
    )

    refresh_table()

    # background loop
    t = threading.Thread(target=background_loop, daemon=True)
    t.start()

ft.app(target=main)
