import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import plotly.graph_objects as go

from analysis.forecast import run_forecast
from app.utils.data_loader import load_krx_listing
from app.utils.watchlist import load_shared

st.set_page_config(page_title="주가 예측", layout="wide")
st.title("📈 주가 예측")
st.caption("선형 회귀 추세 + 이동평균 기반 예측 (참고용, 투자 조언 아님)")

listing = load_krx_listing()
sym_to_name: dict = {}
name_to_sym: dict = {}
if not listing.empty and "Name" in listing.columns:
    sym_to_name = dict(zip(listing["Symbol"], listing["Name"]))
    name_to_sym = dict(zip(listing["Name"], listing["Symbol"]))

# ── 입력 ─────────────────────────────────────────────────────────────
shared = load_shared()
watchlist_options = [f"{sym_to_name.get(s, s)} ({s})" for s in shared]

col1, col2, col3 = st.columns([3, 2, 2])
with col1:
    raw = st.text_input(
        "종목코드 또는 종목명",
        value=shared[0] if shared else "064350",
        placeholder="064350 또는 현대로템",
    )
with col2:
    history_days = st.selectbox("과거 데이터 기간", [30, 60, 90, 180], index=2,
                                format_func=lambda x: f"{x}일")
with col3:
    forecast_days = st.selectbox("예측 기간", [7, 14, 30, 60, 90], index=2,
                                 format_func=lambda x: f"{x}일")

# 종목명 → 코드 변환
token = raw.strip()
symbol = name_to_sym.get(token) or (token if token in sym_to_name else token)

run_btn = st.button("예측 시작", type="primary")

if not run_btn:
    if shared:
        st.info(f"종목을 선택하고 '예측 시작'을 누르세요. 관심 종목: {', '.join(sym_to_name.get(s, s) for s in shared)}")
    st.stop()

# ── 예측 실행 ────────────────────────────────────────────────────────
with st.spinner("데이터 로딩 및 예측 중..."):
    result = run_forecast(symbol, history_days=history_days, forecast_days=forecast_days)

if not result:
    st.error("데이터를 불러올 수 없습니다. 종목코드를 확인하세요.")
    st.stop()

series = result["series"]
linear = result["linear"]
ma20 = result["ma20"]
ma60 = result["ma60"]
current = result["current_price"]
target = result["target_price"]
change_pct = result["change_pct"]
name = sym_to_name.get(symbol, symbol)

# ── 요약 지표 ────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
c1.metric("현재가", f"{current:,.0f}원")
c2.metric(
    f"{forecast_days}일 후 예측가 (선형)",
    f"{target:,.0f}원",
    f"{change_pct:+.2f}%",
    delta_color="normal",
)
c3.metric("추세", linear["trend"], f"기울기 {linear['slope']:+.1f}원/일")
c4.metric("추세 신뢰도 (R²)", f"{linear['r_squared']:.2f}")

# ── 차트 ─────────────────────────────────────────────────────────────
fig = go.Figure()

# 실제 가격
fig.add_trace(go.Scatter(
    x=series.index, y=series.values,
    name="실제 주가", mode="lines",
    line=dict(color="#90caf9", width=2),
))

# 선형 회귀 in-sample
fig.add_trace(go.Scatter(
    x=linear["in_sample"].index, y=linear["in_sample"].values,
    name="선형 추세선", mode="lines",
    line=dict(color="#ffb74d", width=1, dash="dot"),
))

# 선형 회귀 예측
fig.add_trace(go.Scatter(
    x=linear["forecast"].index, y=linear["forecast"].values,
    name="선형 예측", mode="lines",
    line=dict(color="#ff7043", width=2),
))

# 신뢰 구간 (95%)
fig.add_trace(go.Scatter(
    x=list(linear["upper"].index) + list(linear["lower"].index[::-1]),
    y=list(linear["upper"].values) + list(linear["lower"].values[::-1]),
    fill="toself", fillcolor="rgba(255,112,67,0.15)",
    line=dict(color="rgba(0,0,0,0)"),
    name="95% 신뢰 구간",
    hoverinfo="skip",
))

# MA20 예측
fig.add_trace(go.Scatter(
    x=ma20.index, y=ma20.values,
    name="MA20 예측", mode="lines",
    line=dict(color="#66bb6a", width=2, dash="dash"),
))

# MA60 예측
fig.add_trace(go.Scatter(
    x=ma60.index, y=ma60.values,
    name="MA60 예측", mode="lines",
    line=dict(color="#ab47bc", width=2, dash="dash"),
))

# 현재 시점 구분선
fig.add_shape(
    type="line",
    x0=series.index[-1], x1=series.index[-1],
    y0=0, y1=1, yref="paper",
    line=dict(color="rgba(255,255,255,0.4)", dash="dot"),
)
fig.add_annotation(
    x=series.index[-1], y=1, yref="paper",
    text="현재", showarrow=False,
    font=dict(color="rgba(255,255,255,0.6)"),
    xanchor="left",
)

fig.update_layout(
    title=f"{name} ({symbol}) — {forecast_days}일 예측",
    yaxis_title="주가 (원)",
    xaxis_title="날짜",
    paper_bgcolor="#0e1117",
    plot_bgcolor="#0e1117",
    font=dict(color="#fafafa"),
    legend=dict(bgcolor="#262730", x=0.01, y=0.99),
    hovermode="x unified",
    height=520,
)
fig.update_xaxes(showgrid=True, gridcolor="#2a2a2a")
fig.update_yaxes(showgrid=True, gridcolor="#2a2a2a", tickformat=",d")

st.plotly_chart(fig, use_container_width=True)

# ── 예측값 테이블 ─────────────────────────────────────────────────────
with st.expander("예측 수치 상세"):
    import pandas as pd
    tbl = pd.DataFrame({
        "날짜": linear["forecast"].index.strftime("%Y-%m-%d"),
        "선형 예측(원)": linear["forecast"].values.round(0).astype(int),
        "상단 95%(원)": linear["upper"].values.round(0).astype(int),
        "하단 95%(원)": linear["lower"].values.round(0).astype(int),
        "MA20 예측(원)": ma20.values.round(0).astype(int),
        "MA60 예측(원)": ma60.values.round(0).astype(int),
    })
    st.dataframe(tbl.set_index("날짜"), use_container_width=True)

st.warning("⚠️ 이 예측은 통계 모델 기반이며 실제 시장 상황을 보장하지 않습니다. 투자 판단의 참고 자료로만 활용하세요.")
