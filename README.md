# 💰 TabunganBot — Versi Google Sheets

Data tersimpan **permanen** di Google Spreadsheet. Aman meski bot restart,
redeploy, atau pindah server sekalipun.

---

## 🗂️ Struktur Data di Google Sheets

Bot otomatis membuat 3 sheet:

| Sheet | Isi |
|-------|-----|
| **Transaksi** | Semua pemasukan & pengeluaran |
| **Tujuan** | Target tabungan + progres |
| **Catatan** | Catatan keuangan bebas |

---

## 🚀 Setup (±15 menit, sekali saja)

### LANGKAH 1 — Buat Bot Telegram
1. Buka **@BotFather** di Telegram
2. Kirim `/newbot` → ikuti instruksi
3. Simpan **token** yang diberikan

---

### LANGKAH 2 — Buat Google Spreadsheet
1. Buka https://sheets.google.com
2. Buat spreadsheet baru, beri nama **TabunganFahrilFreya**
3. Copy **ID spreadsheet** dari URL:
   ```
   https://docs.google.com/spreadsheets/d/[INI_SPREADSHEET_ID]/edit
   ```

---

### LANGKAH 3 — Buat Google Service Account

1. Buka https://console.cloud.google.com
2. Buat project baru (atau pakai yang ada)
3. Aktifkan **Google Sheets API**:
   - Search "Google Sheets API" → Enable
4. Buat **Service Account**:
   - IAM & Admin → Service Accounts → Create
   - Isi nama, klik Done
5. Download **JSON key**:
   - Klik service account yang baru dibuat
   - Tab **Keys** → Add Key → JSON → Download
   - Rename file jadi `credentials.json`
   - Taruh di folder yang sama dengan `bot.py`
6. Copy **email** service account
   (contoh: `bot@project-xxx.iam.gserviceaccount.com`)

---

### LANGKAH 4 — Share Spreadsheet ke Service Account
1. Buka spreadsheet tadi
2. Klik tombol **Share** (pojok kanan atas)
3. Paste email service account
4. Pilih role **Editor**
5. Klik Send

---

### LANGKAH 5 — Isi Konfigurasi di `bot.py`

```python
BOT_TOKEN      = os.getenv("BOT_TOKEN", "TOKEN_DARI_BOTFATHER")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "ID_DARI_URL_SPREADSHEET")

USERS = {
    "Fahril": 123456789,   # Telegram ID Fahril
    "Freya" : 987654321,   # Telegram ID Freya
}
```

> **Cara tahu Telegram ID:** jalankan bot dulu, lalu kirim `/myid`

---

### LANGKAH 6 — Install & Jalankan

```bash
pip install -r requirements.txt
python bot.py
```

---

## ☁️ Deploy 24 Jam Gratis

### Railway.app (Paling Mudah ✅)
1. Push kode ke GitHub (termasuk `credentials.json`)
2. Daftar di https://railway.app → New Project → dari GitHub
3. Set environment variables:
   ```
   BOT_TOKEN=token_botmu
   SPREADSHEET_ID=id_spreadsheet
   ```
4. Deploy → selesai, jalan terus!

> ⚠️ Jika tidak ingin upload `credentials.json` ke GitHub,
> bisa set isinya sebagai env var `GOOGLE_CREDENTIALS` dan
> modifikasi kode untuk membaca dari env.

### VPS
```bash
pip install -r requirements.txt
screen -S tabunganbot
python bot.py
# Ctrl+A lalu D untuk detach
```

---

## 💡 Contoh Penggunaan

```
# Catat cepat (1 baris)
/nabung 2500000 gaji bulan Maret
/keluar 45000 makan siang warteg

# Catat interaktif (tanpa argumen)
/nabung   → bot panduin step by step

# Target tabungan
/addtarget 10000000 Dana Darurat
/addtarget 3000000 Kado Ultah Freya
/isitarget 1 500000   ← tambah 500rb ke target ID 1

# Laporan
/saldo      → saldo + ringkasan
/laporan    → detail 7 hari
/bulanan    → rekap bulan ini
/bersama    → rekap Fahril & Freya sekaligus
```

---

## 📁 Struktur File
```
tabungan_bot_sheets/
├── bot.py            # Kode utama
├── credentials.json  # ← kamu download dari Google Console
├── requirements.txt
└── README.md
```
# botfrenfah
