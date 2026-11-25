"""
한국 주식 데이터 수집
- FDR StockListing('KRX') + 네이버 증권 업종 매핑 (m.stock.naver.com API)
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
from tenacity import retry, stop_after_attempt, wait_exponential

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
META_DIR = DATA_DIR / "meta"
PRICES_DIR = DATA_DIR / "prices"

NAVER_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}


NAVER_INDUSTRY_API = "https://m.stock.naver.com/api/stocks/industry"
SECTOR_COLUMNS = ["Code", "Sector"]


def _get_json(url: str, params: dict) -> dict:
    r = requests.get(url, params=params, headers=NAVER_HEADERS, timeout=15)
    r.raise_for_status()
    return r.json()


def fetch_naver_sectors() -> pd.DataFrame:
    """네이버 증권 업종별 종목 코드 매핑 테이블 반환 (열: Code, Sector).

    2026-11 네이버가 finance.naver.com/sise/sise_group* 페이지를 stock.naver.com
    (클라이언트 렌더링)으로 리다이렉트해 HTML 파싱이 0건이 됐다.
    그래서 m.stock.naver.com 의 JSON API를 쓴다. 실패해도 빈 표를 돌려준다.
    """
    log.info("네이버 증권 업종 분류 수집 중...")
    try:
        groups = _get_json(NAVER_INDUSTRY_API, {"page": 1, "pageSize": 100}).get("groups") or []
    except Exception as e:
        log.warning(f"업종 목록 수집 실패: {e}")
        groups = []

    rows = []
    for g in groups:
        no, sector_name = g.get("no"), (g.get("name") or "").strip()
        if no is None or not sector_name:
            continue
        page = 1
        try:
            while True:
                data = _get_json(f"{NAVER_INDUSTRY_API}/{no}", {"page": page, "pageSize": 100})
                stocks = data.get("stocks") or []
                for st in stocks:
                    code = str(st.get("itemCode") or "")
                    if len(code) == 6:
                        rows.append({"Code": code, "Sector": sector_name})
                if not stocks or page * 100 >= int(data.get("totalCount") or 0):
                    break
                page += 1
                time.sleep(0.2)
        except Exception as e:
            log.warning(f"업종 {sector_name} 수집 실패: {e}")
        time.sleep(0.2)

    log.info(f"업종 매핑 완료: {len(rows)}개 종목")
    if not rows:
        log.warning("업종 데이터가 비었습니다 — 출처 응답/형식을 확인하세요.")
    return pd.DataFrame(rows, columns=SECTOR_COLUMNS).drop_duplicates("Code")


def fetch_krx_listing() -> pd.DataFrame:
    """FDR + 네이버 업종 병합 후 저장"""
    df = fdr.StockListing('KRX')
    df = df.rename(columns={"Code": "Symbol"})

    try:
        sector_df = fetch_naver_sectors()
    except Exception as e:
        log.warning(f"업종 수집 중 예외: {e}")
        sector_df = pd.DataFrame(columns=SECTOR_COLUMNS)
    sector_df = sector_df.rename(columns={"Code": "Symbol"})

    if sector_df.empty or not {"Symbol", "Sector"} <= set(sector_df.columns):
        log.warning("업종 데이터가 없어 Sector를 빈 값으로 둡니다 (관심 종목만 수집).")
        df["Sector"] = pd.NA
    else:
        df = df.merge(sector_df[["Symbol", "Sector"]], on="Symbol", how="left")
        df["Sector"] = df["Sector"].fillna("기타")

    META_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(META_DIR / "krx_listing.parquet", index=False)
    log.info(f"KRX 종목 {len(df)}개 저장 (Sector 포함) → {META_DIR}/krx_listing.parquet")
    return df


def get_related_tickers(symbols: list, listing: pd.DataFrame) -> list:
    sectors = set()
    for sym in symbols:
        row = listing[listing["Symbol"] == sym]
        if not row.empty and pd.notna(row.iloc[0]["Sector"]):
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


def last_trading_day() -> str:
    """가장 최근 거래일 반환 (오늘 포함)"""
    try:
        import exchange_calendars as ecals
        cal = ecals.get_calendar("XKRX")
        today = datetime.now()
        for i in range(7):
            d = today - timedelta(days=i)
            if cal.is_session(d.strftime("%Y-%m-%d")):
                return d.strftime("%Y-%m-%d")
    except Exception:
        pass
    # fallback: 최근 평일
    d = datetime.now()
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.strftime("%Y-%m-%d")


if __name__ == "__main__":
    import os as _os
    force = _os.environ.get("FORCE_COLLECT", "").lower() in ("1", "true", "yes")
    today = datetime.now()

    if not force and not is_korean_market_open(today):
        log.info(f"{today.date()} 는 한국 장 비영업일 — 수집 건너뜀 (강제 실행: FORCE_COLLECT=1)")
        exit(0)

    today_str = last_trading_day() if not is_korean_market_open(today) else today.strftime("%Y-%m-%d")
    if force:
        log.info(f"강제 수집 모드 — 기준일: {today_str}")

    listing = fetch_krx_listing()

    watch_raw = os.environ.get("WATCH_SYMBOLS", "005930,000660")
    watch_symbols = [s.strip() for s in watch_raw.split(",")]

    all_symbols = get_related_tickers(watch_symbols, listing)
    log.info(f"수집 대상 {len(all_symbols)}개 종목")

    collect_prices(all_symbols, today_str)
