"""
Jalankan ini secara berkala (mis. mingguan/bulanan). SEKARANG discovery-nya
OTOMATIS — tidak perlu isi watchlist manual lagi. Alurnya:

  1. discovery.build_candidate_list() scan pool baru di beberapa network DEX
     (lewat GeckoTerminal API, gratis, cloud, tanpa API key) dan filter umur
     3-13 bulan sesuai spec.
  2. Untuk token yang KAMU SUDAH PUNYA riset manual-nya (mis. HYPE), isi di
     MANUAL_OVERRIDES di bawah supaya faktor #1, #4, #5, #6 tidak ditandai
     "Insufficient" -- ini best-effort enrichment, BUKAN kewajiban tiap run.
  3. Sisanya (kandidat yang belum ada override manual) tetap discoring
     dengan data yang tersedia, dan faktor yang datanya belum lengkap
     ditandai confidence "Insufficient" di UI -- bukan dipaksakan angka palsu.

Cara pakai:
    python run_screener.py
"""

from screener import discovery
from screener.pipeline import run_token_pipeline

# Isi override manual di sini untuk token yang sudah kamu riset lebih dalam
# (key = coingecko_id, BUKAN symbol -- supaya tidak ambigu antar token
# dengan simbol sama di chain berbeda).
MANUAL_OVERRIDES: dict[str, dict] = {
    "hyperliquid": {
        "defillama_slug": "hyperliquid",
        "category": "Derivatives",
        "whitepaper_urls": ["https://hyperliquid.gitbook.io/hyperliquid-docs"],
        "snapshot_space": None,
        "fee_share_to_buyback_pct": 99,
        "mechanism_changed_recently": False,
        "buyback_12m_usd": 1_300_000_000,
        "category_avg_volume_wallet_ratio": 50.0,
        "active_wallets_peak_incentive": None,
        "claim_vs_onchain_diff_pct": None,
        "has_public_explorer": True,
        "top10_wallet_voting_power_pct": 40.0,
    },
    # Tambahkan token lain di sini kalau sudah riset manual lebih dalam...
}

DEFAULT_FIELDS = {
    "defillama_slug": None,
    "category": None,
    "whitepaper_urls": [],
    "snapshot_space": None,
    "explorer_api_key": None,
    "fee_share_to_buyback_pct": None,
    "mechanism_changed_recently": False,
    "buyback_12m_usd": 0,
    "category_avg_volume_wallet_ratio": 1.0,
    "active_wallets_peak_incentive": None,
    "claim_vs_onchain_diff_pct": None,
    "has_public_explorer": True,
    "top10_wallet_voting_power_pct": None,
}


def build_watchlist() -> list[dict]:
    print("Menjalankan discovery layer (scan pool baru via GeckoTerminal)...")
    candidates = discovery.build_candidate_list()
    print(f"Ditemukan {len(candidates)} kandidat token berumur 3-13 bulan.\n")

    watchlist = []
    for c in candidates:
        token_config = {**DEFAULT_FIELDS, **c}
        cid = c.get("coingecko_id")
        if cid and cid in MANUAL_OVERRIDES:
            token_config.update(MANUAL_OVERRIDES[cid])
        watchlist.append(token_config)
    return watchlist


def main():
    watchlist = build_watchlist()
    for token_config in watchlist:
        symbol = token_config.get("symbol", "UNKNOWN")

        if not token_config.get("coingecko_id"):
            print(f"{symbol}: dilewati -- tidak ketemu CoinGecko id "
                  f"(token terlalu baru/kecil untuk terindeks CoinGecko)")
            continue

        print(f"Memproses {symbol} ({token_config['coingecko_id']})...")
        try:
            result = run_token_pipeline(token_config)
            if result.get("skip"):
                print(f"  -> dilewati: {result['reason']}")
            else:
                missing = result.get("missing_manual_data", [])
                print(f"  -> skor total: {result['total']['total_skor_0_20']}/20")
                if missing:
                    print(f"  -> faktor belum lengkap datanya (ditandai Insufficient): {missing}")
        except Exception as e:
            print(f"  -> ERROR: {e}")

    print("\nSelesai. Buka hasilnya dengan: streamlit run app.py")


if __name__ == "__main__":
    main()
