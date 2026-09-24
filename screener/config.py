"""
Konfigurasi terpusat untuk screener 8-faktor.
Semua angka di sini diambil langsung dari screener-spec.md — kalau mau
mengubah bobot/threshold, cukup edit di sini, tidak perlu sentuh scoring.py.
"""

# --- Bobot per faktor (harus total 100) ---
WEIGHTS = {
    "value_accrual": 0.20,
    "revenue": 0.20,
    "market_dominance": 0.15,
    "tokenomics": 0.15,
    "utility": 0.10,
    "governance": 0.10,
    "onchain_activity": 0.05,
    "data_transparency": 0.05,
}
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-6, "Total bobot harus 100%"

# --- Umur token untuk masuk screener (hari) ---
MIN_AGE_DAYS = 90
MAX_AGE_DAYS_FOR_DISCOVERY = 400  # batas atas supaya screener fokus "early-stage"

# --- Age multiplier untuk faktor governance & on-chain activity ---
# (faktor paling rawan sinyal palsu di usia muda)
def age_multiplier(age_days: int) -> float:
    if age_days < 180:
        return 0.7
    elif age_days < 365:
        return 0.85
    return 1.0


def confidence_label(age_days: int, data_complete: bool) -> str:
    if not data_complete:
        return "Insufficient"
    mult = age_multiplier(age_days)
    if mult == 1.0:
        return "Confirmed"
    return "Provisional"


# --- API endpoints ---
DEFILLAMA_BASE = "https://api.llama.fi"
COINGECKO_BASE = "https://api.coingecko.com/api/v3"
GECKOTERMINAL_BASE = "https://api.geckoterminal.com/api/v2"  # gratis, cloud, tanpa API key

# --- Network yang di-scan discovery layer (id sesuai GeckoTerminal) ---
# Tambah/kurangi sesuai chain yang relevan untuk riset kamu.
NETWORKS_TO_SCAN = ["eth", "solana", "base", "arbitrum", "bsc"]

# Mapping id network GeckoTerminal -> id platform CoinGecko
# (dipakai untuk resolve contract address -> CoinGecko id)
GECKOTERMINAL_TO_COINGECKO_PLATFORM = {
    "eth": "ethereum",
    "solana": "solana",
    "base": "base",
    "arbitrum": "arbitrum-one",
    "bsc": "binance-smart-chain",
}

# --- API keys (isi lewat environment variable, JANGAN hardcode di sini) ---
# export GEMINI_API_KEY=...        (gratis dari aistudio.google.com, tanpa billing)
# export COINGECKO_API_KEY=...     (opsional, free tier tidak wajib)
# export ETHERSCAN_API_KEY=...
# export SOLSCAN_API_KEY=...

# --- Model LLM untuk whitepaper reader (Google Gemini, FREE TIER ASLI) ---
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_MODEL = "gemini-2.5-flash"  # cek aistudio.google.com untuk model free-tier terbaru
