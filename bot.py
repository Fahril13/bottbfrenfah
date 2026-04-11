#!/usr/bin/env python3
"""
TabunganBot 💰 + SNBT + Groq AI + Cross Messaging (mutual permission)
Google Sheets | Streak | Custom Reminder | Pesan Antar User
Untuk: Fahril & Freya
"""

import os
import asyncio
import logging
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo

import gspread
from google.oauth2.service_account import Credentials
from groq import Groq

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, filters, ContextTypes
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ═══════════════════════════════════════════════════════════════
#  KONFIGURASI
# ═══════════════════════════════════════════════════════════════
BOT_TOKEN        = os.getenv("BOT_TOKEN",        "GANTI_TOKEN_BOT")
SPREADSHEET_ID   = os.getenv("SPREADSHEET_ID",   "GANTI_ID_SPREADSHEET")
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE", "credentials.json")
GROQ_API_KEY     = os.getenv("GROQ_API_KEY",     "GANTI_GROQ_API_KEY")

USERS: dict[str, int] = {
    "Fahril": 5210728658,
    "Freya" : 6434745020,
}
FREYA_ID  = USERS["Freya"]
FAHRIL_ID = USERS["Fahril"]

REPORT_WEEKDAY = 0
REPORT_HOUR    = 8
REPORT_MINUTE  = 0
WIB  = ZoneInfo("Asia/Jakarta")
WITA = ZoneInfo("Asia/Makassar")

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

# Conversation states — keuangan
ASK_AMOUNT, ASK_CAT, ASK_DESC = range(3)
# Conversation states — custom reminder
REM_NAMA, REM_HARI, REM_JAM, REM_PESAN = range(10, 14)

CATS_IN = [
    "💰 Gaji/Pendapatan", "🎁 Bonus",
    "↩️ Transfer Masuk",  "📈 Investasi/Return",
    "💸 Nabung Rutin",    "📦 Lainnya"
]
CATS_OUT = [
    "🍜 Makan & Minum",    "🚗 Transport",
    "🛍️ Belanja",          "🎮 Hiburan",
    "📱 Tagihan/Langganan", "🏥 Kesehatan",
    "📚 Pendidikan",        "🏠 Rumah/Kos",
    "📦 Lainnya"
]

# ═══════════════════════════════════════════════════════════════
#  JADWAL BIMBEL SNBT
# ═══════════════════════════════════════════════════════════════
BIMBEL_END_DATE = date(2026, 4, 18)

JADWAL_KELAS: dict[str, dict] = {
    "2026-04-07": {"subtes": "PK",  "tutor": "Kak Sugeng",                 "jam": "19.30–21.30 WIB", "tipe": "Kelas Utama"},
    "2026-04-08": {"subtes": "PM",  "tutor": "Kak Nisa",                   "jam": "19.30–21.30 WIB", "tipe": "Kelas Utama"},
    "2026-04-09": {"subtes": "PK",  "tutor": "Kak Sugeng",                 "jam": "19.30–21.30 WIB", "tipe": "Kelas Utama"},
    "2026-04-10": {"subtes": "LBI", "tutor": "Tutor Kampung Inggris Pare", "jam": "19.30–21.30 WIB", "tipe": "Bonus"},
    "2026-04-11": {"subtes": "PM",  "tutor": "Guru PNS",                   "jam": "15.30–17.30 WIB", "tipe": "Bonus",
                   "extra": {"subtes": "LBI", "tutor": "Tutor S2 Luar Negeri", "jam": "19.30–21.30 WIB", "tipe": "Bonus"}},
    "2026-04-12": {"subtes": "PM",  "tutor": "Kak Nisa",                   "jam": "19.30–21.30 WIB", "tipe": "Kelas Utama"},
    "2026-04-13": {"subtes": "PK",  "tutor": "Kak Sugeng",                 "jam": "19.30–21.30 WIB", "tipe": "Kelas Utama"},
    "2026-04-14": {"subtes": "PM",  "tutor": "Kak Nisa",                   "jam": "19.30–21.30 WIB", "tipe": "Kelas Utama"},
    "2026-04-15": {"subtes": "PK",  "tutor": "Kak Sugeng",                 "jam": "19.30–21.30 WIB", "tipe": "Kelas Utama"},
    "2026-04-16": {"subtes": "PM",  "tutor": "Kak Nisa",                   "jam": "19.30–21.30 WIB", "tipe": "Kelas Utama"},
    "2026-04-17": {"subtes": "PM",  "tutor": "Mini Tryout",                "jam": "19.30–20.30 WIB", "tipe": "Mini Tryout"},
    "2026-04-18": {"subtes": "PK",  "tutor": "Mini Tryout",                "jam": "19.30–20.30 WIB", "tipe": "Mini Tryout"},
}

SUBTES_MANDIRI = [
    {"kode": "PU",  "nama": "Penalaran Umum",           "emoji": "🧠", "tips": "Latihan soal inferensi, analogi, silogisme & penalaran logis. Minimal 20 soal per sesi!"},
    {"kode": "PK",  "nama": "Pengetahuan & Pemahaman Umum", "emoji": "📚", "tips": "Review materi dari kelas Kak Sugeng, buat rangkuman, kerjain soal latihan!"},
    {"kode": "PM",  "nama": "Penalaran Matematika",      "emoji": "🔢", "tips": "Review materi Kak Nisa, latihan soal numerasi & aljabar dasar!"},
    {"kode": "PBM", "nama": "Literasi Bahasa Indonesia", "emoji": "📖", "tips": "Baca teks lalu latihan soal pemahaman bacaan, penalaran & menyimpulkan isi!"},
    {"kode": "LBI", "nama": "Literasi Bahasa Inggris",  "emoji": "🇬🇧", "tips": "Reading comprehension, vocabulary in context, dan soal inferensi teks bahasa Inggris!"},
]
_MANDIRI_CYCLE = ["PU", "PBM", "LBI", "PK", "PM"]

def _get_subtes_mandiri(tanggal: date) -> dict:
    kode = _MANDIRI_CYCLE[tanggal.toordinal() % len(_MANDIRI_CYCLE)]
    return next(s for s in SUBTES_MANDIRI if s["kode"] == kode)

def _is_bimbel_active() -> bool:
    return date.today() <= BIMBEL_END_DATE

# ═══════════════════════════════════════════════════════════════
#  STREAK CONFIG
# ═══════════════════════════════════════════════════════════════
STREAK_MILESTONES = [3, 7, 14, 21, 30, 60, 90, 100, 150, 200, 365]

def streak_badge(n: int) -> str:
    if n >= 365: return "🚀"
    if n >= 200: return "💎"
    if n >= 100: return "👑"
    if n >=  90: return "🌟"
    if n >=  60: return "🏆"
    if n >=  30: return "⚡"
    if n >=  21: return "💪"
    if n >=  14: return "🔥"
    if n >=   7: return "✨"
    if n >=   3: return "🌱"
    return "🐣"

def streak_title(n: int) -> str:
    if n >= 365: return "GOAT Nabung 🐐"
    if n >= 200: return "Diamond Saver 💎"
    if n >= 100: return "Rajin Banget 👑"
    if n >=  90: return "Nyaris 3 Bulan 🌟"
    if n >=  60: return "2 Bulan Konsisten 🏆"
    if n >=  30: return "1 Bulan Penuh ⚡"
    if n >=  21: return "3 Minggu Kuat 💪"
    if n >=  14: return "2 Minggu Mantap 🔥"
    if n >=   7: return "1 Minggu Semangat ✨"
    if n >=   3: return "Mulai Tumbuh 🌱"
    return "Hari Pertama 🐣"

# ═══════════════════════════════════════════════════════════════
#  GOOGLE SHEETS
# ═══════════════════════════════════════════════════════════════
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

def _get_client() -> gspread.Client:
    gc_env = os.getenv("GOOGLE_CREDENTIALS")
    if gc_env:
        import json
        creds = Credentials.from_service_account_info(json.loads(gc_env), scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    return gspread.authorize(creds)

def _get_or_create_sheet(ss, title: str, headers: list[str]):
    try:
        return ss.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = ss.add_worksheet(title=title, rows=5000, cols=len(headers))
        ws.append_row(headers, value_input_option="USER_ENTERED")
        return ws

def init_sheets():
    client = _get_client()
    ss     = client.open_by_key(SPREADSHEET_ID)
    _get_or_create_sheet(ss, "Transaksi", ["ID","UserID","Nama","Tipe","Jumlah","Kategori","Catatan","Waktu"])
    _get_or_create_sheet(ss, "Tujuan",    ["ID","UserID","Judul","Target","Terkumpul","Selesai","Waktu"])
    _get_or_create_sheet(ss, "Catatan",   ["ID","UserID","Isi","Waktu"])
    _get_or_create_sheet(ss, "Streak",    ["UserID","CurrentStreak","LongestStreak","LastDate"])
    _get_or_create_sheet(ss, "Pengingat", ["ID","UserID","Nama","Hari","Jam","Pesan","Aktif","Dibuat"])
    _get_or_create_sheet(ss, "IzinPesan", [
        # Aktif: "Ya"/"Tidak"
        # Terakhir update waktu izin
        "UserID","Nama","Aktif","UpdatedAt"
    ])
    log.info("✅ Google Sheets siap.")

def _ss():
    return _get_client().open_by_key(SPREADSHEET_ID)

def _now() -> str:
    return datetime.now(WIB).strftime("%Y-%m-%d %H:%M:%S")

def _today_wita() -> str:
    return datetime.now(WITA).strftime("%Y-%m-%d")

def _yesterday_wita() -> str:
    return (datetime.now(WITA) - timedelta(days=1)).strftime("%Y-%m-%d")

def _next_id(ws) -> int:
    rows = ws.get_all_values()
    if len(rows) <= 1: return 1
    last = rows[-1][0]
    return int(last) + 1 if str(last).isdigit() else 1

# ─── Transaksi ──────────────────────────────────────────────────
def db_add_transaction(uid, name, kind, amount, category, note):
    ws = _ss().worksheet("Transaksi")
    ws.append_row([_next_id(ws), uid, name, kind, amount, category, note, _now()],
                  value_input_option="USER_ENTERED")

def db_get_transactions(uid: int, since_days: int | None = None, limit: int = 100):
    rows = _ss().worksheet("Transaksi").get_all_records()
    result = [r for r in rows if str(r["UserID"]) == str(uid)]
    if since_days is not None:
        cutoff = (datetime.now(WIB) - timedelta(days=since_days)).strftime("%Y-%m-%d %H:%M:%S")
        result = [r for r in result if str(r["Waktu"]) >= cutoff]
    result.sort(key=lambda r: r["Waktu"], reverse=True)
    return result[:limit]

def db_get_balance(uid: int) -> float:
    return sum((float(r["Jumlah"]) if r["Tipe"] == "income" else -float(r["Jumlah"]))
               for r in db_get_transactions(uid))

def db_get_summary(uid: int, since_days: int = 7):
    rows = db_get_transactions(uid, since_days=since_days)
    inc = sum(float(r["Jumlah"]) for r in rows if r["Tipe"] == "income")
    exp = sum(float(r["Jumlah"]) for r in rows if r["Tipe"] == "expense")
    return inc, exp, rows

def db_delete_last_transaction(uid: int) -> bool:
    ws = _ss().worksheet("Transaksi")
    vals = ws.get_all_values()
    for i in range(len(vals) - 1, 0, -1):
        if str(vals[i][1]) == str(uid):
            ws.delete_rows(i + 1); return True
    return False

def db_get_monthly_cats(uid: int):
    m    = datetime.now(WIB).strftime("%Y-%m")
    rows = [r for r in db_get_transactions(uid) if str(r["Waktu"]).startswith(m)]
    cats: dict[tuple, float] = {}
    for r in rows:
        key = (r["Kategori"], r["Tipe"])
        cats[key] = cats.get(key, 0) + float(r["Jumlah"])
    return [(k[0], k[1], v) for k, v in sorted(cats.items(), key=lambda x: -x[1])]

def db_has_transaction_today(uid: int) -> bool:
    today = _today_wita()
    for r in _ss().worksheet("Transaksi").get_all_records():
        if str(r["UserID"]) == str(uid) and str(r["Waktu"]).startswith(today):
            return True
    return False

# ─── Tujuan ─────────────────────────────────────────────────────
def db_get_goals(uid: int):
    return [r for r in _ss().worksheet("Tujuan").get_all_records()
            if str(r["UserID"]) == str(uid)]

def db_add_goal(uid, title, target):
    ws = _ss().worksheet("Tujuan")
    ws.append_row([_next_id(ws), uid, title, target, 0, "Tidak", _now()],
                  value_input_option="USER_ENTERED")

def db_update_goal(goal_id: int, amount: float):
    ws = _ss().worksheet("Tujuan")
    for i, row in enumerate(ws.get_all_values()[1:], start=2):
        if str(row[0]) == str(goal_id):
            new_saved = float(row[4]) + amount
            ws.update_cell(i, 5, new_saved)
            if new_saved >= float(row[3]):
                ws.update_cell(i, 6, "Ya")
            return float(row[3]), new_saved
    return None, None

# ─── Catatan ────────────────────────────────────────────────────
def db_add_note(uid, content):
    ws = _ss().worksheet("Catatan")
    ws.append_row([_next_id(ws), uid, content, _now()], value_input_option="USER_ENTERED")

def db_get_notes(uid: int):
    rows = _ss().worksheet("Catatan").get_all_records()
    return sorted([r for r in rows if str(r["UserID"]) == str(uid)],
                  key=lambda r: r["Waktu"], reverse=True)[:10]

# ─── Streak ─────────────────────────────────────────────────────
def db_get_streak(uid: int) -> dict:
    for r in _ss().worksheet("Streak").get_all_records():
        if str(r["UserID"]) == str(uid):
            return {"current": int(r["CurrentStreak"] or 0),
                    "longest": int(r["LongestStreak"] or 0),
                    "last_date": str(r["LastDate"] or "")}
    return {"current": 0, "longest": 0, "last_date": ""}

def db_update_streak(uid: int) -> dict:
    ws = _ss().worksheet("Streak")
    all_vals = ws.get_all_values()
    today = _today_wita(); yesterday = _yesterday_wita()
    row_idx = None; current = longest = 0; last_date = ""
    for i, row in enumerate(all_vals[1:], start=2):
        if str(row[0]) == str(uid):
            row_idx = i; current = int(row[1] or 0)
            longest = int(row[2] or 0); last_date = str(row[3] or ""); break
    milestone_hit = None
    if last_date == today:   pass
    elif last_date == yesterday: current += 1
    else: current = 1
    longest = max(longest, current)
    if current in STREAK_MILESTONES: milestone_hit = current
    if row_idx: ws.update(f"B{row_idx}:D{row_idx}", [[current, longest, today]])
    else: ws.append_row([uid, current, longest, today], value_input_option="USER_ENTERED")
    return {"current": current, "longest": longest,
            "last_date": today, "milestone_hit": milestone_hit}

def db_check_streak_broken(uid: int) -> int:
    data = db_get_streak(uid)
    if data["current"] == 0 or not data["last_date"]: return 0
    if data["last_date"] not in (_today_wita(), _yesterday_wita()): return data["current"]
    return 0

# ─── Custom Pengingat ────────────────────────────────────────────
HARI_MAP = {
    "senin": 0, "selasa": 1, "rabu": 2, "kamis": 3,
    "jumat": 4, "sabtu": 5, "minggu": 6, "setiap hari": -1,
}

def db_add_pengingat(uid: int, nama: str, hari: str, jam: str, pesan: str) -> int:
    ws  = _ss().worksheet("Pengingat")
    nid = _next_id(ws)
    ws.append_row([nid, uid, nama, hari, jam, pesan, "Ya", _now()],
                  value_input_option="USER_ENTERED")
    return nid

def db_get_pengingat(uid: int, aktif_only: bool = True) -> list[dict]:
    rows = _ss().worksheet("Pengingat").get_all_records()
    result = [r for r in rows if str(r["UserID"]) == str(uid)]
    if aktif_only: result = [r for r in result if str(r["Aktif"]) == "Ya"]
    return result

def db_get_all_pengingat_aktif() -> list[dict]:
    return [r for r in _ss().worksheet("Pengingat").get_all_records()
            if str(r["Aktif"]) == "Ya"]

def db_toggle_pengingat(pid: int, aktif: bool) -> bool:
    ws = _ss().worksheet("Pengingat")
    for i, row in enumerate(ws.get_all_values()[1:], start=2):
        if str(row[0]) == str(pid):
            ws.update_cell(i, 7, "Ya" if aktif else "Tidak"); return True
    return False

def db_delete_pengingat(pid: int) -> bool:
    ws = _ss().worksheet("Pengingat")
    for i, row in enumerate(ws.get_all_values()[1:], start=2):
        if str(row[0]) == str(pid):
            ws.delete_rows(i + 1); return True
    return False

def _should_fire_pengingat(row: dict, now_wita: datetime) -> bool:
    try:
        h, m = map(int, str(row["Jam"]).split(":"))
        if now_wita.hour != h or now_wita.minute != m: return False
        hari_raw = str(row["Hari"]).lower().strip()
        if hari_raw.count("-") == 2:
            return now_wita.strftime("%Y-%m-%d") == hari_raw
        if hari_raw == "setiap hari": return True
        return now_wita.weekday() in [HARI_MAP.get(h.strip(), -99) for h in hari_raw.split(",")]
    except: return False

# ─── Izin Pesan ─────────────────────────────────────────────────
def db_get_izin_pesan(uid: int) -> bool:
    """Return True kalau user sudah mengaktifkan izin terima pesan."""
    ws = _ss().worksheet("IzinPesan")
    for r in ws.get_all_records():
        if str(r["UserID"]) == str(uid):
            return str(r["Aktif"]) == "Ya"
    return False

def db_set_izin_pesan(uid: int, nama: str, aktif: bool):
    ws = _ss().worksheet("IzinPesan")
    all_vals = ws.get_all_values()
    for i, row in enumerate(all_vals[1:], start=2):
        if str(row[0]) == str(uid):
            ws.update(f"C{i}:D{i}", [["Ya" if aktif else "Tidak", _now()]])
            return
    ws.append_row([uid, nama, "Ya" if aktif else "Tidak", _now()],
                  value_input_option="USER_ENTERED")

def db_get_izin_status_all() -> dict[int, bool]:
    """Return {uid: aktif} untuk semua user."""
    ws = _ss().worksheet("IzinPesan")
    result = {}
    for r in ws.get_all_records():
        uid = int(r["UserID"]) if str(r["UserID"]).isdigit() else 0
        result[uid] = str(r["Aktif"]) == "Ya"
    return result

def _both_permitted() -> tuple[bool, bool]:
    """Return (fahril_izin, freya_izin)."""
    status = db_get_izin_status_all()
    return status.get(FAHRIL_ID, False), status.get(FREYA_ID, False)

def _get_partner_uid(uid: int) -> int | None:
    """Return UID partner dari user yang sedang chat."""
    for name, i in USERS.items():
        if i != uid and i != 0:
            return i
    return None

def _get_partner_name(uid: int) -> str | None:
    partner_uid = _get_partner_uid(uid)
    return get_user_name(partner_uid) if partner_uid else None

# ─── Async wrapper ───────────────────────────────────────────────
async def run(func, *args):
    return await asyncio.to_thread(func, *args)

# ═══════════════════════════════════════════════════════════════
#  HELPERS UI
# ═══════════════════════════════════════════════════════════════
def rp(n: float) -> str:
    return f"Rp {int(n):,}".replace(",", ".")

def progress_bar(pct: float, width=12) -> str:
    filled = round(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)

def streak_bar(n: int, width=10) -> str:
    filled = min(width, round(n / 30 * width))
    return "🔥" * filled + "⬜" * (width - filled)

def kb_grid(items, cols=2) -> InlineKeyboardMarkup:
    rows = [items[i:i+cols] for i in range(0, len(items), cols)]
    return InlineKeyboardMarkup([[InlineKeyboardButton(t, callback_data=t) for t in r] for r in rows])

def get_user_name(uid: int) -> str | None:
    return next((n for n, i in USERS.items() if i == uid), None)

def authorized(uid: int) -> bool:
    return uid in USERS.values() and uid != 0

async def check_auth(u: Update) -> bool:
    if not authorized(u.effective_user.id):
        await u.message.reply_text("⛔ *Akses ditolak!*", parse_mode="Markdown")
        return False
    return True

def _streak_summary(data: dict) -> str:
    cur = data["current"]
    return (f"{streak_badge(cur)} *Streak: {cur} hari* — _{streak_title(cur)}_\n"
            f"`{streak_bar(cur)}`\n🏅 Terpanjang: *{data['longest']} hari*")

# ═══════════════════════════════════════════════════════════════
#  IZIN PESAN — COMMANDS
# ═══════════════════════════════════════════════════════════════
async def cmd_izinkan_pesan(u: Update, _):
    """Aktifkan izin terima pesan dari partner."""
    if not await check_auth(u): return
    uid  = u.effective_user.id
    name = get_user_name(uid)
    partner_name = _get_partner_name(uid)

    wait = await u.message.reply_text("⏳ Menyimpan izin...")
    await run(db_set_izin_pesan, uid, name, True)
    fahril_ok, freya_ok = await run(_both_permitted)
    await wait.delete()

    if fahril_ok and freya_ok:
        await u.message.reply_text(
            f"✅ *Izin Pesan Aktif!*\n\n"
            f"Kamu dan *{partner_name}* sudah saling mengizinkan 🎉\n\n"
            f"Sekarang bisa kirim pesan ke *{partner_name}* lewat:\n"
            f"`/pesan [teks pesan]`\n\n"
            f"Atau bilang ke AI: _\"kasih tau {partner_name} ...\"_",
            parse_mode="Markdown"
        )
    else:
        who_left = partner_name if (uid == FAHRIL_ID and not freya_ok) or (uid == FREYA_ID and not fahril_ok) else name
        await u.message.reply_text(
            f"✅ *Kamu sudah mengizinkan!*\n\n"
            f"Menunggu *{who_left}* juga aktifkan izin pesan.\n"
            f"Minta dia ketik `/izinkanpesan` di botnya ya~\n\n"
            f"_Fitur pesan baru aktif setelah keduanya mengizinkan._",
            parse_mode="Markdown"
        )

async def cmd_tolak_pesan(u: Update, _):
    """Matikan izin terima pesan dari partner."""
    if not await check_auth(u): return
    uid  = u.effective_user.id
    name = get_user_name(uid)
    wait = await u.message.reply_text("⏳ Menyimpan...")
    await run(db_set_izin_pesan, uid, name, False)
    await wait.delete()
    await u.message.reply_text(
        "🔕 *Izin pesan dimatikan.*\n\n"
        "Kamu tidak akan menerima pesan dari partner bot.\n"
        "Aktifkan lagi kapanpun dengan /izinkanpesan",
        parse_mode="Markdown"
    )

async def cmd_status_pesan(u: Update, _):
    """Lihat status izin pesan kedua user."""
    if not await check_auth(u): return
    wait = await u.message.reply_text("⏳ Mengecek status...")
    fahril_ok, freya_ok = await run(_both_permitted)
    await wait.delete()
    def icon(ok): return "🟢 Aktif" if ok else "🔴 Belum aktif"
    fitur_aktif = fahril_ok and freya_ok
    await u.message.reply_text(
        f"📡 *Status Fitur Pesan*\n\n"
        f"👤 Fahril : {icon(fahril_ok)}\n"
        f"👤 Freya  : {icon(freya_ok)}\n\n"
        f"{'✅ Fitur pesan *AKTIF* — bisa saling kirim pesan!' if fitur_aktif else '⏳ Fitur pesan belum aktif — keduanya harus /izinkanpesan'}\n\n"
        f"Aktifkan : /izinkanpesan\n"
        f"Matikan  : /tolakpesan",
        parse_mode="Markdown"
    )

async def cmd_pesan(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /pesan [teks] — kirim pesan ke partner.
    Butuh izin dari keduanya.
    """
    if not await check_auth(u): return
    uid          = u.effective_user.id
    sender_name  = get_user_name(uid)
    partner_uid  = _get_partner_uid(uid)
    partner_name = get_user_name(partner_uid)

    if not ctx.args:
        await u.message.reply_text(
            f"Format: `/pesan [teks]`\n"
            f"Contoh: `/pesan Jangan lupa makan ya!`\n\n"
            f"Pesan akan dikirim ke *{partner_name}*.",
            parse_mode="Markdown"
        )
        return

    # Langsung kirim tanpa cek izin
    teks = " ".join(ctx.args)
    try:
        await ctx.bot.send_message(
            partner_uid,
            f"💌 *Pesan dari {sender_name}:*\n\n"
            f"_{teks}_\n\n"
            f"_— dikirim lewat TabunganBot 🤖_\n\n"
            f"Balas ke {sender_name}: `/pesan [balasan kamu]`",
            parse_mode="Markdown"
        )
        await u.message.reply_text(
            f"✅ *Pesan terkirim ke {partner_name}!*\n\n"
            f"💬 _{teks}_",
            parse_mode="Markdown"
        )
        log.info(f"Pesan dari {sender_name} → {partner_name}: {teks[:50]}")
    except Exception as e:
        log.error(f"Gagal kirim pesan: {e}")
        await u.message.reply_text(f"❌ Gagal kirim pesan. Coba lagi ya.")

# ═══════════════════════════════════════════════════════════════
#  GROQ AI ASSISTANT
#  Logic 3 layer (berurutan, tidak pakai AI buat intent):
#
#  LAYER 1 — Rule-based: apakah user mau KIRIM PESAN ke partner?
#             Hanya trigger kalau ada kata eksplisit seperti
#             "kasih tau", "bilang ke", "ingatkan", dll.
#             → kalau iya, forward ke partner langsung.
#
#  LAYER 2 — Rule-based: apakah user minta DATA dari bot?
#             "saldo", "laporan", "bersama", "streak", dll.
#             → kalau iya, panggil fungsi command yang sesuai.
#
#  LAYER 3 — Groq AI chat: semua yang tidak masuk layer 1 & 2.
#             → jawab natural sebagai asisten.
# ═══════════════════════════════════════════════════════════════

_chat_history: dict[int, list[dict]] = {}

_SYSTEM_PROMPT = """Kamu adalah asisten TabunganBot dengan kemampuan reasoning tingkat tinggi.
Bot ini milik Fahril dan Freya — untuk pencatatan keuangan + belajar SNBT/UTBK.

────────────────────
🧠 CARA BERPIKIR (WAJIB DIIKUTI)
1. IDENTIFIKASI TUJUAN USER
   - Apa yang sebenarnya diminta?
   - Apakah eksplisit atau implisit?
2. KLASIFIKASI INTENT
   - Apakah ini:
     a) Perintah (command bot)
     b) Pertanyaan (question)
     c) Permintaan data (data fetch)
     d) Obrolan biasa (casual chat)
     e) Masalah teknis bot
3. CEK KONTEKS
   - Ada info dari percakapan sebelumnya?
   - Perlu asumsi? (hindari kalau tidak perlu)
4. PILIH STRATEGI RESPON
   - Command → arahkan ke command yang tepat
   - Data → tampilkan jelas & ringkas
   - Masalah teknis → diagnosa lalu beri solusi
   - Ambigu → minta klarifikasi singkat
5. VALIDASI LOGIKA
   - Apakah jawaban masuk akal?
   - Apakah ada kemungkinan salah tafsir?
────────────────────
📱 KONTEKS BOT INI

CARA KERJA /nabung DAN /keluar (4 step):
1. Ketik /nabung atau /keluar
2. Masukkan JUMLAH (angka saja, contoh: 50000)
3. Pilih KATEGORI dari tombol yang muncul
4. Masukkan CATATAN — teks bebas ATAU ketik "-" untuk SKIP step ini
⚠️ Step 4 sering bikin bingung — kalau user bilang "udah nabung tapi belum masuk/keitung",
   LANGSUNG diagnosa: kemungkinan besar lupa ketik "-" di step catatan. Suruh ketik "-" sekarang.

MASALAH TEKNIS UMUM:
- Bot tidak merespons / stuck → /cancel dulu, lalu mulai lagi
- Transaksi dobel → /hapusterakhir
- Salah jumlah → /hapusterakhir lalu catat ulang

COMMAND TERSEDIA:
/nabung /keluar /saldo /laporan /bulanan /riwayat /streak
/jadwal /bersama /tujuan /addtarget /isitarget
/ingatkan /daftarpengingat /pesan /catatan /hapusterakhir

SNBT INFO (khusus Freya):
- Bimbel aktif s.d. 18 April 2026
- Kelas PK: Kak Sugeng | Kelas PM: Kak Nisa
- 5 subtes: PU, PK, PM, PBM (B.Indo), LBI (B.Inggris)
- Ketik /jadwal untuk jadwal lengkap

PESAN KE PARTNER:
- Kirim lewat: "kasih tau fahril...", "bilang ke freya...", dll
- Atau manual: /pesan [teks]
────────────────────
⚙️ ATURAN OUTPUT
- Singkat, jelas, tidak bertele-tele
- Gunakan bullet/step hanya kalau memang perlu
- Jangan halusinasi data — kalau tidak tahu, bilang tidak tahu
- Maksimal 3–5 kalimat kecuali diminta detail
────────────────────
🚫 LARANGAN
- Jangan bilang "udah dikirim" atau "udah tersimpan" kalau kamu tidak benar-benar melakukan itu
- Jangan arahkan user ke sesuatu yang tidak ada
- Jangan mengarang data transaksi atau saldo
────────────────────
✨ GAYA KOMUNIKASI
- Santai/gaul tapi jelas
- To the point
- Boleh pakai emoji secukupnya
────────────────────
🎯 PRIORITAS
1. Akurasi — jangan sampai salah diagnosa
2. Kejelasan — user harus paham langkah selanjutnya
3. Efisiensi — tidak perlu panjang kalau tidak perlu
4. Gaya bahasa
"""

# ── LAYER 1: Rule-based send-to-partner detection ────────────────
# Keyword yang EKSPLISIT berarti mau kirim/titip pesan ke partner.
# Sengaja ketat — "bersama", "lihat", "cek" TIDAK masuk di sini.
_SEND_KEYWORDS = [
    "kasih tau", "kasih tahu", "kasihtau",
    "bilang ke", "bilang sama", "bilang ke dia",
    "ingatkan", "ingetin",
    "suruh",
    "titip pesan", "titip ke",
    "tolong bilang", "tolong kasih tau",
    "sampaikan ke", "sampaikan ke dia",
    "beritahu", "beri tau",
    "forward ke",
]

def _detect_send_intent(text: str, sender_uid: int) -> tuple[bool, str]:
    """
    Deteksi apakah user mau kirim pesan ke partner.
    Hanya trigger kalau ada keyword eksplisit — TIDAK pakai AI.
    Return (detected, extracted_message)
    """
    text_lower = text.lower()

    # Semua nama/kata yang merujuk ke partner
    partner_refs = ["fahril", "freya", "dia", "doi", "pacar", "sayang", "cinta"]

    for kw in _SEND_KEYWORDS:
        if kw not in text_lower:
            continue

        # Temukan posisi keyword, ambil teks setelahnya
        idx       = text_lower.find(kw)
        after_kw  = text[idx + len(kw):].strip()

        # Hapus nama partner di awal after_kw kalau ada
        for ref in partner_refs:
            if after_kw.lower().startswith(ref):
                after_kw = after_kw[len(ref):].strip()
                break

        # Pastikan ada isi pesan yang tersisa
        if len(after_kw) >= 3:
            return True, after_kw

    return False, ""

# ── LAYER 2: Rule-based data fetch detection ─────────────────────
# Urut dari panjang ke pendek supaya yang lebih spesifik dicek duluan.
_DATA_FETCH_MAP: list[tuple[list[str], str]] = [
    (["tabungan bersama", "rekap bersama", "lihat bersama", "cek bersama",
      "saldo bersama", "data bersama", "/bersama"], "bersama"),
    (["saldo aku", "cek saldo", "berapa saldo", "lihat saldo",
      "saldo sekarang", "/saldo"], "saldo"),
    (["laporan 7", "laporan minggu", "laporan mingguan",
      "lihat laporan", "cek laporan", "/laporan"], "laporan"),
    (["laporan bulan", "laporan bulanan", "rekap bulan",
      "pengeluaran bulan", "/bulanan"], "bulanan"),
    (["riwayat transaksi", "transaksi terakhir", "history",
      "lihat riwayat", "/riwayat"], "riwayat"),
    (["streak aku", "cek streak", "lihat streak",
      "streak nabung", "/streak"], "streak"),
    (["jadwal hari ini", "jadwal bimbel", "jadwal belajar",
      "kelas hari ini", "ada kelas", "/jadwal"], "jadwal"),
    (["target tabungan", "lihat target", "progres target",
      "cek tujuan", "/tujuan"], "tujuan"),
]

def _detect_data_fetch(text: str) -> str | None:
    """
    Deteksi apakah user minta data dari bot.
    Return nama fetch type, atau None kalau tidak ada.
    """
    text_lower = text.lower()
    for keywords, fetch_type in _DATA_FETCH_MAP:
        if any(kw in text_lower for kw in keywords):
            return fetch_type
    return None

# ── Groq chat (Layer 3) ──────────────────────────────────────────
def _groq_chat(uid: int, user_message: str, user_name: str) -> str:
    client  = Groq(api_key=GROQ_API_KEY)
    history = _chat_history.get(uid, [])
    history.append({"role": "user", "content": f"[{user_name}] {user_message}"})
    if len(history) > 10: history = history[-10:]
    _chat_history[uid] = history
    resp  = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "system", "content": _SYSTEM_PROMPT}, *history],
        max_tokens=300, temperature=0.7,
    )
    reply = resp.choices[0].message.content.strip()
    history.append({"role": "assistant", "content": reply})
    _chat_history[uid] = history
    return reply

# ── Main message handler ─────────────────────────────────────────
async def handle_ai_message(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = u.effective_user.id
    if not authorized(uid): return
    msg = (u.message.text or "").strip()
    if not msg: return

    sender_name  = get_user_name(uid)
    partner_uid  = _get_partner_uid(uid)
    partner_name = get_user_name(partner_uid)

    await ctx.bot.send_chat_action(chat_id=u.effective_chat.id, action="typing")

    # ── LAYER 1: Kirim pesan ke partner ──────────────────────────
    detected, extracted_msg = _detect_send_intent(msg, uid)
    if detected and extracted_msg:
        try:
            await ctx.bot.send_message(
                partner_uid,
                f"💌 *Pesan dari {sender_name}:*\n\n"
                f"_{extracted_msg}_\n\n"
                f"_— dikirim lewat TabunganBot 🤖_\n\n"
                f"Balas: `/pesan [teks balasan kamu]`",
                parse_mode="Markdown"
            )
            await u.message.reply_text(
                f"✅ Pesan terkirim ke *{partner_name}!*\n\n"
                f"💬 _{extracted_msg}_",
                parse_mode="Markdown"
            )
            log.info(f"Pesan forward {sender_name}→{partner_name}: {extracted_msg[:60]}")
        except Exception as e:
            log.error(f"Forward pesan error: {e}")
            await u.message.reply_text(
                f"❌ Gagal kirim pesan ke {partner_name}.\n"
                f"Pastikan dia sudah pernah /start di bot ini ya."
            )
        return

    # ── LAYER 2: Fetch data langsung ─────────────────────────────
    fetch_type = _detect_data_fetch(msg)
    if fetch_type:
        log.info(f"Data fetch '{fetch_type}' dari {sender_name}")
        if fetch_type == "bersama":
            await cmd_bersama(u, ctx)
        elif fetch_type == "saldo":
            await cmd_saldo(u, ctx)
        elif fetch_type == "laporan":
            await cmd_laporan(u, ctx)
        elif fetch_type == "bulanan":
            await cmd_bulanan(u, ctx)
        elif fetch_type == "riwayat":
            await cmd_riwayat(u, ctx)
        elif fetch_type == "streak":
            await cmd_streak(u, ctx)
        elif fetch_type == "jadwal":
            await cmd_jadwal(u, ctx)
        elif fetch_type == "tujuan":
            await cmd_tujuan(u, ctx)
        return

    # ── LAYER 3: Normal AI chat ───────────────────────────────────
    try:
        reply = await run(_groq_chat, uid, msg, sender_name or "User")
        await u.message.reply_text(reply)
    except Exception as e:
        log.error(f"Groq error: {e}")
        await u.message.reply_text("AI-nya lagi gangguan bentar 😅 Coba lagi ya!")

# ═══════════════════════════════════════════════════════════════
#  COMMAND: /jadwal
# ═══════════════════════════════════════════════════════════════
async def cmd_jadwal(u: Update, _):
    if not await check_auth(u): return
    now   = datetime.now(WIB)
    today = date.today()
    lines = [f"📅 *Jadwal SNBT Freya*\n_{now.strftime('%d %B %Y')}_\n"]
    if _is_bimbel_active():
        sisa = (BIMBEL_END_DATE - today).days
        lines.append(f"🎓 *Fase Bimbel* — selesai *{BIMBEL_END_DATE.strftime('%d %B %Y')}* ({sisa} hari lagi)\n")
    else:
        lines.append("📖 *Fase Belajar Mandiri* — bimbel sudah selesai 🎉\n")
    lines.append("━━━━━━━━━━━━━━━━━")
    lines.append("📆 *7 Hari ke Depan:*\n")
    HARI_ID = ["Senin","Selasa","Rabu","Kamis","Jumat","Sabtu","Minggu"]
    for i in range(7):
        d     = today + timedelta(days=i)
        d_str = d.strftime("%Y-%m-%d")
        label = "Hari ini" if i == 0 else HARI_ID[d.weekday()]
        jadwal = JADWAL_KELAS.get(d_str)
        if jadwal and d <= BIMBEL_END_DATE:
            tipe_icon = "🎁" if "Bonus" in jadwal["tipe"] else ("📝" if "Tryout" in jadwal["tipe"] else "🏫")
            s_info = next((s for s in SUBTES_MANDIRI if s["kode"] == jadwal["subtes"]), None)
            em = s_info["emoji"] if s_info else "📌"
            lines.append(f"*{label}, {d.strftime('%d/%m')}*")
            lines.append(f"  {tipe_icon} {jadwal['tipe']}: {em} {jadwal['subtes']} — {jadwal['tutor']}")
            lines.append(f"  🕐 {jadwal['jam']}")
            if "extra" in jadwal:
                ex = jadwal["extra"]
                ex_i = next((s for s in SUBTES_MANDIRI if s["kode"] == ex["subtes"]), None)
                ex_em = ex_i["emoji"] if ex_i else "📌"
                lines.append(f"  🎁 {ex['tipe']}: {ex_em} {ex['subtes']} — {ex['tutor']}")
                lines.append(f"  🕐 {ex['jam']}")
        else:
            subtes = _get_subtes_mandiri(d)
            lines.append(f"*{label}, {d.strftime('%d/%m')}*")
            lines.append(f"  📖 Mandiri: {subtes['emoji']} {subtes['nama']}")
        lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━")
    lines.append("*Subtes:* PU • PK • PM • PBM • LBI")
    await u.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ═══════════════════════════════════════════════════════════════
#  CONVERSATION: Custom Reminder
# ═══════════════════════════════════════════════════════════════
async def cmd_ingatkan_start(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(u): return
    await u.message.reply_text(
        "⏰ *Buat Pengingat Baru*\n\n"
        "Langkah 1/4: Nama pengingat?\n_Contoh: PR Matematika, Review PK_",
        parse_mode="Markdown")
    return REM_NAMA

async def rem_got_nama(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["rem_nama"] = u.message.text.strip()
    await u.message.reply_text(
        f"✅ Nama: *{ctx.user_data['rem_nama']}*\n\n"
        "Langkah 2/4: Hari apa?\n"
        "• `setiap hari`\n• `senin`, `selasa`, dll\n"
        "• Kombinasi: `senin,rabu,jumat`\n• Tanggal: `2026-04-20`",
        parse_mode="Markdown")
    return REM_HARI

async def rem_got_hari(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    hari_raw = u.message.text.strip().lower()
    valid = False
    if hari_raw == "setiap hari": valid = True
    elif hari_raw.count("-") == 2:
        try: datetime.strptime(hari_raw, "%Y-%m-%d"); valid = True
        except: pass
    else:
        parts = [h.strip() for h in hari_raw.split(",")]
        if all(h in HARI_MAP for h in parts): valid = True
    if not valid:
        await u.message.reply_text("❌ Format tidak dikenali. Contoh: `setiap hari` / `senin,rabu` / `2026-04-20`", parse_mode="Markdown")
        return REM_HARI
    ctx.user_data["rem_hari"] = hari_raw
    await u.message.reply_text(
        f"✅ Hari: *{hari_raw}*\n\nLangkah 3/4: Jam berapa? (format 24jam)\nContoh: `19:00`, `08:30`",
        parse_mode="Markdown")
    return REM_JAM

async def rem_got_jam(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    jam_raw = u.message.text.strip()
    try:
        h, m = map(int, jam_raw.split(":"))
        assert 0 <= h <= 23 and 0 <= m <= 59
        jam_str = f"{h:02d}:{m:02d}"
    except:
        await u.message.reply_text("❌ Format jam salah. Contoh: `19:00`", parse_mode="Markdown")
        return REM_JAM
    ctx.user_data["rem_jam"] = jam_str
    await u.message.reply_text(
        f"✅ Jam: *{jam_str} WITA*\n\nLangkah 4/4: Isi pesan pengingatnya?\n_Tulis bebas~_",
        parse_mode="Markdown")
    return REM_PESAN

async def rem_got_pesan(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["rem_pesan"] = u.message.text.strip()
    uid   = u.effective_user.id
    nama  = ctx.user_data["rem_nama"]
    hari  = ctx.user_data["rem_hari"]
    jam   = ctx.user_data["rem_jam"]
    pesan = ctx.user_data["rem_pesan"]
    wait  = await u.message.reply_text("⏳ Menyimpan...")
    pid   = await run(db_add_pengingat, uid, nama, hari, jam, pesan)
    await wait.delete()
    await u.message.reply_text(
        f"✅ *Pengingat Dibuat!* (ID: {pid})\n\n"
        f"📌 *{nama}*\n📅 {hari}  🕐 {jam} WITA\n💬 _{pesan}_\n\n"
        f"/daftarpengingat | `/hapuspengingat {pid}`",
        parse_mode="Markdown")
    return ConversationHandler.END

async def rem_cancel(u: Update, _):
    await u.message.reply_text("❌ Dibatalkan.")
    return ConversationHandler.END

async def cmd_daftar_pengingat(u: Update, _):
    if not await check_auth(u): return
    uid  = u.effective_user.id
    wait = await u.message.reply_text("⏳ Memuat...")
    rows = await run(db_get_pengingat, uid, False)
    await wait.delete()
    if not rows:
        await u.message.reply_text("📭 Belum ada pengingat.\nBuat: /ingatkan", parse_mode="Markdown"); return
    lines = ["⏰ *Daftar Pengingat*\n"]
    for r in rows:
        status = "🟢" if str(r["Aktif"]) == "Ya" else "🔴"
        lines.append(f"{status} *[ID {r['ID']}]* {r['Nama']}\n   📅 {r['Hari']}  🕐 {r['Jam']} WITA\n   💬 _{r['Pesan']}_\n")
    lines += ["━━━━━━━━━━━━━━━━━",
              "`/hapuspengingat [id]`  `/matikanpengingat [id]`  `/aktifkanpengingat [id]`"]
    await u.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_hapus_pengingat(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(u): return
    if not ctx.args or not ctx.args[0].isdigit():
        await u.message.reply_text("Format: `/hapuspengingat [id]`", parse_mode="Markdown"); return
    ok = await run(db_delete_pengingat, int(ctx.args[0]))
    await u.message.reply_text("✅ Terhapus." if ok else "❌ ID tidak ditemukan.")

async def cmd_matikan_pengingat(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(u): return
    if not ctx.args or not ctx.args[0].isdigit():
        await u.message.reply_text("Format: `/matikanpengingat [id]`", parse_mode="Markdown"); return
    ok = await run(db_toggle_pengingat, int(ctx.args[0]), False)
    await u.message.reply_text("🔴 Dimatikan." if ok else "❌ ID tidak ditemukan.")

async def cmd_aktifkan_pengingat(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(u): return
    if not ctx.args or not ctx.args[0].isdigit():
        await u.message.reply_text("Format: `/aktifkanpengingat [id]`", parse_mode="Markdown"); return
    ok = await run(db_toggle_pengingat, int(ctx.args[0]), True)
    await u.message.reply_text("🟢 Diaktifkan." if ok else "❌ ID tidak ditemukan.")

# ═══════════════════════════════════════════════════════════════
#  COMMAND HANDLERS — KEUANGAN
# ═══════════════════════════════════════════════════════════════
async def cmd_start(u: Update, _):
    uid = u.effective_user.id
    if not authorized(uid):
        await u.message.reply_text(f"👋 Bot ini khusus Fahril & Freya.\n🪪 ID kamu: `{uid}`", parse_mode="Markdown"); return
    name = get_user_name(uid)
    wait = await u.message.reply_text("⏳ Memuat...")
    bal  = await run(db_get_balance, uid)
    fahril_ok, freya_ok = await run(_both_permitted)
    await wait.delete()
    fitur_pesan = "✅ Aktif" if (fahril_ok and freya_ok) else "⏳ Belum aktif keduanya"
    partner_name = _get_partner_name(uid)
    await u.message.reply_text(
        f"👋 Halo *{name}*! 💰 Saldo: *{rp(bal)}*\n\n"
        "━━━━━━━━━━━━━━━━━\n"
        "💰 *Keuangan:*\n"
        "➕ /nabung  ➖ /keluar  💼 /saldo\n"
        "📊 /laporan  📅 /bulanan  📜 /riwayat\n"
        "🔥 /streak  🎯 /tujuan  👥 /bersama\n"
        "🗒️ /catatan  ↩️ /hapusterakhir\n\n"
        "━━━━━━━━━━━━━━━━━\n"
        "📚 *Belajar SNBT (Freya):*\n"
        "📅 /jadwal  ⏰ /ingatkan  📋 /daftarpengingat\n\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"💌 *Pesan ke {partner_name}:* {fitur_pesan}\n"
        f"📨 /pesan [teks] — kirim pesan\n"
        f"🔓 /izinkanpesan — aktifkan izin\n"
        f"📡 /statuspesan — cek status\n\n"
        "━━━━━━━━━━━━━━━━━\n"
        "_💬 Bisa ngobrol bebas juga, ada AI Groq!_",
        parse_mode="Markdown")

async def cmd_myid(u: Update, _):
    uid  = u.effective_user.id
    await u.message.reply_text(f"🪪 ID: `{uid}`\nNama: *{get_user_name(uid) or 'Belum terdaftar'}*", parse_mode="Markdown")

async def cmd_spreadsheet(u: Update, _):
    if not await check_auth(u): return
    await u.message.reply_text(f"🔗 https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}")

async def cmd_streak(u: Update, _):
    if not await check_auth(u): return
    uid  = u.effective_user.id
    name = get_user_name(uid)
    wait = await u.message.reply_text("⏳ Memuat streak...")
    data = await run(db_get_streak, uid)
    await wait.delete()
    cur = data["current"]; lng = data["longest"]
    next_ms = next((m for m in STREAK_MILESTONES if m > cur), None)
    cycle = (cur % 30) or (30 if cur > 0 and cur % 30 == 0 else 0)
    pct   = min(100, cycle / 30 * 100)
    lines = [f"🔥 *Streak — {name}*\n",
             f"{streak_badge(cur)} *{cur} Hari*  _{streak_title(cur)}_\n",
             f"`{streak_bar(cur)}` {pct:.0f}% menuju 30 hari",
             f"🏅 Terpanjang: *{lng} hari*"]
    if next_ms: lines.append(f"🎯 Berikutnya: *{next_ms} hari* ({next_ms-cur} lagi)")
    lines.append("\n🏆 *Milestone:*")
    for ms in STREAK_MILESTONES:
        if cur >= ms: lines.append(f"  ✅ {ms}hr {streak_badge(ms)}")
        elif ms == next_ms: lines.append(f"  ⏳ {ms}hr {streak_badge(ms)} ← next")
        else: lines.append(f"  🔒 {ms}hr")
    await u.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_saldo(u: Update, _):
    if not await check_auth(u): return
    uid  = u.effective_user.id
    name = get_user_name(uid)
    wait = await u.message.reply_text("⏳ Mengambil data...")
    bal = await run(db_get_balance, uid)
    inc7, exp7, _  = await run(db_get_summary, uid, 7)
    inc30, exp30, _ = await run(db_get_summary, uid, 30)
    sd  = await run(db_get_streak, uid)
    await wait.delete()
    await u.message.reply_text(
        f"💼 *Saldo — {name}*\n\n💰 *{rp(bal)}*\n\n"
        f"━━ 7 Hari ━━\n📈 {rp(inc7)}  📉 {rp(exp7)}  📊 {rp(inc7-exp7)}\n\n"
        f"━━ 30 Hari ━\n📈 {rp(inc30)}  📉 {rp(exp30)}  📊 {rp(inc30-exp30)}\n\n"
        f"━━ Streak ━━\n{_streak_summary(sd)}",
        parse_mode="Markdown")

async def cmd_laporan(u: Update, _):
    if not await check_auth(u): return
    uid  = u.effective_user.id
    name = get_user_name(uid)
    wait = await u.message.reply_text("⏳ Menyusun laporan...")
    inc, exp, rows = await run(db_get_summary, uid, 7)
    bal = await run(db_get_balance, uid)
    await wait.delete()
    lines = [f"📊 *Laporan 7 Hari — {name}*",
             f"_{datetime.now(WIB).strftime('%d %B %Y')}_\n",
             f"📈 *{rp(inc)}*  📉 *{rp(exp)}*  💰 *{rp(bal)}*\n", "📜 *Transaksi:*"]
    for r in rows[:12]:
        icon = "⬆️" if r["Tipe"] == "income" else "⬇️"
        note = f" _{r['Catatan']}_" if r.get("Catatan") else ""
        lines.append(f"{icon} *{rp(float(r['Jumlah']))}* — {r['Kategori']}{note}")
        lines.append(f"    `{str(r['Waktu'])[:16]}`")
    if not rows: lines.append("_Tidak ada transaksi._")
    await u.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_bulanan(u: Update, _):
    if not await check_auth(u): return
    uid = u.effective_user.id; name = get_user_name(uid); now = datetime.now(WIB)
    wait = await u.message.reply_text("⏳ Menyusun...")
    inc, exp, _ = await run(db_get_summary, uid, now.day + 1)
    cats = await run(db_get_monthly_cats, uid)
    bal  = await run(db_get_balance, uid)
    await wait.delete()
    lines = [f"📅 *Bulanan — {name}* _{now.strftime('%B %Y')}_\n",
             f"📈 *{rp(inc)}*  📉 *{rp(exp)}*  📊 *{rp(inc-exp)}*  💰 *{rp(bal)}*\n"]
    inc_c = [(c, a) for c, t, a in cats if t == "income"]
    exp_c = [(c, a) for c, t, a in cats if t == "expense"]
    if inc_c:
        lines.append("📈 *Pemasukan:*")
        for c, a in inc_c: lines.append(f"  • {c}: *{rp(a)}*")
        lines.append("")
    if exp_c:
        lines.append("📉 *Pengeluaran:*")
        for c, a in exp_c: lines.append(f"  • {c}: *{rp(a)}*")
    await u.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_riwayat(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(u): return
    uid = u.effective_user.id; name = get_user_name(uid)
    n   = min(int(ctx.args[0]) if ctx.args and ctx.args[0].isdigit() else 10, 30)
    wait = await u.message.reply_text("⏳ Mengambil...")
    rows = await run(db_get_transactions, uid, None, n)
    await wait.delete()
    lines = [f"📜 *{n} Transaksi Terakhir — {name}*\n"]
    for r in rows:
        icon = "⬆️" if r["Tipe"] == "income" else "⬇️"
        note = f"\n     _{r['Catatan']}_" if r.get("Catatan") else ""
        lines.append(f"{icon} *{rp(float(r['Jumlah']))}* — {r['Kategori']}{note}\n    `{str(r['Waktu'])[:16]}`\n")
    if not rows: lines.append("Belum ada transaksi.")
    await u.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_bersama(u: Update, _):
    if not await check_auth(u): return
    wait = await u.message.reply_text("⏳ Memuat data berdua...")
    lines = ["👥 *Rekap Bersama — Fahril & Freya*", f"_{datetime.now(WIB).strftime('%d %B %Y')}_\n"]
    total_bal = total_inc = total_exp = 0.0
    for name, uid in USERS.items():
        if uid == 0: continue
        bal = await run(db_get_balance, uid)
        inc7, exp7, _ = await run(db_get_summary, uid, 7)
        sd = await run(db_get_streak, uid)
        total_bal += bal; total_inc += inc7; total_exp += exp7
        cur = sd["current"]
        lines += [f"👤 *{name}*", f"  💰 {rp(bal)}  📈 {rp(inc7)}  📉 {rp(exp7)}",
                  f"  {streak_badge(cur)} Streak *{cur} hari* — _{streak_title(cur)}_\n"]
    lines += ["━━━━━━━━━━━━━━━━━",
              f"  💰 Total: *{rp(total_bal)}*  📊 Selisih: *{rp(total_inc-total_exp)}*"]
    await wait.delete()
    await u.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_tujuan(u: Update, _):
    if not await check_auth(u): return
    uid = u.effective_user.id; name = get_user_name(uid)
    wait = await u.message.reply_text("⏳ Memuat...")
    goals = await run(db_get_goals, uid)
    await wait.delete()
    lines = [f"🎯 *Target Tabungan — {name}*\n"]
    if not goals:
        lines.append("Belum ada target.\n`/addtarget [jumlah] [nama]`")
    else:
        for r in goals:
            t = float(r["Target"]); s = float(r["Terkumpul"])
            pct = min(100.0, (s/t*100) if t > 0 else 0)
            lines += [f"{'✅' if r['Selesai']=='Ya' else '🔄'} *{r['Judul']}* (ID:{r['ID']})",
                      f"  `{progress_bar(pct)}` {pct:.1f}%  {rp(s)}/{rp(t)}\n"]
        lines.append("`/isitarget [id] [jumlah]`")
    await u.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_addtarget(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(u): return
    if not ctx.args or len(ctx.args) < 2:
        await u.message.reply_text("Format: `/addtarget [jumlah] [nama]`", parse_mode="Markdown"); return
    try:
        amount = float(ctx.args[0].replace(".", "").replace(",", ""))
        title  = " ".join(ctx.args[1:])
        wait   = await u.message.reply_text("⏳ Menyimpan...")
        await run(db_add_goal, u.effective_user.id, title, amount)
        await wait.delete()
        await u.message.reply_text(f"🎯 Target *{title}* — *{rp(amount)}* berhasil!", parse_mode="Markdown")
    except: await u.message.reply_text("❌ Format salah.", parse_mode="Markdown")

async def cmd_isitarget(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(u): return
    if not ctx.args or len(ctx.args) < 2:
        await u.message.reply_text("Format: `/isitarget [id] [jumlah]`", parse_mode="Markdown"); return
    try:
        t, s = await run(db_update_goal, int(ctx.args[0]),
                         float(ctx.args[1].replace(".", "").replace(",", "")))
        if t is None:
            await u.message.reply_text("❌ Target tidak ditemukan."); return
        pct = min(100.0, s/t*100)
        await u.message.reply_text(
            f"{'✅ *Target Tercapai! 🎉*' if s>=t else '🔄 *Progres Diperbarui!*'}\n\n"
            f"`{progress_bar(pct)}` {pct:.1f}%\n{rp(s)}/{rp(t)}",
            parse_mode="Markdown")
    except: await u.message.reply_text("❌ Format salah.", parse_mode="Markdown")

async def cmd_catatan(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(u): return
    uid = u.effective_user.id; name = get_user_name(uid)
    if ctx.args:
        content = " ".join(ctx.args)
        wait = await u.message.reply_text("⏳ Menyimpan...")
        await run(db_add_note, uid, content)
        await wait.delete()
        await u.message.reply_text(f"🗒️ Tersimpan:\n_{content}_", parse_mode="Markdown")
    else:
        wait  = await u.message.reply_text("⏳ Memuat...")
        notes = await run(db_get_notes, uid)
        await wait.delete()
        lines = [f"🗒️ *Catatan — {name}*\n"]
        if notes:
            for r in notes: lines.append(f"• _{r['Isi']}_\n  `{str(r['Waktu'])[:16]}`\n")
        else: lines.append("Belum ada. `/catatan [teks]`")
        await u.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_hapusterakhir(u: Update, _):
    if not await check_auth(u): return
    uid  = u.effective_user.id
    wait = await u.message.reply_text("⏳ Menghapus...")
    ok   = await run(db_delete_last_transaction, uid)
    bal  = await run(db_get_balance, uid)
    await wait.delete()
    if ok: await u.message.reply_text(f"↩️ Terhapus. 💰 Saldo: *{rp(bal)}*", parse_mode="Markdown")
    else:  await u.message.reply_text("❌ Tidak ada transaksi.")

# ═══════════════════════════════════════════════════════════════
#  CONVERSATION: /nabung & /keluar
# ═══════════════════════════════════════════════════════════════
async def start_nabung(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not authorized(u.effective_user.id):
        await u.message.reply_text("⛔ Tidak diizinkan."); return ConversationHandler.END
    ctx.user_data.update({"kind": "income", "amount": None, "desc": None})
    if ctx.args:
        try:
            ctx.user_data["amount"] = float(ctx.args[0].replace(".", "").replace(",", ""))
            ctx.user_data["desc"]   = " ".join(ctx.args[1:]) if len(ctx.args) > 1 else ""
            await u.message.reply_text("📂 *Pilih kategori:*", reply_markup=kb_grid(CATS_IN), parse_mode="Markdown")
            return ASK_CAT
        except: pass
    await u.message.reply_text("💵 *Masukkan jumlah:*\n_Contoh: `500000`_", parse_mode="Markdown")
    return ASK_AMOUNT

async def start_keluar(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not authorized(u.effective_user.id):
        await u.message.reply_text("⛔ Tidak diizinkan."); return ConversationHandler.END
    ctx.user_data.update({"kind": "expense", "amount": None, "desc": None})
    if ctx.args:
        try:
            ctx.user_data["amount"] = float(ctx.args[0].replace(".", "").replace(",", ""))
            ctx.user_data["desc"]   = " ".join(ctx.args[1:]) if len(ctx.args) > 1 else ""
            await u.message.reply_text("📂 *Pilih kategori:*", reply_markup=kb_grid(CATS_OUT), parse_mode="Markdown")
            return ASK_CAT
        except: pass
    await u.message.reply_text("💸 *Masukkan jumlah:*\n_Contoh: `50000`_", parse_mode="Markdown")
    return ASK_AMOUNT

async def got_amount(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    txt = u.message.text.strip().replace(".", "").replace(",", "")
    try: ctx.user_data["amount"] = float(txt)
    except:
        await u.message.reply_text("❌ Angka aja, contoh: `150000`", parse_mode="Markdown")
        return ASK_AMOUNT
    cats = CATS_IN if ctx.user_data["kind"] == "income" else CATS_OUT
    await u.message.reply_text("📂 *Pilih kategori:*", reply_markup=kb_grid(cats), parse_mode="Markdown")
    return ASK_CAT

async def got_cat(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    ctx.user_data["category"] = q.data
    if ctx.user_data.get("desc") is not None:
        await _save_tx(q.message, ctx, q.from_user.id); return ConversationHandler.END
    await q.edit_message_text("📝 *Tambahkan catatan:*\n_Ketik `-` untuk skip_", parse_mode="Markdown")
    return ASK_DESC

async def got_desc(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["desc"] = "" if u.message.text.strip() == "-" else u.message.text.strip()
    await _save_tx(u.message, ctx, u.effective_user.id)
    return ConversationHandler.END

async def _save_tx(msg, ctx, uid: int):
    name = get_user_name(uid); kind = ctx.user_data["kind"]
    amount = ctx.user_data["amount"]; cat = ctx.user_data.get("category", "📦 Lainnya")
    note   = ctx.user_data.get("desc") or ""
    wait   = await msg.reply_text("⏳ Menyimpan...")
    await run(db_add_transaction, uid, name, kind, amount, cat, note)
    bal = await run(db_get_balance, uid)
    sd  = await run(db_update_streak, uid)
    await wait.delete()
    cur = sd["current"]
    await msg.reply_text(
        f"{'📈' if kind=='income' else '📉'} *{'Pemasukan' if kind=='income' else 'Pengeluaran'} Berhasil!*\n\n"
        f"👤 {name}  💵 *{rp(amount)}*\n📂 {cat}  📝 {note or '-'}\n\n"
        f"💰 Saldo: *{rp(bal)}*  _✅ Tersimpan_\n\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"{streak_badge(cur)} *Streak: {cur} hari* — _{streak_title(cur)}_\n`{streak_bar(cur)}`",
        parse_mode="Markdown")
    ms = sd.get("milestone_hit")
    if ms:
        msgs = {3:"🌱 *3 Hari!* Mulai tumbuh! 💪",7:"✨ *1 Minggu!* 🎉",14:"🔥 *2 Minggu!* 🔥",
                21:"💪 *3 Minggu!* Kebiasaan terbentuk! 🏆",30:"⚡ *1 BULAN! 🎊* 💰",
                60:"🏆 *2 BULAN! 🎊* 👑",90:"🌟 *90 HARI! 🎊* Legend!",
                100:"👑 *100 HARI! 🎊* SERATUS!",365:"🚀 *1 TAHUN! 🎊* GOAT! 🐐"}
        await msg.reply_text(msgs.get(ms, f"🎉 Streak {ms} Hari! 💪"), parse_mode="Markdown")

async def cancel(u: Update, _):
    await u.message.reply_text("❌ Dibatalkan.")
    return ConversationHandler.END

# ═══════════════════════════════════════════════════════════════
#  SCHEDULED JOBS
# ═══════════════════════════════════════════════════════════════
async def send_weekly_report(app):
    for name, uid in USERS.items():
        if uid == 0: continue
        try:
            inc, exp, rows = await run(db_get_summary, uid, 7)
            bal = await run(db_get_balance, uid)
            goals = await run(db_get_goals, uid)
            sd = await run(db_get_streak, uid); cur = sd["current"]
            lines = [f"📊 *Laporan Mingguan — {name}*",
                     f"_{datetime.now(WIB).strftime('%d %B %Y')}_\n",
                     f"📈 *{rp(inc)}*  📉 *{rp(exp)}*  💰 *{rp(bal)}*\n",
                     f"{streak_badge(cur)} Streak *{cur} hari* — _{streak_title(cur)}_\n"]
            if rows:
                lines.append("📜 *Transaksi:*")
                for r in rows[:8]: lines.append(f"{'⬆️' if r['Tipe']=='income' else '⬇️'} {rp(float(r['Jumlah']))} — {r['Kategori']}")
                lines.append("")
            else: lines.append("_Tidak ada transaksi._\n")
            active = [r for r in goals if r.get("Selesai") != "Ya"]
            if active:
                lines.append("🎯 *Target:*")
                for r in active[:3]:
                    pct = min(100.0, float(r["Terkumpul"])/float(r["Target"])*100)
                    lines.append(f"  {r['Judul']}: `{progress_bar(pct, 8)}` {pct:.0f}%")
            lines.append("\n_TabunganBot 🤖 — Semangat!_ 💪")
            await app.bot.send_message(uid, "\n".join(lines), parse_mode="Markdown")
        except Exception as e: log.error(f"Weekly report {name}: {e}")

async def send_snbt_reminder(app):
    uid = FREYA_ID
    if uid == 0: return
    try:
        today = date.today(); today_str = today.strftime("%Y-%m-%d")
        now_wib = datetime.now(WIB)
        if _is_bimbel_active():
            jadwal = JADWAL_KELAS.get(today_str)
            if jadwal:
                s_info = next((s for s in SUBTES_MANDIRI if s["kode"] == jadwal["subtes"]), None)
                em = s_info["emoji"] if s_info else "📌"
                tipe_icon = "🎁" if "Bonus" in jadwal["tipe"] else ("📝" if "Tryout" in jadwal["tipe"] else "🏫")
                msg = (f"📚 *Reminder Belajar SNBT* — {now_wib.strftime('%d %B %Y')}\n\n"
                       f"{tipe_icon} *{jadwal['tipe']}* hari ini, sayang!\n\n"
                       f"  {em} *{jadwal['subtes']}* — 👨‍🏫 {jadwal['tutor']}\n  🕐 {jadwal['jam']}\n")
                if "extra" in jadwal:
                    ex = jadwal["extra"]
                    ex_i = next((s for s in SUBTES_MANDIRI if s["kode"] == ex["subtes"]), None)
                    msg += f"\n  🎁 Bonus: {ex_i['emoji'] if ex_i else '📌'} {ex['subtes']} — {ex['tutor']}\n  🕐 {ex['jam']}\n"
                msg += "\nLink Zoom dikirim sebelum kelas 📩\n_Semangat cintaku! 💕🤖❤️_\n\n📅 /jadwal"
            else:
                subtes = _get_subtes_mandiri(today)
                msg = (f"📚 *Reminder Belajar Mandiri* — {now_wib.strftime('%d %B %Y')}\n\n"
                       f"Hari ini nggak ada kelas, tapi tetap belajar ya! 💪\n\n"
                       f"{subtes['emoji']} *{subtes['nama']} ({subtes['kode']})*\n📝 _{subtes['tips']}_\n\n"
                       f"_Konsisten kunci sukses SNBT! 🎯_\n_Aku support kamu cintaku~ 🤖❤️_\n\n📅 /jadwal")
        else:
            subtes = _get_subtes_mandiri(today)
            msg = (f"📚 *Belajar Mandiri SNBT* — {now_wib.strftime('%d %B %Y')}\n\n"
                   f"Bimbel udah selesai, saatnya latihan mandiri! 💪\n\n"
                   f"{subtes['emoji']} *{subtes['nama']} ({subtes['kode']})*\n📝 _{subtes['tips']}_\n\n"
                   f"_Kamu pasti bisa! 🤖❤️_\n\n📅 /jadwal")
        await app.bot.send_message(uid, msg, parse_mode="Markdown")
    except Exception as e: log.error(f"SNBT reminder: {e}")

async def check_custom_pengingat(app):
    try:
        now_wita = datetime.now(WITA)
        rows     = await run(db_get_all_pengingat_aktif)
        for r in rows:
            if _should_fire_pengingat(r, now_wita):
                uid = int(r["UserID"]) if str(r["UserID"]).isdigit() else 0
                if uid == 0: continue
                await app.bot.send_message(
                    uid,
                    f"⏰ *Pengingat: {r['Nama']}*\n\n{r['Pesan']}\n\n_TabunganBot 🤖_",
                    parse_mode="Markdown")
                log.info(f"Custom pengingat '{r['Nama']}' → {uid}")
    except Exception as e: log.error(f"Custom pengingat: {e}")

async def send_streak_broken_alert(app):
    for name, uid in USERS.items():
        if uid == 0: continue
        try:
            broken = await run(db_check_streak_broken, uid)
            if broken > 0:
                await app.bot.send_message(uid,
                    f"💔 *Streak putus...*\n\n{streak_badge(broken)} *{broken} hari* hilang 😢\n\nNggak apa-apa! Yuk mulai lagi! 💪\n➕ /nabung  |  ➖ /keluar",
                    parse_mode="Markdown")
        except Exception as e: log.error(f"Streak broken {name}: {e}")

# ── Reminder Nabung Freya ────────────────────────────────────────
_NABUNG_PAGI  = [
    "☀️ *Selamat pagi, sayangku~* 🌸\n\nJangan lupa nabung yaa sayangku cintaku 💰\nWalaupun aku sibuk, aku buatin bot ini buat ingetin kamu 🤖❤️\n\n➕ /nabung  |  ➖ /keluar  |  🔥 /streak",
    "🌤️ *Pagi-pagi udah keinget kamu~* ☀️\n\nJangan lupa nabung yaa sayangku cintaku 💕\nAku bikin bot ini biar ada yang ingetin kamu 🤖\n\n➕ /nabung  |  ➖ /keluar  |  🔥 /streak",
    "🌸 *Hai cintaku, selamat pagi!*\n\nJangan lupa nabung yaa sayangku 💰❤️\nBot ini bukti aku sayang kamu walau lagi sibuk~ 🤖\n\n➕ /nabung  |  ➖ /keluar  |  🔥 /streak",
]
_NABUNG_MALAM = [
    "🌙 *Malam sayang~* ✨\n\nJangan lupa nabung yaa sayangku cintaku 💰\nAku buatin bot ini biar kamu nggak lupa 🤖❤️\n\n➕ /nabung  |  ➖ /keluar  |  🔥 /streak",
    "🌙 *Udah malem, sayang~*\n\nBelum ada catatan hari ini lho 👀\nJangan lupa nabung yaa cintaku 💕\n\n➕ /nabung  |  ➖ /keluar  |  🔥 /streak",
    "✨ *Psst, sayang!*\n\nBot buatan aku mau ingetin — jangan lupa nabung yaa 💰🌙\nDua menit aja buat catat~ 😴❤️\n\n➕ /nabung  |  ➖ /keluar  |  🔥 /streak",
]

async def send_reminder_nabung(app, session: str):
    uid = FREYA_ID
    if not uid: return
    try:
        if await run(db_has_transaction_today, uid): return
        sd = await run(db_get_streak, uid)
        cur = sd["current"]
        warn = ""
        if cur > 0 and sd["last_date"] == _yesterday_wita():
            warn = f"\n\n⚠️ *Streak {streak_badge(cur)} {cur} hari mau putus!*\n_Catat sekarang biar nggak reset~_ 🙏"
        day_idx = datetime.now(WITA).weekday()
        pool    = _NABUNG_PAGI if session == "pagi" else _NABUNG_MALAM
        await app.bot.send_message(uid, pool[day_idx % len(pool)] + warn, parse_mode="Markdown")
    except Exception as e: log.error(f"Reminder nabung: {e}")

_MAKAN_PAGI  = ["🍳 *Pagi sayang!* Udah sarapan belum? Jangan skip ya 🥺☀️💕","🌅 *Selamat pagi cintaku!* Yuk sarapan dulu 🍞🥛💕","☀️ *Ingetin kamu sarapan~* Biar kuat seharian 🍳❤️"]
_MAKAN_SIANG = ["🍱 *Hei sayang, dzuhur nih!* Jangan lupa makan siang ya 🥺❤️","🕛 *Dzuhur udah, makan belum?* Yuk makan siang! 🍛💕","🍜 *Waktunya makan siang!* Jangan lupa cintaku 💕🥗"]
_MAKAN_SORE  = ["🌤️ *Habis ashar, makan belum?* Yuk makan sore sayang! 🍊🥺💕","🍎 *Sore-sore ingetin makan!* Snack dulu ya sayang 🌤️❤️","☕ *Udah sore~* Jangan lupa makan ya cintaku! 🍪🥺❤️"]

async def send_reminder_makan(app, waktu: str):
    uid = FREYA_ID
    if not uid: return
    try:
        pools = {"pagi": _MAKAN_PAGI, "siang": _MAKAN_SIANG, "sore": _MAKAN_SORE}
        day_idx = datetime.now(WITA).weekday()
        await app.bot.send_message(uid, pools[waktu][day_idx % len(pools[waktu])], parse_mode="Markdown")
    except Exception as e: log.error(f"Reminder makan: {e}")

_ISTIRAHAT_SIANG = ["💤 *Habis makan, istirahat dulu ya sayang!* Rebahan sebentar cukup 🛋️❤️","😌 *Istirahat sebentar cintaku~* Badan butuh jeda lho 💕🌸"]
_BEGADANG_11     = ["🌙 *Sayang, udah jam 11!* Yuk bersiap tidur, jangan begadang 🥺💕❤️","⭐ *Udah larut malam~* Jangan begadang! Tubuh perlu istirahat 💤🌸❤️"]
_BEGADANG_12     = ["🌚 *Udah tengah malam sayang!* Yuk tidur, jangan begadang 🥺💕😴❤️","💤 *Tengah malam~* Yuk tidur sekarang! Jangan begadang 😔🌙❤️"]

async def send_reminder_istirahat(app, waktu: str):
    uid = FREYA_ID
    if not uid: return
    try:
        pools   = {"siang": _ISTIRAHAT_SIANG, "malam_11": _BEGADANG_11, "malam_12": _BEGADANG_12}
        day_idx = datetime.now(WITA).weekday()
        await app.bot.send_message(uid, pools[waktu][day_idx % len(pools[waktu])], parse_mode="Markdown")
    except Exception as e: log.error(f"Reminder istirahat: {e}")

# ═══════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════
def main():
    log.info("Inisialisasi Google Sheets...")
    init_sheets()

    app = Application.builder().token(BOT_TOKEN).build()

    conv_keuangan = ConversationHandler(
        entry_points=[CommandHandler("nabung", start_nabung), CommandHandler("keluar", start_keluar)],
        states={
            ASK_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_amount)],
            ASK_CAT:    [CallbackQueryHandler(got_cat)],
            ASK_DESC:   [MessageHandler(filters.TEXT & ~filters.COMMAND, got_desc)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        conversation_timeout=120,
    )
    conv_pengingat = ConversationHandler(
        entry_points=[CommandHandler("ingatkan", cmd_ingatkan_start)],
        states={
            REM_NAMA : [MessageHandler(filters.TEXT & ~filters.COMMAND, rem_got_nama)],
            REM_HARI : [MessageHandler(filters.TEXT & ~filters.COMMAND, rem_got_hari)],
            REM_JAM  : [MessageHandler(filters.TEXT & ~filters.COMMAND, rem_got_jam)],
            REM_PESAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, rem_got_pesan)],
        },
        fallbacks=[CommandHandler("cancel", rem_cancel)],
        conversation_timeout=180,
    )

    app.add_handler(conv_keuangan)
    app.add_handler(conv_pengingat)

    for cmd, fn in [
        ("start",             cmd_start),
        ("help",              cmd_start),
        ("myid",              cmd_myid),
        ("spreadsheet",       cmd_spreadsheet),
        ("saldo",             cmd_saldo),
        ("laporan",           cmd_laporan),
        ("bulanan",           cmd_bulanan),
        ("riwayat",           cmd_riwayat),
        ("bersama",           cmd_bersama),
        ("tujuan",            cmd_tujuan),
        ("addtarget",         cmd_addtarget),
        ("isitarget",         cmd_isitarget),
        ("catatan",           cmd_catatan),
        ("hapusterakhir",     cmd_hapusterakhir),
        ("streak",            cmd_streak),
        ("jadwal",            cmd_jadwal),
        ("daftarpengingat",   cmd_daftar_pengingat),
        ("hapuspengingat",    cmd_hapus_pengingat),
        ("matikanpengingat",  cmd_matikan_pengingat),
        ("aktifkanpengingat", cmd_aktifkan_pengingat),
        # ── Pesan antar user ──
        ("pesan",             cmd_pesan),
        ("izinkanpesan",      cmd_izinkan_pesan),
        ("tolakpesan",        cmd_tolak_pesan),
        ("statuspesan",       cmd_status_pesan),
    ]:
        app.add_handler(CommandHandler(cmd, fn))

    # AI — paling akhir
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ai_message))

    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_weekly_report,      "cron", day_of_week=REPORT_WEEKDAY, hour=REPORT_HOUR, minute=REPORT_MINUTE, timezone="Asia/Jakarta", args=[app])
    scheduler.add_job(send_streak_broken_alert,"cron", hour=7,  minute=0,  timezone="Asia/Makassar", args=[app])
    scheduler.add_job(send_snbt_reminder,      "cron", hour=7,  minute=30, timezone="Asia/Makassar", args=[app])
    scheduler.add_job(send_reminder_nabung,    "cron", hour=9,  minute=0,  timezone="Asia/Makassar", args=[app, "pagi"])
    scheduler.add_job(send_reminder_makan,     "cron", hour=9,  minute=0,  timezone="Asia/Makassar", args=[app, "pagi"])
    scheduler.add_job(send_reminder_makan,     "cron", hour=12, minute=30, timezone="Asia/Makassar", args=[app, "siang"])
    scheduler.add_job(send_reminder_istirahat, "cron", hour=12, minute=31, timezone="Asia/Makassar", args=[app, "siang"])
    scheduler.add_job(send_reminder_makan,     "cron", hour=15, minute=30, timezone="Asia/Makassar", args=[app, "sore"])
    scheduler.add_job(send_reminder_nabung,    "cron", hour=21, minute=0,  timezone="Asia/Makassar", args=[app, "malam"])
    scheduler.add_job(send_reminder_istirahat, "cron", hour=23, minute=0,  timezone="Asia/Makassar", args=[app, "malam_11"])
    scheduler.add_job(send_reminder_istirahat, "cron", hour=0,  minute=0,  timezone="Asia/Makassar", args=[app, "malam_12"])
    scheduler.add_job(check_custom_pengingat,  "cron", minute="*", timezone="Asia/Makassar", args=[app])
    scheduler.start()

    log.info("✅ TabunganBot berjalan!")
    log.info("💌 Fitur pesan antar user: AKTIF (butuh /izinkanpesan keduanya)")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()F
