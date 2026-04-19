"""
관심 종목 관리 (단일 목록)
- 저장소: data/watchlist.json
- 원격 동기화: GitHub API (GITHUB_TOKEN secrets 설정 시)
"""
import json
import base64
import requests
from pathlib import Path

import streamlit as st

WATCHLIST_PATH = Path(__file__).parent.parent.parent / "data" / "watchlist.json"
GITHUB_REPO = "JHS-Code-design/hooni_stock"
GITHUB_FILE = "data/watchlist.json"


def load_watchlist() -> list[str]:
    """관심 종목 목록 반환"""
    if "watchlist_override" in st.session_state:
        return st.session_state["watchlist_override"]
    if WATCHLIST_PATH.exists():
        try:
            data = json.loads(WATCHLIST_PATH.read_text(encoding="utf-8"))
            return data.get("shared", [])
        except Exception:
            pass
    return []


# 하위 호환 alias
def load_shared() -> list[str]:
    return load_watchlist()


def save_watchlist(symbols: list[str]) -> bool:
    """GitHub API로 watchlist 업데이트. 실패 시 session_state에 임시 저장."""
    token = ""
    try:
        token = st.secrets.get("GITHUB_TOKEN", "")
    except Exception:
        pass

    if token:
        content = json.dumps(
            {"shared": symbols, "description": "관심 종목 목록"},
            ensure_ascii=False, indent=2,
        )
        encoded = base64.b64encode(content.encode()).decode()
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }
        url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_FILE}"
        r = requests.get(url, headers=headers, timeout=10)
        sha = r.json().get("sha", "") if r.ok else ""
        payload = {"message": "watchlist: update", "content": encoded}
        if sha:
            payload["sha"] = sha
        resp = requests.put(url, headers=headers, json=payload, timeout=10)
        if resp.ok:
            st.session_state.pop("watchlist_override", None)
            return True

    # GitHub 동기화 실패 → 세션에 임시 보관
    st.session_state["watchlist_override"] = symbols
    return False


# 하위 호환 alias
def save_shared(symbols: list[str]) -> bool:
    return save_watchlist(symbols)


def add_to_watchlist(symbol: str):
    wl = load_watchlist()
    if symbol and symbol not in wl:
        save_watchlist(wl + [symbol])


def remove_from_watchlist(symbol: str):
    wl = load_watchlist()
    save_watchlist([s for s in wl if s != symbol])


# ── 하위 호환 (개인 목록 → 통합 목록으로 리디렉션) ──────────────────────
def get_my_watchlist() -> list[str]:
    return load_watchlist()

def add_to_my(symbol: str):
    add_to_watchlist(symbol)

def remove_from_my(symbol: str):
    remove_from_watchlist(symbol)
