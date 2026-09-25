"""
Penyimpanan berbasis JSON — diganti dari SQLite karena arsitektur sekarang
full cloud (GitHub Actions menjalankan pipeline, hasilnya di-commit balik
ke repo GitHub). JSON jauh lebih cocok untuk disimpan di git dibanding
file database biner seperti SQLite (bisa dilihat isinya langsung di GitHub,
diff-nya juga jelas antar commit).

Prinsip tetap sama seperti versi SQLite: SETIAP run disimpan sebagai entry
baru (bukan overwrite), supaya nanti bisa dipakai untuk backtest.
"""

import json
import os
from datetime import datetime, timezone

DATA_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "snapshots.json")


def _load_all() -> list[dict]:
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r") as f:
        return json.load(f)


def _save_all(snapshots: list[dict]):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(snapshots, f, indent=2, default=str)


def save_snapshot(token_symbol: str, coingecko_id: str, defillama_slug: str,
                   age_days: int, factor_scores: dict, factor_breakdowns: dict,
                   confidence: dict, total_score: dict,
                   network: str | None = None, contract_address: str | None = None,
                   why_on_radar: dict | None = None):
    snapshots = _load_all()
    snapshots.append({
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "token_symbol": token_symbol,
        "coingecko_id": coingecko_id,
        "defillama_slug": defillama_slug,
        "network": network,
        "contract_address": contract_address,
        "age_days": age_days,
        "total_skor_0_20": total_score["total_skor_0_20"],
        "total_skor_persen": total_score["total_skor_persen"],
        "factor_scores": factor_scores,
        "factor_breakdown": factor_breakdowns,
        "confidence": confidence,
        "why_on_radar": why_on_radar or {},
    })
    _save_all(snapshots)


def get_latest_snapshots() -> list[dict]:
    """Ambil snapshot TERBARU per token (untuk tabel utama di Streamlit)."""
    snapshots = _load_all()
    latest_per_token = {}
    for s in snapshots:
        symbol = s["token_symbol"]
        if symbol not in latest_per_token or s["run_timestamp"] > latest_per_token[symbol]["run_timestamp"]:
            latest_per_token[symbol] = s
    return sorted(latest_per_token.values(), key=lambda s: s["total_skor_0_20"], reverse=True)


def get_history_for_token(token_symbol: str) -> list[dict]:
    """Semua snapshot historis satu token — dipakai untuk backtest & tren."""
    snapshots = _load_all()
    history = [s for s in snapshots if s["token_symbol"] == token_symbol]
    return sorted(history, key=lambda s: s["run_timestamp"])
