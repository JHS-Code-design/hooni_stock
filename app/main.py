import streamlit as st
from app.utils.data_loader import get_latest_data_date

st.set_page_config(
    page_title="Hooni Stock",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.sidebar.title("📈 Hooni Stock")
st.sidebar.caption(f"데이터 기준일: {get_latest_data_date()}")

st.title("주식 분석 대시보드")
st.info("좌측 메뉴에서 페이지를 선택하세요.\n- 🇰🇷 한국 시장\n- 🇺🇸 미국 시장")
