# 서울 전체 상가/인허가 데이터 수집
from pathlib import Path
from urllib.parse import urljoin
from zipfile import ZipFile
import argparse
import io
import os
import sys
import warnings

import pandas as pd
import requests
from dotenv import load_dotenv


warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL.*", category=Warning)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT / "backend"))
load_dotenv(PROJECT_ROOT / "backend" / ".env")

from app.data_sources import PublicOpenApiClient


LOCALDATA_LICENSE_URLS = {
    "complex_distribution_game": "https://www.localdata.go.kr/datafile/each/03_05_04_P_CSV.zip",
    "internet_computer_game": "https://www.localdata.go.kr/datafile/each/03_05_05_P_CSV.zip",
    "general_game": "https://www.localdata.go.kr/datafile/each/03_05_06_P_CSV.zip",
    "youth_game": "https://www.localdata.go.kr/datafile/each/03_05_07_P_CSV.zip",
    "tourist_restaurant": "https://www.localdata.go.kr/datafile/each/07_24_01_P_CSV.zip",
    "tourist_entertainment_restaurant": "https://www.localdata.go.kr/datafile/each/07_24_02_P_CSV.zip",
    "foreign_entertainment_restaurant": "https://www.localdata.go.kr/datafile/each/07_24_03_P_CSV.zip",
    "general_restaurant": "https://www.localdata.go.kr/datafile/each/07_24_04_P_CSV.zip",
    "snack_restaurant": "https://www.localdata.go.kr/datafile/each/07_24_05_P_CSV.zip",
}


def fetch_all_seoul_stores(client, page_size=1000, max_pages=None):
    base_url = client.urls["SBIZ_STORE_API_URL"].rsplit("/", 1)[0]
    url = urljoin(base_url + "/", "storeListInDong")
    page_no = 1
    all_rows = []
    total_count = None
    snapshot_ym = None

    while True:
        data = client._request_json(
            url,
            params={
                "type": "json",
                "pageNo": page_no,
                "numOfRows": page_size,
                "divId": "ctprvnCd",
                "key": "11",
            },
        )
        body = data.get("body", {})
        total_count = total_count or int(body.get("totalCount", 0))
        snapshot_ym = snapshot_ym or client._extract_snapshot_ym(data)
        items = client._extract_items(data)
        if not items:
            break

        for item in items:
            item["source_snapshot_ym"] = snapshot_ym
            item["fetched_at"] = client._now()

        all_rows.extend(items)
        print(f"store_page={page_no} rows={len(all_rows)}/{total_count}", flush=True)

        if len(all_rows) >= total_count:
            break
        if max_pages and page_no >= max_pages:
            break
        page_no += 1

    client._save_or_update_csv(
        all_rows,
        client.csv_paths["seoul_sbiz_store_all"],
        unique_key=["bizesId", "source_snapshot_ym"],
    )
    return len(all_rows), total_count


def download_seoul_license_files(client, refresh=False, license_sources=None):
    if client.csv_paths["localdata_license"].exists() and not refresh:
        existing = pd.read_csv(client.csv_paths["localdata_license"], usecols=["business_name"], low_memory=False)
        print(f"license_csv_exists rows={len(existing)}", flush=True)
        return len(existing)

    saved_frames = []

    selected_sources = license_sources or list(LOCALDATA_LICENSE_URLS)

    for source_name, url in LOCALDATA_LICENSE_URLS.items():
        if source_name not in selected_sources:
            continue
        zip_path = client.data_dir / f"{source_name}.zip"
        if zip_path.exists():
            zip_bytes = zip_path.read_bytes()
        else:
            response = requests.get(url, timeout=120)
            response.raise_for_status()
            zip_bytes = response.content
            zip_path.write_bytes(zip_bytes)

        with ZipFile(io.BytesIO(zip_bytes)) as archive:
            for csv_name in archive.namelist():
                if not csv_name.lower().endswith(".csv"):
                    continue
                with archive.open(csv_name) as csv_file:
                    frame = read_license_csv(csv_file)
                frame = filter_seoul_license_rows(frame)
                frame["license_source"] = source_name
                saved_frames.append(frame)
                print(f"license_file={csv_name} seoul_rows={len(frame)}", flush=True)

    if not saved_frames:
        return 0

    license_df = pd.concat(saved_frames, ignore_index=True)
    license_df = standardize_license_columns(license_df)
    license_df.to_csv(client.csv_paths["localdata_license"], index=False, encoding="utf-8-sig")
    return len(license_df)


def read_license_csv(csv_file):
    data = csv_file.read()
    last_error = None
    for encoding in ["cp949", "utf-8-sig", "utf-8"]:
        try:
            return pd.read_csv(io.BytesIO(data), encoding=encoding, low_memory=False)
        except UnicodeDecodeError as error:
            last_error = error
            continue
        except pd.errors.ParserError as error:
            last_error = error
            try:
                return pd.read_csv(
                    io.BytesIO(data),
                    encoding=encoding,
                    engine="python",
                    on_bad_lines="skip",
                )
            except UnicodeDecodeError as fallback_error:
                last_error = fallback_error
            continue
    if last_error:
        raise last_error
    return pd.read_csv(io.BytesIO(data), low_memory=False)


def filter_seoul_license_rows(frame):
    address_candidates = ["소재지전체주소", "도로명전체주소", "siteWhlAddr", "rdnWhlAddr"]
    text_columns = [
        column
        for column in frame.columns
        if any(candidate.lower() in str(column).lower() for candidate in address_candidates)
    ]
    if not text_columns:
        text_columns = [column for column in frame.columns if frame[column].dtype == "object"]

    mask = pd.Series(False, index=frame.index)
    for column in text_columns:
        normalized = frame[column].astype(str).str.strip()
        mask = mask | normalized.str.startswith(("서울특별시", "서울시", "서울"), na=False)
    return frame[mask].copy()


def standardize_license_columns(frame):
    column_map = {}
    candidates = {
        "business_name": ["사업장명", "사업장명칭", "업소명", "bplcNm"],
        "business_type": ["업태구분명", "업종명", "위생업태명", "문화체육업종명", "개방서비스명", "uptaeNm"],
        "license_date": ["인허가일자", "licensgDe", "opnSvcDt"],
        "closed_date": ["폐업일자", "dcbYmd", "폐업일"],
        "business_status": ["영업상태명", "영업상태", "상세영업상태명", "trdStateNm"],
        "address": ["소재지전체주소", "도로명전체주소", "siteWhlAddr", "rdnWhlAddr"],
        "x": ["좌표정보x", "x"],
        "y": ["좌표정보y", "y"],
    }

    for target, names in candidates.items():
        for name in names:
            for column in frame.columns:
                if name.lower() in str(column).lower():
                    column_map[target] = column
                    break
            if target in column_map:
                break

    standardized = pd.DataFrame()
    for target, source in column_map.items():
        standardized[target] = frame[source]

    standardized = fill_business_type_fallbacks(standardized, frame)

    for column in frame.columns:
        if column not in standardized.columns:
            standardized[column] = frame[column]

    standardized["region"] = "서울"
    standardized["district"] = standardized.get("address", pd.Series("", index=standardized.index)).apply(extract_district)
    standardized = filter_standardized_seoul_rows(standardized)
    for column in ["license_date", "closed_date"]:
        if column not in standardized.columns:
            standardized[column] = pd.NA
    standardized["license_date"] = pd.to_datetime(
        standardized["license_date"],
        errors="coerce",
    ).dt.date
    standardized["closed_date"] = pd.to_datetime(
        standardized["closed_date"],
        errors="coerce",
    ).dt.date
    standardized["survived_over_1_year"] = (
        pd.to_datetime(standardized["closed_date"]).fillna(pd.Timestamp.today())
        - pd.to_datetime(standardized["license_date"])
    ).dt.days.ge(365)

    return standardized


def fill_business_type_fallbacks(standardized, source_frame):
    fallback_columns = ["업태구분명", "위생업태명", "문화체육업종명", "개방서비스명", "업종명"]

    if "business_type" not in standardized.columns:
        standardized["business_type"] = pd.NA

    standardized["business_type"] = standardized["business_type"].replace("", pd.NA)
    for column in fallback_columns:
        if column not in source_frame.columns:
            continue
        fallback = source_frame[column].replace("", pd.NA)
        standardized["business_type"] = standardized["business_type"].fillna(fallback)

    return standardized


def filter_standardized_seoul_rows(frame):
    if "address" not in frame.columns:
        return frame

    normalized = frame["address"].astype(str).str.strip()
    return frame[normalized.str.startswith(("서울특별시", "서울시", "서울"), na=False)].copy()


def extract_district(value):
    for token in str(value).replace(",", " ").split():
        if token.endswith("구"):
            return token
    return ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--refresh-license", action="store_true")
    parser.add_argument("--skip-stores", action="store_true")
    parser.add_argument("--license-source", action="append", choices=sorted(LOCALDATA_LICENSE_URLS))
    args = parser.parse_args()

    client = PublicOpenApiClient()
    max_pages_value = os.getenv("SBIZ_MAX_PAGES")
    max_pages = args.max_pages or (int(max_pages_value) if max_pages_value else None)

    if args.skip_stores and client.csv_paths["seoul_sbiz_store_all"].exists():
        existing_store = pd.read_csv(client.csv_paths["seoul_sbiz_store_all"], usecols=["bizesId"], low_memory=False)
        store_rows = len(existing_store)
        total_count = store_rows
        print(f"store_csv_exists rows={store_rows}", flush=True)
    else:
        store_rows, total_count = fetch_all_seoul_stores(client, max_pages=max_pages)
    license_rows = download_seoul_license_files(
        client,
        refresh=args.refresh_license,
        license_sources=args.license_source,
    )
    feature_df = client.update_feature_dataset_from_store_csv()

    print(f"seoul_store_rows_collected={store_rows}", flush=True)
    print(f"seoul_store_total_count={total_count}", flush=True)
    print(f"seoul_license_rows={license_rows}", flush=True)
    print(f"feature_rows={len(feature_df)}", flush=True)
    print(f"store_csv={client.csv_paths['seoul_sbiz_store_all']}", flush=True)
    print(f"license_csv={client.csv_paths['localdata_license']}", flush=True)
    print(f"feature_csv={client.csv_paths['feature_dataset']}", flush=True)


if __name__ == "__main__":
    main()
