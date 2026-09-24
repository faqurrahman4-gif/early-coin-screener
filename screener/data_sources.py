"""
Data layer — semua panggilan ke API gratis (DefiLlama, CoinGecko, block explorer).
Setiap fungsi mengembalikan dict Python biasa; tidak ada scoring di sini,
murni pengambilan & pembersihan data mentah. Scoring ada di scoring.py.
"""

import time
import requests
from . import config

# Sesi requests tunggal supaya bisa reuse koneksi
_session = requests.Session()
_session.headers.update({"User-Agent": "personal-token-screener/0.1"})


def _get(url: str, params: dict | None = None, retries: int = 3):
    """GET dengan retry sederhana — API gratis kadang rate-limit/timeout."""
    for attempt in range(retries):
        try:
            resp = _session.get(url, params=params, timeout=15)
            if resp.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException:
            if attempt == retries - 1:
                raise
            time.sleep(1.5 ** attempt)
    return None


# ---------------------------------------------------------------------------
# DefiLlama — fees, revenue, TVL, volume (dipakai untuk Faktor #1, #2, #7, #8)
# ---------------------------------------------------------------------------

def get_protocol_summary(protocol_slug: str) -> dict:
    """
    Ambil ringkasan fee & revenue protokol dari DefiLlama.
    protocol_slug: nama slug DefiLlama, mis. "hyperliquid", "pump-fun".
    Cari slug yang benar lewat https://api.llama.fi/protocols atau situs DefiLlama.
    """
    fees = _get(f"{config.DEFILLAMA_BASE}/summary/fees/{protocol_slug}",
                params={"dataType": "dailyFees"})
    revenue = _get(f"{config.DEFILLAMA_BASE}/summary/fees/{protocol_slug}",
                    params={"dataType": "dailyRevenue"})
    return {
        "fees": fees,
        "revenue": revenue,
    }


def get_protocol_tvl(protocol_slug: str) -> dict:
    return _get(f"{config.DEFILLAMA_BASE}/protocol/{protocol_slug}")


def list_protocols_in_category(category: str) -> list[dict]:
    """
    Ambil semua protokol dalam satu kategori (mis. 'Derivatives', 'Dexs')
    untuk menghitung rank percentile di Faktor #3 (dominasi pasar).
    """
    all_protocols = _get(f"{config.DEFILLAMA_BASE}/protocols") or []
    return [p for p in all_protocols if p.get("category") == category]


# ---------------------------------------------------------------------------
# CoinGecko — market cap, supply, ranking (Faktor #3, #4)
# ---------------------------------------------------------------------------

def get_coin_market_data(coingecko_id: str) -> dict:
    """
    coingecko_id: id CoinGecko, mis. "hyperliquid", bukan simbol ticker.
    Cari lewat https://api.coingecko.com/api/v3/coins/list
    """
    data = _get(f"{config.COINGECKO_BASE}/coins/{coingecko_id}", params={
        "localization": "false",
        "tickers": "false",
        "market_data": "true",
        "community_data": "false",
        "developer_data": "false",
    })
    if not data:
        return {}
    md = data.get("market_data", {})
    return {
        "market_cap_usd": md.get("market_cap", {}).get("usd"),
        "circulating_supply": md.get("circulating_supply"),
        "total_supply": md.get("total_supply"),
        "max_supply": md.get("max_supply"),
        "market_cap_rank": md.get("market_cap_rank"),
        "genesis_date": data.get("genesis_date"),
        "homepage": data.get("links", {}).get("homepage", [None])[0],
        "whitepaper_hints": data.get("links", {}).get("whitepaper"),
    }


def get_coin_market_chart_range(coingecko_id: str, from_ts: int, to_ts: int) -> dict:
    """Data historis (untuk backtest — 'time travel' ke usia 3 bulan token)."""
    return _get(
        f"{config.COINGECKO_BASE}/coins/{coingecko_id}/market_chart/range",
        params={"vs_currency": "usd", "from": from_ts, "to": to_ts},
    )


# ---------------------------------------------------------------------------
# Block explorer — holder distribution & wallet aktif (Faktor #4, #7, #8)
# NOTE: scaffold ini contoh untuk Etherscan-family API (Etherscan/Basescan/dst).
# Untuk Solana pakai Solscan Public API dengan struktur endpoint berbeda.
# ---------------------------------------------------------------------------

def get_top_holders_etherscan(token_contract: str, api_key: str,
                               explorer_base: str = "https://api.etherscan.io/api") -> list[dict]:
    """
    Endpoint holder list Etherscan butuh API key berbayar untuk beberapa chain;
    untuk chain yang free tier-nya mendukung, ganti explorer_base sesuai chain
    (mis. api.basescan.org, api.arbiscan.io — pola query sama).
    """
    data = _get(explorer_base, params={
        "module": "token",
        "action": "tokenholderlist",
        "contractaddress": token_contract,
        "page": 1,
        "offset": 20,
        "apikey": api_key,
    })
    return (data or {}).get("result", [])


def get_wash_trading_ratio(volume_24h_usd: float, unique_active_wallets_24h: int) -> float | None:
    """Rasio volume/wallet unik — dipakai di Faktor #7. Bandingkan hasilnya
    dengan rata-rata kategori (kamu isi manual angka rata-rata kategori dari
    riset, karena tidak ada API tunggal untuk itu)."""
    if not unique_active_wallets_24h:
        return None
    return volume_24h_usd / unique_active_wallets_24h
