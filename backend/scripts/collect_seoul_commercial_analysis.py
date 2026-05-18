# 서울 열린데이터광장 상권분석서비스 분기 데이터 수집/갱신
from pathlib import Path
from zipfile import ZipFile
import io
import re
import sys
import warnings

import pandas as pd
import requests


warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL.*", category=Warning)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.append(str(BACKEND_DIR))
sys.path.append(str(BACKEND_DIR / "scripts"))
DATA_DIR = BACKEND_DIR / "data"
RAW_DIR = DATA_DIR / "raw" / "seoul_open_data"
DOWNLOAD_URL = "https://datafile.seoul.go.kr/bigfile/iot/inf/nio_download.do?&useCache=false"

DATASETS = {
    "store_admindong": {
        "inf_id": "OA-22172",
        "page_url": "https://data.seoul.go.kr/dataList/OA-22172/S/1/datasetView.do",
        "output_csv": DATA_DIR / "seoul_commercial_store_admindong.csv",
    },
    "sales_admindong": {
        "inf_id": "OA-22175",
        "page_url": "https://data.seoul.go.kr/dataList/OA-22175/S/1/datasetView.do",
        "output_csv": DATA_DIR / "seoul_commercial_sales_admindong.csv",
    },
}


def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    store_df = collect_dataset("store_admindong", normalize_store_frame)
    sales_df = collect_dataset("sales_admindong", normalize_sales_frame)
    official_df = build_model_timeseries(store_df, sales_df)
    license_df = build_license_target_timeseries()
    final_df = pd.concat([official_df, license_df], ignore_index=True)

    output_path = DATA_DIR / "vacancy_quarterly_timeseries.csv"
    final_df.to_csv(output_path, index=False, encoding="utf-8-sig")

    print(f"store_rows={len(store_df)}")
    print(f"sales_rows={len(sales_df)}")
    print(f"created_or_updated={output_path}")
    print(f"rows={len(final_df)}")
    print(f"periods={final_df['period'].min()}..{final_df['period'].max()}")
    print(f"districts={final_df['district'].nunique()}")
    print(f"admin_dongs={final_df['admin_dong'].nunique()}")
    print(f"business_types={final_df['business_type'].nunique()}")
    print(f"target_nonnull={final_df['target_survived_over_1_year'].notna().sum()}")


def collect_dataset(dataset_name, normalizer):
    dataset = DATASETS[dataset_name]
    files = list_download_files(dataset["page_url"])
    if not files:
        raise RuntimeError(f"다운로드 파일 목록을 찾지 못했습니다: {dataset['page_url']}")

    frames = []
    for file_info in files:
        zip_bytes = download_zip(dataset_name, dataset, file_info)
        frame = read_first_csv_from_zip(zip_bytes)
        normalized = normalizer(frame)
        normalized["source_year"] = file_info["year"]
        normalized["source_file_name"] = file_info["file_name"]
        frames.append(normalized)
        print(f"{dataset_name} year={file_info['year']} rows={len(normalized)}")

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.drop_duplicates()
    combined.to_csv(dataset["output_csv"], index=False, encoding="utf-8-sig")
    return combined


def list_download_files(page_url):
    html = requests.get(page_url, timeout=30).text
    pattern = re.compile(
        r'<span[^>]+title="(?P<file_name>[^"]+\.zip)"[^>]+downloadFile\(\'(?P<seq>\d+)\'\)'
    )
    files = []
    seen = set()
    for match in pattern.finditer(html):
        file_name = match.group("file_name")
        seq = match.group("seq")
        key = (file_name, seq)
        if key in seen:
            continue
        seen.add(key)
        year_match = re.search(r"(20\d{2})", file_name)
        files.append(
            {
                "file_name": file_name,
                "seq": seq,
                "year": int(year_match.group(1)) if year_match else None,
            }
        )

    return sorted(files, key=lambda item: item["year"] or 0)


def download_zip(dataset_name, dataset, file_info):
    zip_dir = RAW_DIR / dataset_name
    zip_dir.mkdir(parents=True, exist_ok=True)
    zip_path = zip_dir / f"{file_info['year']}.zip"
    if zip_path.exists() and zip_path.stat().st_size > 0:
        return zip_path.read_bytes()

    response = requests.post(
        DOWNLOAD_URL,
        data={
            "infId": dataset["inf_id"],
            "seqNo": "",
            "seq": file_info["seq"],
            "infSeq": "3",
        },
        headers={"Referer": dataset["page_url"]},
        timeout=180,
    )
    response.raise_for_status()
    if not response.content.startswith(b"PK"):
        raise RuntimeError(f"ZIP 다운로드에 실패했습니다: {dataset_name} {file_info}")
    zip_path.write_bytes(response.content)
    return response.content


def read_first_csv_from_zip(zip_bytes):
    with ZipFile(io.BytesIO(zip_bytes)) as archive:
        csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if not csv_names:
            raise RuntimeError("ZIP 안에 CSV 파일이 없습니다.")
        csv_bytes = archive.read(csv_names[0])

    last_error = None
    for encoding in ["utf-8-sig", "cp949", "euc-kr"]:
        try:
            return pd.read_csv(io.BytesIO(csv_bytes), encoding=encoding, low_memory=False)
        except UnicodeDecodeError as error:
            last_error = error
    raise last_error


def normalize_store_frame(frame):
    normalized = pd.DataFrame(
        {
            "period": frame["기준_년분기_코드"].apply(quarter_code_to_period),
            "admin_dong_code": frame["행정동_코드"].astype(str),
            "admin_dong": frame["행정동_코드_명"].astype(str),
            "service_business_code": frame["서비스_업종_코드"].astype(str),
            "business_type": frame["서비스_업종_코드_명"].astype(str),
            "official_store_count": to_number(frame["점포_수"]),
            "similar_store_count": to_number(frame["유사_업종_점포_수"]),
            "opening_rate": to_number(frame["개업_율"]) / 100,
            "official_openings_in_quarter": to_number(frame["개업_점포_수"]),
            "closure_rate": to_number(frame["폐업_률"]) / 100,
            "official_closures_in_quarter": to_number(frame["폐업_점포_수"]),
            "franchise_store_count": to_number(frame["프랜차이즈_점포_수"]),
        }
    )
    return normalized


def normalize_sales_frame(frame):
    value_columns = {
        "past_commercial_sales": "당월_매출_금액",
        "sales_count": "당월_매출_건수",
        "weekday_sales": "주중_매출_금액",
        "weekend_sales": "주말_매출_금액",
        "male_sales": "남성_매출_금액",
        "female_sales": "여성_매출_금액",
        "age_10s_sales": "연령대_10_매출_금액",
        "age_20s_sales": "연령대_20_매출_금액",
        "age_30s_sales": "연령대_30_매출_금액",
        "age_40s_sales": "연령대_40_매출_금액",
        "age_50s_sales": "연령대_50_매출_금액",
        "age_60s_plus_sales": "연령대_60_이상_매출_금액",
    }
    normalized = pd.DataFrame(
        {
            "period": frame["기준_년분기_코드"].apply(quarter_code_to_period),
            "admin_dong_code": frame["행정동_코드"].astype(str),
            "admin_dong": frame["행정동_코드_명"].astype(str),
            "service_business_code": frame["서비스_업종_코드"].astype(str),
            "business_type": frame["서비스_업종_코드_명"].astype(str),
        }
    )
    for output_column, source_column in value_columns.items():
        if source_column in frame.columns:
            normalized[output_column] = to_number(frame[source_column])
    return normalized


def build_model_timeseries(store_df, sales_df):
    key_columns = ["period", "admin_dong_code", "admin_dong", "service_business_code", "business_type"]
    model_df = store_df.merge(
        sales_df.drop(columns=["source_year", "source_file_name"], errors="ignore"),
        on=key_columns,
        how="left",
    )

    district_map = load_admin_dong_district_map()
    model_df["district"] = model_df["admin_dong_code"].map(district_map)
    missing_district = model_df["district"].isna()
    if missing_district.any():
        name_map = load_admin_dong_name_district_map()
        model_df.loc[missing_district, "district"] = model_df.loc[missing_district, "admin_dong"].map(name_map)

    rent_df = load_quarterly_rent_features()
    model_df = model_df.merge(rent_df, on="period", how="left")

    model_df["period_start"] = model_df["period"].apply(lambda value: pd.Period(value, freq="Q").start_time.date().isoformat())
    model_df["period_end"] = model_df["period"].apply(lambda value: pd.Period(value, freq="Q").end_time.date().isoformat())
    model_df["region"] = "서울"
    model_df["license_source"] = "seoul_open_data_admindong"
    model_df["active_business_count_start"] = pd.NA
    model_df["active_business_count_end"] = model_df["official_store_count"]
    model_df["openings_in_quarter"] = model_df["official_openings_in_quarter"]
    model_df["closures_in_quarter"] = model_df["official_closures_in_quarter"]
    model_df["closure_frequency"] = model_df["closure_rate"]
    model_df["target_survived_over_1_year"] = pd.NA
    model_df["target_known_count"] = 0
    model_df["current_sbiz_store_count"] = pd.NA
    model_df["updated_at"] = pd.Timestamp.now(tz="UTC").isoformat()

    add_sales_ratios(model_df)

    columns = [
        "period",
        "period_start",
        "period_end",
        "region",
        "district",
        "admin_dong_code",
        "admin_dong",
        "license_source",
        "service_business_code",
        "business_type",
        "active_business_count_start",
        "active_business_count_end",
        "openings_in_quarter",
        "closures_in_quarter",
        "closure_frequency",
        "target_survived_over_1_year",
        "target_known_count",
        "past_commercial_sales",
        "sales_count",
        "weekday_sales",
        "weekend_sales",
        "male_sales",
        "female_sales",
        "age_10s_sales_ratio",
        "age_20s_sales_ratio",
        "age_30s_sales_ratio",
        "age_40s_sales_ratio",
        "age_50s_sales_ratio",
        "age_60s_plus_sales_ratio",
        "monthly_rent_per_sqm",
        "monthly_rent_per_pyeong",
        "vacancy_rate",
        "investment_yield",
        "official_store_count",
        "similar_store_count",
        "opening_rate",
        "official_openings_in_quarter",
        "closure_rate",
        "official_closures_in_quarter",
        "franchise_store_count",
        "current_sbiz_store_count",
        "updated_at",
    ]
    return model_df[columns].sort_values(["period", "district", "admin_dong_code", "business_type"])


def build_license_target_timeseries():
    from app.data_sources import PublicOpenApiClient
    from build_quarterly_timeseries import (
        build_periods,
        build_quarterly_rows,
        load_current_store_counts,
        load_license_data,
        load_quarterly_rent_data,
    )

    client = PublicOpenApiClient()
    license_source_path = client.csv_paths["localdata_license"]
    if not license_source_path.exists():
        return pd.DataFrame(columns=model_columns())

    license_source = load_license_data(client)
    rent_df = load_quarterly_rent_data(client)
    current_store_counts = load_current_store_counts(client)
    periods = build_periods(license_source, rent_df)
    rows = build_quarterly_rows(
        client=client,
        license_df=license_source,
        rent_df=rent_df,
        current_store_counts=current_store_counts,
        periods=periods,
    )
    license_df = pd.DataFrame(rows)
    license_df["admin_dong_code"] = pd.NA
    license_df["admin_dong"] = pd.NA
    license_df["service_business_code"] = pd.NA
    license_df["past_commercial_sales"] = pd.NA
    license_df["sales_count"] = pd.NA
    license_df["weekday_sales"] = pd.NA
    license_df["weekend_sales"] = pd.NA
    license_df["male_sales"] = pd.NA
    license_df["female_sales"] = pd.NA
    license_df["age_10s_sales_ratio"] = pd.NA
    license_df["age_20s_sales_ratio"] = pd.NA
    license_df["age_30s_sales_ratio"] = pd.NA
    license_df["age_40s_sales_ratio"] = pd.NA
    license_df["age_50s_sales_ratio"] = pd.NA
    license_df["age_60s_plus_sales_ratio"] = pd.NA
    license_df["official_store_count"] = pd.NA
    license_df["similar_store_count"] = pd.NA
    license_df["opening_rate"] = pd.NA
    license_df["official_openings_in_quarter"] = pd.NA
    license_df["closure_rate"] = pd.NA
    license_df["official_closures_in_quarter"] = pd.NA
    license_df["franchise_store_count"] = pd.NA
    return license_df[model_columns()]


def model_columns():
    return [
        "period",
        "period_start",
        "period_end",
        "region",
        "district",
        "admin_dong_code",
        "admin_dong",
        "license_source",
        "service_business_code",
        "business_type",
        "active_business_count_start",
        "active_business_count_end",
        "openings_in_quarter",
        "closures_in_quarter",
        "closure_frequency",
        "target_survived_over_1_year",
        "target_known_count",
        "past_commercial_sales",
        "sales_count",
        "weekday_sales",
        "weekend_sales",
        "male_sales",
        "female_sales",
        "age_10s_sales_ratio",
        "age_20s_sales_ratio",
        "age_30s_sales_ratio",
        "age_40s_sales_ratio",
        "age_50s_sales_ratio",
        "age_60s_plus_sales_ratio",
        "monthly_rent_per_sqm",
        "monthly_rent_per_pyeong",
        "vacancy_rate",
        "investment_yield",
        "official_store_count",
        "similar_store_count",
        "opening_rate",
        "official_openings_in_quarter",
        "closure_rate",
        "official_closures_in_quarter",
        "franchise_store_count",
        "current_sbiz_store_count",
        "updated_at",
    ]


def add_sales_ratios(frame):
    total = frame["past_commercial_sales"].replace(0, pd.NA)
    age_columns = {
        "age_10s_sales_ratio": "age_10s_sales",
        "age_20s_sales_ratio": "age_20s_sales",
        "age_30s_sales_ratio": "age_30s_sales",
        "age_40s_sales_ratio": "age_40s_sales",
        "age_50s_sales_ratio": "age_50s_sales",
        "age_60s_plus_sales_ratio": "age_60s_plus_sales",
    }
    for ratio_column, amount_column in age_columns.items():
        frame[ratio_column] = frame[amount_column] / total if amount_column in frame.columns else pd.NA


def load_admin_dong_district_map():
    path = DATA_DIR / "seoul_sbiz_store_all.csv"
    if not path.exists():
        return {}
    frame = pd.read_csv(path, usecols=["adongCd", "signguNm"], dtype={"adongCd": str}, low_memory=False)
    frame = frame.dropna().drop_duplicates()
    return frame.groupby("adongCd")["signguNm"].agg(lambda values: values.mode().iat[0]).to_dict()


def load_admin_dong_name_district_map():
    path = DATA_DIR / "seoul_sbiz_store_all.csv"
    if not path.exists():
        return {}
    frame = pd.read_csv(path, usecols=["adongNm", "signguNm"], low_memory=False).dropna().drop_duplicates()
    return frame.groupby("adongNm")["signguNm"].agg(lambda values: values.mode().iat[0]).to_dict()


def load_quarterly_rent_features():
    path = DATA_DIR / "vacancy_Rents_Yields.csv"
    if not path.exists():
        return pd.DataFrame(columns=["period"])
    try:
        raw_df = pd.read_csv(path, low_memory=False)
    except pd.errors.ParserError:
        raw_df = pd.read_csv(path, engine="python", on_bad_lines="skip")
    seoul_df = raw_df[raw_df["지역별"].astype(str).eq("서울")]
    quarter_columns = [column for column in seoul_df.columns if isinstance(column, str) and "." in column and "/4" in column]
    rows = {}
    metric_map = {
        "임대료": "monthly_rent_per_sqm",
        "공실률": "vacancy_rate",
        "투자수익률": "investment_yield",
    }
    for _, row in seoul_df.iterrows():
        metric_name = metric_map.get(str(row.get("구분별")))
        if not metric_name:
            continue
        for quarter_column in quarter_columns:
            period = rent_quarter_to_period(quarter_column)
            rows.setdefault(period, {"period": period})
            rows[period][metric_name] = to_scalar_number(row.get(quarter_column))

    rent_df = pd.DataFrame(rows.values())
    if rent_df.empty:
        return pd.DataFrame(columns=["period"])
    rent_df["monthly_rent_per_pyeong"] = rent_df["monthly_rent_per_sqm"] * 3.3058
    return rent_df


def quarter_code_to_period(value):
    value = str(value).strip()
    return f"{value[:4]}Q{value[-1]}"


def rent_quarter_to_period(column):
    year, quarter_text = str(column).split(".", 1)
    return f"{year}Q{quarter_text.split('/')[0]}"


def to_number(series):
    return pd.to_numeric(series.astype(str).str.replace(",", "", regex=False).str.strip(), errors="coerce")


def to_scalar_number(value):
    if pd.isna(value):
        return pd.NA
    return pd.to_numeric(str(value).replace(",", "").strip(), errors="coerce")


if __name__ == "__main__":
    sys.exit(main())
