# 생존 확률 모델용 최종 특성 파일 생성
from pathlib import Path

import pandas as pd


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
LICENSE_PATH = DATA_DIR / "seoul_business_license.csv"
CONTEXT_PATH = DATA_DIR / "vacancy_quarterly_timeseries.csv"
OUTPUT_PATH = DATA_DIR / "survival_model_dataset.csv"
LEGEND_PATH = DATA_DIR / "survival_model_dataset_columns.csv"


OUTPUT_COLUMNS = [
    "period",
    "year",
    "quarter",
    "region",
    "district",
    "business_type",
    "active_business_count_start",
    "prev_active_business_count_end",
    "prev_openings_in_quarter",
    "prev_closures_in_quarter",
    "prev_closure_frequency",
    "monthly_rent_per_sqm",
    "monthly_rent_per_pyeong",
    "vacancy_rate",
    "investment_yield",
    "current_sbiz_store_count",
    "target_survived_over_1_year",
]

REQUIRED_FEATURE_COLUMNS = [
    "active_business_count_start",
    "prev_active_business_count_end",
    "prev_openings_in_quarter",
    "prev_closures_in_quarter",
    "prev_closure_frequency",
    "monthly_rent_per_sqm",
    "monthly_rent_per_pyeong",
    "vacancy_rate",
    "investment_yield",
    "current_sbiz_store_count",
]


def main():
    license_df = pd.read_csv(LICENSE_PATH, low_memory=False)
    context_df = pd.read_csv(CONTEXT_PATH, low_memory=False)
    model_df = build_survival_model_dataset(license_df, context_df)

    model_df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")
    build_column_legend().to_csv(LEGEND_PATH, index=False, encoding="utf-8-sig")

    print(f"created_or_updated={OUTPUT_PATH}")
    print(f"rows={len(model_df)}")
    print(f"columns={len(model_df.columns)}")
    print(f"periods={model_df['period'].min()}..{model_df['period'].max()}")
    print(f"districts={model_df['district'].nunique()}")
    print(f"business_types={model_df['business_type'].nunique()}")
    print("target_values=" + ",".join(map(str, sorted(model_df["target_survived_over_1_year"].unique()))))
    print(model_df["target_survived_over_1_year"].value_counts().sort_index().to_string())


def build_survival_model_dataset(license_df, context_df, as_of_date=None):
    business_df = build_business_target_rows(license_df, as_of_date=as_of_date)
    feature_df = build_context_feature_rows(context_df)

    model_df = business_df.merge(
        feature_df,
        on=["period", "district", "business_type"],
        how="left",
        validate="many_to_one",
    )
    model_df = model_df.dropna(subset=REQUIRED_FEATURE_COLUMNS).copy()
    model_df = model_df.sort_values(
        ["period", "district", "business_type", "opened_at"],
        kind="mergesort",
    )

    model_df["year"] = model_df["year"].astype("int64")
    model_df["quarter"] = model_df["quarter"].astype("int64")
    model_df["target_survived_over_1_year"] = model_df["target_survived_over_1_year"].astype("int64")

    return model_df[OUTPUT_COLUMNS].reset_index(drop=True)


def build_business_target_rows(license_df, as_of_date=None):
    required_columns = ["license_date", "business_type", "district"]
    missing_columns = [column for column in required_columns if column not in license_df.columns]
    if missing_columns:
        raise ValueError(f"인허가 CSV에 필요한 컬럼이 없습니다: {missing_columns}")

    df = license_df.copy()
    df["opened_at"] = pd.to_datetime(df["license_date"], errors="coerce")
    df["closed_at"] = pd.to_datetime(df.get("closed_date"), errors="coerce")
    df = df[df["opened_at"].notna()]
    df = df[df["district"].notna() & df["business_type"].notna()]

    current_as_of_date = resolve_as_of_date(df, as_of_date=as_of_date)
    df = df[df["opened_at"].le(current_as_of_date)].copy()
    df["business_duration_days"] = (df["closed_at"].fillna(current_as_of_date) - df["opened_at"]).dt.days
    df = df[df["business_duration_days"].ge(0)].copy()

    old_enough_open_business = df["opened_at"].le(current_as_of_date - pd.Timedelta(days=365))
    closed_status_without_date = detect_closed_status_without_date(df)
    df["target_known"] = old_enough_open_business & ~closed_status_without_date
    df = df[df["target_known"]].copy()
    df["target_survived_over_1_year"] = df["business_duration_days"].ge(365).astype("int64")

    df["period"] = df["opened_at"].dt.to_period("Q").astype(str)
    df["year"] = df["opened_at"].dt.year
    df["quarter"] = df["opened_at"].dt.quarter
    df["region"] = df["region"] if "region" in df.columns else "서울"
    df["region"] = df["region"].fillna("서울")

    return df[
        [
            "period",
            "year",
            "quarter",
            "region",
            "district",
            "business_type",
            "opened_at",
            "target_survived_over_1_year",
        ]
    ].copy()


def build_context_feature_rows(context_df):
    required_columns = [
        "period",
        "district",
        "business_type",
        "active_business_count_start",
        "active_business_count_end",
        "openings_in_quarter",
        "closures_in_quarter",
        "closure_frequency",
    ]
    missing_columns = [column for column in required_columns if column not in context_df.columns]
    if missing_columns:
        raise ValueError(f"분기별 CSV에 필요한 컬럼이 없습니다: {missing_columns}")

    df = context_df.copy()
    if "license_source" in df.columns:
        df = df[df["license_source"].ne("seoul_open_data_admindong")].copy()

    df = df[df["period"].notna() & df["district"].notna() & df["business_type"].notna()].copy()
    df["period_order"] = df["period"].apply(period_to_order)
    df = df.sort_values(["district", "business_type", "period_order"], kind="mergesort")

    lag_columns = {
        "active_business_count_end": "prev_active_business_count_end",
        "openings_in_quarter": "prev_openings_in_quarter",
        "closures_in_quarter": "prev_closures_in_quarter",
        "closure_frequency": "prev_closure_frequency",
    }
    group = df.groupby(["district", "business_type"], dropna=False)
    for source_column, output_column in lag_columns.items():
        df[output_column] = group[source_column].shift(1)

    feature_columns = [
        "period",
        "district",
        "business_type",
        *REQUIRED_FEATURE_COLUMNS,
    ]
    return df[feature_columns].drop_duplicates(
        subset=["period", "district", "business_type"],
        keep="last",
    )


def detect_closed_status_without_date(df):
    if "business_status" not in df.columns:
        return pd.Series(False, index=df.index)

    status = df["business_status"].fillna("").astype(str).str.lower()
    is_closed_status = status.str.contains("폐업|closed|close", regex=True, na=False)
    return is_closed_status & df["closed_at"].isna()


def resolve_as_of_date(df, as_of_date=None):
    if as_of_date is not None:
        return pd.Timestamp(as_of_date).normalize()

    date_candidates = [pd.Timestamp.today().normalize()]
    if df["opened_at"].notna().any():
        date_candidates.append(df["opened_at"].max().normalize())
    if df["closed_at"].notna().any():
        date_candidates.append(df["closed_at"].max().normalize())
    return max(date_candidates)


def period_to_order(period):
    year = int(str(period)[:4])
    quarter = int(str(period)[-1])
    return year * 4 + quarter


def build_column_legend():
    rows = [
        ("period", "meta", "사업장이 인허가를 받은 분기"),
        ("year", "feature_time", "인허가 연도"),
        ("quarter", "feature_time", "인허가 분기"),
        ("region", "feature_location", "지역"),
        ("district", "feature_location", "서울 자치구"),
        ("business_type", "feature_category", "입력 업종"),
        ("active_business_count_start", "feature_market", "입점 분기 시작 시 영업 중인 동일 업종 사업체 수"),
        ("prev_active_business_count_end", "feature_market_lag", "전분기 말 영업 중인 동일 업종 사업체 수"),
        ("prev_openings_in_quarter", "feature_market_lag", "전분기 동일 업종 신규 입점 수"),
        ("prev_closures_in_quarter", "feature_market_lag", "전분기 동일 업종 폐업 수"),
        ("prev_closure_frequency", "feature_market_lag", "전분기 동일 업종 폐업 빈도"),
        ("monthly_rent_per_sqm", "feature_rent", "입점 분기 제곱미터당 월 임대료"),
        ("monthly_rent_per_pyeong", "feature_rent", "입점 분기 평당 월 임대료"),
        ("vacancy_rate", "feature_rent", "입점 분기 공실률"),
        ("investment_yield", "feature_rent", "입점 분기 투자수익률"),
        ("current_sbiz_store_count", "feature_context", "현재 기준 자치구 상가업소 수"),
        ("target_survived_over_1_year", "target", "1년 이상 영업 지속 여부: 1=생존, 0=1년 내 폐업"),
    ]
    return pd.DataFrame(rows, columns=["column", "group", "note"])


if __name__ == "__main__":
    main()
