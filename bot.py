#!/usr/bin/env python3
"""
TabunganBot 💰 + SNBT Study Scheduler
Google Sheets | Streak | Groq AI | Custom Reminder
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
FREYA_ID = USERS["Freya"]

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
#  JADWAL BIMBEL SNBT — HARDCODED
#  Setelah BIMBEL_END_DATE → fase mandiri, notif kelas berhenti
# ═══════════════════════════════════════════════════════════════
BIMBEL_END_DATE = date(2026, 4, 18)  # Hari terakhir mini tryout PK

# Jadwal kelas spesifik (format: "YYYY-MM-DD")
JADWAL_KELAS: dict[str, dict] = {
    "2026-04-07": {"subtes": "PK",  "tutor": "Kak Sugeng",                   "jam": "19.30–21.30 WIB", "tipe": "Kelas Utama"},
    "2026-04-08": {"subtes": "PM",  "tutor": "Kak Nisa",                     "jam": "19.30–21.30 WIB", "tipe": "Kelas Utama"},
    "2026-04-09": {"subtes": "PK",  "tutor": "Kak Sugeng",                   "jam": "19.30–21.30 WIB", "tipe": "Kelas Utama"},
    "2026-04-10": {"subtes": "LBI", "tutor": "Tutor Kampung Inggris Pare",   "jam": "19.30–21.30 WIB", "tipe": "Bonus"},
    "2026-04-11": {"subtes": "PM",  "tutor": "Guru PNS",                     "jam": "15.30–17.30 WIB", "tipe": "Bonus",
                   "extra": {"subtes": "LBI", "tutor": "Tutor S2 Luar Negeri", "jam": "19.30–21.30 WIB", "tipe": "Bonus"}},
    "2026-04-12": {"subtes": "PM",  "tutor": "Kak Nisa",                     "jam": "19.30–21.30 WIB", "tipe": "Kelas Utama"},
    "2026-04-13": {"subtes": "PK",  "tutor": "Kak Sugeng",                   "jam": "19.30–21.30 WIB", "tipe": "Kelas Utama"},
    "2026-04-14": {"subtes": "PM",  "tutor": "Kak Nisa",                     "jam": "19.30–21.30 WIB", "tipe": "Kelas Utama"},
    "2026-04-15": {"subtes": "PK",  "tutor": "Kak Sugeng",                   "jam": "19.30–21.30 WIB", "tipe": "Kelas Utama"},
    "2026-04-16": {"subtes": "PM",  "tutor": "Kak Nisa",                     "jam": "19.30–21.30 WIB", "tipe": "Kelas Utama"},
    "2026-04-17": {"subtes": "PM",  "tutor": "Mini Tryout",                  "jam": "19.30–20.30 WIB", "tipe": "Mini Tryout"},
    "2026-04-18": {"subtes": "PK",  "tutor": "Mini Tryout",                  "jam": "19.30–20.30 WIB", "tipe": "Mini Tryout"},
}

# Subtes SNBT lengkap beserta materi untuk belajar mandiri
SUBTES_MANDIRI = [
    {
        "kode" : "PU",
        "nama" : "Penalaran Umum",
        "emoji": "🧠",
        "tips" : "Latihan soal inferensi, analogi, silogisme & penalaran logis. Kerjain minimal 20 soal per sesi!",
    },
    {
        "kode" : "PK",
        "nama" : "Pengetahuan & Pemahaman Umum",
        "emoji": "📚",
        "tips" : "Review materi dari kelas Kak Sugeng, buat rangkuman, kerjain soal latihan!",
    },
    {
        "kode" : "PM",
        "nama" : "Penalaran Matematika",
        "emoji": "🔢",
        "tips" : "Review materi dari kelas Kak Nisa, latihan soal numerasi & aljabar dasar!",
    },
    {
        "kode" : "PBM",
        "nama" : "Literasi Bahasa Indonesia",
        "emoji": "📖",
        "tips" : "Baca teks lalu latihan soal pemahaman bacaan, penalaran teks & menyimpulkan isi!",
    },
    {
        "kode" : "LBI",
        "nama" : "Literasi Bahasa Inggris",
        "emoji": "🇬🇧",
        "tips" : "Reading comprehension, vocabulary in context, dan soal inferensi teks bahasa Inggris!",
    },
]

# Rotasi belajar mandiri di hari tanpa kelas (urut cycling)
_MANDIRI_CYCLE = ["PU", "PBM", "LBI", "PK", "PM"]

def _get_subtes_mandiri(tanggal: date) -> dict:
    """Return subtes mandiri berdasarkan hari (cycling index)."""
    idx = tanggal.toordinal() % len(_MANDIRI_CYCLE)
    kode = _MANDIRI_CYCLE[idx]
    return next(s for s in SUBTES_MANDIRI if s["kode"] == kode)

def _get_jadwal_hari_ini() -> dict | None:
    """Return jadwal kelas hari ini kalau ada, None kalau tidak ada."""
    today_str = datetime.now(WIB).strftime("%Y-%m-%d")
    return JADWAL_KELAS.get(today_str)

def _is_bimbel_active() -> bool:
    """Cek apakah masih dalam periode bimbel."""
    return date.today() <= BIMBEL_END_DATE

def _format_kelas(jadwal: dict, prefix: str = "") -> str:
    """Format info kelas jadi string pesan."""
    subtes_info = next((s for s in SUBTES_MANDIRI if s["kode"] == jadwal["subtes"]), None)
    emoji = subtes_info["emoji"] if subtes_info else "📌"
    tipe  = jadwal["tipe"]
    icon  = "🎁" if "Bonus" in tipe else ("📝" if "Tryout" in tipe else "📌")
    return (
        f"{prefix}{icon} *{tipe}* — {emoji} {jadwal['subtes']}\n"
        f"   👨‍🏫 {jadwal['tutor']}\n"
        f"   🕐 {jadwal['jam']}"
    )

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
#  GOOGLE SHEETS CLIENT
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
    _get_or_create_sheet(ss, "Pengingat", [
        "ID","UserID","Nama","Hari","Jam","Pesan","Aktif","Dibuat"
        # Hari: "senin,rabu,jumat" atau "setiap hari" atau "2026-04-10"
        # Jam : "19:00"
        # Aktif: "Ya" / "Tidak"
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
    rows = db_get_transactions(uid)
    return sum((float(r["Jumlah"]) if r["Tipe"] == "income" else -float(r["Jumlah"])) for r in rows)

def db_get_summary(uid: int, since_days: int = 7):
    rows = db_get_transactions(uid, since_days=since_days)
    inc = sum(float(r["Jumlah"]) for r in rows if r["Tipe"] == "income")
    exp = sum(float(r["Jumlah"]) for r in rows if r["Tipe"] == "expense")
    return inc, exp, rows

def db_delete_last_transaction(uid: int) -> bool:
    ws = _ss().worksheet("Transaksi")
    for i in range(len(ws.get_all_values()) - 1, 0, -1):
        if str(ws.get_all_values()[i][1]) == str(uid):
            ws.delete_rows(i + 1)
            return True
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
    ws        = _ss().worksheet("Streak")
    all_vals  = ws.get_all_values()
    today     = _today_wita()
    yesterday = _yesterday_wita()
    row_idx   = None
    current = longest = 0
    last_date = ""
    for i, row in enumerate(all_vals[1:], start=2):
        if str(row[0]) == str(uid):
            row_idx = i; current = int(row[1] or 0)
            longest = int(row[2] or 0); last_date = str(row[3] or "")
            break
    milestone_hit = None
    if last_date == today:
        pass
    elif last_date == yesterday:
        current += 1
    else:
        current = 1
    longest = max(longest, current)
    if current in STREAK_MILESTONES:
        milestone_hit = current
    if row_idx:
        ws.update(f"B{row_idx}:D{row_idx}", [[current, longest, today]])
    else:
        ws.append_row([uid, current, longest, today], value_input_option="USER_ENTERED")
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
    "jumat": 4, "sabtu": 5, "minggu": 6,
    "setiap hari": -1,
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
    if aktif_only:
        result = [r for r in result if str(r["Aktif"]) == "Ya"]
    return result

def db_get_all_pengingat_aktif() -> list[dict]:
    return [r for r in _ss().worksheet("Pengingat").get_all_records()
            if str(r["Aktif"]) == "Ya"]

def db_toggle_pengingat(pid: int, aktif: bool) -> bool:
    ws = _ss().worksheet("Pengingat")
    for i, row in enumerate(ws.get_all_values()[1:], start=2):
        if str(row[0]) == str(pid):
            ws.update_cell(i, 7, "Ya" if aktif else "Tidak")
            return True
    return False

def db_delete_pengingat(pid: int) -> bool:
    ws = _ss().worksheet("Pengingat")
    for i, row in enumerate(ws.get_all_values()[1:], start=2):
        if str(row[0]) == str(pid):
            ws.delete_rows(i + 1)
            return True
    return False

def _should_fire_pengingat(row: dict, now_wita: datetime) -> bool:
    """
    Cek apakah pengingat ini harus dikirim sekarang.
    Hari format: "setiap hari" | "senin,rabu" | "2026-04-10"
    Jam format : "HH:MM"
    """
    try:
        jam_parts = str(row["Jam"]).split(":")
        h, m = int(jam_parts[0]), int(jam_parts[1])
        if now_wita.hour != h or now_wita.minute != m:
            return False

        hari_raw = str(row["Hari"]).lower().strip()

        # Tanggal spesifik, misal "2026-04-10"
        if hari_raw.count("-") == 2:
            return now_wita.strftime("%Y-%m-%d") == hari_raw

        # "setiap hari"
        if hari_raw == "setiap hari":
            return True

        # "senin,rabu,jumat" dst
        hari_list = [h.strip() for h in hari_raw.split(",")]
        hari_angka = [HARI_MAP.get(h, -99) for h in hari_list]
        return now_wita.weekday() in hari_angka
    except Exception as e:
        log.error(f"Error cek pengingat: {e}")
        return False

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
#  GROQ AI ASSISTANT
# ═══════════════════════════════════════════════════════════════
_chat_history: dict[int, list[dict]] = {}

_SYSTEM_PROMPT = """Kamu adalah asisten TabunganBot yang ramah.
Bot ini milik Fahril dan Freya untuk pencatatan keuangan + belajar SNBT/UTBK.

CARA KERJA /nabung DAN /keluar:
1. Ketik /nabung atau /keluar
2. Masukkan JUMLAH (angka)
3. Pilih KATEGORI (tombol)
4. Masukkan CATATAN — ketik teks ATAU ketik tanda minus "-" untuk skip step ini

MASALAH UMUM:
- Kalau user bilang "aku udah nabung" tapi belum tersimpan → kemungkinan lupa ketik "-" di step catatan. Suruh ketik "-".
- Kalau stuck → suruh /cancel dulu lalu coba lagi.

SNBT INFO:
- Freya lagi bimbel SNBT dengan jadwal kelas PK (Kak Sugeng) dan PM (Kak Nisa)
- Ada 5 subtes: PU (Penalaran Umum), PK, PM, PBM (Literasi B.Indo), LBI (Literasi B.Inggris)
- Bimbel selesai 18 April 2026

CUSTOM REMINDER: Freya bisa set pengingat custom dengan /ingatkan

KEPRIBADIAN: Bahasa Indonesia santai, ramah, singkat, boleh emoji. Maksimal 3-4 kalimat.

COMMAND: /nabung /keluar /saldo /laporan /bulanan /riwayat /streak /jadwal /ingatkan /daftarpengingat /tujuan /bersama /catatan /hapusterakhir /spreadsheet
"""

def _groq_chat(uid: int, user_message: str, user_name: str) -> str:
    client  = Groq(api_key=GROQ_API_KEY)
    history = _chat_history.get(uid, [])
    history.append({"role": "user", "content": f"[{user_name}] {user_message}"})
    if len(history) > 10:
        history = history[-10:]
    _chat_history[uid] = history
    resp  = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "system", "content": _SYSTEM_PROMPT}, *history],
        max_tokens=300, temperature=0.7,
    )
    reply = resp.choices[0].message.content.strip()
    history.append({"role": "assistant", "content": reply})
    _chat_history[uid] = history
    return reply

async def handle_ai_message(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = u.effective_user.id
    if not authorized(uid): return
    msg = u.message.text or ""
    if not msg.strip(): return
    await ctx.bot.send_chat_action(chat_id=u.effective_chat.id, action="typing")
    try:
        reply = await run(_groq_chat, uid, msg, get_user_name(uid) or "User")
        await u.message.reply_text(reply)
    except Exception as e:
        log.error(f"Groq error: {e}")
        await u.message.reply_text("AI-nya lagi gangguan bentar 😅 Coba lagi ya!")

# ═══════════════════════════════════════════════════════════════
#  COMMAND: /jadwal
# ═══════════════════════════════════════════════════════════════
async def cmd_jadwal(u: Update, _):
    if not await check_auth(u): return
    now      = datetime.now(WIB)
    today    = date.today()
    lines    = [f"📅 *Jadwal SNBT Freya*\n_{now.strftime('%d %B %Y')}_\n"]

    # Status fase
    if _is_bimbel_active():
        sisa = (BIMBEL_END_DATE - today).days
        lines.append(f"🎓 *Fase Bimbel* — selesai *{BIMBEL_END_DATE.strftime('%d %B %Y')}* ({sisa} hari lagi)\n")
    else:
        lines.append("📖 *Fase Belajar Mandiri* — bimbel sudah selesai 🎉\n")

    # Jadwal 7 hari ke depan
    lines.append("━━━━━━━━━━━━━━━━━")
    lines.append("📆 *7 Hari ke Depan:*\n")
    HARI_ID = ["Senin","Selasa","Rabu","Kamis","Jumat","Sabtu","Minggu"]

    for i in range(7):
        d = today + timedelta(days=i)
        d_str   = d.strftime("%Y-%m-%d")
        label   = "Hari ini" if i == 0 else HARI_ID[d.weekday()]
        jadwal  = JADWAL_KELAS.get(d_str)

        if jadwal and d <= BIMBEL_END_DATE:
            # Ada kelas
            emoji_tipe = "🎁" if "Bonus" in jadwal["tipe"] else ("📝" if "Tryout" in jadwal["tipe"] else "🏫")
            subtes_info = next((s for s in SUBTES_MANDIRI if s["kode"] == jadwal["subtes"]), None)
            sem = subtes_info["emoji"] if subtes_info else "📌"
            lines.append(f"*{label}, {d.strftime('%d/%m')}*")
            lines.append(f"  {emoji_tipe} {jadwal['tipe']}: {sem} {jadwal['subtes']} — {jadwal['tutor']}")
            lines.append(f"  🕐 {jadwal['jam']}")
            if "extra" in jadwal:
                ex = jadwal["extra"]
                ex_info = next((s for s in SUBTES_MANDIRI if s["kode"] == ex["subtes"]), None)
                ex_em = ex_info["emoji"] if ex_info else "📌"
                lines.append(f"  🎁 {ex['tipe']}: {ex_em} {ex['subtes']} — {ex['tutor']}")
                lines.append(f"  🕐 {ex['jam']}")
        else:
            # Belajar mandiri
            subtes = _get_subtes_mandiri(d)
            lines.append(f"*{label}, {d.strftime('%d/%m')}*")
            lines.append(f"  📖 Mandiri: {subtes['emoji']} {subtes['nama']}")
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━")
    lines.append("*Subtes SNBT:* PU • PK • PM • PBM • LBI")
    await u.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ═══════════════════════════════════════════════════════════════
#  COMMAND: /ingatkan — set custom reminder
#  Flow: Nama → Hari → Jam → Pesan
# ═══════════════════════════════════════════════════════════════
async def cmd_ingatkan_start(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(u): return
    await u.message.reply_text(
        "⏰ *Buat Pengingat Baru*\n\n"
        "Langkah 1/4: Kasih nama pengingat ini apa?\n"
        "_Contoh: PR Matematika, Review PK, Latihan Soal PU_",
        parse_mode="Markdown"
    )
    return REM_NAMA

async def rem_got_nama(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["rem_nama"] = u.message.text.strip()
    await u.message.reply_text(
        f"✅ Nama: *{ctx.user_data['rem_nama']}*\n\n"
        "Langkah 2/4: Mau diingatkan hari apa?\n\n"
        "_Pilihan:_\n"
        "• `setiap hari`\n"
        "• Nama hari: `senin`, `selasa`, `rabu`, `kamis`, `jumat`, `sabtu`, `minggu`\n"
        "• Kombinasi: `senin,rabu,jumat`\n"
        "• Tanggal spesifik: `2026-04-10`",
        parse_mode="Markdown"
    )
    return REM_HARI

async def rem_got_hari(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    hari_raw = u.message.text.strip().lower()
    # Validasi
    valid = False
    if hari_raw == "setiap hari":
        valid = True
    elif hari_raw.count("-") == 2:  # format tanggal
        try:
            datetime.strptime(hari_raw, "%Y-%m-%d")
            valid = True
        except: pass
    else:
        parts = [h.strip() for h in hari_raw.split(",")]
        if all(h in HARI_MAP for h in parts):
            valid = True

    if not valid:
        await u.message.reply_text(
            "❌ Format hari tidak dikenali.\n"
            "Contoh: `setiap hari`, `senin,rabu`, `2026-04-10`",
            parse_mode="Markdown"
        )
        return REM_HARI

    ctx.user_data["rem_hari"] = hari_raw
    await u.message.reply_text(
        f"✅ Hari: *{hari_raw}*\n\n"
        "Langkah 3/4: Jam berapa?\n"
        "_Format 24 jam: `HH:MM`_\n"
        "Contoh: `19:00`, `08:30`, `21:00`",
        parse_mode="Markdown"
    )
    return REM_JAM

async def rem_got_jam(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    jam_raw = u.message.text.strip()
    try:
        parts = jam_raw.split(":")
        h, m = int(parts[0]), int(parts[1])
        assert 0 <= h <= 23 and 0 <= m <= 59
        jam_str = f"{h:02d}:{m:02d}"
    except:
        await u.message.reply_text("❌ Format jam salah. Contoh: `19:00`", parse_mode="Markdown")
        return REM_JAM

    ctx.user_data["rem_jam"] = jam_str
    await u.message.reply_text(
        f"✅ Jam: *{jam_str} WITA*\n\n"
        "Langkah 4/4: Apa pesan pengingatnya?\n"
        "_Contoh: Jangan lupa kerjain PR Matematika dari Kak Nisa ya! 📚_",
        parse_mode="Markdown"
    )
    return REM_PESAN

async def rem_got_pesan(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["rem_pesan"] = u.message.text.strip()
    uid   = u.effective_user.id
    nama  = ctx.user_data["rem_nama"]
    hari  = ctx.user_data["rem_hari"]
    jam   = ctx.user_data["rem_jam"]
    pesan = ctx.user_data["rem_pesan"]

    wait = await u.message.reply_text("⏳ Menyimpan pengingat...")
    pid  = await run(db_add_pengingat, uid, nama, hari, jam, pesan)
    await wait.delete()

    await u.message.reply_text(
        f"✅ *Pengingat Berhasil Dibuat!* (ID: {pid})\n\n"
        f"📌 Nama  : *{nama}*\n"
        f"📅 Hari  : {hari}\n"
        f"🕐 Jam   : {jam} WITA\n"
        f"💬 Pesan : _{pesan}_\n\n"
        f"Lihat semua pengingat: /daftarpengingat\n"
        f"Hapus: `/hapuspengingat {pid}`",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

async def rem_cancel(u: Update, _):
    await u.message.reply_text("❌ Pembuatan pengingat dibatalkan.")
    return ConversationHandler.END

# ─── /daftarpengingat ────────────────────────────────────────────
async def cmd_daftar_pengingat(u: Update, _):
    if not await check_auth(u): return
    uid  = u.effective_user.id
    wait = await u.message.reply_text("⏳ Memuat pengingat...")
    rows = await run(db_get_pengingat, uid, False)  # semua, aktif maupun tidak
    await wait.delete()

    if not rows:
        await u.message.reply_text(
            "📭 Belum ada pengingat.\n\nBuat pengingat baru: /ingatkan",
            parse_mode="Markdown"
        )
        return

    lines = ["⏰ *Daftar Pengingat Kamu*\n"]
    for r in rows:
        status = "🟢" if str(r["Aktif"]) == "Ya" else "🔴"
        lines.append(
            f"{status} *[ID {r['ID']}]* {r['Nama']}\n"
            f"   📅 {r['Hari']}  🕐 {r['Jam']} WITA\n"
            f"   💬 _{r['Pesan']}_\n"
        )

    lines.append("━━━━━━━━━━━━━━━━━")
    lines.append("Hapus   : `/hapuspengingat [id]`")
    lines.append("Matikan : `/matikanpengingat [id]`")
    lines.append("Aktifkan: `/aktifkanpengingat [id]`")
    await u.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ─── /hapuspengingat /matikanpengingat /aktifkanpengingat ───────
async def cmd_hapus_pengingat(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(u): return
    if not ctx.args or not ctx.args[0].isdigit():
        await u.message.reply_text("Format: `/hapuspengingat [id]`\nLihat ID di /daftarpengingat", parse_mode="Markdown"); return
    pid  = int(ctx.args[0])
    wait = await u.message.reply_text("⏳ Menghapus...")
    ok   = await run(db_delete_pengingat, pid)
    await wait.delete()
    await u.message.reply_text(f"{'✅ Pengingat ID '+str(pid)+' dihapus.' if ok else '❌ ID tidak ditemukan.'}")

async def cmd_matikan_pengingat(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(u): return
    if not ctx.args or not ctx.args[0].isdigit():
        await u.message.reply_text("Format: `/matikanpengingat [id]`", parse_mode="Markdown"); return
    ok = await run(db_toggle_pengingat, int(ctx.args[0]), False)
    await u.message.reply_text(f"{'🔴 Pengingat dimatikan.' if ok else '❌ ID tidak ditemukan.'}")

async def cmd_aktifkan_pengingat(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(u): return
    if not ctx.args or not ctx.args[0].isdigit():
        await u.message.reply_text("Format: `/aktifkanpengingat [id]`", parse_mode="Markdown"); return
    ok = await run(db_toggle_pengingat, int(ctx.args[0]), True)
    await u.message.reply_text(f"{'🟢 Pengingat diaktifkan.' if ok else '❌ ID tidak ditemukan.'}")

# ═══════════════════════════════════════════════════════════════
#  COMMAND HANDLERS — KEUANGAN
# ═══════════════════════════════════════════════════════════════
async def cmd_start(u: Update, _):
    uid = u.effective_user.id
    if not authorized(uid):
        await u.message.reply_text(f"👋 Bot ini khusus Fahril & Freya.\n🪪 ID kamu: `{uid}`", parse_mode="Markdown"); return
    name = get_user_name(uid)
    wait = await u.message.reply_text("⏳ Memuat saldo...")
    bal  = await run(db_get_balance, uid)
    await wait.delete()
    await u.message.reply_text(
        f"👋 Halo *{name}*!\n💰 Saldo: *{rp(bal)}*\n\n"
        "━━━━━━━━━━━━━━━━━\n"
        "📌 *Menu Keuangan:*\n"
        "➕ /nabung  ➖ /keluar  💼 /saldo\n"
        "📊 /laporan  📅 /bulanan  📜 /riwayat\n"
        "🔥 /streak  🎯 /tujuan  👥 /bersama\n"
        "🗒️ /catatan  ↩️ /hapusterakhir\n\n"
        "━━━━━━━━━━━━━━━━━\n"
        "📌 *Menu Belajar SNBT (Freya):*\n"
        "📅 /jadwal — Jadwal belajar\n"
        "⏰ /ingatkan — Buat pengingat custom\n"
        "📋 /daftarpengingat — Semua pengingat\n\n"
        "━━━━━━━━━━━━━━━━━\n"
        "_💬 Bisa ngobrol bebas juga, ada AI!_\n"
        "_📊 Data tersimpan di Google Sheets_",
        parse_mode="Markdown")

async def cmd_myid(u: Update, _):
    uid  = u.effective_user.id
    name = get_user_name(uid) or "Belum terdaftar"
    await u.message.reply_text(f"🪪 *Info Akun*\n\nID: `{uid}`\nNama: *{name}*", parse_mode="Markdown")

async def cmd_spreadsheet(u: Update, _):
    if not await check_auth(u): return
    await u.message.reply_text(f"🔗 https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}", parse_mode="Markdown")

async def cmd_streak(u: Update, _):
    if not await check_auth(u): return
    uid  = u.effective_user.id
    name = get_user_name(uid)
    wait = await u.message.reply_text("⏳ Memuat streak...")
    data = await run(db_get_streak, uid)
    await wait.delete()
    cur     = data["current"]
    lng     = data["longest"]
    badge   = streak_badge(cur)
    bar     = streak_bar(cur)
    next_ms = next((m for m in STREAK_MILESTONES if m > cur), None)
    cycle   = (cur % 30) or (30 if cur > 0 and cur % 30 == 0 else 0)
    pct     = min(100, cycle / 30 * 100)
    lines   = [f"🔥 *Streak — {name}*\n",
               f"{badge} *{cur} Hari*  _{streak_title(cur)}_\n",
               f"`{bar}` {pct:.0f}% menuju 30 hari",
               f"🏅 Terpanjang: *{lng} hari*"]
    if next_ms:
        lines.append(f"🎯 Berikutnya: *{next_ms} hari* ({next_ms-cur} lagi)")
    lines.append("\n🏆 *Milestone:*")
    for ms in STREAK_MILESTONES:
        if cur >= ms:      lines.append(f"  ✅ {ms}hr — {streak_badge(ms)}")
        elif ms == next_ms: lines.append(f"  ⏳ {ms}hr — {streak_badge(ms)} ← next")
        else:              lines.append(f"  🔒 {ms}hr")
    await u.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_saldo(u: Update, _):
    if not await check_auth(u): return
    uid  = u.effective_user.id
    name = get_user_name(uid)
    wait = await u.message.reply_text("⏳ Mengambil data...")
    bal              = await run(db_get_balance, uid)
    inc7,  exp7,  _  = await run(db_get_summary, uid, 7)
    inc30, exp30, _  = await run(db_get_summary, uid, 30)
    streak_data      = await run(db_get_streak, uid)
    await wait.delete()
    await u.message.reply_text(
        f"💼 *Saldo — {name}*\n\n"
        f"💰 *{rp(bal)}*\n\n"
        f"━━━ 7 Hari ━━━\n📈 {rp(inc7)}  📉 {rp(exp7)}  📊 {rp(inc7-exp7)}\n\n"
        f"━━━ 30 Hari ━━\n📈 {rp(inc30)}  📉 {rp(exp30)}  📊 {rp(inc30-exp30)}\n\n"
        f"━━━ Streak ━━━\n{_streak_summary(streak_data)}",
        parse_mode="Markdown")

async def cmd_laporan(u: Update, _):
    if not await check_auth(u): return
    uid  = u.effective_user.id
    name = get_user_name(uid)
    wait = await u.message.reply_text("⏳ Menyusun laporan...")
    inc, exp, rows = await run(db_get_summary, uid, 7)
    bal            = await run(db_get_balance, uid)
    await wait.delete()
    lines = [f"📊 *Laporan 7 Hari — {name}*",
             f"_{datetime.now(WIB).strftime('%d %B %Y')}_\n",
             f"📈 *{rp(inc)}*  📉 *{rp(exp)}*  💰 *{rp(bal)}*\n",
             "📜 *Transaksi:*"]
    for r in rows[:12]:
        icon = "⬆️" if r["Tipe"] == "income" else "⬇️"
        note = f" _{r['Catatan']}_" if r.get("Catatan") else ""
        lines.append(f"{icon} *{rp(float(r['Jumlah']))}* — {r['Kategori']}{note}")
        lines.append(f"    `{str(r['Waktu'])[:16]}`")
    if not rows: lines.append("_Tidak ada transaksi._")
    await u.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_bulanan(u: Update, _):
    if not await check_auth(u): return
    uid  = u.effective_user.id
    name = get_user_name(uid)
    now  = datetime.now(WIB)
    wait = await u.message.reply_text("⏳ Menyusun laporan bulanan...")
    inc, exp, _ = await run(db_get_summary, uid, now.day + 1)
    cats        = await run(db_get_monthly_cats, uid)
    bal         = await run(db_get_balance, uid)
    await wait.delete()
    lines = [f"📅 *Laporan Bulanan — {name}*", f"_{now.strftime('%B %Y')}_\n",
             f"📈 *{rp(inc)}*  📉 *{rp(exp)}*  📊 *{rp(inc-exp)}*  💰 *{rp(bal)}*\n"]
    inc_cats = [(c, a) for c, t, a in cats if t == "income"]
    exp_cats = [(c, a) for c, t, a in cats if t == "expense"]
    if inc_cats:
        lines.append("📈 *Pemasukan:*")
        for c, a in inc_cats: lines.append(f"  • {c}: *{rp(a)}*")
        lines.append("")
    if exp_cats:
        lines.append("📉 *Pengeluaran:*")
        for c, a in exp_cats: lines.append(f"  • {c}: *{rp(a)}*")
    await u.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_riwayat(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(u): return
    uid  = u.effective_user.id
    name = get_user_name(uid)
    n    = min(int(ctx.args[0]) if ctx.args and ctx.args[0].isdigit() else 10, 30)
    wait = await u.message.reply_text("⏳ Mengambil riwayat...")
    rows = await run(db_get_transactions, uid, None, n)
    await wait.delete()
    lines = [f"📜 *{n} Transaksi Terakhir — {name}*\n"]
    for r in rows:
        icon = "⬆️" if r["Tipe"] == "income" else "⬇️"
        note = f"\n     _{r['Catatan']}_" if r.get("Catatan") else ""
        lines.append(f"{icon} *{rp(float(r['Jumlah']))}* — {r['Kategori']}{note}")
        lines.append(f"    `{str(r['Waktu'])[:16]}`\n")
    if not rows: lines.append("Belum ada transaksi.")
    await u.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_bersama(u: Update, _):
    if not await check_auth(u): return
    wait = await u.message.reply_text("⏳ Memuat data berdua...")
    lines = ["👥 *Rekap Bersama — Fahril & Freya*", f"_{datetime.now(WIB).strftime('%d %B %Y')}_\n"]
    total_bal = total_inc = total_exp = 0.0
    for name, uid in USERS.items():
        if uid == 0: continue
        bal           = await run(db_get_balance, uid)
        inc7, exp7, _ = await run(db_get_summary, uid, 7)
        streak_data   = await run(db_get_streak, uid)
        total_bal += bal; total_inc += inc7; total_exp += exp7
        cur = streak_data["current"]
        lines += [f"👤 *{name}*", f"  💰 {rp(bal)}  📈 {rp(inc7)}  📉 {rp(exp7)}",
                  f"  {streak_badge(cur)} Streak *{cur} hari* — _{streak_title(cur)}_\n"]
    lines += ["━━━━━━━━━━━━━━━━━",
              f"  💰 Total: *{rp(total_bal)}*  📊 Selisih: *{rp(total_inc-total_exp)}*"]
    await wait.delete()
    await u.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_tujuan(u: Update, _):
    if not await check_auth(u): return
    uid  = u.effective_user.id
    name = get_user_name(uid)
    wait = await u.message.reply_text("⏳ Memuat target...")
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
    except:
        await u.message.reply_text("❌ Format salah.", parse_mode="Markdown")

async def cmd_isitarget(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(u): return
    if not ctx.args or len(ctx.args) < 2:
        await u.message.reply_text("Format: `/isitarget [id] [jumlah]`", parse_mode="Markdown"); return
    try:
        goal_id = int(ctx.args[0])
        amount  = float(ctx.args[1].replace(".", "").replace(",", ""))
        wait    = await u.message.reply_text("⏳ Memperbarui...")
        target, saved = await run(db_update_goal, goal_id, amount)
        await wait.delete()
        if target is None:
            await u.message.reply_text("❌ Target tidak ditemukan."); return
        pct = min(100.0, saved/target*100)
        await u.message.reply_text(
            f"{'✅ *Target Tercapai! 🎉*' if saved>=target else '🔄 *Progres Diperbarui!*'}\n\n"
            f"`{progress_bar(pct)}` {pct:.1f}%\n{rp(saved)}/{rp(target)}",
            parse_mode="Markdown")
    except:
        await u.message.reply_text("❌ Format salah.", parse_mode="Markdown")

async def cmd_catatan(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(u): return
    uid  = u.effective_user.id
    name = get_user_name(uid)
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
        else:
            lines.append("Belum ada. Simpan: `/catatan [teks]`")
        await u.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_hapusterakhir(u: Update, _):
    if not await check_auth(u): return
    uid  = u.effective_user.id
    wait = await u.message.reply_text("⏳ Menghapus...")
    ok   = await run(db_delete_last_transaction, uid)
    bal  = await run(db_get_balance, uid)
    await wait.delete()
    if ok:
        await u.message.reply_text(f"↩️ Terhapus.\n💰 Saldo: *{rp(bal)}*", parse_mode="Markdown")
    else:
        await u.message.reply_text("❌ Tidak ada transaksi.")

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
    try:
        ctx.user_data["amount"] = float(txt)
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
    name   = get_user_name(uid)
    kind   = ctx.user_data["kind"]
    amount = ctx.user_data["amount"]
    cat    = ctx.user_data.get("category", "📦 Lainnya")
    note   = ctx.user_data.get("desc") or ""
    wait   = await msg.reply_text("⏳ Menyimpan...")
    await run(db_add_transaction, uid, name, kind, amount, cat, note)
    bal         = await run(db_get_balance, uid)
    streak_data = await run(db_update_streak, uid)
    await wait.delete()
    icon = "📈" if kind == "income" else "📉"
    cur  = streak_data["current"]
    await msg.reply_text(
        f"{icon} *{'Pemasukan' if kind=='income' else 'Pengeluaran'} Berhasil!*\n\n"
        f"👤 {name}  💵 *{rp(amount)}*\n"
        f"📂 {cat}  📝 {note or '-'}\n\n"
        f"💰 Saldo: *{rp(bal)}*\n_✅ Tersimpan_\n\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"{streak_badge(cur)} *Streak: {cur} hari* — _{streak_title(cur)}_\n`{streak_bar(cur)}`",
        parse_mode="Markdown")
    ms = streak_data.get("milestone_hit")
    if ms:
        milestone_msgs = {
            3:"🌱 *Streak 3 Hari!* Mulai tumbuh! 💪",7:"✨ *1 Minggu!* Konsisten! 🎉",
            14:"🔥 *2 Minggu!* Nonstop! 🔥",21:"💪 *3 Minggu!* Kebiasaan terbentuk! 🏆",
            30:"⚡ *1 BULAN! 🎊* Luar biasa! 💰",60:"🏆 *2 BULAN! 🎊* Pro nabung! 👑",
            90:"🌟 *90 HARI! 🎊* Legend! 🌟",100:"👑 *100 HARI! 🎊* SERATUS! 🎉",
            365:"🚀 *1 TAHUN! 🎊* GOAT! 🐐",
        }
        await msg.reply_text(milestone_msgs.get(ms, f"🎉 Streak {ms} Hari! 💪"), parse_mode="Markdown")

async def cancel(u: Update, _):
    await u.message.reply_text("❌ Dibatalkan.")
    return ConversationHandler.END

# ═══════════════════════════════════════════════════════════════
#  SCHEDULED JOBS
# ═══════════════════════════════════════════════════════════════

# ── Weekly Report ────────────────────────────────────────────────
async def send_weekly_report(app):
    for name, uid in USERS.items():
        if uid == 0: continue
        try:
            inc, exp, rows = await run(db_get_summary, uid, 7)
            bal            = await run(db_get_balance, uid)
            goals          = await run(db_get_goals, uid)
            streak_data    = await run(db_get_streak, uid)
            cur = streak_data["current"]
            lines = [f"📊 *Laporan Mingguan — {name}*",
                     f"_{datetime.now(WIB).strftime('%d %B %Y')}_\n",
                     f"📈 *{rp(inc)}*  📉 *{rp(exp)}*  💰 *{rp(bal)}*\n",
                     f"{streak_badge(cur)} Streak *{cur} hari* — _{streak_title(cur)}_\n"]
            if rows:
                lines.append("📜 *Transaksi:*")
                for r in rows[:8]:
                    lines.append(f"{'⬆️' if r['Tipe']=='income' else '⬇️'} {rp(float(r['Jumlah']))} — {r['Kategori']}")
                lines.append("")
            else:
                lines.append("_Tidak ada transaksi minggu ini._\n")
            active = [r for r in goals if r.get("Selesai") != "Ya"]
            if active:
                lines.append("🎯 *Target:*")
                for r in active[:3]:
                    pct = min(100.0, float(r["Terkumpul"])/float(r["Target"])*100)
                    lines.append(f"  {r['Judul']}: `{progress_bar(pct, 8)}` {pct:.0f}%")
            lines.append("\n_TabunganBot 🤖 — Semangat!_ 💪")
            await app.bot.send_message(uid, "\n".join(lines), parse_mode="Markdown")
        except Exception as e:
            log.error(f"Weekly report error {name}: {e}")

# ── SNBT Study Reminder — Freya ───────────────────────────────────
async def send_snbt_reminder(app):
    """
    Kirim reminder belajar SNBT ke Freya tiap pagi.
    FASE 1 (s.d. 18 April): kalau ada kelas → ingatkan kelas,
                             kalau tidak → ingatkan belajar mandiri subtest lain.
    FASE 2 (setelah 18 April): ingatkan belajar mandiri semua subtes bergilir.
    """
    uid = FREYA_ID
    if uid == 0: return
    try:
        today     = date.today()
        today_str = today.strftime("%Y-%m-%d")
        now_wib   = datetime.now(WIB)

        if _is_bimbel_active():
            # ── FASE 1: Periode bimbel ─────────────────────────────
            jadwal = JADWAL_KELAS.get(today_str)

            if jadwal:
                # Ada kelas hari ini
                subtes_info = next((s for s in SUBTES_MANDIRI if s["kode"] == jadwal["subtes"]), None)
                em = subtes_info["emoji"] if subtes_info else "📌"
                tipe_icon = "🎁" if "Bonus" in jadwal["tipe"] else ("📝" if "Tryout" in jadwal["tipe"] else "🏫")

                msg = (
                    f"📚 *Reminder Belajar SNBT* — {now_wib.strftime('%d %B %Y')}\n\n"
                    f"{tipe_icon} *{jadwal['tipe']}* hari ini, sayang!\n\n"
                    f"  {em} *{jadwal['subtes']}* — 👨‍🏫 {jadwal['tutor']}\n"
                    f"  🕐 {jadwal['jam']}\n"
                )
                if "extra" in jadwal:
                    ex = jadwal["extra"]
                    ex_info = next((s for s in SUBTES_MANDIRI if s["kode"] == ex["subtes"]), None)
                    ex_em   = ex_info["emoji"] if ex_info else "📌"
                    msg += (
                        f"\n  🎁 *Bonus juga*: {ex_em} {ex['subtes']} — {ex['tutor']}\n"
                        f"  🕐 {ex['jam']}\n"
                    )
                msg += (
                    f"\nLink Zoom dikirim sebelum kelas ya 📩\n"
                    f"_Semangat belajarnya cintaku! 💕 Aku support kamu!_ 🤖❤️\n\n"
                    f"📅 /jadwal — Lihat jadwal lengkap"
                )
            else:
                # Tidak ada kelas → belajar mandiri subtest lain
                subtes = _get_subtes_mandiri(today)
                msg = (
                    f"📚 *Reminder Belajar Mandiri* — {now_wib.strftime('%d %B %Y')}\n\n"
                    f"Hari ini nggak ada kelas, tapi tetap belajar ya sayang! 💪\n\n"
                    f"{subtes['emoji']} *{subtes['nama']} ({subtes['kode']})*\n"
                    f"📝 _{subtes['tips']}_\n\n"
                    f"_Konsisten belajar tiap hari kunci sukses SNBT! 🎯_\n"
                    f"_Aku selalu support kamu cintaku~ 🤖❤️_\n\n"
                    f"📅 /jadwal — Lihat jadwal lengkap"
                )
        else:
            # ── FASE 2: Setelah bimbel selesai ────────────────────
            subtes = _get_subtes_mandiri(today)
            msg = (
                f"📚 *Belajar Mandiri SNBT* — {now_wib.strftime('%d %B %Y')}\n\n"
                f"Bimbel udah selesai, sekarang saatnya latihan mandiri sayang! 💪\n\n"
                f"{subtes['emoji']} *{subtes['nama']} ({subtes['kode']})*\n"
                f"📝 _{subtes['tips']}_\n\n"
                f"_Kamu pasti bisa! Aku percaya sama kamu 🤖❤️_\n\n"
                f"📅 /jadwal — Lihat jadwal belajar"
            )

        await app.bot.send_message(uid, msg, parse_mode="Markdown")
        log.info(f"SNBT reminder terkirim ke Freya (fase {'bimbel' if _is_bimbel_active() else 'mandiri'})")
    except Exception as e:
        log.error(f"SNBT reminder error: {e}")

# ── Cek Pengingat Custom — setiap menit ─────────────────────────
async def check_custom_pengingat(app):
    """Cek semua pengingat custom dan kirim kalau cocok jam & harinya."""
    try:
        now_wita = datetime.now(WITA)
        rows     = await run(db_get_all_pengingat_aktif)
        for r in rows:
            if _should_fire_pengingat(r, now_wita):
                uid = int(r["UserID"]) if str(r["UserID"]).isdigit() else 0
                if uid == 0: continue
                msg = (
                    f"⏰ *Pengingat: {r['Nama']}*\n\n"
                    f"💬 {r['Pesan']}\n\n"
                    f"_TabunganBot 🤖_"
                )
                await app.bot.send_message(uid, msg, parse_mode="Markdown")
                log.info(f"Custom pengingat '{r['Nama']}' terkirim ke UserID {uid}")
    except Exception as e:
        log.error(f"Custom pengingat error: {e}")

# ── Reminder Nabung Freya ────────────────────────────────────────
_NABUNG_PAGI = [
    "☀️ *Selamat pagi, sayangku~* 🌸\n\nJangan lupa nabung yaa sayangku cintaku 💰\nWalaupun aku sibuk, tapi aku buatin bot ini khusus buat ingetin kamu 🤖❤️\n\n➕ /nabung  |  ➖ /keluar  |  🔥 /streak",
    "🌤️ *Pagi-pagi udah keinget kamu~* ☀️\n\nJangan lupa nabung yaa sayangku cintaku 💕\nAku bikin bot ini biar ada yang ingetin kamu walaupun aku lagi nggak bisa 🤖\n\n➕ /nabung  |  ➖ /keluar  |  🔥 /streak",
    "🌸 *Hai cintaku, selamat pagi!*\n\nJangan lupa nabung yaa sayangku, aku buatin bot ini buat jagain keuangan kita bareng 💰❤️\n\n➕ /nabung  |  ➖ /keluar  |  🔥 /streak",
]
_NABUNG_MALAM = [
    "🌙 *Malam sayang~* ✨\n\nJangan lupa nabung yaa sayangku cintaku 💰\nAku bikin bot ini biar kamu nggak lupa walau aku sibuk sekalipun 🤖❤️\n\n➕ /nabung  |  ➖ /keluar  |  🔥 /streak",
    "🌙 *Udah malem nih, sayang~*\n\nBelum ada catatan hari ini lho 👀 Jangan lupa nabung yaa cintaku 💕\n\n➕ /nabung  |  ➖ /keluar  |  🔥 /streak",
    "✨ *Psst, sayang!*\n\nBot buatan aku mau ingetin — jangan lupa nabung yaa sayangku 💰🌙\nDua menit aja buat catat~ 😴❤️\n\n➕ /nabung  |  ➖ /keluar  |  🔥 /streak",
]

async def send_reminder_nabung(app, session: str):
    uid = FREYA_ID
    if not uid: return
    try:
        if await run(db_has_transaction_today, uid):
            log.info(f"Reminder nabung {session} skip — sudah catat."); return
        streak_data = await run(db_get_streak, uid)
        cur         = streak_data["current"]
        warn        = ""
        if cur > 0 and streak_data["last_date"] == _yesterday_wita():
            warn = f"\n\n⚠️ *Streak {streak_badge(cur)} {cur} hari mau putus!*\n_Catat sekarang biar nggak reset~_ 🙏"
        day_idx = datetime.now(WITA).weekday()
        pool    = _NABUNG_PAGI if session == "pagi" else _NABUNG_MALAM
        await app.bot.send_message(uid, pool[day_idx % len(pool)] + warn, parse_mode="Markdown")
    except Exception as e:
        log.error(f"Reminder nabung error: {e}")

# ── Reminder Makan ───────────────────────────────────────────────
_MAKAN_PAGI  = ["🍳 *Pagi sayang!* Udah sarapan belum? Jangan skip ya 🥺☀️💕","🌅 *Selamat pagi cintaku!* Yuk sarapan dulu 🍞🥛💕","☀️ *Pagi ingetin kamu~* Sarapan dulu ya sayang! 🍳❤️"]
_MAKAN_SIANG = ["🍱 *Hei sayang, dzuhur nih!* Jangan lupa makan siang ya 🥺❤️","🕛 *Dzuhur udah, makan belum?* Yuk makan siang dulu 🍛💕","🍜 *Waktunya makan siang!* Jangan lupa ya cintaku 💕🥗"]
_MAKAN_SORE  = ["🌤️ *Habis ashar, udah makan belum?* Yuk makan sore sayang! 🍊🥺💕","🍎 *Sore-sore ingetin makan!* Snack atau makan ringan dulu 🌤️❤️","☕ *Udah sore sayang~* Jangan lupa makan ya cintaku! 🍪🥺❤️"]

async def send_reminder_makan(app, waktu: str):
    uid = FREYA_ID
    if not uid: return
    try:
        pools = {"pagi": _MAKAN_PAGI, "siang": _MAKAN_SIANG, "sore": _MAKAN_SORE}
        day_idx = datetime.now(WITA).weekday()
        await app.bot.send_message(uid, pools[waktu][day_idx % len(pools[waktu])], parse_mode="Markdown")
    except Exception as e:
        log.error(f"Reminder makan error: {e}")

# ── Reminder Istirahat ───────────────────────────────────────────
_ISTIRAHAT_SIANG = ["💤 *Habis makan, istirahat dulu ya sayang!* Rebahan sebentar juga cukup 🛋️❤️","😌 *Yuk istirahat sebentar cintaku~* Badan butuh jeda lho 💕🌸"]
_BEGADANG_11     = ["🌙 *Sayang, udah jam 11 malam!* Yuk bersiap tidur ya, jangan begadang 🥺💕❤️","⭐ *Udah larut malam~* Jangan begadang! Tubuh perlu istirahat 💤🌸❤️"]
_BEGADANG_12     = ["🌚 *Udah tengah malam sayang!* Yuk tidur sekarang, jangan begadang 🥺💕😴❤️","💤 *Tengah malam~* Serius yuk tidur! Jangan begadang 😔🌙❤️"]

async def send_reminder_istirahat(app, waktu: str):
    uid = FREYA_ID
    if not uid: return
    try:
        pools   = {"siang": _ISTIRAHAT_SIANG, "malam_11": _BEGADANG_11, "malam_12": _BEGADANG_12}
        day_idx = datetime.now(WITA).weekday()
        await app.bot.send_message(uid, pools[waktu][day_idx % len(pools[waktu])], parse_mode="Markdown")
    except Exception as e:
        log.error(f"Reminder istirahat error: {e}")

# ── Streak Broken Alert ──────────────────────────────────────────
async def send_streak_broken_alert(app):
    for name, uid in USERS.items():
        if uid == 0: continue
        try:
            broken = await run(db_check_streak_broken, uid)
            if broken > 0:
                await app.bot.send_message(
                    uid,
                    f"💔 *Streak putus...*\n\n{streak_badge(broken)} Streak *{broken} hari* hilang kemarin 😢\n\nNggak apa-apa! Yuk mulai lagi! 💪\n➕ /nabung  |  ➖ /keluar",
                    parse_mode="Markdown")
        except Exception as e:
            log.error(f"Streak broken alert error: {e}")

# ═══════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════
def main():
    log.info("Inisialisasi Google Sheets...")
    init_sheets()

    app = Application.builder().token(BOT_TOKEN).build()

    # ── Conversation: keuangan ─────────────────────────────────────
    conv_keuangan = ConversationHandler(
        entry_points=[
            CommandHandler("nabung", start_nabung),
            CommandHandler("keluar", start_keluar),
        ],
        states={
            ASK_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_amount)],
            ASK_CAT:    [CallbackQueryHandler(got_cat)],
            ASK_DESC:   [MessageHandler(filters.TEXT & ~filters.COMMAND, got_desc)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        conversation_timeout=120,
    )

    # ── Conversation: custom reminder ─────────────────────────────
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
    ]:
        app.add_handler(CommandHandler(cmd, fn))

    # AI handler — paling akhir
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ai_message))

    # ── Scheduler ─────────────────────────────────────────────────
    scheduler = AsyncIOScheduler()

    # Laporan mingguan
    scheduler.add_job(send_weekly_report, "cron", day_of_week=REPORT_WEEKDAY,
                      hour=REPORT_HOUR, minute=REPORT_MINUTE, timezone="Asia/Jakarta", args=[app])

    # Streak broken alert
    scheduler.add_job(send_streak_broken_alert, "cron", hour=7, minute=0,
                      timezone="Asia/Makassar", args=[app])

    # SNBT reminder Freya — pagi 07:00 WITA
    scheduler.add_job(send_snbt_reminder, "cron", hour=7, minute=30,
                      timezone="Asia/Makassar", args=[app])

    # Nabung reminders
    scheduler.add_job(send_reminder_nabung, "cron", hour=9, minute=0,
                      timezone="Asia/Makassar", args=[app, "pagi"])
    scheduler.add_job(send_reminder_nabung, "cron", hour=21, minute=0,
                      timezone="Asia/Makassar", args=[app, "malam"])

    # Makan reminders
    scheduler.add_job(send_reminder_makan, "cron", hour=9, minute=0,
                      timezone="Asia/Makassar", args=[app, "pagi"])
    scheduler.add_job(send_reminder_makan, "cron", hour=12, minute=30,
                      timezone="Asia/Makassar", args=[app, "siang"])
    scheduler.add_job(send_reminder_makan, "cron", hour=15, minute=30,
                      timezone="Asia/Makassar", args=[app, "sore"])

    # Istirahat reminders
    scheduler.add_job(send_reminder_istirahat, "cron", hour=12, minute=31,
                      timezone="Asia/Makassar", args=[app, "siang"])
    scheduler.add_job(send_reminder_istirahat, "cron", hour=23, minute=0,
                      timezone="Asia/Makassar", args=[app, "malam_11"])
    scheduler.add_job(send_reminder_istirahat, "cron", hour=0, minute=0,
                      timezone="Asia/Makassar", args=[app, "malam_12"])

    # Custom pengingat — cek setiap menit
    scheduler.add_job(check_custom_pengingat, "cron", minute="*",
                      timezone="Asia/Makassar", args=[app])

    scheduler.start()

    log.info("✅ TabunganBot berjalan!")
    log.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    log.info("💬 AI Groq: AKTIF | ⏰ Custom Pengingat: AKTIF")
    log.info(f"🎓 Bimbel aktif s.d. {BIMBEL_END_DATE}")
    log.info("📅 Jadwal terjadwal:")
    log.info("   📊 Laporan mingguan  → Senin 08:00 WIB")
    log.info("   💔 Streak broken     → 07:00 WITA")
    log.info("   📚 SNBT reminder     → 07:30 WITA")
    log.info("   💰+🍳 Reminder pagi  → 09:00 WITA")
    log.info("   🍱+💤 Makan siang   → 12:30-12:31 WITA")
    log.info("   🍎 Makan sore        → 15:30 WITA")
    log.info("   💰 Nabung malam      → 21:00 WITA")
    log.info("   🌙 Jangan begadang   → 23:00 + 00:00 WITA")
    log.info("   ⏰ Custom pengingat  → cek tiap menit")
    log.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
