"""
Qualitative data layer — baca whitepaper/docs resmi proyek pakai Google
Gemini API (FREE TIER ASLI, tanpa kartu kredit), lalu keluarkan skor
terstruktur untuk Faktor #4 (tokenomics) dan #5 (utilitas). Governance (#6)
dicek terpisah lewat Snapshot.org API (tidak butuh LLM sama sekali).

Kenapa Gemini, bukan API berbayar: Google AI Studio memberi API key gratis
tanpa perlu isi kartu kredit sama sekali (beda dengan Anthropic/OpenAI yang
mewajibkan billing aktif). Ada batas rate limit (request per menit/hari),
tapi untuk screening ~10-20 token/bulan ini jauh lebih dari cukup.

Dipanggil lewat REST API langsung (requests) supaya tidak perlu dependency
tambahan (google-generativeai SDK) — cukup dengan requests yang sudah ada
di requirements.txt.

Cara dapat API key gratis: aistudio.google.com -> "Get API key" -> "Create
API key" -> pilih project baru -> copy key-nya (diawali "AIza..."). TIDAK
perlu isi info kartu kredit untuk pakai tingkatan gratis.

Butuh: environment variable GEMINI_API_KEY
"""

import json
import os
import requests
import trafilatura
from . import config


# ---------------------------------------------------------------------------
# Scraper: ambil teks bersih dari halaman whitepaper/docs resmi
# ---------------------------------------------------------------------------

def scrape_docs_text(url: str) -> str | None:
    """
    Ambil teks utama dari satu halaman docs/whitepaper.
    Untuk whitepaper multi-halaman (mis. GitBook), panggil fungsi ini per URL
    dan gabungkan hasilnya sebelum dikirim ke LLM.
    """
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        return None
    return trafilatura.extract(downloaded, include_tables=True, include_links=False)


# ---------------------------------------------------------------------------
# Rubrik terstruktur — inti dari "LLM whitepaper reader"
# ---------------------------------------------------------------------------

RUBRIC_PROMPT = """Kamu adalah analis tokenomik yang menilai dokumen resmi
sebuah proyek crypto (whitepaper/docs/tokenomics page). Baca teks di bawah,
lalu isi rubrik berikut SEOBJEKTIF mungkin berdasarkan fakta yang benar-benar
tertulis. Jangan menebak angka atau fakta yang tidak disebutkan — kalau tidak
ada, tulis null (untuk field string/angka) atau [] (untuk list) dan turunkan
confidence. AturAN PALING PENTING: JANGAN MENGARANG. Kalau whitepaper tidak
menyebutkan siapa tim/backer proyek, tulis null — JANGAN menebak nama VC atau
orang terkenal manapun.

RUMUS SKOR YANG HARUS KAMU IKUTI:

Faktor 4 - Tokenomics & Struktur Supply (skor 0-20):
  Mulai dari 20, kurangi:
  - Alokasi VC/private sale >30% dari total supply → -5
  - Tidak ada dokumentasi tokenomics resmi/publik  → -6
  - Unlock >15% circulating supply dalam 90 hari ke depan → -5
  - Insider/tim memegang >20% circulating supply   → -4
  Minimum 0.

Faktor 5 - Utilitas Token (skor 0-20):
  +4 per use case WAJIB (bukan opsional) yang ditemukan:
    staking keamanan jaringan, gas fee wajib, collateral/akses fitur inti,
    governance voting berdampak, fee discount/tier signifikan.
  Use case kosmetik/opsional = 0 poin. Maksimal 20.

Jawab HANYA dalam format JSON valid, tanpa teks lain, dengan struktur:
{
  "tokenomics": {
    "skor_0_20": <int>,
    "alokasi_vc_persen": <float atau null>,
    "insider_persen_circulating": <float atau null>,
    "unlock_90_hari_persen": <float atau null>,
    "ada_dokumentasi_resmi": <true/false>,
    "red_flags": [<string>, ...],
    "alasan": "<ringkas, 2-3 kalimat>"
  },
  "utilitas": {
    "skor_0_20": <int>,
    "use_case_wajib_ditemukan": [<string>, ...],
    "use_case_opsional_ditemukan": [<string>, ...],
    "alasan": "<ringkas, 2-3 kalimat>"
  },
  "profil_proyek": {
    "ringkasan": "<2-3 kalimat: proyek ini apa/untuk apa>",
    "mekanisme_kerja": "<ringkas: bagaimana produk/protokol ini bekerja secara teknis>",
    "keunggulan": [<string singkat>, ...],
    "kelemahan_atau_risiko": [<string singkat>, ...],
    "keunikan": "<1-2 kalimat: apa yang membedakan dari kompetitor, atau null kalau tidak jelas>",
    "tim_atau_backer_disebutkan": [<nama tim/investor/VC PERSIS seperti tertulis di dokumen>, ...] ATAU null kalau tidak disebutkan sama sekali,
    "catatan_kejujuran_data": "<sebutkan bagian mana dari profil ini yang confidence-nya rendah/tidak ditemukan di dokumen>"
  },
  "confidence": "tinggi/sedang/rendah",
  "data_tidak_ditemukan": [<string>, ...]
}

TEKS DOKUMEN:
---
{document_text}
---
"""


def _call_gemini(prompt: str) -> str:
    """Panggilan REST langsung ke Gemini API — tanpa SDK tambahan.

    PENTING: API key dikirim lewat HTTP header (x-goog-api-key), BUKAN lewat
    URL query param. Kalau key ada di URL, ada risiko dia ikut ke-log atau
    ke-simpan utuh di pesan error (persis insiden yang pernah terjadi —
    GitHub Push Protection sampai menolak commit karena mendeteksi key
    ke-expose di data/snapshots.json). Header tidak pernah muncul di URL
    sehingga tidak ikut ke pesan error requests/exception.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    url = f"{config.GEMINI_API_BASE}/models/{config.GEMINI_MODEL}:generateContent"
    resp = requests.post(
        url,
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"response_mime_type": "application/json"},
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


def _safe_error_message(e: Exception) -> str:
    """Pesan error yang aman disimpan ke data/snapshots.json — TIDAK PERNAH
    menyertakan str(e) mentah, karena exception dari requests/HTTP bisa
    membawa URL lengkap (berpotensi berisi API key) atau detail teknis lain
    yang tidak seharusnya tersimpan permanen di file yang di-commit ke repo
    publik. Cukup nama jenis error + kode status kalau ada, tanpa detail
    lengkapnya.
    """
    error_type = type(e).__name__
    status_code = getattr(getattr(e, "response", None), "status_code", None)
    if status_code:
        return f"Gagal memanggil Gemini API ({error_type}, HTTP {status_code})"
    return f"Gagal memanggil Gemini API ({error_type})"


def score_qualitative_factors(document_text: str) -> dict:
    """
    Kirim teks whitepaper/docs ke Gemini, dapatkan skor terstruktur
    Faktor #4 dan #5. document_text di-truncate ke ~60.000 karakter supaya
    tetap dalam batas free tier dan hemat kuota harian.
    """
    prompt = RUBRIC_PROMPT.replace("{document_text}", document_text[:60000])

    try:
        raw_text = _call_gemini(prompt)
    except Exception as e:
        safe_msg = _safe_error_message(e)
        return {
            "tokenomics": {"skor_0_20": 0, "alasan": safe_msg},
            "utilitas": {"skor_0_20": 0, "alasan": safe_msg},
            "profil_proyek": None,
            "confidence": "rendah",
            "data_tidak_ditemukan": ["api_error"],
        }

    cleaned = raw_text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {
            "tokenomics": {"skor_0_20": 0, "alasan": "Gagal parse output LLM"},
            "utilitas": {"skor_0_20": 0, "alasan": "Gagal parse output LLM"},
            "profil_proyek": None,
            "confidence": "rendah",
            "data_tidak_ditemukan": ["parse_error"],
            "_raw_output": raw_text,
        }


# ---------------------------------------------------------------------------
# Governance — Snapshot.org GraphQL API (gratis, tanpa key)
# ---------------------------------------------------------------------------

SNAPSHOT_GRAPHQL = "https://hub.snapshot.org/graphql"


def get_snapshot_governance_data(space_id: str) -> dict:
    """
    space_id: nama space Snapshot proyek, mis. "hyperliquid-dao.eth"
    (cari di https://snapshot.org/#/<nama-project>)
    """
    query = """
    query ($space: String!) {
      proposals(first: 50, where: { space: $space }, orderBy: "created", orderDirection: desc) {
        id
        title
        state
        scores_total
        votes
      }
    }
    """
    resp = requests.post(
        SNAPSHOT_GRAPHQL,
        json={"query": query, "variables": {"space": space_id}},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json().get("data", {}).get("proposals", [])

    executed = [p for p in data if p.get("state") == "closed"]
    return {
        "total_proposals": len(data),
        "executed_proposals": len(executed),
        "avg_votes_per_proposal": (
            sum(p.get("votes", 0) for p in data) / len(data) if data else 0
        ),
        "raw_proposals": data,
    }
