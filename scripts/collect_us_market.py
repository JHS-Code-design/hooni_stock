"""
미국 시장 데이터 수집
- yfinance: S&P500, NASDAQ, 환율, VIX
- CNN Fear & Greed Index (fallback: VIX 기반 계산)
"""
import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data" / "us_market"
TICKERS = ["^GSPC", "^IXIC", "KRW=X", "^VIX"]

CNN_FNG_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}


def fetch_us_prices(days: int = 180) -> pd.DataFrame:
    end = datetime.now()
    start = end - timedelta(days=days)
    df = yf.download(
        TICKERS,
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        threads=False,
        progress=False,
    )
    close = df["Close"] if "Close" in df.columns else df.xs("Close", axis=1, level=0)
    close = close.rename(columns={"^GSPC": "SP500", "^IXIC": "NASDAQ", "KRW=X": "KRW", "^VIX": "VIX"})
    return close.dropna(how="all")


def fetch_fear_greed() -> dict:
    """CNN Fear & Greed Index. 실패 시 VIX 기반 fallback 반환"""
    try:
        resp = requests.get(CNN_FNG_URL, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        score = data["fear_and_greed"]["score"]
        rating = data["fear_and_greed"]["rating"]
        log.info(f"F&G: {score:.1f} ({rating})")
        return {"score": round(score, 1), "rating": rating, "source": "CNN"}
    except Exception as e:
        log.warning(f"CNN F&G 실패: {e} → VIX fallback 사용")
        return {"score": None, "rating": None, "source": "VIX_FALLBACK"}


def vix_to_fng(vix: float) -> dict:
    """VIX → 0-100 공포탐욕 추정값 변환 (역방향 정규화)"""
    # VIX 10=탐욕(80), 20=중립(50), 40=공포(10)
    score = max(0, min(100, 100 - (vix - 10) * 2.5))
    if score >= 75:
        rating = "Extreme Greed"
    elif score >= 55:
        rating = "Greed"
    elif score >= 45:
        rating = "Neutral"
    elif score >= 25:
        rating = "Fear"
    else:
        rating = "Extreme Fear"
    return {"score": round(score, 1), "rating": rating, "source": "VIX_FALLBACK"}


if __name__ == "__main__":
    today_str = datetime.now().strftime("%Y-%m-%d")
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 가격 수집
    prices = fetch_us_prices()
    log.info(f"미국 지수 {len(prices)}일치 수집")

    # F&G 수집
    fng = fetch_fear_greed()
    if fng["score"] is None and not prices.empty:
        latest_vix = float(prices["VIX"].dropna().iloc[-1])
        fng = vix_to_fng(latest_vix)
        log.info(f"VIX fallback F&G: {fng['score']} ({fng['rating']})")

    # 저장
    prices.to_parquet(DATA_DIR / f"{today_str}.parquet")

    fng_df = pd.DataFrame([{**fng, "date": today_str}])
    fng_df.to_parquet(DATA_DIR / f"{today_str}_fng.parquet", index=False)

    log.info(f"미국 시장 데이터 저장 완료 → {DATA_DIR}")
