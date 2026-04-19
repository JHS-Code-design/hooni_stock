"""
KRX 업종 → 미국 ETF/대표주 바스켓 매핑
"""

SECTOR_US_BASKET: dict[str, list[str]] = {
    "우주항공과국방": ["ITA", "XAR", "LMT", "RTX", "NOC", "GD"],
    "반도체": ["SOXX", "SMH", "NVDA", "AMD", "INTC", "QCOM"],
    "자동차": ["CARZ", "GM", "F", "TSLA", "TM"],
    "2차전지": ["LIT", "BATT", "ALB", "SQM", "LTHM"],
    "바이오": ["IBB", "XBI", "AMGN", "GILD", "REGN"],
    "은행": ["KBE", "XLF", "JPM", "BAC", "WFC"],
    "철강": ["SLX", "NUE", "STLD", "X"],
    "화학": ["XLB", "LYB", "DOW", "DD"],
    "IT서비스": ["IGV", "MSFT", "ORCL", "ACN"],
    "디스플레이": ["OLED", "QCOM", "AMAT", "LRCX"],
    "조선": ["ITA", "GD", "HII"],  # 미국 직접 대응 없음 → 방산 조선 대체
    "건설": ["XHB", "ITB", "DHI", "LEN"],
    "유통": ["XRT", "AMZN", "WMT", "TGT"],
    "의약품": ["IHE", "PFE", "MRK", "ABBV"],
    "에너지": ["XLE", "XOM", "CVX", "COP"],
    "통신": ["IYZ", "T", "VZ", "TMUS"],
    "기계": ["XLI", "CAT", "DE", "EMR"],
    "음식료": ["XLP", "KO", "PEP", "GIS"],
    "섬유의복": ["XLP", "NKE", "PVH", "RL"],
}

DEFAULT_BASKET = ["SPY", "QQQ"]  # 업종 매핑 없을 때 시장 전체


def get_basket(sector: str) -> list[str]:
    return SECTOR_US_BASKET.get(sector, DEFAULT_BASKET)
