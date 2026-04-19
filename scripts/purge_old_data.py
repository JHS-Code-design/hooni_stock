"""180일 초과 데이터 정리 스크립트"""
import shutil
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
KEEP_DAYS = 180


def purge():
    cutoff = datetime.now() - timedelta(days=KEEP_DAYS)
    cutoff_str = cutoff.strftime("%Y-%m-%d")

    deleted = 0
    # prices/{date}/ 디렉토리
    for d in (DATA_DIR / "prices").glob("????-??-??"):
        if d.is_dir() and d.name < cutoff_str:
            shutil.rmtree(d)
            deleted += 1
            print(f"삭제: {d}")

    # us_market/{date}.parquet 파일
    for f in (DATA_DIR / "us_market").glob("????-??-??.parquet"):
        if f.stem < cutoff_str:
            f.unlink()
            deleted += 1
            print(f"삭제: {f}")

    print(f"정리 완료: {deleted}개 삭제")


if __name__ == "__main__":
    purge()
