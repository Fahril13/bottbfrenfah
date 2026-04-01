#!/usr/bin/env python3
"""
TabunganBot 💰 — versi Google Sheets
Data tersimpan permanen di Google Spreadsheet
Untuk: Fahril & Freya
"""

import os
import asyncio
import logging
from datetime import datetime, timedelta
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
#  KONFIGURASI ─ WAJIB DIISI
# ═══════════════════════════════════════════════════════════════
BOT_TOKEN        = os.getenv("BOT_TOKEN", "GANTI_TOKEN_BOT")
SPREADSHEET_ID   = os.getenv("SPREADSHEET_ID", "GANTI_ID_SPREADSHEET")
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE", "credentials.json")

# Telegram User ID masing-masing (kirim /myid ke bot untuk tahu ID)
USERS: dict[str, int] = {
    "Fahril": 5210728658,   # ← ganti dengan Telegram ID Fahril
    "Freya" : 6434745020,   # ← ganti dengan Telegram ID Freya
}

REPORT_WEEKDAY = 0   # 0=Senin
REPORT_HOUR    = 8
REPORT_MINUTE  = 0
WIB            = ZoneInfo("Asia/Jakarta")

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
log = logging.getLogger(__name__)

# ConversationHandler states
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
        info = json.loads(gc_env)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    return gspread.authorize(creds)

def _get_or_create_sheet(spreadsheet, title: str, headers: list[str]):
    """Ambil worksheet, buat baru dengan header jika belum ada."""
    try:
        ws = spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=title, rows=5000, cols=len(headers))
        ws.append_row(headers, value_input_option="USER_ENTERED")
    return ws

def init_sheets():
    """Inisialisasi semua worksheet yang diperlukan."""
    client = _get_client()
    ss = client.open_by_key(SPREADSHEET_ID)

    _get_or_create_sheet(ss, "Transaksi", [
        "ID", "UserID", "Nama", "Tipe", "Jumlah", "Kategori", "Catatan", "Waktu"
    ])
    _get_or_create_sheet(ss, "Tujuan", [
        "ID", "UserID", "Judul", "Target", "Terkumpul", "Selesai", "Waktu"
    ])
    _get_or_create_sheet(ss, "Catatan", [
        "ID", "UserID", "Isi", "Waktu"
    ])
    log.info("✅ Google Sheets siap.")

# ─── Helpers ────────────────────────────────────────────────────
def _ss():
    return _get_client().open_by_key(SPREADSHEET_ID)

def _now() -> str:
    return datetime.now(WIB).strftime("%Y-%m-%d %H:%M:%S")

def _next_id(ws) -> int:
    rows = ws.get_all_values()
    if len(rows) <= 1:
        return 1
    last = rows[-1][0]
    return int(last) + 1 if str(last).isdigit() else 1

# ─── Transaksi ──────────────────────────────────────────────────
def db_add_transaction(uid, name, kind, amount, category, note):
    ss = _ss()
    ws = ss.worksheet("Transaksi")
    nid = _next_id(ws)
    ws.append_row(
        [nid, uid, name, kind, amount, category, note, _now()],
        value_input_option="USER_ENTERED"
    )

def db_get_transactions(uid: int, since_days: int | None = None, limit: int = 100):
    ws = _ss().worksheet("Transaksi")
    rows = ws.get_all_records()
    result = [r for r in rows if str(r["UserID"]) == str(uid)]
    if since_days is not None:
        cutoff = (datetime.now(WIB) - timedelta(days=since_days)).strftime("%Y-%m-%d %H:%M:%S")
        result = [r for r in result if str(r["Waktu"]) >= cutoff]
    result.sort(key=lambda r: r["Waktu"], reverse=True)
    return result[:limit]

def db_get_balance(uid: int) -> float:
    rows = db_get_transactions(uid)
    total = 0.0
    for r in rows:
        a = float(r["Jumlah"])
        total += a if r["Tipe"] == "income" else -a
    return total

def db_get_summary(uid: int, since_days: int = 7):
    rows = db_get_transactions(uid, since_days=since_days)
    inc = sum(float(r["Jumlah"]) for r in rows if r["Tipe"] == "income")
    exp = sum(float(r["Jumlah"]) for r in rows if r["Tipe"] == "expense")
    return inc, exp, rows

def db_delete_last_transaction(uid: int) -> bool:
    ws = _ss().worksheet("Transaksi")
    all_vals = ws.get_all_values()
    for i in range(len(all_vals) - 1, 0, -1):
        if str(all_vals[i][1]) == str(uid):
            ws.delete_rows(i + 1)
            return True
    return False

def db_get_monthly_cats(uid: int):
    m = datetime.now(WIB).strftime("%Y-%m")
    rows = db_get_transactions(uid)
    rows = [r for r in rows if str(r["Waktu"]).startswith(m)]
    cats: dict[tuple, float] = {}
    for r in rows:
        key = (r["Kategori"], r["Tipe"])
        cats[key] = cats.get(key, 0) + float(r["Jumlah"])
    return [(k[0], k[1], v) for k, v in sorted(cats.items(), key=lambda x: -x[1])]

# ─── Tujuan ─────────────────────────────────────────────────────
def db_get_goals(uid: int):
    ws = _ss().worksheet("Tujuan")
    rows = ws.get_all_records()
    return [r for r in rows if str(r["UserID"]) == str(uid)]

def db_add_goal(uid, title, target):
    ws = _ss().worksheet("Tujuan")
    nid = _next_id(ws)
    ws.append_row([nid, uid, title, target, 0, "Tidak", _now()], value_input_option="USER_ENTERED")

def db_update_goal(goal_id: int, amount: float):
    ws = _ss().worksheet("Tujuan")
    all_vals = ws.get_all_values()
    for i, row in enumerate(all_vals[1:], start=2):
        if str(row[0]) == str(goal_id):
            new_saved = float(row[4]) + amount
            target    = float(row[3])
            ws.update_cell(i, 5, new_saved)
            if new_saved >= target:
                ws.update_cell(i, 6, "Ya")
            return float(row[3]), new_saved
    return None, None

# ─── Catatan ────────────────────────────────────────────────────
def db_add_note(uid, content):
    ws = _ss().worksheet("Catatan")
    nid = _next_id(ws)
    ws.append_row([nid, uid, content, _now()], value_input_option="USER_ENTERED")

def db_get_notes(uid: int):
    ws = _ss().worksheet("Catatan")
    rows = ws.get_all_records()
    result = [r for r in rows if str(r["UserID"]) == str(uid)]
    return sorted(result, key=lambda r: r["Waktu"], reverse=True)[:10]

# ─── Async wrapper ───────────────────────────────────────────────
async def run(func, *args):
    """Jalankan fungsi sync Google Sheets di thread terpisah."""
    return await asyncio.to_thread(func, *args)

# ═══════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════
def rp(n: float) -> str:
    return f"Rp {int(n):,}".replace(",", ".")

def progress_bar(pct: float, width=12) -> str:
    filled = round(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)

def kb_grid(items, cols=2) -> InlineKeyboardMarkup:
    rows = [items[i:i+cols] for i in range(0, len(items), cols)]
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(t, callback_data=t) for t in r] for r in rows]
    )

def get_user_name(uid: int) -> str | None:
    return next((n for n, i in USERS.items() if i == uid), None)

def authorized(uid: int) -> bool:
    return uid in USERS.values() and uid != 0

async def check_auth(u: Update) -> bool:
    uid = u.effective_user.id
    if not authorized(uid):
        await u.message.reply_text(
            f"⛔ *Akses ditolak!*\n\nID Telegram kamu: `{uid}`\n"
            f"Minta Fahril/Freya tambahkan ID ini.",
            parse_mode="Markdown"
        )
        return False
    return True

def loading(msg="⏳ Memuat data..."):
    async def _send(u: Update):
        return await u.message.reply_text(msg)
    return _send

# ═══════════════════════════════════════════════════════════════
#  COMMAND HANDLERS
# ═══════════════════════════════════════════════════════════════
async def cmd_start(u: Update, _):
    uid = u.effective_user.id
    if not authorized(uid):
        await u.message.reply_text(
            f"👋 Bot ini khusus untuk Fahril & Freya.\n\n"
            f"🪪 ID Telegram kamu: `{uid}`\n"
            f"Hubungi pemilik untuk mendapatkan akses.",
            parse_mode="Markdown"
        )
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
        f"🎯 /tujuan — Target tabungan\n"
        f"👥 /bersama — Rekap Fahril+Freya\n"
        f"🗒️ /catatan — Catatan keuangan\n"
        f"↩️ /hapusterakhir — Hapus transaksi terakhir\n"
        f"🔗 /spreadsheet — Link Google Sheets\n"
        f"🆔 /myid — Lihat Telegram ID\n\n"
        f"_📊 Data tersimpan permanen di Google Sheets_\n"
        f"_📬 Laporan otomatis tiap Senin 08:00 WIB_",
        parse_mode="Markdown"
    )

async def cmd_myid(u: Update, _):
    uid  = u.effective_user.id
    name = get_user_name(uid) or "Belum terdaftar"
    await u.message.reply_text(
        f"🪪 *Info Akun*\n\nID Telegram: `{uid}`\nNama di bot: *{name}*",
        parse_mode="Markdown"
    )

async def cmd_spreadsheet(u: Update, _):
    if not await check_auth(u): return
    await u.message.reply_text(
        f"🔗 *Link Google Sheets:*\n"
        f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}",
        parse_mode="Markdown"
    )

async def cmd_saldo(u: Update, _):
    if not await check_auth(u): return
    uid  = u.effective_user.id
    name = get_user_name(uid)
    wait = await u.message.reply_text("⏳ Mengambil data...")
    bal            = await run(db_get_balance, uid)
    inc7,  exp7,  _ = await run(db_get_summary, uid, 7)
    inc30, exp30, _ = await run(db_get_summary, uid, 30)
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
        f"📊 Selisih   : {rp(inc30 - exp30)}",
        parse_mode="Markdown"
    )

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
    if rows:
        for r in rows[:12]:
            icon = "⬆️" if r["Tipe"] == "income" else "⬇️"
            note = f" _{r['Catatan']}_" if r.get("Catatan") else ""
            lines.append(f"{icon} *{rp(float(r['Jumlah']))}* — {r['Kategori']}{note}")
            lines.append(f"    `{str(r['Waktu'])[:16]}`")
    else:
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
    if rows:
        for r in rows:
            icon = "⬆️" if r["Tipe"] == "income" else "⬇️"
            note = f"\n     _{r['Catatan']}_" if r.get("Catatan") else ""
            lines.append(f"{icon} *{rp(float(r['Jumlah']))}* — {r['Kategori']}{note}")
            lines.append(f"    `{str(r['Waktu'])[:16]}`\n")
    else:
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
        total_bal += bal; total_inc += inc7; total_exp += exp7
        lines.append(f"👤 *{name}*")
        lines.append(f"  💰 Saldo     : {rp(bal)}")
        lines.append(f"  📈 Masuk 7hr : {rp(inc7)}")
        lines.append(f"  📉 Keluar 7hr: {rp(exp7)}\n")
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
            "Contoh: `/addtarget 5000000 Liburan Bali`"
        )
    else:
        for r in goals:
            target = float(r["Target"])
            saved  = float(r["Terkumpul"])
            done   = r["Selesai"] == "Ya"
            pct    = min(100.0, (saved / target * 100) if target > 0 else 0)
            bar    = progress_bar(pct)
            status = "✅" if done else "🔄"
            lines.append(f"{status} *{r['Judul']}* (ID: {r['ID']})")
            lines.append(f"  `{bar}` {pct:.1f}%")
            lines.append(f"  {rp(saved)} / {rp(target)}\n")
        lines.append("Tambah progres: `/isitarget [id] [jumlah]`")
    await u.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_addtarget(u: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(u): return
    uid = u.effective_user.id
    if not ctx.args or len(ctx.args) < 2:
        await u.message.reply_text(
            "Format: `/addtarget [jumlah] [nama target]`\n"
            "Contoh: `/addtarget 5000000 Liburan Bali`",
            parse_mode="Markdown"
        ); return
    try:
        amount = float(ctx.args[0].replace(".", "").replace(",", ""))
        title  = " ".join(ctx.args[1:])
        wait   = await u.message.reply_text("⏳ Menyimpan target...")
        await run(db_add_goal, uid, title, amount)
        await wait.delete()
        await u.message.reply_text(
            f"🎯 Target *{title}* sebesar *{rp(amount)}* berhasil dibuat!\n"
            f"Lihat progres di /tujuan",
            parse_mode="Markdown"
        )
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
        bar  = progress_bar(pct)
        done = saved >= target
        msg  = "✅ *Target Tercapai! 🎉*" if done else "🔄 *Progres Diperbarui!*"
        await u.message.reply_text(
            f"{msg}\n\n`{bar}` {pct:.1f}%\n{rp(saved)} / {rp(target)}",
            parse_mode="Markdown"
        )
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
    ok  = await run(db_delete_last_transaction, uid)
    bal = await run(db_get_balance, uid)
    await wait.delete()
    if ok:
        await u.message.reply_text(
            f"↩️ Transaksi terakhir dihapus.\n💰 Saldo sekarang: *{rp(bal)}*",
            parse_mode="Markdown"
        )
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
    wait   = await msg.reply_text("⏳ Menyimpan ke Google Sheets...")
    await run(db_add_transaction, uid, name, kind, amount, cat, note)
    bal = await run(db_get_balance, uid)
    await wait.delete()
    icon   = "📈" if kind == "income" else "📉"
    action = "Pemasukan" if kind == "income" else "Pengeluaran"
    await msg.reply_text(
        f"{icon} *{action} Berhasil Dicatat!*\n\n"
        f"👤 {name}\n"
        f"💵 Jumlah   : *{rp(amount)}*\n"
        f"📂 Kategori : {cat}\n"
        f"📝 Catatan  : {note or '-'}\n\n"
        f"💰 Saldo Sekarang: *{rp(bal)}*\n"
        f"_✅ Tersimpan di Google Sheets_",
        parse_mode="Markdown"
    )

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
            lines = [
                f"📊 *Laporan Mingguan — {name}* 🗓",
                f"_{datetime.now(WIB).strftime('%d %B %Y, %H:%M WIB')}_\n",
                f"📈 Pemasukan : *{rp(inc)}*",
                f"📉 Pengeluaran: *{rp(exp)}*",
                f"💰 Saldo Total: *{rp(bal)}*\n",
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
    ]:
        app.add_handler(CommandHandler(cmd, fn))

    scheduler = AsyncIOScheduler(timezone="Asia/Jakarta")
    scheduler.add_job(
        send_weekly_report, "cron",
        day_of_week=REPORT_WEEKDAY,
        hour=REPORT_HOUR, minute=REPORT_MINUTE,
        args=[app]
    )
    scheduler.start()

    log.info("✅ TabunganBot (Google Sheets) berjalan!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
