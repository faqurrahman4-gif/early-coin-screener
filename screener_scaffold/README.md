# Early-Stage Coin Screener — Versi Full Cloud

Semua langkah di bawah dilakukan lewat **browser**, tidak perlu install
Python, Git, atau aplikasi apa pun di laptop. Ada 2 layanan gratis yang
dipakai:

1. **GitHub** — tempat menyimpan kode + menjalankan pipeline scoring
   secara terjadwal (lewat GitHub Actions).
2. **Streamlit Community Cloud** — meng-hosting tampilan web app-nya,
   otomatis membaca hasil dari GitHub.

## Langkah 1 — Buat akun GitHub (kalau belum punya)
Daftar gratis di github.com pakai email. Tidak perlu install apa pun.

## Langkah 2 — Buat repository baru
1. Klik "New repository" di github.com.
2. Beri nama, mis. `token-screener`.
3. **Set ke Public** (wajib untuk Streamlit Community Cloud gratis).
4. Centang "Add a README file" lalu klik "Create repository".

> Catatan penting soal privasi: repo Public artinya **kode** bisa dilihat
> siapa saja. Ini bukan masalah karena kode ini tidak berisi rahasia apa
> pun (API key disimpan terpisah lewat "Secrets", bukan di kode — lihat
> Langkah 4). Yang perlu kamu sadari: data hasil skor (`data/snapshots.json`)
> juga akan ikut publik kalau kamu commit ke repo publik ini. Kalau ingin
> data skor benar-benar privat, opsinya adalah upgrade ke repo Private
> (GitHub Actions tetap gratis di repo private sampai batas menit
> tertentu/bulan) dan pakai Streamlit Community Cloud versi yang mendukung
> repo private (perlu cek ketersediaan akun kamu), atau simpan
> `data/snapshots.json` di luar repo (mis. Google Sheets) — kalau kamu mau
> opsi ini, beri tahu saya, saya sesuaikan kodenya.

## Langkah 3 — Upload semua file dari scaffold ini
Di halaman repo GitHub kamu:
1. Klik "Add file" → "Upload files".
2. Drag & drop **semua isi folder** `screener_scaffold` (termasuk folder
   `.github`, `screener`, dan file-file di root) ke area upload.
   - Browser kadang tidak bisa upload folder kosong (`data/`) — kalau
     folder `data` tidak ikut ter-upload, buat manual: klik "Add file" →
     "Create new file", beri nama `data/snapshots.json`, isi dengan `[]`,
     lalu commit.
3. Klik "Commit changes".

## Langkah 4 — Tambahkan API key sebagai Secret (bukan ditulis di kode)
1. Di repo, buka tab **Settings** → **Secrets and variables** → **Actions**.
2. Klik "New repository secret".
3. Name: `GEMINI_API_KEY`, Value: API key gratis dari Google AI Studio.
   - Buka aistudio.google.com, login pakai akun Google biasa.
   - Klik "Get API key" → "Create API key in new project".
   - **Tidak perlu kartu kredit atau billing aktif** untuk tier gratis ini.
4. Klik "Add secret".

## Langkah 5 — (Opsional) Tambahkan riset manual untuk token tertentu
Discovery-nya sekarang **otomatis** — `screener/discovery.py` men-scan pool
DEX baru lewat GeckoTerminal API (gratis, tanpa key) di beberapa chain
(Ethereum, Solana, Base, Arbitrum, BSC), lalu filter token berumur 3-13
bulan. Kamu tidak perlu isi watchlist manual lagi.

Tapi beberapa data (mis. "% fee ke buyback", "top 10 wallet voting power")
memang tidak bisa ditarik otomatis dari API mana pun — ini realistis,
karena setiap proyek beda cara melaporkannya. Untuk token yang sudah kamu
riset lebih dalam, tambahkan datanya di `MANUAL_OVERRIDES` dalam
`run_screener.py` (edit langsung di GitHub, klik file → ikon pensil →
commit) — contoh HYPE sudah ada di scaffold. Token yang belum punya
override tetap muncul di screener, hanya saja beberapa faktornya ditandai
"Insufficient" di tampilan sampai kamu lengkapi risetnya.

## Langkah 6 — Jalankan workflow pertama kali (manual)
1. Buka tab **Actions** di repo.
2. Pilih workflow "Run Screener" di sidebar kiri.
3. Klik tombol "Run workflow" → "Run workflow" (trigger manual, tidak
   perlu nunggu jadwal bulanan).
4. Tunggu 1-3 menit sampai selesai (tanda centang hijau). Ini akan mengisi
   `data/snapshots.json` dengan skor pertama.

Setelah ini, workflow akan otomatis jalan ulang sesuai jadwal cron di
`.github/workflows/run_screener.yml` (default: tanggal 1 tiap bulan) —
kamu tidak perlu memicu manual lagi kecuali mau update lebih cepat.

## Langkah 7 — Deploy tampilan web di Streamlit Community Cloud
1. Buka **share.streamlit.io**, klik "Sign up" / "Sign in" pakai akun
   GitHub kamu (satu klik, tidak perlu password baru).
2. Klik "Create app" → pilih "Deploy a public app from GitHub".
3. Pilih repo `token-screener`, branch `main`, file utama `app.py`.
4. Klik "Deploy". Tunggu beberapa menit — Streamlit Cloud yang
   menginstall semua dependency dari `requirements.txt` di server mereka.
5. Selesai — kamu dapat URL publik (mis. `https://token-screener.streamlit.app`)
   yang bisa dibuka kapan saja dari browser mana pun, termasuk HP.

Setiap kali GitHub Actions meng-update `data/snapshots.json`, Streamlit
Cloud otomatis mendeteksi perubahan di repo dan me-refresh app-nya —
kamu tidak perlu redeploy manual.

## Ringkasan alur setelah semua setup selesai
```
[Jadwal bulanan] GitHub Actions jalan otomatis
   → jalankan run_screener.py di server GitHub
   → tarik data DefiLlama/CoinGecko/whitepaper (LLM)
   → hitung skor 8 faktor
   → commit data/snapshots.json ke repo
        ↓
Streamlit Community Cloud mendeteksi perubahan repo
   → otomatis refresh app.py
        ↓
Kamu buka URL app-nya kapan saja lewat browser — tidak perlu jalankan apa pun
```

## Bagian yang masih perlu kamu lengkapi (tidak realistis 100% otomatis)
- Beberapa angka per token masih perlu diisi manual di `MANUAL_OVERRIDES`
  (`fee_share_to_buyback_pct`, `top10_wallet_voting_power_pct`, dll) —
  tidak ada API tunggal yang memberi angka ini otomatis. Token tanpa
  override tetap muncul di screener, faktor terkait ditandai "Insufficient".
- Struktur JSON DefiLlama untuk revenue 30 hari perlu disesuaikan sambil
  jalan (lihat komentar `# TODO: sesuaikan` di `screener/pipeline.py`) —
  bentuk respons API bisa berbeda per protokol.
- `defillama_slug` dan `category` (untuk Faktor #2 dan #3) belum
  di-resolve otomatis dari hasil discovery — token yang baru murni hasil
  auto-discovery (belum ada di `MANUAL_OVERRIDES`) akan menandai kedua
  faktor ini "Insufficient" sampai kamu isi manual.

## Struktur file
```
token-screener/
├── .github/workflows/run_screener.yml   # otomasi jadwal (GitHub Actions)
├── run_screener.py                       # entry point — isi watchlist di sini
├── app.py                                # tampilan Streamlit
├── requirements.txt
├── data/snapshots.json                   # hasil skor, di-update otomatis
└── screener/
    ├── config.py          # bobot, threshold, age multiplier, network yang di-scan
    ├── discovery.py       # scan pool DEX baru otomatis (GeckoTerminal API)
    ├── data_sources.py    # DefiLlama, CoinGecko, block explorer
    ├── llm_reader.py      # scraper whitepaper + panggilan Claude API
    ├── scoring.py         # rumus 0-20 semua 8 faktor
    ├── storage.py         # baca/tulis data/snapshots.json
    └── pipeline.py        # orkestrasi end-to-end per token
```
