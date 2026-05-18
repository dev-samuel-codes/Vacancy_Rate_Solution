import unittest

import pandas as pd

from backend.scripts.build_survival_model_dataset import (
    OUTPUT_COLUMNS,
    build_survival_model_dataset,
)


class BuildSurvivalModelDatasetTest(unittest.TestCase):
    def test_builds_binary_target_per_business(self):
        licenses = pd.DataFrame(
            [
                {
                    "business_name": "long_closed",
                    "business_type": "restaurant",
                    "license_date": "2020-01-15",
                    "closed_date": "2021-02-01",
                    "business_status": "closed",
                    "region": "Seoul",
                    "district": "Gangnam-gu",
                    "license_source": "general_restaurant",
                },
                {
                    "business_name": "short_closed",
                    "business_type": "restaurant",
                    "license_date": "2020-01-20",
                    "closed_date": "2020-06-01",
                    "business_status": "closed",
                    "region": "Seoul",
                    "district": "Gangnam-gu",
                    "license_source": "general_restaurant",
                },
                {
                    "business_name": "old_open",
                    "business_type": "restaurant",
                    "license_date": "2020-05-10",
                    "closed_date": pd.NA,
                    "business_status": "open",
                    "region": "Seoul",
                    "district": "Gangnam-gu",
                    "license_source": "general_restaurant",
                },
                {
                    "business_name": "too_recent_to_know",
                    "business_type": "restaurant",
                    "license_date": "2026-01-01",
                    "closed_date": pd.NA,
                    "business_status": "open",
                    "region": "Seoul",
                    "district": "Gangnam-gu",
                    "license_source": "general_restaurant",
                },
                {
                    "business_name": "recent_fast_closure",
                    "business_type": "restaurant",
                    "license_date": "2026-01-01",
                    "closed_date": "2026-03-01",
                    "business_status": "closed",
                    "region": "Seoul",
                    "district": "Gangnam-gu",
                    "license_source": "general_restaurant",
                },
                {
                    "business_name": "closed_without_closed_date",
                    "business_type": "restaurant",
                    "license_date": "2020-01-10",
                    "closed_date": pd.NA,
                    "business_status": "closed",
                    "region": "Seoul",
                    "district": "Gangnam-gu",
                    "license_source": "general_restaurant",
                },
            ]
        )
        quarterly = self._quarterly_context()

        result = build_survival_model_dataset(
            licenses,
            quarterly,
            as_of_date=pd.Timestamp("2026-05-17"),
        )

        self.assertEqual(list(result["target_survived_over_1_year"]), [1, 0, 1])
        self.assertEqual(result["target_survived_over_1_year"].dtype, "int64")
        self.assertEqual(set(result["target_survived_over_1_year"].unique()), {0, 1})
        self.assertEqual(len(result), 3)

    def test_keeps_training_columns_without_closed_date_leakage(self):
        licenses = pd.DataFrame(
            [
                {
                    "business_name": "short_closed",
                    "business_type": "restaurant",
                    "license_date": "2020-01-20",
                    "closed_date": "2020-06-01",
                    "business_status": "closed",
                    "region": "Seoul",
                    "district": "Gangnam-gu",
                    "license_source": "general_restaurant",
                }
            ]
        )

        result = build_survival_model_dataset(
            licenses,
            self._quarterly_context(),
            as_of_date=pd.Timestamp("2026-05-17"),
        )

        self.assertEqual(list(result.columns), OUTPUT_COLUMNS)
        self.assertNotIn("closed_date", result.columns)
        self.assertNotIn("business_duration_days", result.columns)

    def _quarterly_context(self):
        rows = []
        values_by_period = {
            "2019Q4": (10, 12, 3, 1, 0.10),
            "2020Q1": (12, 13, 4, 2, 0.17),
            "2020Q2": (13, 15, 5, 1, 0.08),
            "2026Q1": (20, 21, 1, 0, 0.00),
        }
        for period, values in values_by_period.items():
            active_start, active_end, openings, closures, closure_frequency = values
            rows.append(
                {
                    "period": period,
                    "region": "Seoul",
                    "district": "Gangnam-gu",
                    "license_source": "general_restaurant",
                    "business_type": "restaurant",
                    "active_business_count_start": active_start,
                    "active_business_count_end": active_end,
                    "openings_in_quarter": openings,
                    "closures_in_quarter": closures,
                    "closure_frequency": closure_frequency,
                    "monthly_rent_per_sqm": 50.0,
                    "monthly_rent_per_pyeong": 165.29,
                    "vacancy_rate": 6.5,
                    "investment_yield": 1.4,
                    "current_sbiz_store_count": 1000,
                }
            )
        return pd.DataFrame(rows)


if __name__ == "__main__":
    unittest.main()
