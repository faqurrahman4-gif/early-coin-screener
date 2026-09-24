"""
Orkestrasi end-to-end untuk SATU token: tarik data kuantitatif + kualitatif,
hitung semua 8 faktor, simpan snapshot. Ini yang dipanggil dari
run_screener.py (batch semua token) atau dari Streamlit (re-score satu token).

CATATAN PENTING: fungsi run_token_pipeline() di bawah ini masih perlu kamu
lengkapi bagian yang ditandai "# TODO: sesuaikan" — karena setiap proyek
punya slug DefiLlama, id CoinGecko, kategori kompetitor, dan URL whitepaper
yang berbeda-beda. Scaffold ini memberi kerangka lengkap, bukan hasil jadi
tanpa perlu sentuhan sama sekali (memang tidak realistis untuk full-auto
100% mengingat variasi struktur tiap proyek crypto).
"""

from datetime import datetime, timezone
from . import config, data_sources, llm_reader, scoring, storage


def compute_age_days(genesis_date_str: str | None) -> int:
    if not genesis_date_str:
        return 9999  # anggap sudah tua kalau tidak diketahui, supaya tidak salah dianggap "baru rilis"
    genesis = datetime.fromisoformat(genesis_date_str).replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - genesis).days


def run_token_pipeline(token_config: dict) -> dict:
    """
    token_config contoh:
    {
        "symbol": "HYPE",
        "coingecko_id": "hyperliquid",
        "defillama_slug": "hyperliquid",
        "category": "Derivatives",
        "whitepaper_urls": ["https://hyperliquid.gitbook.io/hyperliquid-docs"],
        "snapshot_space": None,  # isi kalau ada governance on-chain
        "explorer_contract": None,
        "explorer_api_key": None,
        # override manual untuk data yang API tidak bisa ambil otomatis:
        "fee_share_to_buyback_pct": 99,
        "mechanism_changed_recently": False,
        "buyback_12m_usd": 1_300_000_000,
        "category_avg_volume_wallet_ratio": 50.0,  # dari riset manual kategori
        "active_wallets_peak_incentive": None,
        "claim_vs_onchain_diff_pct": None,
        "has_public_explorer": True,
        "top10_wallet_voting_power_pct": 40.0,
    }
    """
    missing_manual = []  # lacak faktor mana yang datanya belum lengkap

    coingecko_id = token_config.get("coingecko_id")
    if coingecko_id:
        market = data_sources.get_coin_market_data(coingecko_id)
    else:
        market = {}
        missing_manual.append("coingecko_id")

    # Kalau CoinGecko tidak punya genesis_date (umum untuk token super baru),
    # pakai umur dari pool DEX (hasil discovery layer) sebagai fallback.
    age_days = compute_age_days(market.get("genesis_date"))
    if age_days == 9999 and token_config.get("age_days_from_pool") is not None:
        age_days = token_config["age_days_from_pool"]

    if age_days < config.MIN_AGE_DAYS:
        return {"skip": True, "reason": f"Umur token {age_days} hari, di bawah minimum {config.MIN_AGE_DAYS}"}

    # --- Faktor 1: Value Accrual ---
    # Field ini HAMPIR SELALU butuh riset manual singkat (baca dokumentasi
    # resmi proyek) — tidak ada API yang langsung memberi "% fee ke buyback".
    fee_share = token_config.get("fee_share_to_buyback_pct")
    if fee_share is None:
        missing_manual.append("value_accrual")
        fee_share = 0
    f1 = scoring.score_value_accrual(
        fee_share_to_buyback_pct=fee_share,
        mechanism_changed_recently=token_config.get("mechanism_changed_recently", False),
        buyback_12m_usd=token_config.get("buyback_12m_usd") or 0,
        market_cap_usd=market.get("market_cap_usd", 0),
    )

    # --- Faktor 2: Revenue ---
    defillama_slug = token_config.get("defillama_slug")
    if defillama_slug:
        protocol_summary = data_sources.get_protocol_summary(defillama_slug)
    else:
        protocol_summary = {}
        missing_manual.append("revenue")
    # TODO: sesuaikan — struktur JSON DefiLlama fees/revenue perlu di-parse
    # sesuai bentuk respons aktualnya (bisa berubah sewaktu-waktu).
    annualized_revenue = protocol_summary.get("revenue", {}).get("total24h", 0) * 365 \
        if protocol_summary.get("revenue") else 0
    f2 = scoring.score_revenue(
        market_cap_usd=market.get("market_cap_usd", 0),
        annualized_revenue_usd=annualized_revenue,
        revenue_last_30d=0,   # TODO: sesuaikan — hitung dari time-series DefiLlama
        revenue_prev_30d=0,   # TODO: sesuaikan
    )

    # --- Faktor 3: Dominasi Pasar ---
    category = token_config.get("category")
    if category:
        competitors = data_sources.list_protocols_in_category(category)
    else:
        competitors = []
        missing_manual.append("market_dominance")
    f3 = scoring.score_market_dominance(
        rank=market.get("market_cap_rank") or max(len(competitors), 1),
        total_competitors=max(len(competitors), 1),
        market_share_trend="stabil",  # TODO: sesuaikan — hitung dari data historis
    )

    # --- Faktor 4 & 5: Tokenomics & Utilitas (LLM whitepaper reader) ---
    # Sumber URL diambil otomatis dari CoinGecko (field "links.whitepaper")
    # kalau ada; kalau tidak ada, fallback ke homepage proyek (banyak proyek
    # taruh link docs di homepage-nya).
    whitepaper_urls = list(token_config.get("whitepaper_urls") or [])
    if not whitepaper_urls and market.get("whitepaper_hints"):
        whitepaper_urls.append(market["whitepaper_hints"])
    if not whitepaper_urls and market.get("homepage"):
        whitepaper_urls.append(market["homepage"])

    combined_text = ""
    for url in whitepaper_urls:
        text = llm_reader.scrape_docs_text(url)
        if text:
            combined_text += f"\n\n=== {url} ===\n{text}"

    if combined_text.strip():
        llm_output = llm_reader.score_qualitative_factors(combined_text)
    else:
        missing_manual.extend(["tokenomics", "utility"])
        llm_output = {
            "tokenomics": {"skor_0_20": 0, "alasan": "Tidak ada teks whitepaper yang berhasil di-scrape"},
            "utilitas": {"skor_0_20": 0, "alasan": "Tidak ada teks whitepaper yang berhasil di-scrape"},
            "confidence": "rendah",
            "data_tidak_ditemukan": ["whitepaper_text"],
        }
    f4 = scoring.normalize_llm_tokenomics(llm_output)
    f5 = scoring.normalize_llm_utility(llm_output)

    # --- Faktor 6: Governance ---
    top10_pct = token_config.get("top10_wallet_voting_power_pct")
    if token_config.get("snapshot_space"):
        gov_data = llm_reader.get_snapshot_governance_data(token_config["snapshot_space"])
        if top10_pct is None:
            missing_manual.append("governance")
            top10_pct = 100  # konservatif: anggap terpusat kalau tidak diketahui
        f6 = scoring.score_governance(
            executed_proposals=gov_data["executed_proposals"],
            total_proposals=gov_data["total_proposals"],
            top10_wallet_voting_power_pct=top10_pct,
            age_days=age_days,
        )
    else:
        missing_manual.append("governance")
        f6 = scoring.score_governance(0, 0, 100, age_days)  # tidak ada governance on-chain / belum diverifikasi

    # --- Faktor 7: Aktivitas On-Chain ---
    # TODO: sesuaikan — ambil volume_24h & wallet aktif dari block explorer API.
    # Sementara pakai volume pool dari discovery layer (GeckoTerminal) kalau ada,
    # tapi tanpa data wallet unik aktif, rasio wash-trading belum bisa dihitung akurat.
    if token_config.get("active_wallets_peak_incentive") is None:
        missing_manual.append("onchain_activity")
    f7 = scoring.score_onchain_activity(
        volume_wallet_ratio=0,
        category_avg_ratio=token_config.get("category_avg_volume_wallet_ratio", 1),
        active_wallets_now=0,
        active_wallets_peak_incentive=token_config.get("active_wallets_peak_incentive"),
        age_days=age_days,
    )

    # --- Faktor 8: Transparansi Data ---
    f8 = scoring.score_data_transparency(
        claim_vs_onchain_diff_pct=token_config.get("claim_vs_onchain_diff_pct"),
        indexed_on_defillama=bool(protocol_summary.get("fees")),
        has_public_explorer=token_config.get("has_public_explorer", True),
    )

    factor_scores = {
        "value_accrual": f1["skor"],
        "revenue": f2["skor"],
        "market_dominance": f3["skor"],
        "tokenomics": f4["skor"],
        "utility": f5["skor"],
        "governance": f6["skor"],
        "onchain_activity": f7["skor"],
        "data_transparency": f8["skor"],
    }
    factor_breakdowns = {
        "value_accrual": f1["breakdown"],
        "revenue": f2["breakdown"],
        "market_dominance": f3["breakdown"],
        "tokenomics": f4["breakdown"],
        "utility": f5["breakdown"],
        "governance": f6["breakdown"],
        "onchain_activity": f7["breakdown"],
        "data_transparency": f8["breakdown"],
    }
    confidence = {
        "value_accrual": "Insufficient" if "value_accrual" in missing_manual else "Confirmed",
        "revenue": "Insufficient" if "revenue" in missing_manual else "Confirmed",
        "market_dominance": "Insufficient" if "market_dominance" in missing_manual else "Confirmed",
        "governance": "Insufficient" if "governance" in missing_manual
                       else config.confidence_label(age_days, True),
        "onchain_activity": "Insufficient" if "onchain_activity" in missing_manual
                             else config.confidence_label(age_days, True),
        "tokenomics": "Insufficient" if "tokenomics" in missing_manual else llm_output.get("confidence", "sedang"),
        "utility": "Insufficient" if "utility" in missing_manual else llm_output.get("confidence", "sedang"),
        "data_transparency": "Confirmed",
    }

    total = scoring.compute_total_score(factor_scores)

    storage.save_snapshot(
        token_symbol=token_config["symbol"],
        coingecko_id=token_config["coingecko_id"],
        defillama_slug=token_config["defillama_slug"],
        age_days=age_days,
        factor_scores=factor_scores,
        factor_breakdowns=factor_breakdowns,
        confidence=confidence,
        total_score=total,
    )

    return {
        "skip": False,
        "symbol": token_config["symbol"],
        "age_days": age_days,
        "factor_scores": factor_scores,
        "factor_breakdowns": factor_breakdowns,
        "confidence": confidence,
        "total": total,
        "missing_manual_data": missing_manual,
    }
