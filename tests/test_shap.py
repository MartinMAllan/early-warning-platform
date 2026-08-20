import pytest
import json
from pathlib import Path

OUTPUT = Path(__file__).resolve().parents[1] / "output"


class TestSamplePredictionsExist:

    @pytest.fixture
    def predictions(self):
        path = OUTPUT / "sample_predictions.json"
        if not path.exists():
            pytest.skip("Sample predictions file not found.")
        with open(path) as f:
            return json.load(f)

    def test_predictions_not_empty(self, predictions):
        if isinstance(predictions, list):
            assert len(predictions) > 0
        elif isinstance(predictions, dict):
            assert len(predictions) > 0

    def test_each_prediction_has_risk_score(self, predictions):
        records = predictions if isinstance(predictions, list) else predictions.get("predictions", [])
        for record in records:
            has_score = (
                "risk_score" in record
                or "calibrated_risk" in record
                or "probability" in record
            )
            assert has_score

    def test_risk_scores_between_zero_and_one(self, predictions):
        records = predictions if isinstance(predictions, list) else predictions.get("predictions", [])
        for record in records:
            score = record.get("risk_score", record.get("calibrated_risk", record.get("probability", -1)))
            assert 0.0 <= score <= 1.0


class TestSHAPAttributions:

    @pytest.fixture
    def predictions(self):
        path = OUTPUT / "sample_predictions.json"
        if not path.exists():
            pytest.skip("Sample predictions file not found.")
        with open(path) as f:
            return json.load(path)

    @pytest.fixture
    def trimmed(self):
        path = OUTPUT / "sample_predictions_trimmed.json"
        if not path.exists():
            pytest.skip("Trimmed predictions file not found.")
        with open(path) as f:
            return json.load(f)

    def test_trimmed_predictions_not_empty(self, trimmed):
        if isinstance(trimmed, list):
            assert len(trimmed) > 0
        elif isinstance(trimmed, dict):
            assert len(trimmed) > 0

    def test_each_record_has_feature_contributions(self, trimmed):
        records = trimmed if isinstance(trimmed, list) else trimmed.get("predictions", [])
        for record in records:
            has_features = (
                "features" in record
                or "contributions" in record
                or "shap_values" in record
                or "top_features" in record
            )
            assert has_features

    def test_feature_contributions_have_names_and_values(self, trimmed):
        records = trimmed if isinstance(trimmed, list) else trimmed.get("predictions", [])
        for record in records:
            features = record.get(
                "features",
                record.get("contributions", record.get("shap_values", record.get("top_features", [])))
            )
            if isinstance(features, list):
                for f in features:
                    has_name = "feature" in f or "name" in f
                    has_value = "value" in f or "contribution" in f or "shap_value" in f
                    assert has_name
                    assert has_value

    def test_at_least_five_features_per_prediction(self, trimmed):
        records = trimmed if isinstance(trimmed, list) else trimmed.get("predictions", [])
        for record in records:
            features = record.get(
                "features",
                record.get("contributions", record.get("shap_values", record.get("top_features", [])))
            )
            if isinstance(features, list):
                assert len(features) >= 5

    def test_no_protected_features_in_attributions(self, trimmed):
        protected = {"gender", "disability", "ethnicity", "race"}
        records = trimmed if isinstance(trimmed, list) else trimmed.get("predictions", [])
        for record in records:
            features = record.get(
                "features",
                record.get("contributions", record.get("shap_values", record.get("top_features", [])))
            )
            if isinstance(features, list):
                for f in features:
                    name = f.get("feature", f.get("name", "")).lower()
                    assert name not in protected


class TestFeatureImportanceAlignsSHAP:

    @pytest.fixture
    def importance(self):
        path = OUTPUT / "feature_importance.json"
        if not path.exists():
            pytest.skip("Feature importance file not found.")
        with open(path) as f:
            return json.load(f)

    def test_top_feature_is_submission_rate(self, importance):
        if isinstance(importance, list):
            top = importance[0]
            name = top.get("feature", top.get("name", "")).lower()
        elif isinstance(importance, dict):
            name = max(importance, key=importance.get).lower()
        else:
            name = ""
        assert "submission" in name
