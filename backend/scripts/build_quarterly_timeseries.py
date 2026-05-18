# 분기별 시계열 모델 데이터 생성
from pathlib import Path
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT / "backend"))

from app.data_sources import PublicOpenApiClient


OUTPUT_COLUMNS = [
    "period",
    "period_start",
    "period_end",
    "region",
    "district",
    "license_source",
    "business_type",
    "active_business_count_start",
    "active_business_count_end",
    "openings_in_quarter",
    "closures_in_quarter",
    "closure_frequency",
    "target_survived_over_1_year",
    "target_known_count",
    "monthly_rent_per_sqm",
    "monthly_rent_per_pyeong",
    "vacancy_rate",
    "investment_yield",
    "current_sbiz_store_count",
    "updated_at",
]


def main():
    client = PublicOpenApiClient()
    output_path = client.data_dir / "vacancy_quarterly_timeseries.csv"

    license_df = load_license_data(client)
    rent_df = load_quarterly_rent_data(client)
    current_store_counts = load_current_store_counts(client)
    periods = build_periods(license_df, rent_df)

    rows = build_quarterly_rows(
        client=client,
        license_df=license_df,
        rent_df=rent_df,
        current_store_counts=current_store_counts,
        periods=periods,
    )

    output_df = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    output_df.to_csv(output_path, index=False, encoding="utf-8-sig")

    print(f"created_or_updated={output_path}")
    print(f"rows={len(output_df)}")
    print(f"periods={output_df['period'].min()}..{output_df['period'].max()}")
    print(f"districts={output_df['district'].nunique()}")
    print(f"target_nonnull={output_df['target_survived_over_1_year'].notna().sum()}")
    print(f"closure_frequency_nonnull={output_df['closure_frequency'].notna().sum()}")


def load_license_data(client):
    path = client.csv_paths["localdata_license"]
    if not path.exists():
        raise FileNotFoundError(f"서울 인허가 CSV가 없습니다: {path}")

    df = pd.read_csv(path, low_memory=False)
    required_columns = ["license_date", "closed_date", "district"]
    missing_columns = [column for column in required_columns if column not in df.columns]
    if missing_columns:
        raise ValueError(f"인허가 CSV에 필요한 컬럼이 없습니다: {missing_columns}")

    df = df.copy()
    df["opened_at"] = pd.to_datetime(df["license_date"], errors="coerce")
    df["closed_at"] = pd.to_datetime(df["closed_date"], errors="coerce")
    df["license_source"] = df.get("license_source", "localdata").fillna("localdata")
    df["business_type"] = df.get("business_type", df.get("개방서비스명", "unknown")).fillna("unknown")
    df = df[df["opened_at"].notna()]
    df = df[df["district"].notna()]

    as_of_date = max(pd.Timestamp.today().normalize(), df["closed_at"].dropna().max())
    df["business_days"] = (df["closed_at"].fillna(as_of_date) - df["opened_at"]).dt.days
    df["target_known"] = df["closed_at"].notna() | df["opened_at"].le(as_of_date - pd.Timedelta(days=365))
    df["survived_over_1_year"] = df["business_days"].ge(365)

    return df


def load_quarterly_rent_data(client):
    path = client.csv_paths["rone_commercial"]
    if not path.exists():
        return pd.DataFrame(columns=["period"])

    raw_df = read_csv_safely(path)
    seoul_df = raw_df[raw_df["지역별"].astype(str).eq("서울")]
    quarter_columns = [
        column
        for column in seoul_df.columns
        if isinstance(column, str) and "." in column and "/4" in column
    ]

    metric_map = {
        "임대료": "monthly_rent_per_sqm",
        "공실률": "vacancy_rate",
        "투자수익률": "investment_yield",
    }
    rows = {}

    for _, row in seoul_df.iterrows():
        metric_name = metric_map.get(str(row.get("구분별")))
        if not metric_name:
            continue

        for quarter_column in quarter_columns:
            period = quarter_column_to_period(quarter_column)
            if not period:
                continue
            rows.setdefault(period, {"period": period})
            rows[period][metric_name] = to_number(row.get(quarter_column))

    rent_df = pd.DataFrame(rows.values())
    if rent_df.empty:
        return pd.DataFrame(columns=["period"])

    rent_df["monthly_rent_per_pyeong"] = rent_df["monthly_rent_per_sqm"] * 3.3058
    return rent_df


def load_current_store_counts(client):
    path = client.csv_paths["seoul_sbiz_store_all"]
    if not path.exists():
        return {}

    store_df = pd.read_csv(path, usecols=["signguNm"], low_memory=False)
    counts = store_df.groupby("signguNm").size()
    return counts.to_dict()


def build_periods(license_df, rent_df):
    min_period = "2013Q1"
    latest_license_quarter = timestamp_to_period(license_df["opened_at"].max())
    latest_rent_quarter = rent_df["period"].max() if not rent_df.empty else latest_license_quarter
    max_period = max(latest_license_quarter, latest_rent_quarter)

    period_index = pd.period_range(min_period, max_period, freq="Q")
    return [
        {
            "period": str(period).replace("Q", "Q"),
            "start": period.start_time.normalize(),
            "end": period.end_time.normalize(),
        }
        for period in period_index
    ]


def build_quarterly_rows(client, license_df, rent_df, current_store_counts, periods):
    updated_at = client._now()
    rent_by_period = rent_df.set_index("period").to_dict("index") if not rent_df.empty else {}
    groups = license_df[["district", "license_source", "business_type"]].drop_duplicates()
    rows = []

    for _, group in groups.iterrows():
        district = group["district"]
        license_source = group["license_source"]
        business_type = group["business_type"]
        group_df = license_df[
            license_df["district"].eq(district)
            & license_df["license_source"].eq(license_source)
            & license_df["business_type"].eq(business_type)
        ]

        for period in periods:
            period_name = period["period"]
            start = period["start"]
            end = period["end"]
            opened_before_start = group_df["opened_at"].lt(start)
            not_closed_before_start = group_df["closed_at"].isna() | group_df["closed_at"].ge(start)
            active_start = int((opened_before_start & not_closed_before_start).sum())

            opened_before_end = group_df["opened_at"].le(end)
            not_closed_by_end = group_df["closed_at"].isna() | group_df["closed_at"].gt(end)
            active_end = int((opened_before_end & not_closed_by_end).sum())

            opened_in_quarter = group_df["opened_at"].between(start, end, inclusive="both")
            closed_in_quarter = group_df["closed_at"].between(start, end, inclusive="both")
            openings = int(opened_in_quarter.sum())
            closures = int(closed_in_quarter.sum())
            target_group = group_df[opened_in_quarter & group_df["target_known"]]
            target_value = (
                float(target_group["survived_over_1_year"].mean())
                if not target_group.empty
                else pd.NA
            )

            rent = rent_by_period.get(period_name, {})
            rows.append(
                {
                    "period": period_name,
                    "period_start": start.date().isoformat(),
                    "period_end": end.date().isoformat(),
                    "region": "서울",
                    "district": district,
                    "license_source": license_source,
                    "business_type": business_type,
                    "active_business_count_start": active_start,
                    "active_business_count_end": active_end,
                    "openings_in_quarter": openings,
                    "closures_in_quarter": closures,
                    "closure_frequency": closures / active_start if active_start else pd.NA,
                    "target_survived_over_1_year": target_value,
                    "target_known_count": int(len(target_group)),
                    "monthly_rent_per_sqm": rent.get("monthly_rent_per_sqm", pd.NA),
                    "monthly_rent_per_pyeong": rent.get("monthly_rent_per_pyeong", pd.NA),
                    "vacancy_rate": rent.get("vacancy_rate", pd.NA),
                    "investment_yield": rent.get("investment_yield", pd.NA),
                    "current_sbiz_store_count": current_store_counts.get(district, pd.NA),
                    "updated_at": updated_at,
                }
            )

    return rows


def quarter_column_to_period(column):
    try:
        year_part, quarter_part = column.split(".")
        quarter = quarter_part.strip().split("/")[0]
        return f"{year_part.strip()}Q{quarter}"
    except ValueError:
        return None


def timestamp_to_period(value):
    return str(pd.Period(value, freq="Q"))


def to_number(value):
    if pd.isna(value):
        return pd.NA
    return pd.to_numeric(str(value).replace(",", "").strip(), errors="coerce")


def read_csv_safely(path, **kwargs):
    try:
        return pd.read_csv(path, low_memory=False, **kwargs)
    except pd.errors.ParserError:
        return pd.read_csv(path, engine="python", on_bad_lines="skip", **kwargs)


if __name__ == "__main__":
    main()
