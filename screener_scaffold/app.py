"""
Web app screener — di-hosting gratis lewat Streamlit Community Cloud.
Tidak perlu dijalankan manual; Streamlit Cloud yang menjalankan file ini
otomatis dan mengekspos ke URL publik begitu repo di-deploy.

Data yang ditampilkan berasal dari data/snapshots.json, yang diperbarui
otomatis oleh GitHub Actions (lihat .github/workflows/run_screener.yml)
sesuai jadwal, TANPA kamu perlu menjalankan apa pun secara lokal.
"""

import pandas as pd
import streamlit as st
from screener import storage, scoring

st.set_page_config(page_title="Early-Stage Coin Screener", layout="wide")
st.title("🔍 Early-Stage Coin Screener")
st.caption("8-faktor quality model — data pribadi, di-update otomatis via GitHub Actions")

snapshots = storage.get_latest_snapshots()

if not snapshots:
    st.warning(
        "Belum ada data. Data akan muncul otomatis setelah GitHub Actions "
        "menjalankan pipeline pertama kali (cek tab 'Actions' di repo GitHub kamu, "
        "atau trigger manual lewat 'Run workflow')."
    )
    st.stop()

EXPLORER_URL_TEMPLATES = {
    "eth": "https://etherscan.io/token/{addr}",
    "solana": "https://solscan.io/token/{addr}",
    "base": "https://basescan.org/token/{addr}",
    "arbitrum": "https://arbiscan.io/token/{addr}",
    "bsc": "https://bscscan.com/token/{addr}",
}


def explorer_link(network: str | None, address: str | None) -> str | None:
    if not network or not address:
        return None
    template = EXPLORER_URL_TEMPLATES.get(network)
    return template.format(addr=address) if template else None


# --- Tabel ringkasan utama ---
table_rows = [{
    "Token": s["token_symbol"],
    "Chain": s.get("network") or "-",
    "Contract Address": s.get("contract_address") or "-",
    "Umur (hari)": s["age_days"],
    "Skor Total (0-20)": s["total_skor_0_20"],
    "Skor Total (%)": s["total_skor_persen"],
    "Terakhir di-update": s["run_timestamp"][:10],
} for s in snapshots]

df = pd.DataFrame(table_rows).sort_values("Skor Total (0-20)", ascending=False)

st.subheader("Ranking Screener")
st.caption(
    "⚠️ Skor rendah pada token yang baru pertama kali muncul (belum ada di "
    "MANUAL_OVERRIDES) itu WAJAR — bukan berarti token-nya jelek. 3 faktor "
    "berbobot terbesar (Value Accrual, Revenue, Dominasi Pasar = 55% dari "
    "skor total) butuh riset manual singkat sebelum bisa dinilai akurat. "
    "Klik token di bawah untuk lihat faktor mana yang masih 'Insufficient'."
)
st.dataframe(df, use_container_width=True, hide_index=True)

st.divider()

# --- Detail per token (expand ke 8 faktor) ---
st.subheader("Detail 8 Faktor per Token")
selected_symbol = st.selectbox(
    "Pilih token untuk lihat breakdown lengkap:",
    options=[s["token_symbol"] for s in snapshots],
)

selected = next(s for s in snapshots if s["token_symbol"] == selected_symbol)
factor_scores = selected["factor_scores"]
factor_breakdowns = selected["factor_breakdown"]
confidence = selected["confidence"]
radar = selected.get("why_on_radar") or {}

# --- Identitas token: chain + contract address (supaya tidak salah token) ---
addr = selected.get("contract_address")
network = selected.get("network")
link = explorer_link(network, addr)
id_col1, id_col2 = st.columns([1, 3])
with id_col1:
    st.markdown(f"**Chain:** `{network or '-'}`")
with id_col2:
    if link:
        st.markdown(f"**Contract:** [`{addr}`]({link})")
    else:
        st.markdown(f"**Contract:** `{addr or '-'}`")

st.divider()

# --- Kenapa token ini masuk radar (narasi fundamental) ---
st.subheader("💡 Kenapa token ini masuk radar")
if radar.get("ringkasan"):
    st.write(radar["ringkasan"])
else:
    st.info("Belum ada narasi — whitepaper/docs resmi token ini belum berhasil "
            "dibaca. Isi 'whitepaper_urls' di MANUAL_OVERRIDES (run_screener.py) "
            "untuk token ini supaya narasinya lengkap.")

fact_col1, fact_col2, fact_col3 = st.columns(3)
with fact_col1:
    mc = radar.get("market_cap_usd")
    st.metric("Market Cap", f"${mc:,.0f}" if mc else "Belum ada data")
with fact_col2:
    rank = radar.get("rank_kategori")
    total_comp = radar.get("total_kompetitor_sekategori")
    st.metric("Rank di kategori", f"#{rank} dari {total_comp}" if rank and total_comp else "Belum ada data")
with fact_col3:
    rev = radar.get("revenue_tahunan_estimasi_usd")
    st.metric("Revenue tahunan (estimasi)", f"${rev:,.0f}" if rev else "Belum ada data")

if radar.get("mekanisme_kerja"):
    st.markdown("**Mekanisme kerja:**")
    st.write(radar["mekanisme_kerja"])

adv_col, risk_col = st.columns(2)
with adv_col:
    st.markdown("**Keunggulan:**")
    keunggulan = radar.get("keunggulan") or []
    if keunggulan:
        for item in keunggulan:
            st.markdown(f"- {item}")
    else:
        st.caption("Tidak ada data")
with risk_col:
    st.markdown("**Kelemahan / risiko:**")
    kelemahan = radar.get("kelemahan_atau_risiko") or []
    if kelemahan:
        for item in kelemahan:
            st.markdown(f"- {item}")
    else:
        st.caption("Tidak ada data")

if radar.get("keunikan"):
    st.markdown("**Keunikan dibanding kompetitor:**")
    st.write(radar["keunikan"])

backers = radar.get("tim_atau_backer_disebutkan")
st.markdown("**Tim/backer yang disebutkan di dokumen resmi:**")
if backers:
    st.write(", ".join(backers))
else:
    st.caption("Tidak disebutkan di whitepaper/docs — bukan berarti tidak ada, "
               "cuma tidak tercantum di dokumen yang dibaca screener.")

top10 = radar.get("top10_wallet_konsentrasi_pct")
st.markdown("**Proxy konsentrasi holder (top 10 wallet):**")
st.write(f"{top10}%" if top10 is not None else "Tidak ada data (bukan breakdown institusi vs retail — data itu tidak tersedia gratis untuk token seukuran ini)")

if radar.get("catatan"):
    st.caption(f"ℹ️ {radar['catatan']}")

st.divider()

col1, col2 = st.columns([1, 2])
with col1:
    st.metric("Skor Total", f"{selected['total_skor_0_20']} / 20",
               f"{selected['total_skor_persen']}%")
    st.metric("Umur Token", f"{selected['age_days']} hari")

with col2:
    st.write("**Breakdown per Faktor**")
    for key, label in scoring.FACTOR_KEY_MAP.items():
        skor = factor_scores.get(key, 0)
        conf = confidence.get(key)
        conf_badge = f" `{conf}`" if conf else ""
        st.progress(min(skor / 20, 1.0), text=f"{label}: {skor}/20{conf_badge}")

st.divider()

with st.expander("Lihat detail mentah (alasan & red flags per faktor)"):
    for key, label in scoring.FACTOR_KEY_MAP.items():
        st.markdown(f"**{label}**")
        st.json(factor_breakdowns.get(key, {}))

st.divider()

# --- Tren historis token ---
with st.expander("📈 Riwayat skor token ini (untuk pantau tren / backtest)"):
    history = storage.get_history_for_token(selected_symbol)
    if len(history) > 1:
        hist_df = pd.DataFrame([
            {"Tanggal": h["run_timestamp"][:10], "Skor Total": h["total_skor_0_20"]}
            for h in history
        ])
        st.line_chart(hist_df.set_index("Tanggal"))
    else:
        st.info("Baru ada 1 snapshot — GitHub Actions akan menambah data baru "
                 "tiap kali workflow terjadwal jalan (mis. tiap bulan).")
