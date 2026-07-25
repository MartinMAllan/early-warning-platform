"""
Model training/evaluation for student-attrition risk scoring.

Maps to Modelling component objectives 3-6 (candidate algorithms, imbalanced-
classification metrics, probability calibration, feature attribution, subgroup
fairness check). Trains on the dataset produced by ../data_engineering/etl.py.

Usage: python train_models.py
"""
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (average_precision_score, brier_score_loss,
                              f1_score, roc_auc_score)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from xgboost import XGBClassifier

OUT = Path(__file__).resolve().parents[1] / "output"

CATEGORICAL = ["gender", "region", "highest_education", "imd_band", "age_band", "disability", "code_module"]
NUMERIC = [
    "num_of_prev_attempts", "studied_credits", "date_registration",
    "submission_rate", "mean_score", "min_score", "weighted_score",
    "mean_days_late", "pct_late", "total_clicks", "active_days",
    "mean_clicks_per_active_day", "early_clicks", "early_active_days",
]
TARGET = "withdrawn"


def build_preprocessor():
    return ColumnTransformer([
        ("num", StandardScaler(), NUMERIC),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
    ])


def evaluate(name, y_true, proba):
    pred = (proba >= 0.5).astype(int)
    return {
        "model": name,
        "auc_roc": round(float(roc_auc_score(y_true, proba)), 4),
        "auc_pr": round(float(average_precision_score(y_true, proba)), 4),
        "f1": round(float(f1_score(y_true, pred)), 4),
        "brier_score": round(float(brier_score_loss(y_true, proba)), 4),
    }


def reliability_curve(y_true, proba, n_bins=10):
    bins = np.linspace(0, 1, n_bins + 1)
    idx = np.digitize(proba, bins) - 1
    idx = np.clip(idx, 0, n_bins - 1)
    points = []
    for b in range(n_bins):
        mask = idx == b
        if mask.sum() == 0:
            continue
        points.append({
            "bin_center": round(float((bins[b] + bins[b + 1]) / 2), 3),
            "predicted_mean": round(float(proba[mask].mean()), 3),
            "observed_rate": round(float(y_true[mask].mean()), 3),
            "n": int(mask.sum()),
        })
    return points


def main():
    df = pd.read_csv(OUT / "processed_student_data.csv")
    df = df.dropna(subset=[TARGET])

    X = df[CATEGORICAL + NUMERIC]
    y = df[TARGET].astype(int)

    X_train, X_temp, y_train, y_temp = train_test_split(
        X, y, test_size=0.4, random_state=42, stratify=y
    )
    X_val, X_test, y_val, y_test = train_test_split(
        X_temp, y_temp, test_size=0.5, random_state=42, stratify=y_temp
    )

    pre = build_preprocessor()

    candidates = {
        "logistic_regression": LogisticRegression(max_iter=1000, class_weight="balanced"),
        "random_forest": RandomForestClassifier(
            n_estimators=300, max_depth=12, min_samples_leaf=5,
            class_weight="balanced", random_state=42, n_jobs=-1,
        ),
        "xgboost": XGBClassifier(
            n_estimators=300, max_depth=5, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8, eval_metric="logloss",
            random_state=42, n_jobs=-1,
        ),
    }

    results = []
    fitted = {}
    for name, clf in candidates.items():
        pipe = Pipeline([("pre", pre), ("clf", clf)])
        pipe.fit(X_train, y_train)
        proba_val = pipe.predict_proba(X_val)[:, 1]
        res = evaluate(name, y_val, proba_val)
        results.append(res)
        fitted[name] = pipe

    results_sorted = sorted(results, key=lambda r: r["auc_pr"], reverse=True)
    best_name = results_sorted[0]["model"]
    best_pipe = fitted[best_name]

    # --- Calibration (Platt scaling) on the best model -----------------------
    calibrated = CalibratedClassifierCV(best_pipe, method="sigmoid", cv=5)
    calibrated.fit(X_train, y_train)

    proba_test_raw = best_pipe.predict_proba(X_test)[:, 1]
    proba_test_cal = calibrated.predict_proba(X_test)[:, 1]

    test_metrics_raw = evaluate(f"{best_name}_uncalibrated", y_test, proba_test_raw)
    test_metrics_cal = evaluate(f"{best_name}_calibrated", y_test, proba_test_cal)

    reliability = reliability_curve(y_test.values, proba_test_cal)

    # --- Feature importance (permutation-style via model coefficients / tree importances)
    feature_names = list(NUMERIC)
    ohe = best_pipe.named_steps["pre"].named_transformers_["cat"]
    feature_names += list(ohe.get_feature_names_out(CATEGORICAL))

    clf = best_pipe.named_steps["clf"]
    if hasattr(clf, "feature_importances_"):
        importances = clf.feature_importances_
    else:
        importances = np.abs(clf.coef_[0])
    importances = importances / importances.sum()

    imp_df = pd.DataFrame({"feature": feature_names, "importance": importances})
    imp_df = imp_df.sort_values("importance", ascending=False).head(15)
    feature_importance = [
        {"feature": r.feature, "importance": round(float(r.importance), 4)}
        for r in imp_df.itertuples()
    ]

    # --- Subgroup fairness check (objective 7) --------------------------------
    subgroup_rows = df.loc[X_test.index].copy()
    subgroup_rows["risk_score"] = proba_test_cal
    subgroup_rows["true_label"] = y_test.values
    subgroup_rows["pred_label"] = (proba_test_cal >= 0.5).astype(int)

    fairness = {}
    for col in ["gender", "age_band", "highest_education"]:
        rows = []
        for val, g in subgroup_rows.groupby(col):
            if len(g) < 20:
                continue
            tp = ((g.pred_label == 1) & (g.true_label == 1)).sum()
            fn = ((g.pred_label == 0) & (g.true_label == 1)).sum()
            fp = ((g.pred_label == 1) & (g.true_label == 0)).sum()
            tn = ((g.pred_label == 0) & (g.true_label == 0)).sum()
            tpr = tp / (tp + fn) if (tp + fn) else None
            fpr = fp / (fp + tn) if (fp + tn) else None
            rows.append({
                "group": str(val), "n": int(len(g)),
                "true_positive_rate": round(float(tpr), 3) if tpr is not None else None,
                "false_positive_rate": round(float(fpr), 3) if fpr is not None else None,
                "mean_risk_score": round(float(g.risk_score.mean()), 3),
            })
        fairness[col] = rows

    # --- Sample predictions for the dashboard (per-student) -------------------
    sample = subgroup_rows.sample(n=min(400, len(subgroup_rows)), random_state=7)
    sample_out = sample[[
        "id_student", "code_module", "code_presentation", "gender", "age_band",
        "highest_education", "region", "num_of_prev_attempts", "studied_credits",
        "submission_rate", "mean_score", "total_clicks", "active_days",
        "early_clicks", "risk_score", "true_label", "final_result",
    ]].copy()
    sample_out["risk_score"] = sample_out["risk_score"].round(4)
    sample_out = sample_out.sort_values("risk_score", ascending=False)

    metrics_out = {
        "candidate_comparison": results,
        "selected_model": best_name,
        "test_set_uncalibrated": test_metrics_raw,
        "test_set_calibrated": test_metrics_cal,
        "reliability_curve": reliability,
        "n_train": int(len(X_train)), "n_val": int(len(X_val)), "n_test": int(len(X_test)),
        "withdrawal_rate_overall": round(float(y.mean()), 4),
    }

    (OUT / "model_metrics.json").write_text(json.dumps(metrics_out, indent=2))
    (OUT / "feature_importance.json").write_text(json.dumps(feature_importance, indent=2))
    (OUT / "fairness_audit.json").write_text(json.dumps(fairness, indent=2))
    sample_out.to_json(OUT / "sample_predictions.json", orient="records", indent=2)

    joblib.dump(calibrated, OUT / "attrition_risk_model.joblib")

    print("Candidate comparison:")
    for r in results_sorted:
        print(" ", r)
    print("Selected model:", best_name)
    print("Test (calibrated):", test_metrics_cal)
    print("Wrote model_metrics.json, feature_importance.json, fairness_audit.json, sample_predictions.json")


if __name__ == "__main__":
    main()
