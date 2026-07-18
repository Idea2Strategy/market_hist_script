# 데이터 검사 및 체크

수집 데이터의 기본 상태와 정규장 데이터의 기간·누락 구간을 검사합니다.

## 스크립트

### `check_data.py`

`market_data/parquet/`의 Raw Parquet을 검사해 행 수, 시작·종료 시각과 정규장 비율을 터미널에 출력합니다. 파일은 생성하지 않습니다.

```bash
python data_validation/check_data.py
```

### `data_report.py`

`market_data/parquet/`의 Raw Parquet 전 종목을 검사하고 텍스트 보고서를 생성합니다.

```bash
python data_validation/data_report.py
```

생성 파일: `report/data_audit_report.txt`

### `audit_regular_session.py`

`regular_market_data/`의 선택한 Raw/Adjusted 및 CSV/Parquet 결과에서 종목별 시작·종료일, 기대 봉 수, 누락 봉, 커버리지와 연속 누락 구간을 계산합니다. 누락 봉을 채우거나 원본을 수정하지 않습니다.

```bash
python data_validation/audit_regular_session.py
```

자동 실행 예시:

```bash
python data_validation/audit_regular_session.py --data-type adjusted --format parquet
```

## 생성되는 폴더와 파일

```text
report/regular_session_audit/
├── {type}_{format}_summary.csv
└── {type}_{format}_missing_intervals.csv
```

- `summary.csv`: 종목별 관측 시작·종료일, 기대 봉, 누락 봉, 커버리지, 중복과 비정상 타임스탬프
- `missing_intervals.csv`: 같은 거래일 안에서 연속된 누락의 시작·종료 시각과 직전·직후 봉
