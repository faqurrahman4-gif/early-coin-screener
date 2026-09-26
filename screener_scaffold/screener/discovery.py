"""
Discovery layer otomatis — menggantikan watchlist manual.
Sumber: GeckoTerminal Public API (bagian dari CoinGecko, gratis, cloud,
TANPA API key).

## KENAPA DESAIN INI (penting untuk dipahami sebelum mengubah lagi)

Endpoint `/networks/{network}/new_pools` HANYA berisi pool yang baru dibuat
dalam beberapa hari/jam terakhir — begitu pool berumur 3+ bulan, dia sudah
lama "lulus" dari daftar itu. Kalau discovery cuma pakai new_pools lalu
difilter umur 90-400 hari, hasilnya SELALU 0 (bug yang sempat terjadi).

Solusinya dua lapis:

1. **Immediate source — `/networks/{network}/trending_pools`**: endpoint ini
   berisi pool yang SEDANG aktif/relevan (bukan cuma yang baru dibuat),
   diukur dari engagement & aktivitas on-chain. Beberapa di antaranya
   berumur 3-13 bulan dan masih trending — ini justru sinyal bagus (token
   yang masih hidup & relevan, bukan yang sudah mati). Ini yang memberi
   hasil SEKARANG, tanpa perlu nunggu.

2. **Long-term source — Candidate Journal**: setiap run, semua pool baru
   dari new_pools dicatat ke data/candidate_journal.json (bukan langsung
   dibuang setelah dicek umurnya). Bulan-bulan berikutnya, entry di
   journal ini "naik kelas" begitu umurnya masuk window 90-400 hari.
   Ini investasi jangka panjang: makin lama screener jalan, makin lengkap
   coverage-nya (tidak cuma bergantung pada yang kebetulan trending).

Kedua sumber digabung, difilter umur, dedupe, baru di-resolve ke CoinGecko id.

CATATAN JUJUR: tidak semua token baru punya CoinGecko id (banyak yang
terlalu baru/kecil untuk diindeks CoinGecko) — kalau tidak ketemu,
kandidat tetap dikeluarkan tapi ditandai coingecko_id=None, dan pipeline
akan menandai faktor-faktor yang butuh data itu sebagai "Insufficient"
alih-alih memaksakan angka palsu.
"""

import json
import os
import time
from datetime import datetime, timezone
from . import config
from .data_sources import _get  # reuse session + retry logic


# ---------------------------------------------------------------------------
# Pengambilan pool mentah dari GeckoTerminal
# ---------------------------------------------------------------------------

def _parse_pools_response(data: dict, network: str) -> list[dict]:
    if not data or not data.get("data"):
        return []
    included = {item["id"]: item for item in data.get("included", [])}
    results = []
    for pool in data["data"]:
        attrs = pool.get("attributes", {})
        rel = pool.get("relationships", {})
        base_ref = rel.get("base_token", {}).get("data", {})
        base_info = included.get(base_ref.get("id"), {}).get("attributes", {})
        results.append({
            "network": network,
            "pool_address": attrs.get("address"),
            "pool_created_at": attrs.get("pool_created_at"),
            "base_token_symbol": base_info.get("symbol"),
            "base_token_address": base_info.get("address"),
            "volume_24h_usd": (attrs.get("volume_usd") or {}).get("h24"),
            "reserve_usd": attrs.get("reserve_in_usd"),
        })
    return results


def get_new_pools(network: str, pages: int = 3) -> list[dict]:
    """Pool yang BARU DIBUAT beberapa hari terakhir — untuk mengisi journal,
    BUKAN untuk langsung dicari yang umur 3-13 bulan (pasti nihil)."""
    pages = min(pages, config.MAX_PAGES_FREE_TIER)
    results = []
    for page in range(1, pages + 1):
        data = _get(
            f"{config.GECKOTERMINAL_BASE}/networks/{network}/new_pools",
            params={"page": page, "include": "base_token"},
        )
        parsed = _parse_pools_response(data, network)
        if not parsed:
            break
        results.extend(parsed)
        time.sleep(0.5)  # sopan ke free API, hindari rate-limit
    return results


def get_trending_pools(network: str, pages: int = 5) -> list[dict]:
    """Pool yang SEDANG aktif/relevan — sumber utama kandidat 'sekarang',
    karena tidak dibatasi hanya pool yang baru dibuat."""
    pages = min(pages, config.MAX_PAGES_FREE_TIER)
    results = []
    for page in range(1, pages + 1):
        data = _get(
            f"{config.GECKOTERMINAL_BASE}/networks/{network}/trending_pools",
            params={"page": page, "include": "base_token"},
        )
        parsed = _parse_pools_response(data, network)
        if not parsed:
            break
        results.extend(parsed)
        time.sleep(0.5)
    return results


# ---------------------------------------------------------------------------
# Candidate Journal — memori jangka panjang lintas-run
# ---------------------------------------------------------------------------

def _load_journal() -> dict:
    """Key: 'network:base_token_address', Value: entry pool + first_seen_at."""
    if not os.path.exists(config.CANDIDATE_JOURNAL_PATH):
        return {}
    with open(config.CANDIDATE_JOURNAL_PATH, "r") as f:
        return json.load(f)


def _save_journal(journal: dict):
    os.makedirs(os.path.dirname(config.CANDIDATE_JOURNAL_PATH), exist_ok=True)
    with open(config.CANDIDATE_JOURNAL_PATH, "w") as f:
        json.dump(journal, f, indent=2, default=str)


def update_journal_with_new_pools(pools: list[dict]) -> None:
    """Catat pool baru ke journal kalau belum pernah tercatat. Dipanggil
    tiap run supaya lama-lama journal makin lengkap."""
    journal = _load_journal()
    now_iso = datetime.now(timezone.utc).isoformat()
    added = 0
    for p in pools:
        addr = p.get("base_token_address")
        if not addr:
            continue
        key = f"{p['network']}:{addr}"
        if key not in journal:
            journal[key] = {**p, "first_seen_at": now_iso}
            added += 1
    if added:
        _save_journal(journal)
    print(f"  Journal: +{added} pool baru dicatat (total {len(journal)} pool tercatat sepanjang waktu).")


def get_aged_candidates_from_journal() -> list[dict]:
    """Ambil entry journal yang SEKARANG sudah masuk window umur 90-400 hari."""
    journal = _load_journal()
    aged = []
    for entry in journal.values():
        age = compute_pool_age_days(entry.get("pool_created_at"))
        if age is None:
            continue
        if config.MIN_AGE_DAYS <= age <= config.MAX_AGE_DAYS_FOR_DISCOVERY:
            entry = dict(entry)
            entry["age_days"] = age
            aged.append(entry)
    return aged


# ---------------------------------------------------------------------------
# Filter umur & dedupe
# ---------------------------------------------------------------------------

def compute_pool_age_days(pool_created_at: str | None) -> int | None:
    if not pool_created_at:
        return None
    try:
        created = datetime.fromisoformat(pool_created_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - created).days


def filter_by_age(pools: list[dict]) -> list[dict]:
    filtered = []
    for p in pools:
        age = compute_pool_age_days(p.get("pool_created_at"))
        if age is None:
            continue
        if config.MIN_AGE_DAYS <= age <= config.MAX_AGE_DAYS_FOR_DISCOVERY:
            p = dict(p)
            p["age_days"] = age
            filtered.append(p)
    return filtered


def dedupe_by_token_address(pools: list[dict]) -> list[dict]:
    """Satu token bisa punya beberapa pool (pair berbeda) — ambil satu per
    token address, prioritaskan yang volume 24h tertinggi."""
    best_by_address: dict[str, dict] = {}
    for p in pools:
        addr = p.get("base_token_address")
        if not addr:
            continue
        key = f"{p['network']}:{addr}"
        current_best = best_by_address.get(key)
        if not current_best or (p.get("volume_24h_usd") or 0) > (current_best.get("volume_24h_usd") or 0):
            best_by_address[key] = p
    return list(best_by_address.values())


def resolve_coingecko_id(network: str, contract_address: str) -> str | None:
    """CoinGecko punya endpoint lookup token by contract address — ini cara
    gratis menjembatani 'alamat token di chain X' -> 'id CoinGecko'."""
    platform_id = config.GECKOTERMINAL_TO_COINGECKO_PLATFORM.get(network)
    if not platform_id or not contract_address:
        return None
    data = _get(f"{config.COINGECKO_BASE}/coins/{platform_id}/contract/{contract_address}")
    if not data:
        return None
    return data.get("id")


# ---------------------------------------------------------------------------
# Fungsi utama — dipanggil dari run_screener.py
# ---------------------------------------------------------------------------

def build_candidate_list(networks: list[str] | None = None,
                          pages_per_network: int = 5) -> list[dict]:
    """
    Mengembalikan list token_config MENTAH (belum lengkap data manual) —
    run_screener.py akan menggabungkannya dengan MANUAL_OVERRIDES kalau ada.

    Menggabungkan 2 sumber:
    - trending_pools (kandidat langsung, tersedia sejak run pertama)
    - candidate_journal (kandidat yang "naik kelas" dari pool baru yang
      dicatat di run-run sebelumnya)
    """
    networks = networks or config.NETWORKS_TO_SCAN
    all_new_pools = []
    all_trending_pools = []

    for network in networks:
        print(f"  Scanning trending pools di network: {network} ...")
        trending = get_trending_pools(network, pages=pages_per_network)
        all_trending_pools.extend(trending)

        print(f"  Scanning new pools di network: {network} (untuk journal) ...")
        new_pools = get_new_pools(network, pages=3)
        all_new_pools.extend(new_pools)

    # Catat pool baru ke journal untuk coverage jangka panjang
    update_journal_with_new_pools(all_new_pools)

    # Gabungkan kandidat dari trending (langsung) + journal (yang sudah "naik umur")
    journal_aged = get_aged_candidates_from_journal()
    trending_aged = filter_by_age(all_trending_pools)

    combined = trending_aged + journal_aged
    deduped = dedupe_by_token_address(combined)

    print(f"  Kandidat dari trending_pools (umur cocok): {len(trending_aged)}")
    print(f"  Kandidat dari candidate journal (umur cocok): {len(journal_aged)}")
    print(f"  Total setelah dedupe: {len(deduped)}")

    candidates = []
    for p in deduped:
        cg_id = resolve_coingecko_id(p["network"], p["base_token_address"])
        candidates.append({
            "symbol": (p.get("base_token_symbol") or "UNKNOWN").upper(),
            "coingecko_id": cg_id,
            "network": p["network"],
            "explorer_contract": p.get("base_token_address"),
            "age_days_from_pool": p.get("age_days"),
            "volume_24h_usd_pool": p.get("volume_24h_usd"),
            "auto_discovered": True,
        })
    return candidates
