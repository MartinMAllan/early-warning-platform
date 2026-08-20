import pandas as pd
import numpy as np
import pytest
from pathlib import Path


def compute_submission_rate(submitted, expected):
    rate = submitted / expected if expected > 0 else 0.0
    return min(rate, 1.0)


def median_impute(series):
    median_val = series.median()
    return series.fillna(median_val)


class TestSubmissionRate:

    def test_normal_case(self):
        assert compute_submission_rate(3, 5) == 0.6

    def test_all_submitted(self):
        assert compute_submission_rate(5, 5) == 1.0

    def test_cap_at_one(self):
        result = compute_submission_rate(7, 5)
        assert result == 1.0

    def test_zero_expected(self):
        result = compute_submission_rate(0, 0)
        assert result == 0.0

    def test_none_submitted(self):
        assert compute_submission_rate(0, 5) == 0.0


class TestMedianImputation:

    def test_fills_nan_with_median(self):
        s = pd.Series([10, 20, np.nan, 40, 50])
        result = median_impute(s)
        assert result.iloc[2] == 30.0

    def test_no_nans_unchanged(self):
        s = pd.Series([10, 20, 30])
        result = median_impute(s)
        assert list(result) == [10, 20, 30]

    def test_all_nans(self):
        s = pd.Series([np.nan, np.nan, np.nan])
        result = median_impute(s)
        assert result.isna().all()


class TestOutputDataQuality:

    @pytest.fixture
    def processed_data(self):
        path = Path(__file__).resolve().parents[1] / "output" / "processed_student_data.csv"
        if not path.exists():
            pytest.skip("Processed data file not found.")
        return pd.read_csv(path)

    def test_no_duplicate_keys(self, processed_data):
        key_cols = ["id_student", "code_module", "code_presentation"]
        available = [c for c in key_cols if c in processed_data.columns]
        if available:
            duplicates = processed_data.duplicated(subset=available, keep=False).sum()
            assert duplicates == 0

    def test_no_null_target(self, processed_data):
        target = "final_result"
        if target in processed_data.columns:
            nulls = processed_data[target].isna().sum()
            assert nulls == 0

    def test_score_range(self, processed_data):
        score_col = "mean_score"
        if score_col in processed_data.columns:
            assert processed_data[score_col].min() >= 0
            assert processed_data[score_col].max() <= 100

    def test_record_count(self, processed_data):
        count = len(processed_data)
        assert count > 30000
        assert count < 35000
