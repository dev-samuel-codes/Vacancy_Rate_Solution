# 데이터 소스와 특성값 연결

## 현재 자동 생성됨

- `backend/data/seoul_sbiz_store_all.csv`
  - 서울 전체 상가업소 API 결과
  - `ctprvnCd=11` 기준으로 수집
  - 행정동/업종 단위 특성값 생성의 기본 데이터
- `backend/data/sbiz_store_list.csv`
  - 소상공인 상가업소 반경 조회 API 결과
  - 과거 입점 업종 수, 상권 입종 밀도 계산에 사용
- `backend/data/sbiz_store_history.csv`
  - 기준년월별 상가업소 스냅샷 저장
  - 같은 `bizesId + source_snapshot_ym + area_id`는 새 데이터로 업데이트
- `backend/data/vacancy_feature_dataset.csv`
  - 모델 입력용 최종 특성값 CSV
  - 서울 전체 최신 스냅샷 기준 집계 데이터
- `backend/data/vacancy_quarterly_timeseries.csv`
  - 분기별 시계열 모델 입력용 CSV
  - `period + district + admin_dong + business_type + license_source` 단위
  - 서울 열린데이터광장 상권분석서비스 `점포-행정동`, `추정매출-행정동`의 2019~2024년 분기 데이터를 결합
  - 공식 상권 데이터로 업종별 점포 수, 개업 수, 폐업 수, 폐업률, 매출, 매출 연령대 비율을 계산
  - 인허가 데이터 행은 별도로 함께 보존해서 1년 이상 지속 타깃을 유지
  - 한국부동산원 임대료 원본의 분기별 임대료/공실률/투자수익률을 결합
- `backend/data/seoul_commercial_store_admindong.csv`
  - 서울 열린데이터광장 상권분석서비스 `점포-행정동` 2019~2024년 ZIP을 정규화한 원천 CSV
- `backend/data/seoul_commercial_sales_admindong.csv`
  - 서울 열린데이터광장 상권분석서비스 `추정매출-행정동` 2019~2024년 ZIP을 정규화한 원천 CSV
- `backend/data/raw/seoul_open_data/`
  - 공식 ZIP 다운로드 캐시
  - `backend/scripts/collect_seoul_commercial_analysis.py`를 다시 실행하면 캐시를 재사용하고 최종 CSV를 갱신
- `backend/data/seoul_business_license.csv`
  - 서울 일반음식점 인허가 데이터
  - 입점일(`license_date`), 폐업일(`closed_date`), 영업상태, 1년 이상 지속 여부 계산에 사용
- `backend/data/data_source_status.csv`
  - 어떤 데이터 소스가 연결됐고 어떤 특성값이 비어 있는지 확인하는 상태표

## 추가 연결하면 자동으로 채워지는 값

- `SEOUL_COMMERCIAL_SALES_API_URL` 또는 `SEOUL_SALES_CSV_PATH`
  - `past_commercial_sales`
  - 추천 소스: 서울시 우리마을가게 상권분석서비스 추정매출
- `SEOUL_FOOT_TRAFFIC_API_URL` 또는 `SEOUL_FOOT_TRAFFIC_CSV_PATH`
  - `foot_traffic`
  - `age_10s_ratio` ~ `age_60s_plus_ratio`
  - 추천 소스: 서울시 우리마을가게 상권분석서비스 생활인구/유동인구
- `SEOUL_STORE_SURVIVAL_API_URL` 또는 `SEOUL_STORE_SURVIVAL_CSV_PATH`
  - `closure_frequency`
  - `target_survived_over_1_year`
  - 추천 소스: 서울시 우리마을가게 상권분석서비스 개폐업/생존율
- `LOCALDATA_LICENSE_CSV_PATH`
  - `closure_frequency`
  - `target_survived_over_1_year`
  - 추천 소스: 공공데이터포털 지방행정 인허가정보
- `MOLIT_COMMERCIAL_TRADE_API_URL` 또는 `MOLIT_COMMERCIAL_TRADE_CSV_PATH`
  - `sale_price`
  - `sale_price_per_pyeong`
  - 추천 소스: 국토교통부 상업업무용 부동산 매매 실거래가
- `MOLIT_COMMERCIAL_RENT_API_URL` 또는 `MOLIT_COMMERCIAL_RENT_CSV_PATH`
  - `deposit`
  - 추천 소스: 국토교통부 상업업무용 임대/전월세 실거래가 계열 자료

## 현재 확인된 제한

- `MOLIT_COMMERCIAL_TRADE_API_URL`은 `.env`에 있지만 현재 호출 결과가 `HTTP 403`이라 CSV가 생성되지 않았다.
- 서울시 매출은 `추정매출-행정동` 파일로 연결했다.
- 유동인구/상주인구/직장인구 계열은 파일 ZIP이 없고 Open API 형태라 서울 열린데이터광장 인증키가 있어야 전체 갱신할 수 있다.
- 공식 상권분석 점포 데이터에는 개별 사업장의 입점일/폐업일이 없어서 1년 이상 지속 타깃은 인허가일자/폐업일자/영업상태 데이터가 있는 행에서만 계산된다.
