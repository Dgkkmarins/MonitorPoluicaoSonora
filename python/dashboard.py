"""
Dashboard: le o historico de leituras (gravado pelo gateway.py a partir
dos dados do ESP8266) e exibe graficos em tempo real.

Rodar com: streamlit run dashboard.py

Fonte dos dados:
- Local (SQLite, mesma base do gateway): historico completo, sempre disponivel.
- ThingSpeak (nuvem): confirma que o dado realmente chegou na nuvem.
"""

import sqlite3
import time
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

DB_PATH = Path(__file__).parent / "monitor.db"

THINGSPEAK_CHANNEL_ID = "COLOQUE_SEU_CHANNEL_ID_AQUI"
THINGSPEAK_READ_API_KEY = "COLOQUE_SUA_READ_API_KEY_AQUI"
THINGSPEAK_READ_URL = f"https://api.thingspeak.com/channels/{THINGSPEAK_CHANNEL_ID}/feeds.json"

# Paleta de status (mesma logica do semaforo VERDE/AMARELO/VERMELHO do projeto)
COR_NIVEL = {
    "BAIXO": "#2E7D32",
    "MODERADO": "#F9A825",
    "ALTO": "#EF6C00",
    "CRITICO": "#C62828",
}
COR_LINHA_DB = "#2563EB"

st.set_page_config(page_title="Monitor de Poluicao Sonora", page_icon="🔊", layout="wide")


@st.cache_data(ttl=3)
def carregar_historico_local(limite: int = 200) -> pd.DataFrame:
    if not DB_PATH.exists():
        return pd.DataFrame()
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT * FROM leituras ORDER BY id DESC LIMIT ?", conn, params=(limite,)
    )
    conn.close()
    if df.empty:
        return df
    df["horario"] = pd.to_datetime(df["timestamp"], unit="s")
    return df.sort_values("horario")


def buscar_confirmacao_cloud() -> dict | None:
    try:
        resposta = requests.get(
            THINGSPEAK_READ_URL, params={"api_key": THINGSPEAK_READ_API_KEY, "results": 1}, timeout=5
        )
        resposta.raise_for_status()
        feeds = resposta.json().get("feeds", [])
        return feeds[-1] if feeds else None
    except (requests.RequestException, ValueError):
        return None


def main():
    st.title("🔊 Monitor de Poluição Sonora")
    st.caption("Sensor → ESP8266 → Wi-Fi → Python (gateway) → ThingSpeak (cloud) → Dashboard")

    df = carregar_historico_local()

    if df.empty:
        st.warning("Nenhuma leitura recebida ainda. Rode o gateway.py e ligue o ESP8266.")
        st.stop()

    ultima = df.iloc[-1]

    col_dB, col_nivel, col_cloud = st.columns(3)

    col_dB.metric("Decibéis (última leitura)", f"{ultima['decibeis']:.1f} dB")

    cor_nivel = COR_NIVEL.get(ultima["nivel"], "#888888")
    col_nivel.markdown(
        f"""
        <div style="padding:0.75rem 1rem;border-radius:8px;background:{cor_nivel}22;
                    border:1px solid {cor_nivel};">
            <div style="font-size:0.8rem;color:#666;">Nível de poluição sonora</div>
            <div style="font-size:1.4rem;font-weight:600;color:{cor_nivel};">{ultima['nivel']}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    confirmacao = buscar_confirmacao_cloud()
    if confirmacao:
        col_cloud.metric("Última confirmação na nuvem (ThingSpeak)", confirmacao.get("created_at", "—"))
    else:
        col_cloud.metric("Última confirmação na nuvem (ThingSpeak)", "sem conexão")

    st.divider()

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["horario"],
            y=df["decibeis"],
            mode="lines",
            line=dict(color=COR_LINHA_DB, width=2, shape="spline"),
            name="Decibéis",
        )
    )
    fig.update_layout(
        title="Decibéis ao longo do tempo",
        xaxis_title="Horário",
        yaxis_title="dB",
        template="plotly_white",
        height=400,
        margin=dict(l=40, r=20, t=50, b=40),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Últimas leituras")
    st.dataframe(
        df[["horario", "device_id", "valor_sensor", "decibeis", "nivel"]]
        .sort_values("horario", ascending=False)
        .reset_index(drop=True),
        use_container_width=True,
    )

    time.sleep(3)
    st.rerun()


if __name__ == "__main__":
    main()
