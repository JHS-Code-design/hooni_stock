from pathlib import Path
import pandas as pd
import streamlit as st

DATA_DIR = Path(__file__).parent.parent.parent / "data"


@st.cache_data(ttl=3600)
def load_krx_listing() -> pd.DataFrame:
    p = DATA_DIR / "meta" / "krx_listing.parquet"
    if not p.exists():
        return pd.DataFrame()
    return pd.read_parquet(p)


@st.cache_data(ttl=3600)
def load_us_market_history(days: int = 180) -> pd.DataFrame:
    us_dir = DATA_DIR / "us_market"
    if not us_dir.exists():
        return pd.DataFrame()
    files = sorted(us_dir.glob("????-??-??.parquet"), reverse=True)[:days]
    if not files:
        return pd.DataFrame()
    frames = [pd.read_parquet(f) for f in reversed(files)]
    return pd.concat(frames).sort_index()


@st.cache_data(ttl=3600)
def load_latest_fng() -> dict:
    us_dir = DATA_DIR / "us_market"
    if not us_dir.exists():
        return {}
    files = sorted(us_dir.glob("????-??-??_fng.parquet"), reverse=True)
    if not files:
        return {}
    df = pd.read_parquet(files[0])
    return df.iloc[0].to_dict() if not df.empty else {}


@st.cache_data(ttl=3600)
def load_latest_prices_df(symbols: list) -> "pd.DataFrame":
    import pandas as pd
    prices_dir = DATA_DIR / "prices"
    if not prices_dir.exists():
        return pd.DataFrame()
    dates = sorted([d.name for d in prices_dir.iterdir() if d.is_dir()], reverse=True)
    if not dates:
        return pd.DataFrame()
    latest = prices_dir / dates[0]
    frames = {}
    for sym in symbols:
        p = latest / f"{sym}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            col = "Close" if "Close" in df.columns else df.columns[-1]
            frames[sym] = df[col]
    return pd.DataFrame(frames) if frames else pd.DataFrame()


def get_latest_data_date() -> str:
    prices_dir = DATA_DIR / "prices"
    if not prices_dir.exists():
        return "데이터 없음"
    dates = sorted([d.name for d in prices_dir.iterdir() if d.is_dir()], reverse=True)
    return dates[0] if dates else "데이터 없음"
