# 데이터 필터링

기존 수집 데이터와 SIP 1분봉에서 미국 주식 정규장 데이터만 별도 저장합니다.

## 스크립트

### `filter_regular_session.py`

실행 시 원본 데이터셋, Raw/Adjusted, CSV/Parquet을 차례로 선택합니다. `pandas-market-calendars`의 `XNYS` 일정으로 거래일, 휴장, 조기 폐장과 서머타임을 반영하며 봉 간격과 관계없이 봉 시작 시각이 정규장 안에 있는 행만 남깁니다. 원본 파일은 수정하지 않습니다.

```bash
python data_filtering/filter_regular_session.py
```

선택 순서는 다음과 같습니다.

```text
1. 기존 수집 데이터/5분봉 또는 SIP 1분봉
2. Raw 또는 Adjusted
3. CSV 또는 Parquet
```

자동 실행 예시:

```bash
# 기존 5분봉 Adjusted Parquet
python data_filtering/filter_regular_session.py --dataset standard --data-type adjusted --format parquet

# SIP 1분봉 Adjusted Parquet
python data_filtering/filter_regular_session.py --dataset sip --data-type adjusted --format parquet
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

regular_sip_market_data/
├── raw/
│   ├── csv/{TICKER}_1min_sip_historical.csv
│   └── parquet/{TICKER}_1min_sip_historical.parquet
└── adjusted/
    ├── csv/{TICKER}_1min_sip_historical.csv
    └── parquet/{TICKER}_1min_sip_historical.parquet
```

기존 데이터 결과는 `regular_market_data/`, SIP 결과는 `regular_sip_market_data/`로 분리되므로 피드와 봉 간격이 섞이지 않습니다. 같은 조합을 다시 실행하면 최신 원본을 필터링한 결과로 대상 파일을 안전하게 교체합니다.
