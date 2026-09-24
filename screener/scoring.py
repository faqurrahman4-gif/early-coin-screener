"""
Implementasi rumus skoring 0-20 per faktor, persis mengikuti screener-spec.md.
Fungsi di sini murni matematis — menerima data mentah yang sudah diambil
oleh data_sources.py / llm_reader.py, dan mengeluarkan skor + breakdown.

Setiap fungsi mengembalikan dict {"skor": float, "breakdown": {...}} supaya
UI Streamlit bisa menampilkan alasan di balik angka, bukan cuma angkanya.
"""

import math
from . import config


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# Faktor 1 — Value Accrual Mechanism
# ---------------------------------------------------------------------------

def score_value_accrual(fee_share_to_buyback_pct: float,
                         mechanism_changed_recently: bool,
                         buyback_12m_usd: float,
                         market_cap_usd: float) -> dict:
    if fee_share_to_buyback_pct > 90:
        konsistensi = 10
    elif fee_share_to_buyback_pct >= 40:
        konsistensi = 6
    else:
        konsistensi = 2
    if mechanism_changed_recently:
        konsistensi -= 3
    konsistensi = clamp(konsistensi, 0, 10)

    if market_cap_usd and market_cap_usd > 0:
        buyback_yield_pct = (buyback_12m_usd / market_cap_usd) * 100
    else:
        buyback_yield_pct = 0
    skala_dampak = clamp((buyback_yield_pct / 7) * 10, 0, 10)

    skor = konsistensi + skala_dampak
    return {
        "skor": round(skor, 2),
        "breakdown": {
            "konsistensi_mekanisme": konsistensi,
            "skala_dampak": round(skala_dampak, 2),
            "buyback_yield_tahunan_pct": round(buyback_yield_pct, 2),
        },
    }


# ---------------------------------------------------------------------------
# Faktor 2 — Revenue Riil Protokol
# ---------------------------------------------------------------------------

def score_revenue(market_cap_usd: float, annualized_revenue_usd: float,
                   revenue_last_30d: float, revenue_prev_30d: float) -> dict:
    if not annualized_revenue_usd or annualized_revenue_usd <= 0:
        pf_ratio = float("inf")
    else:
        pf_ratio = market_cap_usd / annualized_revenue_usd

    if pf_ratio < 20:
        skala_revenue = 12
    elif pf_ratio < 50:
        skala_revenue = 8
    elif pf_ratio < 100:
        skala_revenue = 4
    else:
        skala_revenue = 0

    if revenue_prev_30d and revenue_prev_30d > 0:
        growth_pct = ((revenue_last_30d - revenue_prev_30d) / revenue_prev_30d) * 100
    else:
        growth_pct = 0

    if growth_pct > 30:
        tren = 8
    elif growth_pct >= 0:
        tren = 5
    else:
        tren = 1

    skor = skala_revenue + tren
    return {
        "skor": round(skor, 2),
        "breakdown": {
            "price_to_fee_ratio": None if pf_ratio == float("inf") else round(pf_ratio, 1),
            "skala_revenue": skala_revenue,
            "tren_growth_pct_30d": round(growth_pct, 1),
            "tren_pertumbuhan": tren,
        },
    }


# ---------------------------------------------------------------------------
# Faktor 3 — Dominasi Pasar & Moat
# ---------------------------------------------------------------------------

def score_market_dominance(rank: int, total_competitors: int,
                            market_share_trend: str) -> dict:
    """market_share_trend: 'naik' | 'stabil' | 'turun'"""
    if total_competitors > 1 and rank >= 1:
        rank_percentile = 12 * (1 - math.log(rank) / math.log(total_competitors))
    else:
        rank_percentile = 12
    rank_percentile = clamp(rank_percentile, 0, 12)

    trend_map = {"naik": 8, "stabil": 5, "turun": 1}
    trend_share = trend_map.get(market_share_trend, 5)

    skor = rank_percentile + trend_share
    return {
        "skor": round(skor, 2),
        "breakdown": {
            "rank": rank,
            "total_kompetitor": total_competitors,
            "rank_percentile": round(rank_percentile, 2),
            "trend_share": trend_share,
        },
    }


# ---------------------------------------------------------------------------
# Faktor 4 & 5 — hasil langsung dari llm_reader.score_qualitative_factors()
# Fungsi ini hanya membungkus/normalisasi output LLM jadi format konsisten.
# ---------------------------------------------------------------------------

def normalize_llm_tokenomics(llm_output: dict) -> dict:
    t = llm_output.get("tokenomics", {})
    return {"skor": clamp(t.get("skor_0_20", 0), 0, 20), "breakdown": t}


def normalize_llm_utility(llm_output: dict) -> dict:
    u = llm_output.get("utilitas", {})
    return {"skor": clamp(u.get("skor_0_20", 0), 0, 20), "breakdown": u}


# ---------------------------------------------------------------------------
# Faktor 6 — Tata Kelola (Governance)
# ---------------------------------------------------------------------------

def score_governance(executed_proposals: int, total_proposals: int,
                      top10_wallet_voting_power_pct: float,
                      age_days: int) -> dict:
    if executed_proposals > 0:
        aktivitas = 10
    elif total_proposals > 0:
        aktivitas = 5
    else:
        aktivitas = 0

    if top10_wallet_voting_power_pct < 30:
        desentralisasi = 10
    elif top10_wallet_voting_power_pct <= 60:
        desentralisasi = 5
    else:
        desentralisasi = 1

    raw_skor = aktivitas + desentralisasi
    mult = config.age_multiplier(age_days)
    skor = raw_skor * mult

    return {
        "skor": round(skor, 2),
        "breakdown": {
            "aktivitas_voting": aktivitas,
            "desentralisasi": desentralisasi,
            "raw_skor_sebelum_multiplier": raw_skor,
            "age_multiplier": mult,
        },
    }


# ---------------------------------------------------------------------------
# Faktor 7 — Aktivitas & Pertumbuhan On-Chain
# ---------------------------------------------------------------------------

def score_onchain_activity(volume_wallet_ratio: float,
                            category_avg_ratio: float,
                            active_wallets_now: int,
                            active_wallets_peak_incentive: int,
                            age_days: int) -> dict:
    if category_avg_ratio and category_avg_ratio > 0:
        multiple_of_avg = volume_wallet_ratio / category_avg_ratio
    else:
        multiple_of_avg = 1

    if multiple_of_avg <= 2:
        kualitas_volume = 10
    elif multiple_of_avg <= 5:
        kualitas_volume = 4
    else:
        kualitas_volume = 0

    if active_wallets_peak_incentive and active_wallets_peak_incentive > 0:
        retensi_pct = (active_wallets_now / active_wallets_peak_incentive) * 100
    else:
        retensi_pct = 100  # tidak ada data insentif puncak -> anggap netral

    if retensi_pct > 70:
        retensi = 10
    elif retensi_pct >= 40:
        retensi = 5
    else:
        retensi = 1

    raw_skor = kualitas_volume + retensi
    mult = config.age_multiplier(age_days)
    skor = raw_skor * mult

    return {
        "skor": round(skor, 2),
        "breakdown": {
            "kualitas_volume": kualitas_volume,
            "retensi": retensi,
            "retensi_pct": round(retensi_pct, 1),
            "wash_trading_multiple_of_category_avg": round(multiple_of_avg, 2),
            "raw_skor_sebelum_multiplier": raw_skor,
            "age_multiplier": mult,
        },
    }


# ---------------------------------------------------------------------------
# Faktor 8 — Transparansi Data
# ---------------------------------------------------------------------------

def score_data_transparency(claim_vs_onchain_diff_pct: float,
                             indexed_on_defillama: bool,
                             has_public_explorer: bool) -> dict:
    skor = 20
    if claim_vs_onchain_diff_pct is not None and claim_vs_onchain_diff_pct > 20:
        skor -= 8
    if not indexed_on_defillama:
        skor -= 6
    if not has_public_explorer:
        skor -= 6
    skor = clamp(skor, 0, 20)
    return {
        "skor": round(skor, 2),
        "breakdown": {
            "claim_vs_onchain_diff_pct": claim_vs_onchain_diff_pct,
            "indexed_on_defillama": indexed_on_defillama,
            "has_public_explorer": has_public_explorer,
        },
    }


# ---------------------------------------------------------------------------
# Skor gabungan akhir
# ---------------------------------------------------------------------------

FACTOR_KEY_MAP = {
    "value_accrual": "Value accrual mechanism",
    "revenue": "Revenue riil protokol",
    "market_dominance": "Dominasi pasar & moat",
    "tokenomics": "Tokenomics & struktur supply",
    "utility": "Utilitas token",
    "governance": "Tata kelola (governance)",
    "onchain_activity": "Aktivitas & pertumbuhan on-chain",
    "data_transparency": "Transparansi data",
}


def compute_total_score(factor_scores: dict) -> dict:
    """
    factor_scores: dict dengan key sesuai config.WEIGHTS, value = skor 0-20.
    Mengembalikan skor total dinormalisasi ke 0-20 (rata-rata tertimbang).
    """
    total = 0.0
    for key, weight in config.WEIGHTS.items():
        skor = factor_scores.get(key, 0)
        total += skor * weight
    return {
        "total_skor_0_20": round(total, 2),
        "total_skor_persen": round((total / 20) * 100, 1),
    }
