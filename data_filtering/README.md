# 데이터 필터링

수집한 5분봉에서 미국 주식 정규장 데이터만 별도 저장합니다.

## 스크립트

### `filter_regular_session.py`

실행 시 Raw/Adjusted와 CSV/Parquet을 차례로 선택합니다. `pandas-market-calendars`의 `XNYS` 일정으로 거래일, 휴장, 조기 폐장과 서머타임을 반영하며 원본 파일은 수정하지 않습니다.

```bash
python data_filtering/filter_regular_session.py
```

자동 실행 예시:

```bash
python data_filtering/filter_regular_session.py --data-type adjusted --format parquet
```

## 생성되는 폴더와 파일

```text
regular_market_data/
├── raw/
│   ├── csv/{TICKER}_5min_historical.csv
│   └── parquet/{TICKER}_5min_historical.parquet
└── adjusted/
    ├── csv/{TICKER}_5min_historical.csv
    └── parquet/{TICKER}_5min_historical.parquet
```

같은 조합을 다시 실행하면 최신 원본을 필터링한 결과로 대상 파일을 안전하게 교체합니다.
