# 특성값 CSV 생성/업데이트 실행
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT / "backend"))

from app.data_sources import PublicOpenApiClient


def main():
    client = PublicOpenApiClient()
    if client.csv_paths["seoul_sbiz_store_all"].exists():
        feature_df = client.update_feature_dataset_from_store_csv()
    else:
        feature_df = client.update_feature_dataset()
    output_path = client.csv_paths["feature_dataset"]
    status_df = client._read_csv(client.csv_paths["data_source_status"])

    print(f"created_or_updated={output_path}")
    print(f"rows={len(feature_df)}")
    print("columns=" + ",".join(feature_df.columns))
    print(f"source_status={client.csv_paths['data_source_status']}")
    print(status_df[["source_name", "available", "feature_name"]].to_string(index=False))


if __name__ == "__main__":
    main()
