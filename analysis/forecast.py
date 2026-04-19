"""
주가 예측 엔진
- 선형 회귀 추세 + 이동평균 기반 예측
- scipy.stats.linregress 사용 (외부 ML 라이브러리 불필요)
"""
import numpy as np
import pandas as pd
from scipy import stats
from datetime import timedelta


def _load_price_series(symbol: str, days: int = 180) -> pd.Series:
    """로컬 parquet → 없으면 yfinance fallback"""
    from pathlib import Path
    import yfinance as yf

    data_dir = Path(__file__).parent.parent / "data" / "prices"
    if data_dir.exists():
        dates = sorted([d.name for d in data_dir.iterdir() if d.is_dir()], reverse=True)
        if dates:
            p = data_dir / dates[0] / f"{symbol}.parquet"
            if p.exists():
                df = pd.read_parquet(p)
                col = "Close" if "Close" in df.columns else df.columns[-1]
                return df[col].dropna().tail(days)

    # fallback: yfinance
    ticker = yf.Ticker(f"{symbol}.KS")
    hist = ticker.history(period=f"{days}d")
    if hist.empty:
        ticker = yf.Ticker(f"{symbol}.KQ")
        hist = ticker.history(period=f"{days}d")
    return hist["Close"].dropna() if not hist.empty else pd.Series(dtype=float)


def linear_forecast(series: pd.Series, forecast_days: int) -> dict:
    """선형 회귀 추세선 + 예측"""
    x = np.arange(len(series))
    y = series.values.astype(float)

    slope, intercept, r, p, se = stats.linregress(x, y)

    # 신뢰 구간 (residual 표준편차 기반)
    y_pred_in = slope * x + intercept
    residuals = y - y_pred_in
    std_res = np.std(residuals)

    # 미래 x
    x_future = np.arange(len(series), len(series) + forecast_days)
    future_dates = pd.date_range(
        start=series.index[-1] + timedelta(days=1),
        periods=forecast_days,
        freq="B",  # 영업일
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
    """이동평균 기반 예측 (마지막 MA값을 수평 연장)"""
    ma = series.rolling(window, min_periods=1).mean()
    last_ma = float(ma.iloc[-1])
    future_dates = pd.date_range(
        start=series.index[-1] + timedelta(days=1),
        periods=forecast_days,
        freq="B",
    )
    return pd.Series(last_ma, index=future_dates)


def run_forecast(symbol: str, history_days: int = 90, forecast_days: int = 30) -> dict:
    """
    Returns:
        {
          "symbol": str,
          "series": pd.Series,        # 실제 가격
          "linear": dict,             # 선형 회귀 결과
          "ma20": pd.Series,          # MA20 예측
          "ma60": pd.Series,          # MA60 예측
          "current_price": float,
          "target_price": float,      # 선형 회귀 기준 예측 종가
          "change_pct": float,        # 현재→예측 등락률
        }
    """
    series = _load_price_series(symbol, history_days)
    if series.empty or len(series) < 10:
        return {}

    linear = linear_forecast(series, forecast_days)
    ma20 = ma_forecast(series, forecast_days, window=20)
    ma60 = ma_forecast(series, forecast_days, window=min(60, len(series)))

    current = float(series.iloc[-1])
    target = float(linear["forecast"].iloc[-1])
    change_pct = (target - current) / current * 100

    return {
        "symbol": symbol,
        "series": series,
        "linear": linear,
        "ma20": ma20,
        "ma60": ma60,
        "current_price": current,
        "target_price": target,
        "change_pct": change_pct,
    }
