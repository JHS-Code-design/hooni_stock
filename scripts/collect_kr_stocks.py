"""
한국 주식 데이터 수집
- FDR StockListing('KRX') + 네이버 금융 업종 매핑
- 관심 종목 + 동일 업종 종목의 180일 OHLCV 수집
"""
import os
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path

import requests
import pandas as pd
import FinanceDataReader as fdr
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
META_DIR = DATA_DIR / "meta"
PRICES_DIR = DATA_DIR / "prices"

NAVER_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}


def fetch_naver_sectors() -> pd.DataFrame:
    """네이버 금융에서 업종별 종목 코드 매핑 테이블 반환"""
    log.info("네이버 금융 업종 분류 수집 중...")
    base = "https://finance.naver.com"
    r = requests.get(f"{base}/sise/sise_group.nhn?type=upjong", headers=NAVER_HEADERS, timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")
    links = soup.select("a[href*=sise_group_detail]")

    rows = []
    for link in links:
        sector_name = link.text.strip()
        no = link["href"].split("no=")[-1]
        detail_url = f"{base}/sise/sise_group_detail.naver?type=upjong&no={no}"
        try:
            dr = requests.get(detail_url, headers=NAVER_HEADERS, timeout=15)
            dsoup = BeautifulSoup(dr.text, "html.parser")
            for a in dsoup.select("a[href*='item/main']"):
                href = a["href"]
                code = href.split("code=")[-1] if "code=" in href else None
                if code and len(code) == 6:
                    rows.append({"Code": code, "Sector": sector_name})
            time.sleep(0.3)
        except Exception as e:
            log.warning(f"업종 {sector_name} 수집 실패: {e}")

    log.info(f"업종 매핑 완료: {len(rows)}개 종목")
    return pd.DataFrame(rows).drop_duplicates("Code")


def fetch_krx_listing() -> pd.DataFrame:
    """FDR + 네이버 업종 병합 후 저장"""
    df = fdr.StockListing('KRX')
    df = df.rename(columns={"Code": "Symbol"})

    sector_df = fetch_naver_sectors()
    sector_df = sector_df.rename(columns={"Code": "Symbol"})

    df = df.merge(sector_df, on="Symbol", how="left")
    df["Sector"] = df["Sector"].fillna("기타")

    META_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(META_DIR / "krx_listing.parquet", index=False)
    log.info(f"KRX 종목 {len(df)}개 저장 (Sector 포함) → {META_DIR}/krx_listing.parquet")
    return df


def get_related_tickers(symbols: list, listing: pd.DataFrame) -> list:
    sectors = set()
    for sym in symbols:
        row = listing[listing["Symbol"] == sym]
        if not row.empty:
            sectors.add(row.iloc[0]["Sector"])

    if not sectors:
        return symbols

    related = listing[listing["Sector"].isin(sectors)]["Symbol"].tolist()
    ordered = symbols + [s for s in related if s not in symbols]
    return ordered[:100]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def fetch_ohlcv(symbol: str, start: str, end: str) -> pd.DataFrame:
    df = fdr.DataReader(symbol, start, end)
    if df is None or df.empty:
        raise ValueError(f"{symbol}: 빈 데이터")
    return df


def collect_prices(symbols: list, today_str: str):
    end_date = datetime.strptime(today_str, "%Y-%m-%d")
    start_date = end_date - timedelta(days=270)
    out_dir = PRICES_DIR / today_str
    out_dir.mkdir(parents=True, exist_ok=True)

    success, failed = 0, 0
    for sym in symbols:
        try:
            df = fetch_ohlcv(sym, start_date.strftime("%Y-%m-%d"), today_str)
            df.to_parquet(out_dir / f"{sym}.parquet")
            success += 1
            log.info(f"[OK] {sym} {len(df)}행")
        except Exception as e:
            failed += 1
            log.warning(f"[SKIP] {sym}: {e}")
        time.sleep(0.5)

    log.info(f"수집 완료 — 성공:{success} 실패:{failed}")


def is_korean_market_open(date: datetime) -> bool:
    try:
        import exchange_calendars as ecals
        cal = ecals.get_calendar("XKRX")
        return cal.is_session(date.strftime("%Y-%m-%d"))
    except Exception:
        return date.weekday() < 5


if __name__ == "__main__":
    today = datetime.now()

    if not is_korean_market_open(today):
        log.info(f"{today.date()} 는 한국 장 비영업일 — 수집 건너뜀")
        exit(0)

    today_str = today.strftime("%Y-%m-%d")

    listing = fetch_krx_listing()

    watch_raw = os.environ.get("WATCH_SYMBOLS", "005930,000660")
    watch_symbols = [s.strip() for s in watch_raw.split(",")]

    all_symbols = get_related_tickers(watch_symbols, listing)
    log.info(f"수집 대상 {len(all_symbols)}개 종목")

    collect_prices(all_symbols, today_str)
