"""
관심 종목 관리
- 개인 목록: st.session_state (세션 내 유지)
- 공유 목록: data/watchlist.json + GitHub API 동기화
"""
import json
import base64
import requests
from pathlib import Path

import streamlit as st

WATCHLIST_PATH = Path(__file__).parent.parent.parent / "data" / "watchlist.json"
GITHUB_REPO = "JHS-Code-design/hooni_stock"
GITHUB_FILE = "data/watchlist.json"


def load_shared() -> list[str]:
    if WATCHLIST_PATH.exists():
        try:
            data = json.loads(WATCHLIST_PATH.read_text(encoding="utf-8"))
            return data.get("shared", [])
        except Exception:
            pass
    return []


def save_shared(symbols: list[str]) -> bool:
    """GitHub API로 공유 watchlist 업데이트. 실패 시 False 반환."""
    token = st.secrets.get("GITHUB_TOKEN", "")
    if not token:
        return False

    content = json.dumps({"shared": symbols, "description": "공유 관심 종목 목록"},
                         ensure_ascii=False, indent=2)
    encoded = base64.b64encode(content.encode()).decode()

    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE}"

    # 현재 SHA 조회
    r = requests.get(url, headers=headers, timeout=10)
    sha = r.json().get("sha", "") if r.ok else ""

    # 파일 업데이트
    payload = {"message": "watchlist: update shared symbols", "content": encoded}
    if sha:
        payload["sha"] = sha

    resp = requests.put(url, headers=headers, json=payload, timeout=10)
    return resp.ok


def get_my_watchlist() -> list[str]:
    """session_state에서 개인 watchlist 반환"""
    if "my_watchlist" not in st.session_state:
        st.session_state.my_watchlist = []
    return st.session_state.my_watchlist


def add_to_my(symbol: str):
    wl = get_my_watchlist()
    if symbol and symbol not in wl:
        st.session_state.my_watchlist = wl + [symbol]


def remove_from_my(symbol: str):
    st.session_state.my_watchlist = [s for s in get_my_watchlist() if s != symbol]
