import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import plotly.graph_objects as go
import pandas as pd

from analysis.forecast import run_forecast, _load_price_series
from analysis.backtest import run_backtest
from app.utils.data_loader import load_krx_listing
from app.utils.watchlist import load_shared

st.set_page_config(page_title="주가 예측", layout="wide")
st.title("📈 주가 예측 (복합)")
st.caption("선형 회귀 + 미국 섹터 ETF 연동 + ATR 신뢰 구간 (참고용, 투자 조언 아님)")

listing = load_krx_listing()
sym_to_name: dict = {}
name_to_sym: dict = {}
sym_to_sector: dict = {}
if not listing.empty and "Name" in listing.columns:
    sym_to_name = dict(zip(listing["Symbol"], listing["Name"]))
    name_to_sym = dict(zip(listing["Name"], listing["Symbol"]))
    if "Sector" in listing.columns:
        sym_to_sector = dict(zip(listing["Symbol"], listing["Sector"]))

# ── 입력 ─────────────────────────────────────────────────────────────
shared = load_shared()

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

token = raw.strip()
symbol = name_to_sym.get(token) or (token if token in sym_to_name else token)
_s = sym_to_sector.get(symbol, "")
sector = _s if isinstance(_s, str) and _s else ""  # NaN 방어

run_btn = st.button("예측 시작", type="primary")

if not run_btn:
    if shared:
        st.info(f"종목을 선택하고 '예측 시작'을 누르세요. 관심 종목: {', '.join(sym_to_name.get(s, s) for s in shared)}")
    st.stop()

# ── 예측 실행 ────────────────────────────────────────────────────────
with st.spinner("데이터 로딩 및 예측 중..."):
    result = run_forecast(symbol, history_days=history_days,
                          forecast_days=forecast_days, sector=sector)

if not result:
    st.error("데이터를 불러올 수 없습니다. 종목코드를 확인하세요.")
    st.stop()

series   = result["series"]
linear   = result["linear"]
ma20     = result["ma20"]
ma60     = result["ma60"]
current  = result["current_price"]
target   = result["target_price"]
target_c = result["target_combined"]
chg      = result["change_pct"]
chg_c    = result["change_pct_combined"]
us_info  = result["us"]
atr      = result["atr"]
name     = sym_to_name.get(symbol, symbol)

# ── 요약 지표 ────────────────────────────────────────────────────────
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("현재가", f"{current:,.0f}원")
c2.metric(
    f"{forecast_days}일 후 예측 (선형)",
    f"{target:,.0f}원",
    f"{chg:+.2f}%",
    delta_color="normal",
)
c3.metric(
    f"{forecast_days}일 후 예측 (복합)",
    f"{target_c:,.0f}원",
    f"{chg_c:+.2f}%",
    delta_color="normal",
)
c4.metric("ATR14 (1일 변동폭)", f"{atr:,.0f}원")
c5.metric("추세 신뢰도 (R²)", f"{linear['r_squared']:.2f}")

# ── 미국 섹터 패널 ────────────────────────────────────────────────────
with st.expander("🇺🇸 미국 섹터 연동 분석", expanded=True):
    if us_info["tickers"]:
        ua1, ua2, ua3, ua4 = st.columns(4)
        ua1.metric("업종", sector or "미분류")
        ua2.metric("베타 (β)", f"{us_info['beta']:.3f}")
        ua3.metric("상관계수 (ρ)", f"{us_info['rho']:.3f}")
        ua4.metric(
            "미국 바스켓 최근 수익률",
            f"{us_info['basket_return_1d']*100:+.2f}%",
        )

        # 기여도 바 차트
        contrib_labels = ["국내 기술적 (선형)", "미국 섹터 조정"]
        base_chg = chg
        us_contrib = chg_c - chg
        colors = ["#42a5f5", "#ff7043" if us_contrib >= 0 else "#66bb6a"]
        fig_bar = go.Figure(go.Bar(
            x=contrib_labels,
            y=[base_chg, us_contrib],
            marker_color=colors,
            text=[f"{base_chg:+.2f}%", f"{us_contrib:+.2f}%"],
            textposition="outside",
        ))
        fig_bar.update_layout(
            title="예측 기여도 분해",
            yaxis_title="등락률 기여 (%)",
            paper_bgcolor="#0e1117",
            plot_bgcolor="#0e1117",
            font=dict(color="#fafafa"),
            height=280,
            showlegend=False,
        )
        fig_bar.update_xaxes(showgrid=False)
        fig_bar.update_yaxes(showgrid=True, gridcolor="#2a2a2a", zeroline=True,
                              zerolinecolor="#555")
        st.plotly_chart(fig_bar, use_container_width=True)

        tickers_str = ", ".join(us_info["tickers"])
        direction = "상승" if us_info["basket_return_1d"] >= 0 else "하락"
        st.caption(
            f"바스켓: {tickers_str} | "
            f"전일 미국 {direction} {abs(us_info['basket_return_1d'])*100:.2f}% → "
            f"β={us_info['beta']:.2f}, ρ={us_info['rho']:.2f} 반영 → "
            f"복합 조정 {us_info['adj_pct']:+.2f}%/일"
        )
    else:
        st.caption("업종 정보 없음 — 미국 섹터 연동 생략 (선형 예측만 사용)")

# ── 차트 ─────────────────────────────────────────────────────────────
fig = go.Figure()

fig.add_trace(go.Scatter(
    x=series.index, y=series.values,
    name="실제 주가", mode="lines",
    line=dict(color="#90caf9", width=2),
))

fig.add_trace(go.Scatter(
    x=linear["in_sample"].index, y=linear["in_sample"].values,
    name="선형 추세선", mode="lines",
    line=dict(color="#ffb74d", width=1, dash="dot"),
))

fig.add_trace(go.Scatter(
    x=linear["forecast"].index, y=linear["forecast"].values,
    name="선형 예측", mode="lines",
    line=dict(color="#ff7043", width=2),
))

# 복합 예측선 (선형 + 미국 조정)
if us_info["tickers"]:
    combined_series = linear["forecast"] * (target_c / target if target != 0 else 1)
    fig.add_trace(go.Scatter(
        x=combined_series.index, y=combined_series.values,
        name="복합 예측 (US 조정)", mode="lines",
        line=dict(color="#ce93d8", width=2, dash="dash"),
    ))

# ATR 밴드 (95% 신뢰 구간)
fig.add_trace(go.Scatter(
    x=list(linear["upper"].index) + list(linear["lower"].index[::-1]),
    y=list(linear["upper"].values) + list(linear["lower"].values[::-1]),
    fill="toself", fillcolor="rgba(255,112,67,0.12)",
    line=dict(color="rgba(0,0,0,0)"),
    name="95% 신뢰 구간",
    hoverinfo="skip",
))

fig.add_trace(go.Scatter(
    x=ma20.index, y=ma20.values,
    name="MA20 예측", mode="lines",
    line=dict(color="#66bb6a", width=1, dash="dash"),
))

fig.add_trace(go.Scatter(
    x=ma60.index, y=ma60.values,
    name="MA60 예측", mode="lines",
    line=dict(color="#ab47bc", width=1, dash="dash"),
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
    title=f"{name} ({symbol}) — {forecast_days}일 복합 예측",
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
    tbl = pd.DataFrame({
        "날짜": linear["forecast"].index.strftime("%Y-%m-%d"),
        "선형 예측(원)": linear["forecast"].values.round(0).astype(int),
        "복합 예측(원)": (linear["forecast"] * (target_c / target if target != 0 else 1)).values.round(0).astype(int),
        "상단 95%(원)": linear["upper"].values.round(0).astype(int),
        "하단 95%(원)": linear["lower"].values.round(0).astype(int),
        "MA20 예측(원)": ma20.values.round(0).astype(int),
        "MA60 예측(원)": ma60.values.round(0).astype(int),
    })
    st.dataframe(tbl.set_index("날짜"), use_container_width=True)

# ── 백테스트 ─────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("🔬 모델 백테스트 (과거 검증)")
st.caption(f"동일 모델로 과거 {history_days}일 데이터를 이용해 {forecast_days}일 후를 예측, 실제값과 비교")

with st.spinner("백테스트 실행 중..."):
    full_series = _load_price_series(symbol, 270)
    bt = run_backtest(
        full_series, sector=sector,
        history_days=history_days, forecast_days=forecast_days, n_tests=5,
    )

if not bt:
    st.warning("데이터가 부족하여 백테스트를 수행할 수 없습니다. (최소 120일 이상 필요)")
else:
    # 요약 테이블
    summary_df = pd.DataFrame({
        "모델":      ["선형 회귀", "복합(US조정)", "MA20"],
        "MAPE(%)":   [bt["linear"]["mape"], bt["combined"]["mape"], bt["ma20"]["mape"]],
        "방향 정확도(%)": [bt["linear"]["direction_acc"], bt["combined"]["direction_acc"], bt["ma20"]["direction_acc"]],
        "MAE(원)":   [f"{bt['linear']['mae']:,}", f"{bt['combined']['mae']:,}", f"{bt['ma20']['mae']:,}"],
    })

    def _color_mape(val):
        try:
            v = float(val)
            if v < 5:   return "color: #66bb6a"
            if v < 10:  return "color: #ffb74d"
            return "color: #ef5350"
        except Exception:
            return ""

    def _color_dir(val):
        try:
            v = float(val)
            if v >= 65: return "color: #66bb6a"
            if v >= 55: return "color: #ffb74d"
            return "color: #ef5350"
        except Exception:
            return ""

    st.dataframe(
        summary_df.style
            .map(_color_mape, subset=["MAPE(%)"])
            .map(_color_dir, subset=["방향 정확도(%)"]),
        use_container_width=True, hide_index=True,
    )

    # 개별 윈도우 차트 (예측 vs 실제)
    with st.expander("백테스트 상세 — 윈도우별 예측/실제 비교"):
        lin_tests = bt["linear"]["tests"]
        comb_tests = bt["combined"]["tests"]

        fig_bt = go.Figure()
        dates = [t["cutoff_date"] for t in lin_tests]

        fig_bt.add_trace(go.Scatter(
            x=dates, y=[t["actual"] for t in lin_tests],
            name="실제 주가", mode="lines+markers",
            line=dict(color="#90caf9", width=2),
            marker=dict(size=8),
        ))
        fig_bt.add_trace(go.Scatter(
            x=dates, y=[t["predicted"] for t in lin_tests],
            name="선형 예측", mode="lines+markers",
            line=dict(color="#ff7043", width=2, dash="dash"),
            marker=dict(size=8),
        ))
        fig_bt.add_trace(go.Scatter(
            x=dates, y=[t["predicted"] for t in comb_tests],
            name="복합 예측", mode="lines+markers",
            line=dict(color="#ce93d8", width=2, dash="dot"),
            marker=dict(size=8),
        ))

        fig_bt.update_layout(
            title=f"백테스트: cutoff 시점 기준 {forecast_days}일 후 예측 vs 실제",
            yaxis_title="주가 (원)",
            xaxis_title="예측 기준 날짜",
            paper_bgcolor="#0e1117",
            plot_bgcolor="#0e1117",
            font=dict(color="#fafafa"),
            legend=dict(bgcolor="#262730"),
            height=380,
        )
        fig_bt.update_xaxes(showgrid=True, gridcolor="#2a2a2a")
        fig_bt.update_yaxes(showgrid=True, gridcolor="#2a2a2a", tickformat=",d")
        st.plotly_chart(fig_bt, use_container_width=True)

        # 수치 테이블
        detail_rows = []
        for t in lin_tests:
            detail_rows.append({
                "기준일": t["cutoff_date"],
                "실제가(원)": f"{t['actual']:,}",
                "선형 예측(원)": f"{t['predicted']:,}",
                "선형 오차": f"{t['mape']:.1f}%",
                "방향": "✅" if t["direction_correct"] else "❌",
            })
        st.dataframe(pd.DataFrame(detail_rows).set_index("기준일"), use_container_width=True)

    st.caption(
        f"검증 윈도우 {bt['n_valid']}개 | "
        f"MAPE: 녹색 <5%, 주황 5~10%, 빨강 >10% | "
        f"방향 정확도: 녹색 ≥65%, 주황 55~64%, 빨강 <55%"
    )

st.warning("⚠️ 이 예측은 통계 모델 기반이며 실제 시장 상황을 보장하지 않습니다. 투자 판단의 참고 자료로만 활용하세요.")
