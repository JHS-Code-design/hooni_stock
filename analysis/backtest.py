"""
Walk-forward 백테스트 엔진

방식:
  과거 데이터에서 여러 cutoff 시점을 선택 →
  각 시점에서 예측 실행 → 실제값과 비교
  (선형 / 복합(US조정) / MA20 세 가지 동시 검증)
"""
import numpy as np
import pandas as pd
from datetime import timedelta

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from analysis.forecast import linear_forecast, ma_forecast, fetch_us_basket, compute_beta_rho, _us_adjustment
from analysis.sector_map import get_basket


def _mape(actual: float, predicted: float) -> float:
    if actual == 0:
        return np.nan
    return abs(actual - predicted) / actual * 100


def run_backtest(
    series: pd.Series,
    sector: str = "",
    history_days: int = 90,
    forecast_days: int = 30,
    n_tests: int = 5,
) -> dict:
    """
    Walk-forward 백테스트.

    Parameters
    ----------
    series       : 전체 가격 시계열 (최소 history_days + forecast_days * n_tests 행 필요)
    sector       : KRX 업종명 (미국 연동용)
    history_days : 각 시점에서 사용할 과거 일수
    forecast_days: 예측 기간
    n_tests      : 테스트 윈도우 수

    Returns
    -------
    {
      "linear":   {"mape": float, "direction_acc": float, "mae": float, "tests": list},
      "combined": {"mape": float, "direction_acc": float, "mae": float, "tests": list},
      "ma20":     {"mape": float, "direction_acc": float, "mae": float, "tests": list},
      "n_valid":  int,   # 실제로 검증된 윈도우 수
    }
    """
    min_len = history_days + forecast_days + 1
    if len(series) < min_len:
        return {}

    # 미국 바스켓 (전체 기간 한 번만 가져옴)
    basket_tickers = get_basket(sector) if sector else []
    us_df = fetch_us_basket(basket_tickers, days=len(series) + 30) if basket_tickers else pd.DataFrame()

    # cutoff 시점 선택: 뒤에서부터 균등하게
    # 마지막 cutoff = 전체 끝 - forecast_days (실제값 존재)
    max_idx = len(series) - forecast_days - 1
    min_idx = history_days
    if max_idx <= min_idx:
        return {}

    step = max(1, (max_idx - min_idx) // n_tests)
    cutoff_indices = list(range(min_idx, max_idx, step))[:n_tests]

    linear_tests, combined_tests, ma20_tests = [], [], []

    for cut_i in cutoff_indices:
        train = series.iloc[:cut_i]
        # 실제 forecast_days 영업일 후 가격 (가능하면 정확히, 아니면 가장 가까운)
        future_slice = series.iloc[cut_i: cut_i + forecast_days * 2]  # 여유분
        if future_slice.empty:
            continue
        # forecast_days 영업일 후 실제값 (영업일 기준으로 최대한 맞춤)
        biz_future = future_slice.resample("B").last().dropna()
        if len(biz_future) < forecast_days:
            actual_price = float(biz_future.iloc[-1])
        else:
            actual_price = float(biz_future.iloc[forecast_days - 1])

        current_price = float(train.iloc[-1])
        actual_direction = actual_price >= current_price  # True=상승

        # ── 선형 예측 ────────────────────────────────────────────────────
        lin = linear_forecast(train, forecast_days)
        pred_linear = float(lin["forecast"].iloc[-1])

        linear_tests.append({
            "cutoff_date": str(train.index[-1].date()),
            "predicted": round(pred_linear),
            "actual": round(actual_price),
            "mape": _mape(actual_price, pred_linear),
            "mae": abs(actual_price - pred_linear),
            "direction_correct": (pred_linear >= current_price) == actual_direction,
        })

        # ── 복합 예측 (선형 + US 조정) ───────────────────────────────────
        if not us_df.empty:
            # cutoff 이전 데이터만 사용
            us_cut = us_df[us_df.index <= train.index[-1]]
            br = compute_beta_rho(train, us_cut)
        else:
            br = {"beta": 0.0, "rho": 0.0, "basket_return_1d": 0.0}

        adj = _us_adjustment(br["beta"], br["rho"], br["basket_return_1d"])
        decay = 0.5
        cum_adj = adj * (1 - decay ** forecast_days) / (1 - decay + 1e-9)
        cum_adj = float(np.clip(cum_adj, -0.20, 0.20))
        pred_combined = pred_linear * (1 + cum_adj)

        combined_tests.append({
            "cutoff_date": str(train.index[-1].date()),
            "predicted": round(pred_combined),
            "actual": round(actual_price),
            "mape": _mape(actual_price, pred_combined),
            "mae": abs(actual_price - pred_combined),
            "direction_correct": (pred_combined >= current_price) == actual_direction,
        })

        # ── MA20 예측 ─────────────────────────────────────────────────────
        ma = ma_forecast(train, forecast_days, window=20)
        pred_ma = float(ma.iloc[-1])

        ma20_tests.append({
            "cutoff_date": str(train.index[-1].date()),
            "predicted": round(pred_ma),
            "actual": round(actual_price),
            "mape": _mape(actual_price, pred_ma),
            "mae": abs(actual_price - pred_ma),
            "direction_correct": (pred_ma >= current_price) == actual_direction,
        })

    def _summarize(tests: list) -> dict:
        if not tests:
            return {"mape": np.nan, "direction_acc": np.nan, "mae": np.nan, "tests": []}
        mapes = [t["mape"] for t in tests if not np.isnan(t["mape"])]
        maes  = [t["mae"]  for t in tests]
        dirs  = [t["direction_correct"] for t in tests]
        return {
            "mape":          round(float(np.mean(mapes)), 2) if mapes else np.nan,
            "direction_acc": round(float(np.mean(dirs)) * 100, 1),
            "mae":           round(float(np.mean(maes))),
            "tests":         tests,
        }

    return {
        "linear":   _summarize(linear_tests),
        "combined": _summarize(combined_tests),
        "ma20":     _summarize(ma20_tests),
        "n_valid":  len(linear_tests),
        "forecast_days": forecast_days,
    }
