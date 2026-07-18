import unittest
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from data_collection.collect_sip_1min import (
    collection_window,
    merge_frames,
    storage_path,
)


class CollectSipOneMinuteTests(unittest.TestCase):
    @staticmethod
    def make_frame(timestamps: list[str], values: list[int]) -> pd.DataFrame:
        index = pd.MultiIndex.from_arrays(
            [
                ["AAPL"] * len(timestamps),
                pd.to_datetime(timestamps, utc=True),
            ],
            names=["symbol", "timestamp"],
        )
        return pd.DataFrame({"close": values}, index=index)

    def test_collection_window_uses_exact_three_years_and_fifteen_minute_delay(self):
        now = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)
        start, end = collection_window(now)

        self.assertEqual(end, datetime(2026, 7, 19, 11, 45, tzinfo=timezone.utc))
        self.assertEqual(start, datetime(2023, 7, 19, 12, 0, tzinfo=timezone.utc))

    def test_storage_path_separates_feed_type_and_format(self):
        path = storage_path("BRK/B", "adjusted", "parquet", Path("sip_market_data"))
        self.assertEqual(
            path,
            Path("sip_market_data/adjusted/parquet/BRK-B_1min_sip_historical.parquet"),
        )

    def test_merge_deduplicates_and_keeps_latest_value_inside_window(self):
        existing = self.make_frame(
            ["2025-01-02 14:30:00Z", "2025-01-02 14:31:00Z"],
            [100, 101],
        )
        new = self.make_frame(
            ["2025-01-02 14:31:00Z", "2025-01-02 14:32:00Z"],
            [201, 202],
        )

        combined = merge_frames(
            existing,
            [new],
            datetime(2025, 1, 2, 14, 30, tzinfo=timezone.utc),
            datetime(2025, 1, 2, 14, 33, tzinfo=timezone.utc),
        )

        self.assertEqual(len(combined), 3)
        self.assertEqual(combined.loc[("AAPL", pd.Timestamp("2025-01-02 14:31:00Z")), "close"], 201)


if __name__ == "__main__":
    unittest.main()
