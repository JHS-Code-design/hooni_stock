import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import plotly.graph_objects as go

from app.utils.data_loader import load_us_market_history, load_latest_fng

st.set_page_config(page_title="미국 시장", layout="wide")
st.title("🇺🇸 미국 시장 동향")

us = load_us_market_history()
fng = load_latest_fng()

if us.empty:
    st.warning("미국 시장 데이터 없음. 수집 스크립트를 먼저 실행하세요.")
    st.stop()

# ── 주요 지표 요약 ────────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)

def delta(series):
    if len(series) < 2:
        return None
    return float(series.iloc[-1] - series.iloc[-2])

with col1:
    if "SP500" in us.columns:
        v = float(us["SP500"].dropna().iloc[-1])
        d = delta(us["SP500"].dropna())
        st.metric("S&P 500", f"{v:,.0f}", f"{d:+.1f}" if d else None)

with col2:
    if "NASDAQ" in us.columns:
        v = float(us["NASDAQ"].dropna().iloc[-1])
        d = delta(us["NASDAQ"].dropna())
        st.metric("NASDAQ", f"{v:,.0f}", f"{d:+.1f}" if d else None)

with col3:
    if "KRW" in us.columns:
        v = float(us["KRW"].dropna().iloc[-1])
        d = delta(us["KRW"].dropna())
        st.metric("원/달러", f"{v:,.1f}", f"{d:+.1f}" if d else None)

with col4:
    if "VIX" in us.columns:
        v = float(us["VIX"].dropna().iloc[-1])
        st.metric("VIX", f"{v:.2f}")

# ── 공포탐욕 게이지 ───────────────────────────────────────────────────
if fng:
    score = fng.get("score")
    rating = fng.get("rating", "")
    source = fng.get("source", "")

    if score is not None:
        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=score,
            title={"text": f"공포탐욕지수 ({rating})"},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": "#1f77b4"},
                "steps": [
                    {"range": [0, 25], "color": "#d62728"},
                    {"range": [25, 45], "color": "#ff7f0e"},
                    {"range": [45, 55], "color": "#bcbd22"},
                    {"range": [55, 75], "color": "#2ca02c"},
                    {"range": [75, 100], "color": "#17becf"},
                ],
                "threshold": {"line": {"color": "white", "width": 4}, "value": score},
            },
        ))
        fig.update_layout(
            paper_bgcolor="#0e1117",
            font=dict(color="#fafafa"),
            height=300,
        )
        st.plotly_chart(fig, use_container_width=True)
        if source == "VIX_FALLBACK":
            st.caption("* VIX 기반 추정값 (CNN 엔드포인트 사용 불가)")

# ── 차트 ─────────────────────────────────────────────────────────────
st.subheader("지수 추이")
tab1, tab2, tab3 = st.tabs(["S&P500 / NASDAQ", "원/달러 환율", "VIX"])

with tab1:
    fig = go.Figure()
    for col, name in [("SP500", "S&P 500"), ("NASDAQ", "NASDAQ")]:
        if col in us.columns:
            s = us[col].dropna()
            norm = s / s.iloc[0] * 100
            fig.add_trace(go.Scatter(x=norm.index, y=norm.values, name=name, mode="lines"))
    fig.update_layout(
        yaxis_title="정규화 (기준=100)",
        paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
        font=dict(color="#fafafa"), legend=dict(bgcolor="#262730"),
    )
    st.plotly_chart(fig, use_container_width=True)

with tab2:
    if "KRW" in us.columns:
        s = us["KRW"].dropna()
        fig = go.Figure(go.Scatter(x=s.index, y=s.values, mode="lines", name="원/달러"))
        fig.update_layout(
            yaxis_title="원/달러",
            paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
            font=dict(color="#fafafa"),
        )
        st.plotly_chart(fig, use_container_width=True)

with tab3:
    if "VIX" in us.columns:
        s = us["VIX"].dropna()
        fig = go.Figure(go.Scatter(x=s.index, y=s.values, mode="lines", name="VIX",
                                   line=dict(color="#d62728")))
        fig.update_layout(
            yaxis_title="VIX",
            paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
            font=dict(color="#fafafa"),
        )
        st.plotly_chart(fig, use_container_width=True)
