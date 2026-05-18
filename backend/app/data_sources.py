# api 호출 및 특성값 CSV 생성/업데이트
import os
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree

import pandas as pd

warnings.filterwarnings(
    "ignore",
    message="urllib3 v2 only supports OpenSSL.*",
    category=Warning,
)
warnings.filterwarnings(
    "ignore",
    message="The behavior of DataFrame concatenation with empty or all-NA entries is deprecated.*",
    category=FutureWarning,
)

import requests
from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")


class PublicOpenApiClient:
    FEATURE_COLUMNS = [
        "area_id",
        "area_name",
        "region",
        "district",
        "admin_dong",
        "business_category_large",
        "business_category_middle",
        "business_category_small",
        "past_commercial_sales",
        "closure_frequency",
        "foot_traffic",
        "age_10s_ratio",
        "age_20s_ratio",
        "age_30s_ratio",
        "age_40s_ratio",
        "age_50s_ratio",
        "age_60s_plus_ratio",
        "past_business_type_count",
        "monthly_rent_per_sqm",
        "monthly_rent_per_pyeong",
        "sale_price",
        "sale_price_per_pyeong",
        "deposit",
        "business_density_per_km2",
        "store_count_in_radius",
        "target_survived_over_1_year",
        "source_snapshot_ym",
        "updated_at",
    ]

    DEFAULT_AREAS = [
        {
            "area_id": "gangnam_station",
            "area_name": "강남역",
            "region": "서울",
            "district": "서초구",
            "admin_dong": "서초2동",
            "cx": 127.02758,
            "cy": 37.49794,
            "radius": 500,
        },
    ]

    def __init__(self):
        self.service_key = os.getenv("DATA_GO_KR_SERVICE_KEY")
        self.data_dir = BACKEND_DIR / "data"

        self.urls = {
            "SBIZ_STORE_API_URL": os.getenv("SBIZ_STORE_API_URL"),
            "MOLIT_COMMERCIAL_TRADE_API_URL": os.getenv("MOLIT_COMMERCIAL_TRADE_API_URL"),
            "MOLIT_COMMERCIAL_RENT_API_URL": os.getenv("MOLIT_COMMERCIAL_RENT_API_URL"),
            "SEOUL_COMMERCIAL_SALES_API_URL": os.getenv("SEOUL_COMMERCIAL_SALES_API_URL"),
            "SEOUL_FOOT_TRAFFIC_API_URL": os.getenv("SEOUL_FOOT_TRAFFIC_API_URL"),
            "SEOUL_STORE_SURVIVAL_API_URL": os.getenv("SEOUL_STORE_SURVIVAL_API_URL"),
            "JUSO_COORD_API_URL": os.getenv("JUSO_COORD_API_URL"),
        }

        self.csv_paths = {
            "sbiz_store": self._path_from_env("SBIZ_STORE_CSV_PATH", "sbiz_store_list.csv"),
            "seoul_sbiz_store_all": self.data_dir / "seoul_sbiz_store_all.csv",
            "sbiz_store_history": self.data_dir / "sbiz_store_history.csv",
            "feature_dataset": self.data_dir / "vacancy_feature_dataset.csv",
            "data_source_status": self.data_dir / "data_source_status.csv",
            "rone_commercial": self._path_from_env(
                "RONE_COMMERCIAL_CSV_PATH",
                "vacancy_Rents_Yields.csv",
            ),
            "localdata_license": self._path_from_env("LOCALDATA_LICENSE_CSV_PATH", "seoul_business_license.csv"),
            "seoul_sales": self._path_from_env("SEOUL_SALES_CSV_PATH", "seoul_commercial_sales.csv"),
            "seoul_foot_traffic": self._path_from_env(
                "SEOUL_FOOT_TRAFFIC_CSV_PATH",
                "seoul_foot_traffic.csv",
            ),
            "seoul_store_survival": self._path_from_env(
                "SEOUL_STORE_SURVIVAL_CSV_PATH",
                "seoul_store_survival.csv",
            ),
            "molit_commercial_trade": self._path_from_env(
                "MOLIT_COMMERCIAL_TRADE_CSV_PATH",
                "molit_commercial_trade.csv",
            ),
            "molit_commercial_rent": self._path_from_env(
                "MOLIT_COMMERCIAL_RENT_CSV_PATH",
                "molit_commercial_rent.csv",
            ),
        }

    def get_list_data(self, params, csv_filename="sbiz_store_list.csv", unique_key="bizesId"):
        data = self._request_json(
            self.urls["SBIZ_STORE_API_URL"],
            params={
                "type": "json",
                **params,
            },
        )
        items = self._extract_items(data)
        self._save_or_update_csv(items, self.data_dir / csv_filename, unique_key)

        return data

    def update_feature_dataset(self, areas=None, output_csv=None):
        areas = areas or self.DEFAULT_AREAS
        source_status = self.update_configured_source_csvs(areas)
        rent_features = self._load_rent_features()
        sales_features = self._load_sales_features()
        population_features = self._load_population_features()
        real_estate_features = self._load_real_estate_features()
        license_features = self._load_license_features()
        feature_rows = []

        for area in areas:
            stores = self.fetch_sbiz_stores_in_radius(area)
            feature_rows.extend(
                self._build_area_feature_rows(
                    area=area,
                    stores=stores,
                    rent_features=rent_features,
                    sales_features=sales_features,
                    population_features=population_features,
                    real_estate_features=real_estate_features,
                    license_features=license_features,
                )
            )

        feature_df = pd.DataFrame(feature_rows, columns=self.FEATURE_COLUMNS)
        output_path = Path(output_csv) if output_csv else self.csv_paths["feature_dataset"]
        self._save_or_update_csv(
            feature_df.to_dict("records"),
            output_path,
            unique_key=[
                "area_id",
                "business_category_large",
                "business_category_middle",
                "business_category_small",
            ],
        )

        self._save_or_update_csv(
            source_status,
            self.csv_paths["data_source_status"],
            unique_key=["source_name"],
        )

        return self._read_csv(output_path)

    def update_configured_source_csvs(self, areas=None):
        areas = areas or self.DEFAULT_AREAS
        status_rows = []
        status_rows.append(self._source_status("sbiz_store_api", True, "상가/업소, 과거 입점 업종, 업종 밀도"))

        api_sources = [
            (
                "seoul_sales",
                self.urls["SEOUL_COMMERCIAL_SALES_API_URL"],
                self.csv_paths["seoul_sales"],
                "과거 상권 매출",
            ),
            (
                "seoul_foot_traffic",
                self.urls["SEOUL_FOOT_TRAFFIC_API_URL"],
                self.csv_paths["seoul_foot_traffic"],
                "유동인구, 연령대 분포",
            ),
            (
                "seoul_store_survival",
                self.urls["SEOUL_STORE_SURVIVAL_API_URL"],
                self.csv_paths["seoul_store_survival"],
                "폐업 빈도, 1년 이상 생존 타깃",
            ),
            (
                "molit_commercial_rent",
                self.urls["MOLIT_COMMERCIAL_RENT_API_URL"],
                self.csv_paths["molit_commercial_rent"],
                "보증금, 월세",
            ),
        ]

        for source_name, url, csv_path, feature_name in api_sources:
            if url:
                rows = self._fetch_json_table(url)
                self._save_or_update_csv(rows, csv_path, unique_key=self._guess_unique_columns(rows))
                status_rows.append(self._source_status(source_name, True, feature_name, csv_path))
            else:
                status_rows.append(self._source_status(source_name, csv_path.exists(), feature_name, csv_path))

        trade_status = self._update_molit_trade_csv(areas)
        status_rows.append(trade_status)
        status_rows.append(
            self._source_status(
                "rone_commercial_csv",
                self.csv_paths["rone_commercial"].exists(),
                "상권 월세, 평당 월세",
                self.csv_paths["rone_commercial"],
            )
        )
        status_rows.append(
            self._source_status(
                "local_license_csv",
                self.csv_paths["localdata_license"] is not None
                and self.csv_paths["localdata_license"].exists(),
                "인허가일자, 폐업일자 기반 폐업 빈도와 타깃",
                self.csv_paths["localdata_license"],
            )
        )

        return status_rows

    def fetch_sbiz_stores_in_radius(self, area, page_no=1, num_rows=200):
        params = {
            "pageNo": page_no,
            "numOfRows": num_rows,
            "radius": area["radius"],
            "cx": area["cx"],
            "cy": area["cy"],
        }
        data = self.get_list_data(params)
        items = self._extract_items(data)
        snapshot_ym = self._extract_snapshot_ym(data)
        fetched_at = self._now()

        for item in items:
            item["area_id"] = area["area_id"]
            item["area_name"] = area["area_name"]
            item["search_radius_m"] = area["radius"]
            item["source_snapshot_ym"] = snapshot_ym
            item["fetched_at"] = fetched_at

        self._save_or_update_csv(
            items,
            self.csv_paths["sbiz_store_history"],
            unique_key=["bizesId", "source_snapshot_ym", "area_id"],
        )

        return pd.DataFrame(items)

    def update_feature_dataset_from_store_csv(self, store_csv=None, output_csv=None):
        store_path = Path(store_csv) if store_csv else self.csv_paths["seoul_sbiz_store_all"]
        if not store_path.exists():
            raise FileNotFoundError(f"서울 전체 상가 CSV가 없습니다: {store_path}")

        stores = self._read_csv(store_path)
        rent_features = self._load_rent_features()
        sales_features = self._load_sales_features()
        population_features = self._load_population_features()
        real_estate_features = self._load_real_estate_features()
        license_features = self._load_license_features()

        stores = stores.copy()
        for column in ["ctprvnNm", "signguNm", "adongNm", "indsLclsNm", "indsMclsNm", "indsSclsNm"]:
            if column not in stores.columns:
                stores[column] = ""
            stores[column] = stores[column].fillna("").astype(str)

        group_columns = ["ctprvnNm", "signguNm", "adongNm", "indsLclsNm", "indsMclsNm", "indsSclsNm"]
        grouped = stores.groupby(group_columns, dropna=False).size().reset_index(name="store_count")
        updated_at = self._now()
        rows = []

        for _, row in grouped.iterrows():
            area = {
                "area_id": f"{row['signguNm']}_{row['adongNm']}",
                "area_name": f"{row['signguNm']} {row['adongNm']}".strip(),
                "region": row["ctprvnNm"].replace("특별시", ""),
                "district": row["signguNm"],
                "admin_dong": row["adongNm"],
            }
            category_key = (
                area["region"],
                row["indsLclsNm"],
                row["indsMclsNm"],
                row["indsSclsNm"],
            )
            rent = rent_features.get(area["region"], {})
            sales_feature = self._lookup_feature(sales_features, area, category_key)
            population_feature = self._lookup_feature(population_features, area, category_key)
            real_estate_feature = self._lookup_feature(real_estate_features, area, category_key)
            license_feature = self._lookup_feature(license_features, area, category_key)
            store_count = int(row["store_count"])

            rows.append(
                {
                    "area_id": area["area_id"],
                    "area_name": area["area_name"],
                    "region": area["region"],
                    "district": area["district"],
                    "admin_dong": area["admin_dong"],
                    "business_category_large": row["indsLclsNm"],
                    "business_category_middle": row["indsMclsNm"],
                    "business_category_small": row["indsSclsNm"],
                    "past_commercial_sales": sales_feature.get("past_commercial_sales", pd.NA),
                    "closure_frequency": license_feature.get("closure_frequency", pd.NA),
                    "foot_traffic": population_feature.get("foot_traffic", pd.NA),
                    "age_10s_ratio": population_feature.get("age_10s_ratio", pd.NA),
                    "age_20s_ratio": population_feature.get("age_20s_ratio", pd.NA),
                    "age_30s_ratio": population_feature.get("age_30s_ratio", pd.NA),
                    "age_40s_ratio": population_feature.get("age_40s_ratio", pd.NA),
                    "age_50s_ratio": population_feature.get("age_50s_ratio", pd.NA),
                    "age_60s_plus_ratio": population_feature.get("age_60s_plus_ratio", pd.NA),
                    "past_business_type_count": store_count,
                    "monthly_rent_per_sqm": rent.get("monthly_rent_per_sqm", pd.NA),
                    "monthly_rent_per_pyeong": rent.get("monthly_rent_per_pyeong", pd.NA),
                    "sale_price": real_estate_feature.get("sale_price", pd.NA),
                    "sale_price_per_pyeong": real_estate_feature.get("sale_price_per_pyeong", pd.NA),
                    "deposit": real_estate_feature.get("deposit", pd.NA),
                    "business_density_per_km2": pd.NA,
                    "store_count_in_radius": store_count,
                    "target_survived_over_1_year": license_feature.get("target_survived_over_1_year", pd.NA),
                    "source_snapshot_ym": stores["source_snapshot_ym"].dropna().max()
                    if "source_snapshot_ym" in stores.columns
                    else pd.NA,
                    "updated_at": updated_at,
                }
            )

        output_path = Path(output_csv) if output_csv else self.csv_paths["feature_dataset"]
        self._save_or_update_csv(
            rows,
            output_path,
            unique_key=[
                "area_id",
                "business_category_large",
                "business_category_middle",
                "business_category_small",
            ],
        )
        self._save_or_update_csv(
            [
                self._source_status(
                    "seoul_sbiz_store_all",
                    store_path.exists(),
                    "서울 전체 상가/업소, 행정동별 업종 수",
                    store_path,
                ),
                self._source_status(
                    "local_license_csv",
                    self.csv_paths["localdata_license"].exists(),
                    "입점일, 폐업일, 폐업 빈도, 1년 이상 생존 타깃",
                    self.csv_paths["localdata_license"],
                ),
                self._source_status(
                    "rone_commercial_csv",
                    self.csv_paths["rone_commercial"].exists(),
                    "상권 월세, 평당 월세",
                    self.csv_paths["rone_commercial"],
                ),
            ],
            self.csv_paths["data_source_status"],
            unique_key=["source_name"],
        )

        return self._read_csv(output_path)

    def _build_area_feature_rows(
        self,
        area,
        stores,
        rent_features,
        sales_features,
        population_features,
        real_estate_features,
        license_features,
    ):
        updated_at = self._now()
        rent = rent_features.get(area["region"], {})

        if stores.empty:
            return [
                self._empty_feature_row(
                    area=area,
                    rent=rent,
                    updated_at=updated_at,
                )
            ]

        stores = stores.copy()
        stores["indsLclsNm"] = stores.get("indsLclsNm", pd.Series(dtype="object")).fillna("")
        stores["indsMclsNm"] = stores.get("indsMclsNm", pd.Series(dtype="object")).fillna("")
        stores["indsSclsNm"] = stores.get("indsSclsNm", pd.Series(dtype="object")).fillna("")

        group_columns = ["indsLclsNm", "indsMclsNm", "indsSclsNm"]
        category_counts = stores.groupby(group_columns, dropna=False).size().reset_index(name="count")
        total_store_count = int(len(stores))
        density = self._calculate_density(total_store_count, area["radius"])
        snapshot_ym = stores["source_snapshot_ym"].dropna().max() if "source_snapshot_ym" in stores else pd.NA

        rows = []
        for _, category in category_counts.iterrows():
            category_key = (
                area["region"],
                category["indsLclsNm"],
                category["indsMclsNm"],
                category["indsSclsNm"],
            )
            sales_feature = self._lookup_feature(sales_features, area, category_key)
            population_feature = self._lookup_feature(population_features, area, category_key)
            real_estate_feature = self._lookup_feature(real_estate_features, area, category_key)
            license_feature = self._lookup_feature(license_features, area, category_key)

            rows.append(
                {
                    "area_id": area["area_id"],
                    "area_name": area["area_name"],
                    "region": area["region"],
                    "district": area.get("district"),
                    "admin_dong": area.get("admin_dong"),
                    "business_category_large": category["indsLclsNm"],
                    "business_category_middle": category["indsMclsNm"],
                    "business_category_small": category["indsSclsNm"],
                    "past_commercial_sales": sales_feature.get("past_commercial_sales", pd.NA),
                    "closure_frequency": license_feature.get("closure_frequency", pd.NA),
                    "foot_traffic": population_feature.get("foot_traffic", pd.NA),
                    "age_10s_ratio": population_feature.get("age_10s_ratio", pd.NA),
                    "age_20s_ratio": population_feature.get("age_20s_ratio", pd.NA),
                    "age_30s_ratio": population_feature.get("age_30s_ratio", pd.NA),
                    "age_40s_ratio": population_feature.get("age_40s_ratio", pd.NA),
                    "age_50s_ratio": population_feature.get("age_50s_ratio", pd.NA),
                    "age_60s_plus_ratio": population_feature.get("age_60s_plus_ratio", pd.NA),
                    "past_business_type_count": int(category["count"]),
                    "monthly_rent_per_sqm": rent.get("monthly_rent_per_sqm", pd.NA),
                    "monthly_rent_per_pyeong": rent.get("monthly_rent_per_pyeong", pd.NA),
                    "sale_price": real_estate_feature.get("sale_price", pd.NA),
                    "sale_price_per_pyeong": real_estate_feature.get("sale_price_per_pyeong", pd.NA),
                    "deposit": real_estate_feature.get("deposit", pd.NA),
                    "business_density_per_km2": density,
                    "store_count_in_radius": total_store_count,
                    "target_survived_over_1_year": license_feature.get(
                        "target_survived_over_1_year",
                        pd.NA,
                    ),
                    "source_snapshot_ym": snapshot_ym,
                    "updated_at": updated_at,
                }
            )

        return rows

    def _empty_feature_row(self, area, rent, updated_at):
        return {
            "area_id": area["area_id"],
            "area_name": area["area_name"],
            "region": area["region"],
            "district": area.get("district"),
            "admin_dong": area.get("admin_dong"),
            "business_category_large": pd.NA,
            "business_category_middle": pd.NA,
            "business_category_small": pd.NA,
            "past_commercial_sales": pd.NA,
            "closure_frequency": pd.NA,
            "foot_traffic": pd.NA,
            "age_10s_ratio": pd.NA,
            "age_20s_ratio": pd.NA,
            "age_30s_ratio": pd.NA,
            "age_40s_ratio": pd.NA,
            "age_50s_ratio": pd.NA,
            "age_60s_plus_ratio": pd.NA,
            "past_business_type_count": 0,
            "monthly_rent_per_sqm": rent.get("monthly_rent_per_sqm", pd.NA),
            "monthly_rent_per_pyeong": rent.get("monthly_rent_per_pyeong", pd.NA),
            "sale_price": pd.NA,
            "sale_price_per_pyeong": pd.NA,
            "deposit": pd.NA,
            "business_density_per_km2": 0,
            "store_count_in_radius": 0,
            "target_survived_over_1_year": pd.NA,
            "source_snapshot_ym": pd.NA,
            "updated_at": updated_at,
        }

    def _load_rent_features(self):
        path = self.csv_paths["rone_commercial"]
        if not path.exists():
            return {}

        df = self._read_csv(path)
        latest_quarter = self._latest_time_column(df.columns, marker="/4")
        if latest_quarter is None:
            return {}

        rent_rows = df[df["구분별"].eq("임대료")]
        rent_features = {}

        for _, row in rent_rows.iterrows():
            rent_per_sqm = pd.to_numeric(row.get(latest_quarter), errors="coerce")
            rent_features[row["지역별"]] = {
                "monthly_rent_per_sqm": rent_per_sqm,
                "monthly_rent_per_pyeong": rent_per_sqm * 3.3058 if pd.notna(rent_per_sqm) else pd.NA,
            }

        return rent_features

    def _load_sales_features(self):
        path = self.csv_paths["seoul_sales"]
        if not path.exists():
            return {}

        df = self._read_csv(path)
        sales_col = self._find_first_column(
            df,
            ["past_commercial_sales", "당월_매출_금액", "분기당_매출_금액", "월_매출_금액", "selng_amt"],
        )
        if not sales_col:
            return {}

        return self._aggregate_optional_features(
            df,
            {"past_commercial_sales": sales_col},
        )

    def _load_population_features(self):
        path = self.csv_paths["seoul_foot_traffic"]
        if not path.exists():
            return {}

        df = self._read_csv(path)
        value_columns = {
            "foot_traffic": self._find_first_column(
                df,
                ["foot_traffic", "총_유동인구_수", "총생활인구수", "tot_flpop_co", "tot_lvpop_co"],
            ),
            "age_10s_ratio": self._find_first_column(df, ["age_10s_ratio", "10대", "agrde_10"]),
            "age_20s_ratio": self._find_first_column(df, ["age_20s_ratio", "20대", "agrde_20"]),
            "age_30s_ratio": self._find_first_column(df, ["age_30s_ratio", "30대", "agrde_30"]),
            "age_40s_ratio": self._find_first_column(df, ["age_40s_ratio", "40대", "agrde_40"]),
            "age_50s_ratio": self._find_first_column(df, ["age_50s_ratio", "50대", "agrde_50"]),
            "age_60s_plus_ratio": self._find_first_column(df, ["age_60s_plus_ratio", "60대", "agrde_60"]),
        }
        value_columns = {name: column for name, column in value_columns.items() if column}
        if not value_columns:
            return {}

        return self._aggregate_optional_features(df, value_columns)

    def _load_real_estate_features(self):
        feature_map = {}

        trade_path = self.csv_paths["molit_commercial_trade"]
        if trade_path.exists():
            trade_df = self._read_csv(trade_path)
            trade_features = self._aggregate_optional_features(
                trade_df,
                {
                    "sale_price": self._find_first_column(
                        trade_df,
                        ["sale_price", "거래금액", "dealAmount", "deal_amount"],
                    ),
                    "sale_price_per_pyeong": self._find_first_column(
                        trade_df,
                        ["sale_price_per_pyeong", "평당거래금액", "dealAmountPerPyeong"],
                    ),
                },
            )
            feature_map.update(trade_features)

        rent_path = self.csv_paths["molit_commercial_rent"]
        if rent_path.exists():
            rent_df = self._read_csv(rent_path)
            rent_features = self._aggregate_optional_features(
                rent_df,
                {
                    "deposit": self._find_first_column(rent_df, ["deposit", "보증금", "depositAmount"]),
                    "monthly_rent_per_sqm": self._find_first_column(
                        rent_df,
                        ["monthly_rent_per_sqm", "월세", "monthlyRent"],
                    ),
                },
            )

            for key, values in rent_features.items():
                feature_map.setdefault(key, {}).update(values)

        return feature_map

    def _load_license_features(self):
        path = self.csv_paths["localdata_license"]
        if path is None or not path.exists():
            return {}

        df = self._read_csv(path)
        open_col = self._find_first_column(df, ["인허가일자", "LICENSG_DE", "opnSvcDt"])
        close_col = self._find_first_column(df, ["폐업일자", "CLSBIZ_DE", "dcbYmd"])
        state_col = self._find_first_column(df, ["영업상태명", "영업상태", "BSN_STATE_NM", "trdStateNm"])
        region_col = self._find_first_column(df, ["시도명", "지역별", "CTPRVN_NM", "siteWhlAddr"])
        district_col = self._find_first_column(df, ["시군구명", "소재지전체주소", "도로명전체주소", "siteWhlAddr", "rdnWhlAddr"])
        large_col = self._find_first_column(df, ["상권업종대분류명", "업태구분명", "업종명"])
        middle_col = self._find_first_column(df, ["상권업종중분류명", "위생업태명"])
        small_col = self._find_first_column(df, ["상권업종소분류명", "상세영업상태명"])

        if not open_col:
            return {}

        df["_region"] = df[region_col].apply(self._extract_seoul_region) if region_col else "서울"
        df["_district"] = df[district_col].apply(self._extract_seoul_district) if district_col else ""
        df["_opened_at"] = pd.to_datetime(df[open_col], errors="coerce")
        df["_closed_at"] = pd.to_datetime(df[close_col], errors="coerce") if close_col else pd.NaT
        df["_closed"] = False

        if state_col:
            df["_closed"] = df[state_col].astype(str).str.contains("폐업|취소|말소|만료|정지|중지", regex=True)
        if close_col:
            df["_closed"] = df["_closed"] | df["_closed_at"].notna()

        df["_business_days"] = (df["_closed_at"].fillna(pd.Timestamp.today()) - df["_opened_at"]).dt.days
        df["_survived_over_1_year"] = df["_business_days"].ge(365)

        features = {}
        group_sets = [
            ["_region"],
            ["_region", "_district"],
        ]
        category_columns = [column for column in [large_col, middle_col, small_col] if column]
        if category_columns:
            group_sets.append(["_region", *category_columns])
            group_sets.append(["_region", "_district", *category_columns])

        valid_df = df.dropna(subset=["_opened_at"])
        for group_columns in group_sets:
            for key, group in valid_df.groupby(group_columns, dropna=False):
                key = key if isinstance(key, tuple) else (key,)
                features[self._normalize_feature_key(key)] = self._license_summary(group)

        return features

    def _license_summary(self, group):
        return {
            "closure_frequency": float(group["_closed"].mean()),
            "target_survived_over_1_year": float(group["_survived_over_1_year"].mean()),
        }

    def _update_molit_trade_csv(self, areas):
        url = self.urls["MOLIT_COMMERCIAL_TRADE_API_URL"]
        csv_path = self.csv_paths["molit_commercial_trade"]
        if not url:
            return self._source_status("molit_commercial_trade", csv_path.exists(), "상권 매매가", csv_path)

        rows = []
        last_error = ""
        for area in areas:
            lawd_cd = area.get("lawd_cd") or self._guess_lawd_cd(area)
            deal_ymd = area.get("deal_ymd") or os.getenv("MOLIT_DEAL_YMD", "202501")
            if not lawd_cd:
                continue

            try:
                data = self._request_xml_or_json(
                    url,
                    params={
                        "LAWD_CD": lawd_cd,
                        "DEAL_YMD": deal_ymd,
                        "numOfRows": 100,
                        "pageNo": 1,
                    },
                )
            except requests.HTTPError as error:
                last_error = f"HTTP {error.response.status_code}"
                continue

            items = self._extract_items(data) if isinstance(data, dict) else data
            for item in items:
                item["area_id"] = area["area_id"]
                item["area_name"] = area["area_name"]
                item["region"] = area["region"]
                item["district"] = area.get("district")
                item["deal_ymd"] = deal_ymd
                item["fetched_at"] = self._now()
                item["sale_price"] = self._number_from_any(
                    item.get("dealAmount")
                    or item.get("거래금액")
                    or item.get("deal_amount")
                )
                area_sqm = self._number_from_any(
                    item.get("excluUseAr")
                    or item.get("전용면적")
                    or item.get("area")
                )
                if pd.notna(item["sale_price"]) and area_sqm and pd.notna(area_sqm):
                    item["sale_price_per_pyeong"] = item["sale_price"] / (area_sqm / 3.3058)
            rows.extend(items)

        if rows:
            self._save_or_update_csv(
                rows,
                csv_path,
                unique_key=self._guess_unique_columns(rows),
            )

        status = self._source_status("molit_commercial_trade", bool(rows) or csv_path.exists(), "상권 매매가", csv_path)
        status["message"] = last_error
        return status

    def _fetch_json_table(self, url):
        if not url:
            return []

        response = requests.get(url, timeout=30)
        response.raise_for_status()

        try:
            data = response.json()
        except ValueError:
            return self._xml_text_to_rows(response.text)

        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            items = self._extract_items(data)
            if items:
                return items
            for value in data.values():
                if isinstance(value, dict) and "row" in value:
                    return value["row"]
                if isinstance(value, list):
                    return value
        return []

    def _request_xml_or_json(self, url, params):
        if not self.service_key:
            raise ValueError("DATA_GO_KR_SERVICE_KEY가 .env에 설정되어 있지 않습니다.")

        response = requests.get(
            url,
            params={
                **params,
                "serviceKey": self.service_key,
            },
            timeout=30,
        )
        response.raise_for_status()

        try:
            return response.json()
        except ValueError:
            return self._xml_text_to_rows(response.text)

    def _xml_text_to_rows(self, text):
        root = ElementTree.fromstring(text)
        rows = []

        for item in root.findall(".//item"):
            row = {}
            for child in list(item):
                row[child.tag] = child.text
            rows.append(row)

        return rows

    def _aggregate_optional_features(self, df, value_columns):
        area_columns = self._infer_area_columns(df)
        category_columns = self._infer_category_columns(df)
        value_columns = {name: column for name, column in value_columns.items() if column}
        if not value_columns:
            return {}

        for column in value_columns.values():
            df[column] = df[column].apply(self._number_from_any)

        group_columns = [column for column in area_columns + category_columns if column]

        feature_map = {}
        grouped = df.groupby(group_columns, dropna=False) if group_columns else [(("",), df)]

        for key, group in grouped:
            key = key if isinstance(key, tuple) else (key,)
            map_key = self._normalize_feature_key(key)
            feature_map[map_key] = {
                feature_name: pd.to_numeric(group[column], errors="coerce").mean()
                for feature_name, column in value_columns.items()
            }

        return feature_map

    def _lookup_feature(self, feature_map, area, category_key):
        if not feature_map:
            return {}

        large, middle, small = category_key[1], category_key[2], category_key[3]
        candidates = [
            (area.get("area_id"), large, middle, small),
            (area.get("area_name"), large, middle, small),
            (area.get("region"), area.get("district"), area.get("admin_dong"), large, middle, small),
            (area.get("region"), area.get("district"), large, middle, small),
            (area.get("region"), large, middle, small),
            (area.get("region"), area.get("district"), area.get("admin_dong")),
            (area.get("region"), area.get("district")),
            (area.get("region"),),
            (area.get("area_id"),),
            (area.get("area_name"),),
        ]

        for candidate in candidates:
            key = self._normalize_feature_key(candidate)
            if key in feature_map:
                return feature_map[key]
        return {}

    def _infer_area_columns(self, df):
        candidates = [
            ["area_id", "상권_코드", "TRDAR_CD"],
            ["area_name", "상권_코드_명", "TRDAR_CD_NM"],
            ["region", "시도명", "지역별", "CTPRVN_NM"],
            ["district", "시군구명", "자치구_코드_명", "SIGNGU_NM"],
            ["admin_dong", "행정동명", "행정동_코드_명", "ADSTRD_NM"],
        ]
        return [self._find_first_column(df, group) for group in candidates if self._find_first_column(df, group)]

    def _infer_category_columns(self, df):
        candidates = [
            ["business_category_large", "상권업종대분류명", "서비스_업종_코드_명", "indsLclsNm"],
            ["business_category_middle", "상권업종중분류명", "indsMclsNm"],
            ["business_category_small", "상권업종소분류명", "indsSclsNm"],
        ]
        return [self._find_first_column(df, group) for group in candidates if self._find_first_column(df, group)]

    def _request_json(self, url, params):
        if not url:
            raise ValueError("API URL이 .env에 설정되어 있지 않습니다.")
        if not self.service_key:
            raise ValueError("DATA_GO_KR_SERVICE_KEY가 .env에 설정되어 있지 않습니다.")

        response = requests.get(
            url,
            params={
                **params,
                "serviceKey": self.service_key,
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def _extract_items(self, data):
        body = data.get("body") or data.get("response", {}).get("body", {})
        items = body.get("items", [])

        if isinstance(items, dict):
            item_list = items.get("item", [])
        else:
            item_list = items

        if isinstance(item_list, dict):
            return [item_list]

        return item_list or []

    def _extract_snapshot_ym(self, data):
        header = data.get("header") or data.get("response", {}).get("header", {})
        return header.get("stdrYm", pd.NA)

    def _save_or_update_csv(self, items, csv_path, unique_key):
        if isinstance(items, pd.DataFrame):
            new_data = items.copy()
        else:
            items = list(items or [])
            if not items:
                return
            new_data = pd.DataFrame(items)

        self.data_dir.mkdir(parents=True, exist_ok=True)
        csv_path = Path(csv_path)
        csv_path.parent.mkdir(parents=True, exist_ok=True)

        if csv_path.exists():
            old_data = self._read_csv(csv_path)
            merged_data = pd.concat([old_data, new_data], ignore_index=True)
        else:
            merged_data = new_data

        unique_columns = self._normalize_unique_key(unique_key)
        if all(column in merged_data.columns for column in unique_columns):
            for column in unique_columns:
                merged_data[column] = merged_data[column].astype(str)
            merged_data = merged_data.drop_duplicates(
                subset=unique_columns,
                keep="last",
            )

        merged_data.to_csv(csv_path, index=False, encoding="utf-8-sig")

    def _read_csv(self, path):
        try:
            return pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
        except pd.errors.ParserError:
            return pd.read_csv(
                path,
                encoding="utf-8-sig",
                engine="python",
                on_bad_lines="skip",
            )

    def _path_from_env(self, env_name, default_filename):
        value = os.getenv(env_name)
        return Path(value).expanduser() if value else self.data_dir / default_filename

    def _optional_path_from_env(self, env_name):
        value = os.getenv(env_name)
        return Path(value).expanduser() if value else None

    def _normalize_unique_key(self, unique_key):
        if isinstance(unique_key, str):
            return [unique_key]
        if isinstance(unique_key, Iterable):
            return list(unique_key)
        return []

    def _guess_unique_columns(self, rows):
        if not rows:
            return []

        columns = set(rows[0].keys())
        candidate_groups = [
            ["bizesId"],
            ["area_id", "business_category_large", "business_category_middle", "business_category_small"],
            ["area_id", "deal_ymd", "dealAmount", "excluUseAr"],
            ["상권_코드", "서비스_업종_코드", "기준_년분기_코드"],
            ["TRDAR_CD", "SVC_INDUTY_CD", "STDR_YYQU_CD"],
        ]

        for group in candidate_groups:
            if all(column in columns for column in group):
                return group
        return list(rows[0].keys())

    def _normalize_feature_key(self, values):
        if isinstance(values, str):
            values = (values,)
        return tuple(
            str(value).strip()
            for value in values
            if value is not None and str(value).strip() and str(value).strip().lower() != "nan"
        )

    def _source_status(self, source_name, available, feature_name, path=None):
        return {
            "source_name": source_name,
            "available": bool(available),
            "feature_name": feature_name,
            "path": str(path) if path else "",
            "updated_at": self._now(),
        }

    def _number_from_any(self, value):
        if value is None or pd.isna(value):
            return pd.NA

        cleaned = str(value).replace(",", "").replace(" ", "").strip()
        if not cleaned:
            return pd.NA

        number = pd.to_numeric(cleaned, errors="coerce")
        return number if pd.notna(number) else pd.NA

    def _extract_seoul_region(self, value):
        text = "" if value is None or pd.isna(value) else str(value)
        return "서울" if "서울" in text else text.strip()

    def _extract_seoul_district(self, value):
        text = "" if value is None or pd.isna(value) else str(value)
        for token in text.replace(",", " ").split():
            if token.endswith("구"):
                return token
        return ""

    def _guess_lawd_cd(self, area):
        district = area.get("district")
        known_codes = {
            "종로구": "11110",
            "중구": "11140",
            "용산구": "11170",
            "성동구": "11200",
            "광진구": "11215",
            "동대문구": "11230",
            "중랑구": "11260",
            "성북구": "11290",
            "강북구": "11305",
            "도봉구": "11320",
            "노원구": "11350",
            "은평구": "11380",
            "서대문구": "11410",
            "마포구": "11440",
            "양천구": "11470",
            "강서구": "11500",
            "구로구": "11530",
            "금천구": "11545",
            "영등포구": "11560",
            "동작구": "11590",
            "관악구": "11620",
            "서초구": "11650",
            "강남구": "11680",
            "송파구": "11710",
            "강동구": "11740",
        }
        return known_codes.get(district)

    def _latest_time_column(self, columns, marker):
        candidates = [column for column in columns if marker in str(column)]
        return candidates[-1] if candidates else None

    def _find_first_column(self, df, candidates):
        normalized = {str(column).lower(): column for column in df.columns}
        for candidate in candidates:
            candidate_lower = candidate.lower()
            if candidate_lower in normalized:
                return normalized[candidate_lower]
            for column in df.columns:
                if candidate_lower in str(column).lower():
                    return column
        return None

    def _calculate_density(self, count, radius_m):
        area_km2 = 3.141592653589793 * (radius_m / 1000) ** 2
        return count / area_km2 if area_km2 else 0

    def _now(self):
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
