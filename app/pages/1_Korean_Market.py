import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import streamlit as st

from analysis.correlation import find_related
from app.utils.data_loader import load_krx_listing, load_latest_prices_df
from app.utils.chart_builder import (
    build_network_graph, build_heatmap, build_treemap, build_comparison_chart
)

st.set_page_config(page_title="한국 시장", layout="wide")
st.title("🇰🇷 한국 주식 분석")

# ── 종목 입력 ──────────────────────────────────────────────────────────
listing = load_krx_listing()

col1, col2 = st.columns([3, 1])
with col1:
    raw_input = st.text_input(
        "관심 종목 입력 (종목코드 또는 종목명, 쉼표 구분)",
        value="005930, 000660",
        placeholder="005930, 삼성전자, SK하이닉스",
    )
with col2:
    st.markdown("<br>", unsafe_allow_html=True)
    analyze = st.button("분석 시작", type="primary", use_container_width=True)

if not analyze:
    st.stop()

# ── 입력 파싱 ─────────────────────────────────────────────────────────
watch_raw = [s.strip() for s in raw_input.split(",") if s.strip()]

# 종목명 → 코드 변환
name_to_sym = {}
sym_to_name = {}
if not listing.empty and "Name" in listing.columns and "Symbol" in listing.columns:
    name_to_sym = dict(zip(listing["Name"], listing["Symbol"]))
    sym_to_name = dict(zip(listing["Symbol"], listing["Name"]))

watch_symbols = []
unknown = []
for token in watch_raw:
    if token in listing.get("Symbol", pd.Series()).values if not listing.empty else []:
        watch_symbols.append(token)
    elif token in name_to_sym:
        watch_symbols.append(name_to_sym[token])
    else:
        unknown.append(token)

if unknown:
    st.warning(f"인식 불가 종목: {', '.join(unknown)} (종목코드 6자리 또는 정확한 종목명 사용)")

if not watch_symbols:
    st.error("유효한 종목이 없습니다.")
    st.stop()

# ── 연관 종목 분석 ────────────────────────────────────────────────────
with st.spinner("연관 종목 탐색 중..."):
    result = find_related(watch_symbols)

nodes = result["nodes"]
edges = result["edges"]
corr_matrix = result["corr_matrix"]

if not nodes:
    st.warning("데이터가 없습니다. 먼저 수집 스크립트를 실행하세요.")
    st.stop()

st.success(f"종목 {len(nodes)}개, 연관 관계 {len(edges)}개 탐색 완료")

# ── 탭 구성 ───────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(["🔗 네트워크", "🌡️ 히트맵", "🗺️ 트리맵", "📊 비교 차트"])

with tab1:
    fig = build_network_graph(nodes, edges)
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("연관 종목 목록"):
        related_syms = [n["id"] for n in nodes if n["id"] not in watch_symbols]
        related_names = [f"{sym_to_name.get(s, s)} ({s})" for s in related_syms]
        st.write(", ".join(related_names) if related_names else "없음")

with tab2:
    fig = build_heatmap(corr_matrix, watch_symbols)
    st.plotly_chart(fig, use_container_width=True)

with tab3:
    fig = build_treemap(listing)
    st.plotly_chart(fig, use_container_width=True)

with tab4:
    all_syms = [n["id"] for n in nodes]
    prices_df = load_latest_prices_df(all_syms)
    fig = build_comparison_chart(prices_df, all_syms, sym_to_name)
    st.plotly_chart(fig, use_container_width=True)
