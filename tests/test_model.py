import pytest
import json
import joblib
import numpy as np
from pathlib import Path

OUTPUT = Path(__file__).resolve().parents[1] / "output"


class TestModelArtefactExists:

    def test_model_file_exists(self):
        path = OUTPUT / "attrition_risk_model.joblib"
        assert path.exists()

    def test_model_file_not_empty(self):
        path = OUTPUT / "attrition_risk_model.joblib"
        assert path.stat().st_size > 0

    def test_feature_importance_file_exists(self):
        path = OUTPUT / "feature_importance.json"
        assert path.exists()

    def test_model_metrics_file_exists(self):
        path = OUTPUT / "model_metrics.json"
        assert path.exists()

    def test_fairness_audit_file_exists(self):
        path = OUTPUT / "fairness_audit.json"
        assert path.exists()

    def test_quality_checks_file_exists(self):
        path = OUTPUT / "quality_checks.json"
        assert path.exists()

    def test_sample_predictions_file_exists(self):
        path = OUTPUT / "sample_predictions.json"
        assert path.exists()


class TestModelLoadsAndPredicts:

    @pytest.fixture
    def model(self):
        path = OUTPUT / "attrition_risk_model.joblib"
        if not path.exists():
            pytest.skip("Model file not found.")
        return joblib.load(path)

    def test_model_loads_without_error(self, model):
        assert model is not None

    def test_model_has_predict_method(self, model):
        assert hasattr(model, "predict")

    def test_model_has_predict_proba_method(self, model):
        assert hasattr(model, "predict_proba")


class TestModelMetricsIntegrity:

    @pytest.fixture
    def metrics(self):
        path = OUTPUT / "model_metrics.json"
        if not path.exists():
            pytest.skip("Metrics file not found.")
        with open(path) as f:
            return json.load(f)

    def test_three_candidates_compared(self, metrics):
        candidates = metrics.get("candidate_comparison", [])
        assert len(candidates) == 3

    def test_each_candidate_has_auc_pr(self, metrics):
        for candidate in metrics.get("candidate_comparison", []):
            assert "auc_pr" in candidate

    def test_auc_pr_values_in_valid_range(self, metrics):
        for candidate in metrics.get("candidate_comparison", []):
            score = candidate["auc_pr"]
            assert 0.0 <= score <= 1.0

    def test_xgboost_has_highest_auc_pr(self, metrics):
        candidates = metrics.get("candidate_comparison", [])
        scores = {c["model"]: c["auc_pr"] for c in candidates}
        best = max(scores, key=scores.get)
        assert best == "xgboost"

    def test_brier_scores_in_valid_range(self, metrics):
        for candidate in metrics.get("candidate_comparison", []):
            if "brier_score" in candidate:
                score = candidate["brier_score"]
                assert 0.0 <= score <= 1.0


class TestFeatureImportance:

    @pytest.fixture
    def features(self):
        path = OUTPUT / "feature_importance.json"
        if not path.exists():
            pytest.skip("Feature importance file not found.")
        with open(path) as f:
            return json.load(f)

    def test_at_least_ten_features(self, features):
        if isinstance(features, list):
            assert len(features) >= 10
        elif isinstance(features, dict):
            assert len(features) >= 10

    def test_importances_are_positive(self, features):
        if isinstance(features, list):
            for item in features:
                val = item.get("importance", item.get("value", 0))
                assert val >= 0
        elif isinstance(features, dict):
            for val in features.values():
                assert val >= 0

    def test_importances_sum_close_to_one(self, features):
        if isinstance(features, list):
            total = sum(item.get("importance", item.get("value", 0)) for item in features)
        elif isinstance(features, dict):
            total = sum(features.values())
        else:
            total = 0
        assert 0.95 <= total <= 1.05


class TestFairnessAuditIntegrity:

    @pytest.fixture
    def audit(self):
        path = OUTPUT / "fairness_audit.json"
        if not path.exists():
            pytest.skip("Fairness audit file not found.")
        with open(path) as f:
            return json.load(f)

    def test_gender_groups_present(self, audit):
        gender = audit.get("gender", [])
        groups = [g["group"] for g in gender]
        assert "F" in groups
        assert "M" in groups

    def test_tpr_values_in_valid_range(self, audit):
        for axis in audit.values():
            if isinstance(axis, list):
                for group in axis:
                    tpr = group.get("true_positive_rate", 0)
                    assert 0.0 <= tpr <= 1.0

    def test_fpr_values_in_valid_range(self, audit):
        for axis in audit.values():
            if isinstance(axis, list):
                for group in axis:
                    fpr = group.get("false_positive_rate", 0)
                    assert 0.0 <= fpr <= 1.0

    def test_sample_sizes_positive(self, audit):
        for axis in audit.values():
            if isinstance(axis, list):
                for group in axis:
                    n = group.get("n", 0)
                    assert n > 0
