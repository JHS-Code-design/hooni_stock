"""GitHub Actions 진입점 — 전체 수집 실행"""
import subprocess
import sys
from pathlib import Path

scripts = Path(__file__).parent

def run(script: str):
    result = subprocess.run([sys.executable, str(scripts / script)], check=True)
    return result.returncode

if __name__ == "__main__":
    run("collect_us_market.py")
    run("collect_kr_stocks.py")
    print("전체 수집 완료")
