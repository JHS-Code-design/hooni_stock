import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import streamlit as st

from analysis.correlation import find_related
from app.utils.data_loader import load_krx_listing, load_latest_prices_df, fetch_current_prices
from app.utils.chart_builder import (
    build_network_graph, build_heatmap, build_treemap, build_comparison_chart
)
from app.utils.watchlist import (
    load_watchlist, save_watchlist,
    add_to_watchlist, remove_from_watchlist,
    load_shared,  # 하위 호환
)

st.set_page_config(page_title="한국 시장", layout="wide")
st.title("🇰🇷 한국 주식 분석")

listing = load_krx_listing()

sym_to_name: dict = {}
name_to_sym: dict = {}
if not listing.empty and "Name" in listing.columns and "Symbol" in listing.columns:
    sym_to_name = dict(zip(listing["Symbol"], listing["Name"]))
    name_to_sym = dict(zip(listing["Name"], listing["Symbol"]))


def sym_label(sym: str) -> str:
    name = sym_to_name.get(sym, "")
    return f"{name} ({sym})" if name else sym


# ── 사이드바: 관심 종목 관리 ─────────────────────────────────────────
with st.sidebar:
    st.markdown("---")
    st.subheader("⭐ 관심 종목")

    watchlist = load_watchlist()

    for sym in watchlist:
        c1, c2 = st.columns([4, 1])
        c1.write(sym_label(sym))
        if c2.button("✕", key=f"rm_{sym}", use_container_width=True):
            remove_from_watchlist(sym)
            st.rerun()

    with st.form("add_watch_form", clear_on_submit=True):
        new_sym = st.text_input("종목코드/종목명 추가",
                                placeholder="005930 또는 삼성전자")
        if st.form_submit_button("추가", use_container_width=True):
            token_input = new_sym.strip()
            resolved = (name_to_sym.get(token_input) or
                        (token_input if token_input in sym_to_name else None))
            if resolved:
                add_to_watchlist(resolved)
                st.rerun()
            else:
                st.error("인식 불가 종목")

    if watchlist:
        if st.button("📋 관심 목록으로 분석", use_container_width=True, key="use_watch"):
            st.session_state["watch_input"] = ", ".join(watchlist)
            st.rerun()

# ── 종목 입력 ──────────────────────────────────────────────────────────
_shared = load_shared()
if "watch_input" not in st.session_state:
    st.session_state["watch_input"] = ", ".join(_shared) if _shared else "005930, 000660"

col1, col2 = st.columns([3, 1])
with col1:
    raw_input = st.text_input(
        "관심 종목 입력 (종목코드 또는 종목명, 쉼표 구분)",
        key="watch_input",
        placeholder="005930, 삼성전자, SK하이닉스",
    )
with col2:
    st.markdown("<br>", unsafe_allow_html=True)
    analyze = st.button("분석 시작", type="primary", use_container_width=True)

if not analyze:
    st.stop()

# ── 입력 파싱 ─────────────────────────────────────────────────────────
watch_raw = [s.strip() for s in raw_input.split(",") if s.strip()]

watch_symbols = []
unknown = []
for token in watch_raw:
    if token in (listing["Symbol"].values if not listing.empty else []):
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

# ── 현재가 테이블 ─────────────────────────────────────────────────────
with st.spinner("현재가 조회 중..."):
    all_node_syms = [n["id"] for n in nodes]
    price_df = fetch_current_prices(all_node_syms)

if not price_df.empty:
    rows = []
    for n in nodes:
        sid = n["id"]
        row = {
            "종목코드": sid,
            "종목명": sym_to_name.get(sid, sid),
            "업종": n.get("sector", ""),
            "관심": "★" if n["is_watch"] else "",
        }
        if sid in price_df.index:
            row["현재가(원)"] = f"{price_df.loc[sid, '현재가']:,}"
            pct = price_df.loc[sid, "등락률(%)"]
            row["등락률"] = f"{'+' if pct >= 0 else ''}{pct:.2f}%"
        else:
            row["현재가(원)"] = "-"
            row["등락률"] = "-"
        rows.append(row)

    tbl = pd.DataFrame(rows).set_index("종목코드")

    def color_change(val):
        if val.startswith("+"):
            return "color: #ef5350"
        elif val.startswith("-"):
            return "color: #42a5f5"
        return ""

    st.dataframe(
        tbl.style.map(color_change, subset=["등락률"]),
        use_container_width=True,
        height=min(400, 40 + len(tbl) * 35),
    )
else:
    st.caption("현재가 조회 실패 (장 마감 후 또는 네트워크 오류)")

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
