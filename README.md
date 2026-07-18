# S&P 500 5분봉 데이터 파이프라인

Wikipedia와 Alpaca에서 최근 3년의 S&P 500 관련 종목을 수집하고, 정규장 데이터 분리와 데이터 품질 검사를 수행하는 프로젝트입니다.

## 프로젝트 구조

스크립트는 역할에 따라 세 폴더로 분류합니다. 각 폴더의 자세한 실행법은 해당 README에서 확인할 수 있습니다.

```text
script/
├── data_collection/              # API 호출 및 크롤링
│   ├── script.py
│   ├── get_ticker.py
│   └── README.md
├── data_filtering/               # 정규장 데이터 필터링
│   ├── filter_regular_session.py
│   └── README.md
├── data_validation/              # 데이터 검사 및 보고서 생성
│   ├── audit_regular_session.py
│   ├── check_data.py
│   ├── data_report.py
│   └── README.md
├── tests/                        # 자동 테스트
├── .env.example                  # Alpaca 인증정보 예시
├── requirements.txt              # Python 의존성
└── README.md
```

| 폴더 | 역할 | 상세 설명 |
| --- | --- | --- |
| `data_collection/` | 티커 크롤링과 Alpaca 5분봉 수집·갱신 | [수집 스크립트 안내](data_collection/README.md) |
| `data_filtering/` | XNYS 일정 기반 정규장 데이터 분리 | [필터링 스크립트 안내](data_filtering/README.md) |
| `data_validation/` | 수집 결과와 정규장 누락 구간 검사 | [검사 스크립트 안내](data_validation/README.md) |

## 실행으로 생성되는 구조

스크립트 위치만 분류했으며 기존 데이터와 보고서의 출력 구조는 유지합니다.

```text
script/
├── market_data/                  # Raw 데이터
│   ├── csv/
│   └── parquet/
├── adjust_market_data/           # 배당·분할 반영 데이터
│   ├── csv/
│   └── parquet/
├── regular_market_data/          # 정규장 필터 결과
│   ├── raw/{csv,parquet}/
│   └── adjusted/{csv,parquet}/
├── ticker_info/
│   └── sp500_tickers_3years.txt
└── report/
    ├── data_audit_report.txt
    └── regular_session_audit/
        ├── {type}_{format}_summary.csv
        └── {type}_{format}_missing_intervals.csv
```

| 생성 경로 | 생성 스크립트 | 내용 |
| --- | --- | --- |
| `market_data/` | `data_collection/script.py` | Raw 5분봉 CSV 또는 Parquet |
| `adjust_market_data/` | `data_collection/script.py` | 수정주가 5분봉 CSV 또는 Parquet |
| `ticker_info/` | `data_collection/script.py` | 수집 대상 티커 목록 |
| `regular_market_data/` | `data_filtering/filter_regular_session.py` | 휴장·조기 폐장·서머타임을 반영한 정규장 데이터 |
| `report/data_audit_report.txt` | `data_validation/data_report.py` | Raw Parquet 전체 검사 보고서 |
| `report/regular_session_audit/` | `data_validation/audit_regular_session.py` | 종목별 기간·커버리지와 누락 구간 CSV |

## 사전 준비

- Python 3.10 이상
- 유효한 Alpaca Market Data API Key와 Secret Key
- 전체 수집 결과를 저장할 충분한 디스크 공간

### 1. 가상환경 만들기

Windows PowerShell:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

macOS/Linux:

```bash
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

### 2. 의존성 설치하기

```bash
python -m pip install -r requirements.txt
```

주요 의존성은 `alpaca-py`, `pandas`, `pandas-market-calendars`, `pyarrow`, `lxml`, `python-dotenv`입니다.

### 3. Alpaca 인증정보 설정하기

Windows PowerShell:

```powershell
$env:ALPACA_API_KEY = "발급받은_API_KEY"
$env:ALPACA_SECRET_KEY = "발급받은_SECRET_KEY"
```

macOS/Linux:

```bash
export ALPACA_API_KEY="발급받은_API_KEY"
export ALPACA_SECRET_KEY="발급받은_SECRET_KEY"
```

또는 `.env.example`을 `.env`로 복사한 뒤 실제 키를 입력할 수 있습니다. 실제 키가 들어 있는 `.env`는 커밋하지 마세요.

## 기본 실행 순서

명령은 프로젝트 루트에서 실행하는 것을 권장합니다.

```bash
# 1. 데이터 수집 또는 갱신
python data_collection/script.py

# 2. 정규장 데이터 분리
python data_filtering/filter_regular_session.py

# 3. 종목별 기간과 누락 구간 검사
python data_validation/audit_regular_session.py
```

보조 명령:

```bash
# API 호출 없이 티커 목록 확인
python data_collection/get_ticker.py

# Raw Parquet 간단 검사
python data_validation/check_data.py

# Raw Parquet 텍스트 보고서 생성
python data_validation/data_report.py

# 전체 자동 테스트
python -m unittest discover -s tests -v
```

모든 스크립트는 자신의 파일 위치를 기준으로 프로젝트 루트를 계산하므로, 실행 위치와 관계없이 기존 루트 출력 폴더를 사용합니다.
