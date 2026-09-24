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

# --- Tabel ringkasan utama ---
table_rows = [{
    "Token": s["token_symbol"],
    "Umur (hari)": s["age_days"],
    "Skor Total (0-20)": s["total_skor_0_20"],
    "Skor Total (%)": s["total_skor_persen"],
    "Terakhir di-update": s["run_timestamp"][:10],
} for s in snapshots]

df = pd.DataFrame(table_rows).sort_values("Skor Total (0-20)", ascending=False)

st.subheader("Ranking Screener")
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
