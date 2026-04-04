#!/usr/bin/env python3
"""
TabunganBot 💰 — versi Google Sheets + Streak System
Data tersimpan permanen di Google Spreadsheet
Untuk: Fahril & Freya
"""

import os
import asyncio
import logging
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo

import gspread
from google.oauth2.service_account import Credentials

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, filters, ContextTypes
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ═══════════════════════════════════════════════════════════════
#  KONFIGURASI
# ═══════════════════════════════════════════════════════════════
BOT_TOKEN        = os.getenv("BOT_TOKEN", "GANTI_TOKEN_BOT")
SPREADSHEET_ID   = os.getenv("SPREADSHEET_ID", "GANTI_ID_SPREADSHEET")
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE", "credentials.json")

USERS: dict[str, int] = {
    "Fahril": 5210728658,
    "Freya" : 6434745020,
}

REPORT_WEEKDAY = 0
REPORT_HOUR    = 8
REPORT_MINUTE  = 0
WIB            = ZoneInfo("Asia/Jakarta")
WITA           = ZoneInfo("Asia/Makassar")

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

ASK_AMOUNT, ASK_CAT, ASK_DESC = range(3)

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
#  STREAK CONFIG
# ═══════════════════════════════════════════════════════════════
STREAK_MILESTONES = [3, 7, 14, 21, 30, 60, 90, 100, 150, 200, 365]

def streak_badge(n: int) -> str:
    """Ambil badge berdasarkan jumlah streak hari."""
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
    """Ambil label/title berdasarkan streak."""
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
    ss = client.open_by_key(SPREADSHEET_ID)
    _get_or_create_sheet(ss, "Transaksi", ["ID","UserID","Nama","Tipe","Jumlah","Kategori","Catatan","Waktu"])
    _get_or_create_sheet(ss, "Tujuan",    ["ID","UserID","Judul","Target","Terkumpul","Selesai","Waktu"])
    _get_or_create_sheet(ss, "Catatan",   ["ID","UserID","Isi","Waktu"])
    _get_or_create_sheet(ss, "Streak",    ["UserID","CurrentStreak","LongestStreak","LastDate"])
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
    ws  = _ss().worksheet("Transaksi")
    all_vals = ws.get_all_values()
    for i in range(len(all_vals) - 1, 0, -1):
        if str(all_vals[i][1]) == str(uid):
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
    ws    = _ss().worksheet("Transaksi")
    for r in ws.get_all_records():
        if str(r["UserID"]) == str(uid) and str(r["Waktu"]).startswith(today):
            return True
    return False

# ─── Tujuan ─────────────────────────────────────────────────────
def db_get_goals(uid: int):
    rows = _ss().worksheet("Tujuan").get_all_records()
    return [r for r in rows if str(r["UserID"]) == str(uid)]

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
    result = [r for r in rows if str(r["UserID"]) == str(uid)]
    return sorted(result, key=lambda r: r["Waktu"], reverse=True)[:10]

# ─── Streak ─────────────────────────────────────────────────────
def db_get_streak(uid: int) -> dict:
    """
    Return dict: {current, longest, last_date}
    Kalau belum ada row → return default 0.
    """
    ws   = _ss().worksheet("Streak")
    rows = ws.get_all_records()
    for r in rows:
        if str(r["UserID"]) == str(uid):
            return {
                "current"  : int(r["CurrentStreak"] or 0),
                "longest"  : int(r["LongestStreak"] or 0),
                "last_date": str(r["LastDate"] or ""),
            }
    return {"current": 0, "longest": 0, "last_date": ""}

def db_update_streak(uid: int) -> dict:
    """
    Panggil setiap kali transaksi berhasil disimpan.
    Return dict: {current, longest, last_date, milestone_hit, was_reset}
      - milestone_hit : int | None  → kalau baru capai milestone, isi nilainya
      - was_reset     : bool        → True kalau streak sempat putus sebelumnya
    """
    ws      = _ss().worksheet("Streak")
    all_vals = ws.get_all_values()  # [header, row1, row2, ...]
    today    = _today_wita()
    yesterday = _yesterday_wita()

    # Cari row existing
    row_idx = None
    for i, row in enumerate(all_vals[1:], start=2):
        if str(row[0]) == str(uid):
            row_idx = i
            current  = int(row[1] or 0)
            longest  = int(row[2] or 0)
            last_date = str(row[3] or "")
            break
    else:
        current = longest = 0
        last_date = ""

    was_reset    = False
    milestone_hit = None

    if last_date == today:
        # Sudah catat hari ini, tidak ubah streak
        pass
    elif last_date == yesterday:
        # Lanjutkan streak
        current += 1
    else:
        # Streak putus (atau baru pertama kali)
        was_reset = (current > 0)
        current   = 1

    longest = max(longest, current)

    # Cek milestone
    if current in STREAK_MILESTONES:
        milestone_hit = current

    # Simpan ke sheet
    if row_idx:
        ws.update(f"B{row_idx}:D{row_idx}", [[current, longest, today]])
    else:
        ws.append_row([uid, current, longest, today], value_input_option="USER_ENTERED")

    return {
        "current"      : current,
        "longest"      : longest,
        "last_date"    : today,
        "milestone_hit": milestone_hit,
        "was_reset"    : was_reset,
    }

def db_get_all_streaks() -> list[dict]:
    """Ambil semua streak untuk leaderboard /bersama."""
    ws   = _ss().worksheet("Streak")
    rows = ws.get_all_records()
    result = []
    for r in rows:
        uid = int(r["UserID"]) if str(r["UserID"]).isdigit() else 0
        result.append({
            "uid"    : uid,
            "name"   : get_user_name(uid) or "Unknown",
            "current": int(r["CurrentStreak"] or 0),
            "longest": int(r["LongestStreak"] or 0),
        })
    return result

def db_check_streak_broken(uid: int) -> int:
    """
    Cek apakah streak kemarin putus (belum catat kemarin).
    Return streak yang hilang (int > 0), atau 0 kalau tidak putus.
    """
    data = db_get_streak(uid)
    if data["current"] == 0 or data["last_date"] == "":
        return 0
    # Kalau last_date bukan kemarin dan bukan hari ini → streak sudah putus
    if data["last_date"] not in (_today_wita(), _yesterday_wita()):
        return data["current"]  # streak yang akan direset
    return 0

# ─── Async wrapper ───────────────────────────────────────────────
async def run(func, *args):
    return await asyncio.to_thread(func, *args)

# ═══════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════
def rp(n: float) -> str:
    return f"Rp {int(n):,}".replace(",", ".")

def progress_bar(pct: float, width=12) -> str:
    filled = round(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)

def streak_bar(n: int, width=10) -> str:
    """Mini visual bar streak (max 30 hari per bar)."""
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
    uid = u.effective_user.id
    if not authorized(uid):
        await u.message.reply_text(
            f"⛔ *Akses ditolak!*\n\nID Telegram kamu: `{uid}`\n"
            f"Minta Fahril/Freya tambahkan ID ini.", parse_mode="Markdown")
        return False
    return True

def _streak_summary(data: dict) -> str:
    """Buat teks ringkasan streak untuk ditampilkan."""
    cur = data["current"]
    lng = data["longest"]
    badge = streak_badge(cur)
    title = streak_title(cur)
    bar   = streak_bar(cur)
    return (
        f"{badge} *Streak: {cur} hari* — _{title}_\n"
        f"`{bar}`\n"
        f"🏅 Terpanjang: *{lng} hari*"
    )

# ═══════════════════════════════════════════════════════════════
#  COMMAND HANDLERS
# ═══════════════════════════════════════════════════════════════
async def cmd_start(u: Update, _):
    uid = u.effective_user.id
    if not authorized(uid):
        await u.message.reply_text(
            f"👋 Bot ini khusus untuk Fahril & Freya.\n\n"
            f"🪪 ID Telegram kamu: `{uid}`\n"
            f"Hubungi pemilik untuk mendapatkan akses.", parse_mode="Markdown")
        return
    name = get_user_name(uid)
    wait = await u.message.reply_text("⏳ Memuat saldo...")
    bal  = await run(db_get_balance, uid)
    await wait.delete()
    await u.message.reply_text(
        f"👋 Halo *{name}*!\n"
        f"💰 Saldo kamu: *{rp(bal)}*\n\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"📌 *Menu Utama:*\n\n"
        f"➕ /nabung — Catat pemasukan\n"
        f"➖ /keluar — Catat pengeluaran\n"
        f"💼 /saldo — Cek saldo terkini\n"
        f"📊 /laporan — Laporan 7 hari\n"
        f"📅 /bulanan — Laporan bulan ini\n"
        f"📜 /riwayat — Riwayat transaksi\n"
        f"🔥 /streak — Lihat streak nabung\n"
        f"🎯 /tujuan — Target tabungan\n"
        f"👥 /bersama — Rekap Fahril+Freya\n"
        f"🗒️ /catatan — Catatan keuangan\n"
        f"↩️ /hapusterakhir — Hapus transaksi terakhir\n"
        f"🔗 /spreadsheet — Link Google Sheets\n"
        f"🆔 /myid — Lihat Telegram ID\n\n"
        f"_📊 Data tersimpan permanen di Google Sheets_\n"
        f"_📬 Laporan otomatis tiap Senin 08:00 WIB_",
        parse_mode="Markdown")

async def cmd_myid(u: Update, _):
    uid  = u.effective_user.id
    name = get_user_name(uid) or "Belum terdaftar"
    await u.message.reply_text(
        f"🪪 *Info Akun*\n\nID Telegram: `{uid}`\nNama di bot: *{name}*",
        parse_mode="Markdown")

async def cmd_spreadsheet(u: Update, _):
    if not await check_auth(u): return
    await u.message.reply_text(
        f"🔗 *Link Google Sheets:*\n"
        f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}",
        parse_mode="Markdown")

async def cmd_streak(u: Update, _):
    """Command /streak — lihat streak detail."""
    if not await check_auth(u): return
    uid  = u.effective_user.id
    name = get_user_name(uid)
    wait = await u.message.reply_text("⏳ Memuat streak...")
    data = await run(db_get_streak, uid)
    await wait.delete()

    cur = data["current"]
    lng = data["longest"]
    badge = streak_badge(cur)
    title = streak_title(cur)
    bar   = streak_bar(cur)

    # Hitung milestone berikutnya
    next_ms = next((m for m in STREAK_MILESTONES if m > cur), None)
    next_txt = f"\n🎯 Milestone berikutnya: *{next_ms} hari* ({next_ms - cur} hari lagi)" if next_ms else "\n🎉 Kamu udah capai semua milestone!"

    # Progress ke 30 hari (satu siklus)
    cycle = (cur % 30) or (30 if cur > 0 and cur % 30 == 0 else 0)
    pct   = min(100, cycle / 30 * 100)

    lines = [
        f"🔥 *Streak Nabung — {name}*\n",
        f"{badge} *{cur} Hari Berturut-turut*",
        f"_{title}_\n",
        f"`{bar}` {pct:.0f}% menuju 30 hari",
        f"\n🏅 Streak terpanjang: *{lng} hari*",
        next_txt,
        f"\n━━━━━━━━━━━━━━━━━",
        f"🏆 *Milestone yang tersedia:*",
    ]

    for ms in STREAK_MILESTONES:
        if cur >= ms:
            lines.append(f"  ✅ {ms} hari — {streak_badge(ms)} {streak_title(ms)}")
        elif ms == next_ms:
            lines.append(f"  ⏳ {ms} hari — {streak_badge(ms)} {streak_title(ms)} ← berikutnya")
        else:
            lines.append(f"  🔒 {ms} hari — {streak_badge(ms)}")

    lines.append(f"\n_Catat transaksi tiap hari biar streak-nya nggak putus!_ 💪")
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
        f"💰 *Saldo Sekarang: {rp(bal)}*\n\n"
        f"━━━━━ 7 Hari Terakhir ━━━━━\n"
        f"📈 Pemasukan : {rp(inc7)}\n"
        f"📉 Pengeluaran: {rp(exp7)}\n"
        f"📊 Selisih   : {rp(inc7 - exp7)}\n\n"
        f"━━━━━ 30 Hari Terakhir ━━━━\n"
        f"📈 Pemasukan : {rp(inc30)}\n"
        f"📉 Pengeluaran: {rp(exp30)}\n"
        f"📊 Selisih   : {rp(inc30 - exp30)}\n\n"
        f"━━━━━ Streak ━━━━━━━━━━━━\n"
        f"{_streak_summary(streak_data)}",
        parse_mode="Markdown")

async def cmd_laporan(u: Update, _):
    if not await check_auth(u): return
    uid  = u.effective_user.id
    name = get_user_name(uid)
    wait = await u.message.reply_text("⏳ Menyusun laporan...")
    inc, exp, rows = await run(db_get_summary, uid, 7)
    bal            = await run(db_get_balance, uid)
    await wait.delete()
    lines = [
        f"📊 *Laporan 7 Hari — {name}*",
        f"_{datetime.now(WIB).strftime('%d %B %Y')}_\n",
        f"📈 Pemasukan : *{rp(inc)}*",
        f"📉 Pengeluaran: *{rp(exp)}*",
        f"💰 Saldo Total: *{rp(bal)}*\n",
        "📜 *Transaksi Terakhir:*"
    ]
    for r in rows[:12]:
        icon = "⬆️" if r["Tipe"] == "income" else "⬇️"
        note = f" _{r['Catatan']}_" if r.get("Catatan") else ""
        lines.append(f"{icon} *{rp(float(r['Jumlah']))}* — {r['Kategori']}{note}")
        lines.append(f"    `{str(r['Waktu'])[:16]}`")
    if not rows:
        lines.append("_Tidak ada transaksi._")
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
    lines = [
        f"📅 *Laporan Bulanan — {name}*",
        f"_{now.strftime('%B %Y')}_\n",
        f"📈 Total Masuk : *{rp(inc)}*",
        f"📉 Total Keluar: *{rp(exp)}*",
        f"📊 Selisih     : *{rp(inc - exp)}*",
        f"💰 Saldo Total : *{rp(bal)}*\n",
    ]
    inc_cats = [(c, a) for c, t, a in cats if t == "income"]
    exp_cats = [(c, a) for c, t, a in cats if t == "expense"]
    if inc_cats:
        lines.append("📈 *Pemasukan per Kategori:*")
        for c, a in inc_cats:
            lines.append(f"  • {c}: *{rp(a)}*")
        lines.append("")
    if exp_cats:
        lines.append("📉 *Pengeluaran per Kategori:*")
        for c, a in exp_cats:
            lines.append(f"  • {c}: *{rp(a)}*")
    await u.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_riwayat(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(u): return
    uid  = u.effective_user.id
    name = get_user_name(uid)
    n    = int(ctx.args[0]) if ctx.args and ctx.args[0].isdigit() else 10
    n    = min(n, 30)
    wait = await u.message.reply_text("⏳ Mengambil riwayat...")
    rows = await run(db_get_transactions, uid, None, n)
    await wait.delete()
    lines = [f"📜 *{n} Transaksi Terakhir — {name}*\n"]
    for r in rows:
        icon = "⬆️" if r["Tipe"] == "income" else "⬇️"
        note = f"\n     _{r['Catatan']}_" if r.get("Catatan") else ""
        lines.append(f"{icon} *{rp(float(r['Jumlah']))}* — {r['Kategori']}{note}")
        lines.append(f"    `{str(r['Waktu'])[:16]}`\n")
    if not rows:
        lines.append("Belum ada transaksi.")
    await u.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_bersama(u: Update, _):
    if not await check_auth(u): return
    wait = await u.message.reply_text("⏳ Memuat data berdua...")
    lines = [
        "👥 *Rekap Bersama — Fahril & Freya*",
        f"_{datetime.now(WIB).strftime('%d %B %Y')}_\n"
    ]
    total_bal = total_inc = total_exp = 0.0
    for name, uid in USERS.items():
        if uid == 0: continue
        bal           = await run(db_get_balance, uid)
        inc7, exp7, _ = await run(db_get_summary, uid, 7)
        streak_data   = await run(db_get_streak, uid)
        total_bal += bal; total_inc += inc7; total_exp += exp7
        cur   = streak_data["current"]
        badge = streak_badge(cur)
        lines.append(f"👤 *{name}*")
        lines.append(f"  💰 Saldo     : {rp(bal)}")
        lines.append(f"  📈 Masuk 7hr : {rp(inc7)}")
        lines.append(f"  📉 Keluar 7hr: {rp(exp7)}")
        lines.append(f"  {badge} Streak  : *{cur} hari* — _{streak_title(cur)}_\n")
    lines.append("━━━━━━━━━━━━━━━━━")
    lines.append("📊 *Gabungan 7 Hari:*")
    lines.append(f"  💰 Total Saldo  : *{rp(total_bal)}*")
    lines.append(f"  📈 Total Masuk  : *{rp(total_inc)}*")
    lines.append(f"  📉 Total Keluar : *{rp(total_exp)}*")
    lines.append(f"  📊 Selisih      : *{rp(total_inc - total_exp)}*")
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
        lines.append(
            "Belum ada target.\n\n"
            "Buat target baru:\n"
            "`/addtarget [jumlah] [nama target]`\n"
            "Contoh: `/addtarget 5000000 Liburan Bali`")
    else:
        for r in goals:
            target = float(r["Target"]); saved = float(r["Terkumpul"])
            done   = r["Selesai"] == "Ya"
            pct    = min(100.0, (saved / target * 100) if target > 0 else 0)
            status = "✅" if done else "🔄"
            lines.append(f"{status} *{r['Judul']}* (ID: {r['ID']})")
            lines.append(f"  `{progress_bar(pct)}` {pct:.1f}%")
            lines.append(f"  {rp(saved)} / {rp(target)}\n")
        lines.append("Tambah progres: `/isitarget [id] [jumlah]`")
    await u.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_addtarget(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(u): return
    uid = u.effective_user.id
    if not ctx.args or len(ctx.args) < 2:
        await u.message.reply_text(
            "Format: `/addtarget [jumlah] [nama target]`\n"
            "Contoh: `/addtarget 5000000 Liburan Bali`", parse_mode="Markdown"); return
    try:
        amount = float(ctx.args[0].replace(".", "").replace(",", ""))
        title  = " ".join(ctx.args[1:])
        wait   = await u.message.reply_text("⏳ Menyimpan target...")
        await run(db_add_goal, uid, title, amount)
        await wait.delete()
        await u.message.reply_text(
            f"🎯 Target *{title}* sebesar *{rp(amount)}* berhasil dibuat!\nLihat progres di /tujuan",
            parse_mode="Markdown")
    except:
        await u.message.reply_text("❌ Format salah. Contoh: `/addtarget 5000000 Liburan Bali`", parse_mode="Markdown")

async def cmd_isitarget(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(u): return
    if not ctx.args or len(ctx.args) < 2:
        await u.message.reply_text("Format: `/isitarget [id] [jumlah]`\nLihat ID di /tujuan", parse_mode="Markdown"); return
    try:
        goal_id = int(ctx.args[0])
        amount  = float(ctx.args[1].replace(".", "").replace(",", ""))
        wait    = await u.message.reply_text("⏳ Memperbarui progres...")
        target, saved = await run(db_update_goal, goal_id, amount)
        await wait.delete()
        if target is None:
            await u.message.reply_text("❌ Target tidak ditemukan."); return
        pct  = min(100.0, saved / target * 100)
        done = saved >= target
        msg  = "✅ *Target Tercapai! 🎉*" if done else "🔄 *Progres Diperbarui!*"
        await u.message.reply_text(
            f"{msg}\n\n`{progress_bar(pct)}` {pct:.1f}%\n{rp(saved)} / {rp(target)}",
            parse_mode="Markdown")
    except:
        await u.message.reply_text("❌ Format salah. Contoh: `/isitarget 1 500000`", parse_mode="Markdown")

async def cmd_catatan(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(u): return
    uid  = u.effective_user.id
    name = get_user_name(uid)
    if ctx.args:
        content = " ".join(ctx.args)
        wait = await u.message.reply_text("⏳ Menyimpan catatan...")
        await run(db_add_note, uid, content)
        await wait.delete()
        await u.message.reply_text(f"🗒️ Catatan tersimpan:\n_{content}_", parse_mode="Markdown")
    else:
        wait  = await u.message.reply_text("⏳ Memuat catatan...")
        notes = await run(db_get_notes, uid)
        await wait.delete()
        lines = [f"🗒️ *Catatan Keuangan — {name}*\n"]
        if notes:
            for r in notes:
                lines.append(f"• _{r['Isi']}_")
                lines.append(f"  `{str(r['Waktu'])[:16]}`\n")
        else:
            lines.append("Belum ada catatan.\nSimpan dengan: `/catatan [teks]`")
        await u.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_hapusterakhir(u: Update, _):
    if not await check_auth(u): return
    uid  = u.effective_user.id
    wait = await u.message.reply_text("⏳ Menghapus transaksi...")
    ok   = await run(db_delete_last_transaction, uid)
    bal  = await run(db_get_balance, uid)
    await wait.delete()
    if ok:
        await u.message.reply_text(
            f"↩️ Transaksi terakhir dihapus.\n💰 Saldo sekarang: *{rp(bal)}*",
            parse_mode="Markdown")
    else:
        await u.message.reply_text("❌ Tidak ada transaksi yang bisa dihapus.")

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
            await u.message.reply_text("📂 *Pilih kategori pemasukan:*", reply_markup=kb_grid(CATS_IN), parse_mode="Markdown")
            return ASK_CAT
        except: pass
    await u.message.reply_text("💵 *Masukkan jumlah pemasukan/tabungan:*\n_Contoh: `500000`_", parse_mode="Markdown")
    return ASK_AMOUNT

async def start_keluar(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not authorized(u.effective_user.id):
        await u.message.reply_text("⛔ Tidak diizinkan."); return ConversationHandler.END
    ctx.user_data.update({"kind": "expense", "amount": None, "desc": None})
    if ctx.args:
        try:
            ctx.user_data["amount"] = float(ctx.args[0].replace(".", "").replace(",", ""))
            ctx.user_data["desc"]   = " ".join(ctx.args[1:]) if len(ctx.args) > 1 else ""
            await u.message.reply_text("📂 *Pilih kategori pengeluaran:*", reply_markup=kb_grid(CATS_OUT), parse_mode="Markdown")
            return ASK_CAT
        except: pass
    await u.message.reply_text("💸 *Masukkan jumlah pengeluaran:*\n_Contoh: `50000`_", parse_mode="Markdown")
    return ASK_AMOUNT

async def got_amount(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    txt = u.message.text.strip().replace(".", "").replace(",", "")
    try:
        ctx.user_data["amount"] = float(txt)
    except:
        await u.message.reply_text("❌ Masukkan angka saja, contoh: `150000`", parse_mode="Markdown")
        return ASK_AMOUNT
    cats = CATS_IN if ctx.user_data["kind"] == "income" else CATS_OUT
    await u.message.reply_text("📂 *Pilih kategori:*", reply_markup=kb_grid(cats), parse_mode="Markdown")
    return ASK_CAT

async def got_cat(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = u.callback_query; await q.answer()
    ctx.user_data["category"] = q.data
    if ctx.user_data.get("desc") is not None:
        await _save_tx(q.message, ctx, q.from_user.id)
        return ConversationHandler.END
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

    wait = await msg.reply_text("⏳ Menyimpan ke Google Sheets...")
    await run(db_add_transaction, uid, name, kind, amount, cat, note)
    bal          = await run(db_get_balance, uid)
    streak_data  = await run(db_update_streak, uid)  # ← UPDATE STREAK
    await wait.delete()

    icon   = "📈" if kind == "income" else "📉"
    action = "Pemasukan" if kind == "income" else "Pengeluaran"
    cur    = streak_data["current"]
    badge  = streak_badge(cur)

    # Pesan utama
    await msg.reply_text(
        f"{icon} *{action} Berhasil Dicatat!*\n\n"
        f"👤 {name}\n"
        f"💵 Jumlah   : *{rp(amount)}*\n"
        f"📂 Kategori : {cat}\n"
        f"📝 Catatan  : {note or '-'}\n\n"
        f"💰 Saldo Sekarang: *{rp(bal)}*\n"
        f"_✅ Tersimpan di Google Sheets_\n\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"{badge} *Streak: {cur} hari* — _{streak_title(cur)}_\n"
        f"`{streak_bar(cur)}`",
        parse_mode="Markdown")

    # Notifikasi milestone
    ms = streak_data.get("milestone_hit")
    if ms:
        milestone_msgs = {
            3  : f"🌱 *Streak 3 Hari!*\nMulai tumbuh nih, pertahankan ya! 💪",
            7  : f"✨ *Streak 1 Minggu!*\nSatu minggu penuh konsisten catat keuangan! Luar biasa 🎉",
            14 : f"🔥 *Streak 2 Minggu!*\nDua minggu nonstop! Kamu udah mulai jadi kebiasaan bagus 🔥",
            21 : f"💪 *Streak 3 Minggu!*\nKatanya butuh 21 hari buat bikin kebiasaan — dan kamu udah lakuin itu! 🏆",
            30 : f"⚡ *STREAK 1 BULAN! 🎊*\nSatu bulan penuh tanpa putus! Ini pencapaian luar biasa {badge}\nSaldo pasti makin sehat! 💰",
            60 : f"🏆 *STREAK 2 BULAN! 🎊*\nDua bulan konsisten! Kamu udah jadi pro nabung sekarang 👑",
            90 : f"🌟 *STREAK 90 HARI! 🎊*\nNyaris 3 bulan! Kamu legend! 🌟",
            100: f"👑 *STREAK 100 HARI! 🎊*\nSERATUS HARI BERTURUT-TURUT!\nIni pencapaian yang nggak semua orang bisa lakuin 👑🎉",
            365: f"🚀 *STREAK 1 TAHUN! 🎊🎊🎊*\nSETAHUN PENUH! GOAT! 🐐\nKamu udah jadi master keuangan sejati! 🚀",
        }
        congrats = milestone_msgs.get(ms, f"🎉 *Streak {ms} Hari!*\nMantap banget! Terus pertahankan! 💪")
        await msg.reply_text(congrats, parse_mode="Markdown")

async def cancel(u: Update, _):
    await u.message.reply_text("❌ Dibatalkan.")
    return ConversationHandler.END

# ═══════════════════════════════════════════════════════════════
#  WEEKLY AUTO REPORT
# ═══════════════════════════════════════════════════════════════
async def send_weekly_report(app):
    log.info("Mengirim laporan mingguan...")
    for name, uid in USERS.items():
        if uid == 0: continue
        try:
            inc, exp, rows = await run(db_get_summary, uid, 7)
            bal            = await run(db_get_balance, uid)
            goals          = await run(db_get_goals, uid)
            streak_data    = await run(db_get_streak, uid)
            cur    = streak_data["current"]
            badge  = streak_badge(cur)
            lines  = [
                f"📊 *Laporan Mingguan — {name}* 🗓",
                f"_{datetime.now(WIB).strftime('%d %B %Y, %H:%M WIB')}_\n",
                f"📈 Pemasukan : *{rp(inc)}*",
                f"📉 Pengeluaran: *{rp(exp)}*",
                f"💰 Saldo Total: *{rp(bal)}*\n",
                f"{badge} *Streak: {cur} hari* — _{streak_title(cur)}_\n",
            ]
            if rows:
                lines.append("📜 *Transaksi Minggu Ini:*")
                for r in rows[:10]:
                    icon = "⬆️" if r["Tipe"] == "income" else "⬇️"
                    lines.append(f"{icon} {rp(float(r['Jumlah']))} — {r['Kategori']}")
                lines.append("")
            else:
                lines.append("_Tidak ada transaksi minggu ini._\n")
            active_goals = [r for r in goals if r.get("Selesai") != "Ya"]
            if active_goals:
                lines.append("🎯 *Progres Target:*")
                for r in active_goals[:3]:
                    target = float(r["Target"]); saved = float(r["Terkumpul"])
                    pct    = min(100.0, saved / target * 100)
                    lines.append(f"  {r['Judul']}: `{progress_bar(pct, 8)}` {pct:.1f}%")
                lines.append("")
            lines.append("_TabunganBot 🤖 — Semangat nabung!_ 💪")
            await app.bot.send_message(uid, "\n".join(lines), parse_mode="Markdown")
            log.info(f"Laporan terkirim ke {name}")
        except Exception as e:
            log.error(f"Gagal kirim laporan ke {name}: {e}")

# ═══════════════════════════════════════════════════════════════
#  REMINDER FREYA — NABUNG 💰
# ═══════════════════════════════════════════════════════════════

_NABUNG_PAGI = [
    (
        "☀️ *Selamat pagi, sayangku~* 🌸\n\n"
        "Jangan lupa nabung yaa sayangku cintaku 💰\n"
        "Walaupun aku sibuk, tapi aku buatin bot ini khusus buat ingetin kamu 🤖❤️\n\n"
        "Yuk catat dulu sebelum hari makin sibuk!\n"
        "➕ /nabung  |  ➖ /keluar  |  🔥 /streak"
    ),
    (
        "🌤️ *Pagi-pagi udah keinget kamu~* ☀️\n\n"
        "Jangan lupa nabung yaa sayangku cintaku 💕\n"
        "Aku bikin bot ini biar ada yang ingetin kamu walaupun aku lagi nggak bisa 🤖\n\n"
        "Hari ini udah ada yang mau dicatat?\n"
        "➕ /nabung  |  ➖ /keluar  |  🔥 /streak"
    ),
    (
        "🌸 *Hai cintaku, selamat pagi!*\n\n"
        "Ini pengingatnya dateng lagi 🤖💌\n"
        "Jangan lupa nabung yaa sayangku, aku buatin bot ini buat jagain keuangan kita bareng 💰❤️\n\n"
        "➕ /nabung  |  ➖ /keluar  |  🔥 /streak"
    ),
]

_NABUNG_MALAM = [
    (
        "🌙 *Malam sayang~* ✨\n\n"
        "Hari ini ada yang belum dicatat nggak? 🤔\n"
        "Jangan lupa nabung yaa sayangku cintaku 💰\n"
        "Aku bikin bot ini biar kamu nggak lupa walau aku sibuk sekalipun 🤖❤️\n\n"
        "Yuk recap bentar sebelum istirahat!\n"
        "➕ /nabung  |  ➖ /keluar  |  🔥 /streak"
    ),
    (
        "🌙 *Udah malem nih, sayang~*\n\n"
        "Belum ada catatan keuangan hari ini lho 👀\n"
        "Jangan lupa nabung yaa cintaku 💕\n"
        "Walaupun aku sibuk, bot ini tetep setia ingetin kamu 🤖\n\n"
        "➕ /nabung  |  ➖ /keluar  |  🔥 /streak"
    ),
    (
        "✨ *Psst, sayang!*\n\n"
        "Bot buatan aku mau ingetin — jangan lupa nabung yaa sayangku 💰🌙\n"
        "Dua menit aja buat catat, biar tidurnya tenang~ 😴❤️\n\n"
        "➕ /nabung  |  ➖ /keluar  |  🔥 /streak"
    ),
]

async def send_reminder_nabung(app, session: str):
    uid = USERS.get("Freya")
    if not uid or uid == 0: return
    try:
        sudah_catat = await run(db_has_transaction_today, uid)
        if sudah_catat:
            log.info(f"Reminder nabung {session} Freya dilewati — sudah catat hari ini.")
            return

        day_idx = datetime.now(WITA).weekday()

        # Cek apakah streak mau putus (belum catat hari ini, tapi kemarin catat)
        streak_data = await run(db_get_streak, uid)
        cur         = streak_data["current"]
        last_date   = streak_data["last_date"]
        streak_warn = ""
        if cur > 0 and last_date == _yesterday_wita():
            # Streak aktif, tapi belum catat hari ini → kasih warning
            streak_warn = (
                f"\n\n⚠️ *Streak kamu {streak_badge(cur)} {cur} hari mau putus lho!*\n"
                f"_Catat sekarang biar nggak reset dari awal~_ 🙏"
            )

        if session == "pagi":
            msg = _NABUNG_PAGI[day_idx % len(_NABUNG_PAGI)] + streak_warn
        else:
            msg = _NABUNG_MALAM[day_idx % len(_NABUNG_MALAM)] + streak_warn

        await app.bot.send_message(uid, msg, parse_mode="Markdown")
        log.info(f"Reminder nabung {session} terkirim ke Freya.")
    except Exception as e:
        log.error(f"Gagal kirim reminder nabung {session} ke Freya: {e}")

# ═══════════════════════════════════════════════════════════════
#  REMINDER FREYA — MAKAN & MINUM 🍱
# ═══════════════════════════════════════════════════════════════

_MAKAN_PAGI = [
    "🍳 *Pagi sayang!*\n\nUdah sarapan belum? Jangan skip makan pagi yaa 🥺\nPerut kenyang, semangat pun ikut naik! ☀️💕",
    "🌅 *Selamat pagi, cintaku!*\n\nYuk sarapan dulu sebelum mulai aktivitas 🍞🥛\nJangan biasain skip makan pagi yaa sayang~ 💕",
    "☀️ *Pagi-pagi ingetin kamu~*\n\nSarapan dulu ya sayang! Biar kuat dan semangat seharian 🍳❤️\nAku selalu perhatiin kamu walau dari jauh 💌",
    "🌤️ *Good morning sayang~*\n\nInget makan pagi ya cintaku! 🥯🧃\nJangan sampai perut kosong seharian, kasian badannya 🥺❤️",
]

_MAKAN_SIANG = [
    "🍱 *Hei sayang, udah dzuhur nih!*\n\nJangan lupa makan siang ya cintaku 🥺\nMakan yang beneran, bukan nyemil doang~ 😄❤️",
    "🕛 *Dzuhur udah, makan belum?*\n\nYuk makan siang dulu sayang! Jaga energi buat sore 🍛💕",
    "🍜 *Waktunya makan siang, sayang!*\n\nJangan sampai lupa makan ya cintaku 💕\nMakanlah yang bergizi biar tetap sehat~ 🥗",
    "🌞 *Siang-siang jangan lupa makan ya!*\n\nMakan dulu sayang sebelum lanjut aktivitas 🍚\nAku khawatir kalau kamu nggak makan 🥺❤️",
]

_MAKAN_SORE = [
    "🌤️ *Habis ashar, udah makan belum?*\n\nYuk makan sore sayang! Jangan sampai lapar sampai malam 🍊🥺\nInget jaga makan ya cintaku~ 💕",
    "🍎 *Sore-sore ingetin kamu makan!*\n\nSnack atau makan ringan dulu sayang 🌤️\nBiar nggak drop sebelum malam~ ❤️",
    "☕ *Udah sore nih, sayang~*\n\nJangan lupa makan ya cintaku! 🍪\nPerut jangan dibiarkan kosong terlalu lama 🥺❤️",
    "🌇 *Sore cantik buat kamu yang cantik~*\n\nYuk makan dulu sayang, habis ashar nih 🍽️\nJaga badan ya, aku sayang kamu 💕",
]

async def send_reminder_makan(app, waktu: str):
    uid = USERS.get("Freya")
    if not uid or uid == 0: return
    try:
        day_idx = datetime.now(WITA).weekday()
        pools   = {"pagi": _MAKAN_PAGI, "siang": _MAKAN_SIANG, "sore": _MAKAN_SORE}
        msg     = pools[waktu][day_idx % len(pools[waktu])]
        await app.bot.send_message(uid, msg, parse_mode="Markdown")
        log.info(f"Reminder makan {waktu} terkirim ke Freya.")
    except Exception as e:
        log.error(f"Gagal kirim reminder makan {waktu} ke Freya: {e}")

# ═══════════════════════════════════════════════════════════════
#  REMINDER FREYA — ISTIRAHAT & JANGAN BEGADANG 😴
# ═══════════════════════════════════════════════════════════════

_ISTIRAHAT_SIANG = [
    "💤 *Habis makan, istirahat dulu ya sayang!*\n\nNggak harus tidur siang, rebahan sebentar juga udah cukup 🛋️\nJaga energi buat aktivitas sore~ ❤️",
    "😌 *Yuk istirahat sebentar, cintaku~*\n\nBadan juga butuh jeda lho sayang 💕\nMeski cuma 15-20 menit, udah ngebantu banget 🌸",
    "☁️ *Me time sebentar yaa sayang!*\n\nAbis makan, luangin waktu buat istirahat dulu 💤\nAku sayang kamu makanya aku ingetin~ 🤖❤️",
    "🛋️ *Rehat dulu ya sayang~*\n\nJangan langsung balik aktivitas, kasih tubuh kamu waktu buat istirahat 💕\nKamu penting banget buat aku 🥺❤️",
]

_JANGAN_BEGADANG_11 = [
    "🌙 *Hei sayang, udah jam 11 malam lho!*\n\nYuk mulai bersiap tidur ya cintaku 🥺\nJangan begadang, istirahat yang cukup penting banget buat kesehatan kamu~ 💕",
    "⭐ *Sayang, udah larut malam nih~*\n\nJangan begadang yaa! Tubuh kamu perlu istirahat 💤\nBesok masih ada aktivitas, hemat energinya sekarang~ 🌸❤️",
    "🌛 *Psst sayang, udah jam 11!*\n\nWaktunya mulai winding down dan bersiap tidur 🛏️\nJangan begadang ya cintaku, aku khawatir sama kesehatanmu 🥺💕",
    "💫 *Malam sayang, ini udah jam 11~*\n\nYuk simpan HP sebentar dan bersiap istirahat 🌙\nTidur yang cukup biar besok tetap semangat ya cintaku ❤️",
]

_JANGAN_BEGADANG_12 = [
    "🌚 *Sayang, ini udah tengah malam!*\n\nYuk tidur sekarang ya, jangan begadang lagi 🥺\nKalau kamu sehat, aku juga tenang~ 💕 Selamat istirahat cintaku! 😴❤️",
    "💤 *Tengah malam nih sayang~*\n\nSerius deh, yuk tidur sekarang! Jangan begadang 😔\nIstirahatin badanmu, besok bisa lanjut lagi kegiatannya~ 🌙❤️",
    "🌟 *Ayo tidur sayang, udah malam banget!*\n\nJangan begadang ya cintaku 🥺\nBadan butuh istirahat yang cukup biar tetap fit 💪\nSelamat tidur, mimpi indah ya~ 😴💕",
    "🌙 *Ini udah 12 malam lho sayang...*\n\nAku khawatir kamu belum tidur 🥺\nYuk istirahat, jangan begadang ya cintaku\nBadan yang sehat itu nomor satu~ ❤️ Good night sayang!",
]

async def send_reminder_istirahat(app, waktu: str):
    uid = USERS.get("Freya")
    if not uid or uid == 0: return
    try:
        day_idx = datetime.now(WITA).weekday()
        pools   = {
            "siang"   : _ISTIRAHAT_SIANG,
            "malam_11": _JANGAN_BEGADANG_11,
            "malam_12": _JANGAN_BEGADANG_12,
        }
        msg = pools[waktu][day_idx % len(pools[waktu])]
        await app.bot.send_message(uid, msg, parse_mode="Markdown")
        log.info(f"Reminder istirahat {waktu} terkirim ke Freya.")
    except Exception as e:
        log.error(f"Gagal kirim reminder istirahat {waktu} ke Freya: {e}")

# ═══════════════════════════════════════════════════════════════
#  STREAK BROKEN ALERT — dikirim pagi kalau streak putus semalam
# ═══════════════════════════════════════════════════════════════
async def send_streak_broken_alert(app):
    """
    Cek semua user. Kalau streak mereka aktif tapi kemarin
    tidak ada transaksi (streak putus), kirim notif.
    """
    for name, uid in USERS.items():
        if uid == 0: continue
        try:
            broken_streak = await run(db_check_streak_broken, uid)
            if broken_streak > 0:
                badge = streak_badge(broken_streak)
                await app.bot.send_message(
                    uid,
                    f"💔 *Aduh, streak kamu putus...*\n\n"
                    f"{badge} Streak *{broken_streak} hari* kamu hilang kemarin 😢\n\n"
                    f"Tenang, nggak apa-apa! Yuk mulai lagi dari hari ini 💪\n"
                    f"Streak baru dimulai pas kamu catat transaksi pertama!\n\n"
                    f"➕ /nabung  |  ➖ /keluar",
                    parse_mode="Markdown"
                )
                log.info(f"Streak broken alert terkirim ke {name} (streak {broken_streak} putus)")
        except Exception as e:
            log.error(f"Gagal kirim streak broken alert ke {name}: {e}")

# ═══════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════
def main():
    log.info("Inisialisasi Google Sheets...")
    init_sheets()

    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
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
    app.add_handler(conv)

    for cmd, fn in [
        ("start",         cmd_start),
        ("help",          cmd_start),
        ("myid",          cmd_myid),
        ("spreadsheet",   cmd_spreadsheet),
        ("saldo",         cmd_saldo),
        ("laporan",       cmd_laporan),
        ("bulanan",       cmd_bulanan),
        ("riwayat",       cmd_riwayat),
        ("bersama",       cmd_bersama),
        ("tujuan",        cmd_tujuan),
        ("addtarget",     cmd_addtarget),
        ("isitarget",     cmd_isitarget),
        ("catatan",       cmd_catatan),
        ("hapusterakhir", cmd_hapusterakhir),
        ("streak",        cmd_streak),
    ]:
        app.add_handler(CommandHandler(cmd, fn))

    # ── Scheduler ────────────────────────────────────────────────
    scheduler = AsyncIOScheduler()

    # 📊 Laporan mingguan — Senin 08:00 WIB
    scheduler.add_job(
        send_weekly_report, "cron",
        day_of_week=REPORT_WEEKDAY, hour=REPORT_HOUR, minute=REPORT_MINUTE,
        timezone="Asia/Jakarta", args=[app]
    )

    # 💔 Cek streak putus — setiap hari 07:00 WITA (sebelum reminder nabung)
    scheduler.add_job(
        send_streak_broken_alert, "cron",
        hour=7, minute=0, timezone="Asia/Makassar", args=[app]
    )

    # 💰 Reminder nabung Freya
    scheduler.add_job(send_reminder_nabung, "cron",
        hour=9, minute=0, timezone="Asia/Makassar", args=[app, "pagi"])
    scheduler.add_job(send_reminder_nabung, "cron",
        hour=21, minute=0, timezone="Asia/Makassar", args=[app, "malam"])

    # 🍱 Reminder makan & minum Freya
    scheduler.add_job(send_reminder_makan, "cron",
        hour=9, minute=0, timezone="Asia/Makassar", args=[app, "pagi"])
    scheduler.add_job(send_reminder_makan, "cron",
        hour=12, minute=30, timezone="Asia/Makassar", args=[app, "siang"])
    scheduler.add_job(send_reminder_makan, "cron",
        hour=15, minute=30, timezone="Asia/Makassar", args=[app, "sore"])

    # 😴 Reminder istirahat & jangan begadang Freya
    scheduler.add_job(send_reminder_istirahat, "cron",
        hour=12, minute=31, timezone="Asia/Makassar", args=[app, "siang"])
    scheduler.add_job(send_reminder_istirahat, "cron",
        hour=23, minute=0, timezone="Asia/Makassar", args=[app, "malam_11"])
    scheduler.add_job(send_reminder_istirahat, "cron",
        hour=0, minute=0, timezone="Asia/Makassar", args=[app, "malam_12"])

    scheduler.start()

    log.info("✅ TabunganBot berjalan!")
    log.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    log.info("📅 Jadwal aktif:")
    log.info("   📊 Laporan mingguan       → Senin 08:00 WIB")
    log.info("   💔 Cek streak putus       → 07:00 WITA (semua user)")
    log.info("   💰 Reminder nabung pagi   → 09:00 WITA (+streak warning)")
    log.info("   🍳 Reminder sarapan       → 09:00 WITA")
    log.info("   🍱 Reminder makan siang   → 12:30 WITA")
    log.info("   💤 Reminder istirahat     → 12:31 WITA")
    log.info("   🍎 Reminder makan sore    → 15:30 WITA")
    log.info("   💰 Reminder nabung malam  → 21:00 WITA (+streak warning)")
    log.info("   🌙 Jangan begadang #1     → 23:00 WITA")
    log.info("   🌚 Jangan begadang #2     → 00:00 WITA")
    log.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
