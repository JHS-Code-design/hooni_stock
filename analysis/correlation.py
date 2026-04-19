"""
연관 종목 탐색 엔진
- 동일 Sector 필터 → 60일 수익률 상관계수 0.7 이상 추출
"""
from pathlib import Path
import pandas as pd
import numpy as np

DATA_DIR = Path(__file__).parent.parent / "data"
MIN_TRADING_DAYS = 20
CORR_THRESHOLD = 0.7
MAX_RELATED = 50


def load_listing() -> pd.DataFrame:
    p = DATA_DIR / "meta" / "krx_listing.parquet"
    if not p.exists():
        raise FileNotFoundError("krx_listing.parquet 없음 — 먼저 collect_kr_stocks.py 실행")
    return pd.read_parquet(p)


def fetch_prices_online(symbols: list[str], days: int = 90) -> pd.DataFrame:
    """FDR로 실시간 주가 조회 (로컬 데이터 없을 때 fallback)"""
    import FinanceDataReader as fdr
    from datetime import datetime, timedelta
    import time

    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    frames = {}
    for sym in symbols[:30]:  # 최대 30개 제한
        try:
            df = fdr.DataReader(sym, start, end)
            if df is not None and not df.empty:
                col = "Close" if "Close" in df.columns else df.columns[-1]
                frames[sym] = df[col]
            time.sleep(0.3)
        except Exception:
            pass
    return pd.DataFrame(frames) if frames else pd.DataFrame()


def load_latest_prices(symbols: list[str]) -> pd.DataFrame:
    """가장 최근 날짜 디렉토리에서 종목 OHLCV 로드 → 없으면 FDR 실시간 조회"""
    prices_dir = DATA_DIR / "prices"

    local_syms = []
    if prices_dir.exists():
        dates = sorted([d.name for d in prices_dir.iterdir() if d.is_dir()], reverse=True)
        if dates:
            latest = prices_dir / dates[0]
            local_syms = [f.stem for f in latest.glob("*.parquet")]

    # 로컬에 있는 종목
    frames = {}
    if local_syms:
        dates = sorted([d.name for d in prices_dir.iterdir() if d.is_dir()], reverse=True)
        latest = prices_dir / dates[0]
        for sym in symbols:
            if sym in local_syms:
                p = latest / f"{sym}.parquet"
                df = pd.read_parquet(p)
                col = "Close" if "Close" in df.columns else df.columns[-1]
                frames[sym] = df[col]

    # 로컬에 없는 종목 → 온라인 조회
    missing = [s for s in symbols if s not in frames]
    if missing:
        online = fetch_prices_online(missing)
        for col in online.columns:
            frames[col] = online[col]

    if not frames:
        return pd.DataFrame()
    return pd.DataFrame(frames)


def find_related(watch_symbols: list[str]) -> dict:
    """
    관심 종목 → 연관 종목 탐색

    Returns:
        {
          "nodes": [{"id": "005930", "name": "삼성전자", "sector": "반도체", "corr": 1.0}, ...],
          "edges": [{"source": "005930", "target": "000660", "weight": 0.85}, ...],
          "corr_matrix": pd.DataFrame,
        }
    """
    listing = load_listing()

    # 종목명 → Symbol 매핑 지원
    name_to_sym = {}
    if 'Name' in listing.columns:
        name_to_sym = dict(zip(listing['Name'], listing['Symbol']))

    resolved = []
    for s in watch_symbols:
        if s in listing['Symbol'].values:
            resolved.append(s)
        elif s in name_to_sym:
            resolved.append(name_to_sym[s])

    if not resolved:
        return {"nodes": [], "edges": [], "corr_matrix": pd.DataFrame()}

    # 동일 섹터 종목 수집
    sectors = set()
    for sym in resolved:
        row = listing[listing['Symbol'] == sym]
        if not row.empty:
            sectors.add(str(row.iloc[0]['Sector']))

    candidate_mask = listing['Sector'].isin(sectors)
    candidates = listing[candidate_mask]['Symbol'].tolist()
    all_syms = list(dict.fromkeys(resolved + candidates))[:100]

    # 가격 로드
    prices = load_latest_prices(all_syms)
    if prices.empty:
        return {"nodes": [], "edges": [], "corr_matrix": pd.DataFrame()}

    # 60일 수익률 계산
    returns = prices.pct_change().dropna()
    # 거래일 최소 기준 미달 종목 제거
    valid = returns.columns[returns.count() >= MIN_TRADING_DAYS].tolist()
    returns = returns[valid]

    # 최근 60 거래일만 사용
    returns = returns.tail(60)

    corr = returns.corr()

    # 노드
    sym_to_name = {}
    sym_to_sector = {}
    if 'Name' in listing.columns:
        sym_to_name = dict(zip(listing['Symbol'], listing['Name']))
    if 'Sector' in listing.columns:
        sym_to_sector = dict(zip(listing['Symbol'], listing['Sector']))

    nodes = []
    for sym in corr.columns:
        nodes.append({
            "id": sym,
            "name": sym_to_name.get(sym, sym),
            "sector": str(sym_to_sector.get(sym, "기타")),
            "is_watch": sym in resolved,
        })

    # 엣지 (관심 종목 기준 상관계수 0.7 이상)
    edges = []
    seen = set()
    for w in resolved:
        if w not in corr.columns:
            continue
        for other in corr.columns:
            if other == w:
                continue
            pair = tuple(sorted([w, other]))
            if pair in seen:
                continue
            val = corr.loc[w, other]
            if pd.notna(val) and abs(val) >= CORR_THRESHOLD:
                edges.append({"source": w, "target": other, "weight": round(float(val), 3)})
                seen.add(pair)

    # 연관 종목 상위 MAX_RELATED 개만
    edges = sorted(edges, key=lambda x: abs(x["weight"]), reverse=True)[:MAX_RELATED]
    edge_syms = {e["source"] for e in edges} | {e["target"] for e in edges}
    nodes = [n for n in nodes if n["id"] in edge_syms or n["id"] in resolved]

    return {"nodes": nodes, "edges": edges, "corr_matrix": corr}
