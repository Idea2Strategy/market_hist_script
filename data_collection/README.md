# API 호출 및 크롤링

티커 목록을 크롤링하고 Alpaca에서 5분봉을 수집·갱신하는 스크립트가 있습니다.

## 스크립트

### `get_ticker.py`

Wikipedia의 현재 S&P 500 구성 종목과 최근 3년의 편출 이력을 결합해 티커 목록을 터미널에 출력합니다. 파일을 생성하지 않으며, 크롤링 실패 시 기본 7개 티커를 표시합니다.

```bash
python data_collection/get_ticker.py
```

### `script.py`

저장 형식(CSV/Parquet)과 데이터 타입(Raw/Adjusted)을 선택한 뒤 Alpaca에서 최근 3년의 5분봉을 종목별로 수집합니다. 기존 파일이 있으면 마지막 타임스탬프 다음부터 증분 갱신합니다.

```bash
python data_collection/script.py
```

## 생성되는 폴더와 파일

| 선택 | 생성 경로 |
| --- | --- |
| Raw CSV | `market_data/csv/{TICKER}_5min_historical.csv` |
| Raw Parquet | `market_data/parquet/{TICKER}_5min_historical.parquet` |
| Adjusted CSV | `adjust_market_data/csv/{TICKER}_5min_historical.csv` |
| Adjusted Parquet | `adjust_market_data/parquet/{TICKER}_5min_historical.parquet` |
| 공통 | `ticker_info/sp500_tickers_3years.txt` |

Alpaca 인증정보는 프로젝트 루트의 `.env` 또는 환경변수에서 읽습니다.
