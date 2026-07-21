# 데이터 필터링

기존 수집 데이터와 SIP 1분봉에서 미국 주식 정규장 데이터만 별도 저장합니다.

## 스크립트

### `filter_regular_session.py`

실행 시 원본 데이터셋, Raw/Adjusted, CSV/Parquet을 차례로 선택합니다. `pandas-market-calendars`의 `XNYS` 일정으로 거래일, 휴장, 조기 폐장과 서머타임을 반영하며 봉 간격과 관계없이 봉 시작 시각이 정규장 안에 있는 행만 남깁니다. 원본 파일은 수정하지 않습니다.

`timestamp`는 ISO 날짜 문자열과 Unix epoch 숫자를 모두 인식합니다. 숫자형은 초·밀리초·마이크로초·나노초 단위를 자동 판별하며 결과 인덱스는 UTC datetime으로 통일합니다. Alpaca JSON에서 보이는 `1689697260000` 같은 값도 밀리초로 처리됩니다.

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

regular_sip_1min_market_data/
├── raw/
│   ├── csv/{TICKER}_1min_sip_historical.csv
│   └── parquet/{TICKER}_1min_sip_historical.parquet
└── adjusted/
    ├── csv/{TICKER}_1min_sip_historical.csv
    └── parquet/{TICKER}_1min_sip_historical.parquet
```

기존 데이터 결과는 `regular_market_data/`, SIP 1분봉 결과는 `regular_sip_1min_market_data/`로 분리되므로 피드와 봉 간격이 섞이지 않습니다. 같은 조합을 다시 실행하면 최신 원본을 필터링한 결과로 대상 파일을 안전하게 교체합니다.

### `resample_sip_5min.py`

정규장 SIP Adjusted 또는 Raw 1분봉을 종목·거래일별 5분·15분·1시간·4시간·1일봉으로 집계합니다. 파일명은 기존 호환성을 위해 유지했지만 공통 다중 주기 리샘플러로 동작합니다. OHLC는 첫 시가, 최고 고가, 최저 저가, 마지막 종가를 사용하고 `volume`과 `trade_count`는 합산합니다. `vwap`은 1분봉 거래량으로 가중해 다시 계산하며, 각 구간에 실제로 존재한 1분봉 개수는 `source_minutes`로 저장합니다. 누락된 1분봉을 임의로 생성하거나 보간하지 않습니다.

모든 구간은 자정이 아닌 XNYS 공식 개장 시각에 맞춰집니다. 정상 거래일의 1시간봉은 09:30부터 시작하고 마지막 봉은 30분 분량이며, 4시간봉은 09:30부터 4시간과 남은 2시간 30분으로 나뉩니다. 조기폐장일도 실제 세션 종료까지만 집계하고, 1일봉은 세션당 한 행을 생성합니다.

```bash
python data_filtering/resample_sip_5min.py --format parquet

# Raw 정규장 1분봉을 Raw 15분봉으로 집계
python data_filtering/resample_sip_5min.py --format parquet --data-type raw --interval 15min

# 지원 간격: 5min, 15min, 1hour, 4hour, 1day
python data_filtering/resample_sip_5min.py --format parquet --interval 1hour
```

```text
입력: regular_sip_1min_market_data/{adjusted,raw}/{format}/
출력: regular_sip_{interval}_market_data/{adjusted,raw}/{format}/
파일: {TICKER}_{interval}_sip_historical.{format}
```

`daily_pipeline.py`를 실행하면 Adjusted와 Raw에 대해 지원하는 다섯 간격이 모두 자동으로 생성됩니다.

통합 파이프라인에서는 정규장 필터와 각 집계봉 생성을 증분 방식으로 처리합니다. 주기별 기존 결과의 마지막 거래 세션을 다시 계산해 부분 저장이나 마지막 미완성 구간을 교체하고, 그보다 오래된 결과는 유지한 채 새 거래 세션만 병합합니다. 이 동작은 개별 스크립트의 전체 재생성 모드에는 영향을 주지 않습니다.
