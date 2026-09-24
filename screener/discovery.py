"""
Discovery layer otomatis — menggantikan watchlist manual.
Sumber: GeckoTerminal Public API (bagian dari CoinGecko, gratis, cloud,
TANPA API key, tanpa perlu jalan di komputer sendiri selain kode Python-nya).
Endpoint /networks/{network}/new_pools memberi daftar pool DEX yang baru
dibuat per chain — inilah discovery layer real untuk "token baru rilis di DEX".

Alur:
  1. Ambil pool baru per network dari GeckoTerminal
  2. Filter umur pool sesuai MIN_AGE_DAYS s.d. MAX_AGE_DAYS_FOR_DISCOVERY
  3. Coba resolve ke CoinGecko id (buat narik market cap/supply nanti)
  4. Keluarkan daftar kandidat token_config siap dipakai pipeline.py

CATATAN JUJUR: tidak semua token baru punya CoinGecko id (banyak yang
terlalu baru/kecil untuk diindeks CoinGecko) — kalau tidak ketemu,
kandidat tetap dikeluarkan tapi ditandai coingecko_id=None, dan pipeline
akan menandai faktor-faktor yang butuh data itu sebagai "Insufficient"
alih-alih memaksakan angka palsu.
"""

import time
from datetime import datetime, timezone
from . import config
from .data_sources import _get  # reuse session + retry logic


def get_new_pools(network: str, pages: int = 3) -> list[dict]:
    """Ambil pool baru dari satu network. pages=3 -> ~60-90 pool terbaru
    (tiap halaman GeckoTerminal berisi ~20 item)."""
    results = []
    for page in range(1, pages + 1):
        data = _get(
            f"{config.GECKOTERMINAL_BASE}/networks/{network}/new_pools",
            params={"page": page, "include": "base_token"},
        )
        if not data or not data.get("data"):
            break

        included = {item["id"]: item for item in data.get("included", [])}

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
        time.sleep(0.5)  # sopan ke free API, hindari rate-limit
    return results


def compute_pool_age_days(pool_created_at: str | None) -> int | None:
    if not pool_created_at:
        return None
    try:
        created = datetime.fromisoformat(pool_created_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - created).days


def filter_by_age(pools: list[dict]) -> list[dict]:
    """Sesuai spec: umur minimal 3 bulan. Ditambah batas atas supaya
    screener tetap fokus 'early-stage', bukan token yang sudah lama sekali
    (yang mestinya sudah dianalisis lewat jalur riset biasa, bukan screener ini)."""
    filtered = []
    for p in pools:
        age = compute_pool_age_days(p.get("pool_created_at"))
        if age is None:
            continue
        if config.MIN_AGE_DAYS <= age <= config.MAX_AGE_DAYS_FOR_DISCOVERY:
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
        current_best = best_by_address.get(addr)
        if not current_best or (p.get("volume_24h_usd") or 0) > (current_best.get("volume_24h_usd") or 0):
            best_by_address[addr] = p
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


def build_candidate_list(networks: list[str] | None = None,
                          pages_per_network: int = 3) -> list[dict]:
    """
    Fungsi utama discovery layer. Panggil ini dari run_screener.py.
    Mengembalikan list token_config MENTAH (belum lengkap data manual) —
    run_screener.py akan menggabungkannya dengan MANUAL_OVERRIDES kalau ada.
    """
    networks = networks or config.NETWORKS_TO_SCAN
    all_pools = []
    for network in networks:
        print(f"  Scanning pool baru di network: {network} ...")
        pools = get_new_pools(network, pages=pages_per_network)
        all_pools.extend(pools)

    aged = filter_by_age(all_pools)
    deduped = dedupe_by_token_address(aged)

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
