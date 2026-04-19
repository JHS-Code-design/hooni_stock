"""
주가 예측 엔진 (복합) v2
- 선형 회귀 추세 + 이동평균 기반 예측
- 미국 섹터 ETF/대표주 연동 (베타·상관계수)
- ATR14 신뢰 구간
- sector 파라미터 지원
"""
_VERSION = "2.0"
import numpy as np
import pandas as pd
from scipy import stats
from datetime import timedelta


# ── 데이터 로딩 ──────────────────────────────────────────────────────────

def _load_price_series(symbol: str, days: int = 180) -> pd.Series:
    """로컬 parquet → 부족하면 yfinance fallback"""
    from pathlib import Path
    from datetime import datetime, timedelta
    import yfinance as yf

    data_dir = Path(__file__).parent.parent / "data" / "prices"
    if data_dir.exists():
        dates = sorted([d.name for d in data_dir.iterdir() if d.is_dir()], reverse=True)
        if dates:
            p = data_dir / dates[0] / f"{symbol}.parquet"
            if p.exists():
                df = pd.read_parquet(p)
                col = "Close" if "Close" in df.columns else df.columns[-1]
                local = df[col].dropna()
                if len(local) >= days:
                    return local.tail(days)
                # 로컬 데이터 부족 → yfinance로 보충

    start = (datetime.today() - timedelta(days=days + 30)).strftime("%Y-%m-%d")
    for suffix in (".KS", ".KQ"):
        hist = yf.Ticker(f"{symbol}{suffix}").history(start=start)
        if not hist.empty:
            return hist["Close"].dropna().tail(days)
    return pd.Series(dtype=float)


def fetch_us_basket(tickers: list[str], days: int = 120) -> pd.DataFrame:
    """미국 ETF/주식 종가 DataFrame 반환 (열=ticker)"""
    import yfinance as yf

    if not tickers:
        return pd.DataFrame()
    try:
        raw = yf.download(tickers, period=f"{days}d", progress=False, threads=False)
        if raw.empty:
            return pd.DataFrame()
        if isinstance(raw.columns, pd.MultiIndex):
            close = raw["Close"]
        else:
            close = raw[["Close"]] if "Close" in raw.columns else raw
        close = close.dropna(how="all")
        return close
    except Exception:
        return pd.DataFrame()


# ── 기술적 지표 ──────────────────────────────────────────────────────────

def compute_atr(series: pd.Series, window: int = 14) -> float:
    """ATR14 근사 (Close 전용 — High/Low 없을 때)"""
    diff = series.diff().abs()
    return float(diff.rolling(window, min_periods=1).mean().iloc[-1])


def compute_beta_rho(
    kr_series: pd.Series, us_df: pd.DataFrame
) -> dict:
    """
    미국 바스켓 대비 한국 종목의 베타·상관계수 계산.
    미국이 하루 먼저 마감 → us_returns.shift(1) 적용.
    """
    if us_df.empty:
        return {"beta": 0.0, "rho": 0.0, "basket_return_1d": 0.0}

    kr_ret = kr_series.pct_change().dropna()

    basket_avg = us_df.pct_change().shift(1).mean(axis=1).dropna()

    common = kr_ret.index.intersection(basket_avg.index)
    if len(common) < 10:
        return {"beta": 0.0, "rho": 0.0, "basket_return_1d": 0.0}

    x = basket_avg.loc[common].values
    y = kr_ret.loc[common].values

    slope, intercept, r, p, se = stats.linregress(x, y)

    # 최근 1영업일 미국 바스켓 수익률 (오늘 한국 장에 반영될 값)
    basket_return_1d = float(basket_avg.iloc[-1]) if not basket_avg.empty else 0.0

    return {
        "beta": float(slope),
        "rho": float(r),
        "basket_return_1d": basket_return_1d,
    }


# ── 예측 핵심 ────────────────────────────────────────────────────────────

def linear_forecast(series: pd.Series, forecast_days: int) -> dict:
    """선형 회귀 추세선 + ATR 기반 신뢰 구간"""
    x = np.arange(len(series))
    y = series.values.astype(float)

    slope, intercept, r, p, se = stats.linregress(x, y)

    y_pred_in = slope * x + intercept
    residuals = y - y_pred_in
    std_res = np.std(residuals)

    x_future = np.arange(len(series), len(series) + forecast_days)
    future_dates = pd.date_range(
        start=series.index[-1] + timedelta(days=1),
        periods=forecast_days,
        freq="B",
    )

    y_future = slope * x_future + intercept
    upper = y_future + 1.96 * std_res
    lower = y_future - 1.96 * std_res

    return {
        "slope": slope,
        "r_squared": r ** 2,
        "trend": "상승" if slope > 0 else "하락",
        "in_sample": pd.Series(y_pred_in, index=series.index),
        "forecast": pd.Series(y_future, index=future_dates),
        "upper": pd.Series(upper, index=future_dates),
        "lower": pd.Series(lower, index=future_dates),
        "std": std_res,
    }


def ma_forecast(series: pd.Series, forecast_days: int, window: int = 20) -> pd.Series:
    """이동평균 수평 연장"""
    ma = series.rolling(window, min_periods=1).mean()
    last_ma = float(ma.iloc[-1])
    future_dates = pd.date_range(
        start=series.index[-1] + timedelta(days=1),
        periods=forecast_days,
        freq="B",
    )
    return pd.Series(last_ma, index=future_dates)


# ── 복합 조정 ────────────────────────────────────────────────────────────

def _us_adjustment(beta: float, rho: float, basket_return_1d: float) -> float:
    """
    미국 섹터 연동 조정값 (일별 수익률 기준).
    rho 신뢰도 가중, 최대 ±5% 제한.
    """
    raw = beta * basket_return_1d * abs(rho)
    return float(np.clip(raw, -0.05, 0.05))


# ── 공개 API ─────────────────────────────────────────────────────────────

def run_forecast(
    symbol: str,
    history_days: int = 90,
    forecast_days: int = 30,
    sector: str = "",
) -> dict:
    """
    복합 예측 실행.

    Returns:
        {
          "symbol": str,
          "series": pd.Series,
          "linear": dict,
          "ma20": pd.Series,
          "ma60": pd.Series,
          "current_price": float,
          "target_price": float,       # 선형 기준
          "target_combined": float,    # 복합 조정 후
          "change_pct": float,
          "change_pct_combined": float,
          "us": dict,                  # beta, rho, basket_return_1d, tickers
          "atr": float,
        }
    """
    from analysis.sector_map import get_basket

    series = _load_price_series(symbol, history_days)
    if series.empty or len(series) < 10:
        return {}

    linear = linear_forecast(series, forecast_days)
    ma20 = ma_forecast(series, forecast_days, window=20)
    ma60 = ma_forecast(series, forecast_days, window=min(60, len(series)))

    current = float(series.iloc[-1])
    target = float(linear["forecast"].iloc[-1])
    change_pct = (target - current) / current * 100

    # 미국 섹터 연동 (실패해도 선형 예측으로 fallback)
    try:
        sector_str = str(sector).strip() if sector and str(sector) != "nan" else ""
        basket_tickers = get_basket(sector_str) if sector_str else []
        us_df = fetch_us_basket(basket_tickers, days=max(history_days, 60)) if basket_tickers else pd.DataFrame()
        br = compute_beta_rho(series, us_df)
        adj = _us_adjustment(br["beta"], br["rho"], br["basket_return_1d"])
        decay = 0.5
        cumulative_adj = float(np.clip(
            adj * (1 - decay ** forecast_days) / (1 - decay + 1e-9),
            -0.20, 0.20,
        ))
    except Exception:
        basket_tickers = []
        br = {"beta": 0.0, "rho": 0.0, "basket_return_1d": 0.0}
        cumulative_adj = 0.0

    target_combined = target * (1 + cumulative_adj)
    change_pct_combined = (target_combined - current) / current * 100

    atr = compute_atr(series)

    return {
        "symbol": symbol,
        "series": series,
        "linear": linear,
        "ma20": ma20,
        "ma60": ma60,
        "current_price": current,
        "target_price": target,
        "target_combined": float(target_combined),
        "change_pct": change_pct,
        "change_pct_combined": float(change_pct_combined),
        "us": {
            **br,
            "tickers": basket_tickers,
            "adj_pct": float(adj * 100),
        },
        "atr": atr,
    }
