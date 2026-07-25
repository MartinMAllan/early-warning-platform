"""
ETL pipeline for the OULAD dataset -> modelling-ready student-attrition dataset.

Maps to Data Engineering component objectives 2-6 (profiling, normalised data
model / data dictionary, cleaning + feature engineering, bias audit, automated
quality checks).

Usage: python etl.py
Reads from ../../open+university+learning+analytics+dataset/*.csv
Writes to ../output/*.csv and ../output/*.json
"""
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

RAW = Path(__file__).resolve().parents[2] / "open+university+learning+analytics+dataset"
OUT = Path(__file__).resolve().parents[1] / "output"
OUT.mkdir(exist_ok=True, parents=True)


def load_raw():
    courses = pd.read_csv(RAW / "courses.csv")
    assessments = pd.read_csv(RAW / "assessments.csv")
    student_info = pd.read_csv(RAW / "studentInfo.csv")
    student_reg = pd.read_csv(RAW / "studentRegistration.csv")
    student_assess = pd.read_csv(RAW / "studentAssessment.csv")
    student_vle = pd.read_csv(RAW / "studentVle.csv")
    vle = pd.read_csv(RAW / "vle.csv")
    return courses, assessments, student_info, student_reg, student_assess, student_vle, vle


# ---------------------------------------------------------------------------
# 1. Data quality profiling (objective 2)
# ---------------------------------------------------------------------------

def profile_dataset(name, df):
    n = len(df)
    missing = {}
    for col in df.columns:
        vals = df[col]
        n_missing = int((vals.astype(str).str.strip() == "?").sum() + vals.isna().sum())
        if n_missing:
            missing[col] = {"missing": n_missing, "pct": round(100 * n_missing / n, 2)}
    return {
        "table": name,
        "rows": n,
        "columns": list(df.columns),
        "missingness": missing,
        "duplicate_rows": int(df.duplicated().sum()),
    }


# ---------------------------------------------------------------------------
# 2. Feature engineering (objective 4)
# ---------------------------------------------------------------------------

def engineer_features(student_info, student_reg, student_assess, assessments, student_vle):
    df = student_info.merge(
        student_reg, on=["code_module", "code_presentation", "id_student"], how="left"
    )

    # Target: binary attrition flag. Withdrawn = 1 (left the programme before
    # completion); Pass/Distinction/Fail = 0 (student saw the module through
    # to a final assessed outcome, even if they failed it academically).
    df["withdrawn"] = (df["final_result"] == "Withdrawn").astype(int)

    # --- Assessment performance features -----------------------------------
    sa = student_assess.merge(assessments, on="id_assessment", how="left")
    sa["score"] = pd.to_numeric(sa["score"], errors="coerce")
    sa["date_submitted"] = pd.to_numeric(sa["date_submitted"], errors="coerce")
    sa["date"] = pd.to_numeric(sa["date"], errors="coerce")
    sa["days_late"] = (sa["date_submitted"] - sa["date"]).clip(lower=0)

    perf = sa.groupby(["code_module", "code_presentation", "id_student"]).agg(
        n_assessments_submitted=("score", "count"),
        mean_score=("score", "mean"),
        min_score=("score", "min"),
        weighted_score=("score", lambda s: np.average(s, weights=sa.loc[s.index, "weight"].fillna(1) + 1e-9)
                        if len(s) else np.nan),
        mean_days_late=("days_late", "mean"),
        pct_late=("days_late", lambda s: float((s > 0).mean())),
    ).reset_index()

    n_expected = assessments.groupby(["code_module", "code_presentation"]).size().rename(
        "n_assessments_expected").reset_index()
    perf = perf.merge(n_expected, on=["code_module", "code_presentation"], how="left")
    perf["submission_rate"] = (perf["n_assessments_submitted"] / perf["n_assessments_expected"]).clip(upper=1)

    df = df.merge(perf, on=["code_module", "code_presentation", "id_student"], how="left")

    # --- VLE engagement features --------------------------------------------
    sv = student_vle.copy()
    sv["date"] = pd.to_numeric(sv["date"], errors="coerce")

    engagement = sv.groupby(["code_module", "code_presentation", "id_student"]).agg(
        total_clicks=("sum_click", "sum"),
        active_days=("date", "nunique"),
        mean_clicks_per_active_day=("sum_click", "mean"),
    ).reset_index()

    # Early-window engagement (first 4 weeks / 28 days) - key early-warning signal
    early = sv[sv["date"] <= 28].groupby(
        ["code_module", "code_presentation", "id_student"]
    ).agg(early_clicks=("sum_click", "sum"), early_active_days=("date", "nunique")).reset_index()

    df = df.merge(engagement, on=["code_module", "code_presentation", "id_student"], how="left")
    df = df.merge(early, on=["code_module", "code_presentation", "id_student"], how="left")

    # --- Fill / clean --------------------------------------------------------
    numeric_fill_zero = [
        "n_assessments_submitted", "total_clicks", "active_days",
        "mean_clicks_per_active_day", "early_clicks", "early_active_days",
        "submission_rate", "pct_late",
    ]
    for col in numeric_fill_zero:
        df[col] = df[col].fillna(0)

    for col in ["mean_score", "min_score", "weighted_score", "mean_days_late"]:
        df[col] = df[col].fillna(df[col].median())

    df["date_registration"] = pd.to_numeric(df["date_registration"], errors="coerce")
    df["date_unregistration"] = pd.to_numeric(
        df["date_unregistration"].replace("?", np.nan), errors="coerce"
    )
    df["date_registration"] = df["date_registration"].fillna(df["date_registration"].median())

    df["imd_band"] = df["imd_band"].replace("?", np.nan)
    df["imd_band"] = df["imd_band"].fillna("Unknown")

    return df


# ---------------------------------------------------------------------------
# 3. Bias / fairness audit (objective 5)
# ---------------------------------------------------------------------------

def bias_audit(df):
    report = {}
    for col in ["gender", "age_band", "disability", "highest_education", "imd_band"]:
        grp = df.groupby(col)["withdrawn"].agg(["mean", "count"]).reset_index()
        grp["mean"] = (grp["mean"] * 100).round(2)
        report[col] = grp.rename(columns={"mean": "withdrawal_rate_pct", "count": "n"}).to_dict("records")
    return report


# ---------------------------------------------------------------------------
# 4. Automated quality checks (objective 6)
# ---------------------------------------------------------------------------

def quality_checks(df):
    checks = {}
    checks["unique_student_module_presentation"] = bool(
        not df.duplicated(subset=["code_module", "code_presentation", "id_student"]).any()
    )
    checks["no_null_target"] = bool(df["withdrawn"].isna().sum() == 0)
    checks["score_range_valid"] = bool(df["mean_score"].between(0, 100).all())
    class_counts = df["withdrawn"].value_counts(normalize=True).round(4).to_dict()
    checks["class_balance"] = {str(k): v for k, v in class_counts.items()}
    checks["n_rows"] = int(len(df))
    checks["n_features"] = int(df.shape[1])
    return checks


def main():
    courses, assessments, student_info, student_reg, student_assess, student_vle, vle = load_raw()

    profile = {
        "generated_from": "OULAD (Kuzilek, Hlosta & Zdrahal, 2017)",
        "tables": [
            profile_dataset("courses", courses),
            profile_dataset("assessments", assessments),
            profile_dataset("studentInfo", student_info),
            profile_dataset("studentRegistration", student_reg),
            profile_dataset("studentAssessment", student_assess),
            profile_dataset("studentVle", student_vle),
            profile_dataset("vle", vle),
        ],
    }
    (OUT / "data_quality_report.json").write_text(json.dumps(profile, indent=2))

    df = engineer_features(student_info, student_reg, student_assess, assessments, student_vle)

    keep_cols = [
        "code_module", "code_presentation", "id_student", "gender", "region",
        "highest_education", "imd_band", "age_band", "num_of_prev_attempts",
        "studied_credits", "disability", "final_result", "withdrawn",
        "date_registration", "date_unregistration",
        "n_assessments_submitted", "n_assessments_expected", "submission_rate",
        "mean_score", "min_score", "weighted_score", "mean_days_late", "pct_late",
        "total_clicks", "active_days", "mean_clicks_per_active_day",
        "early_clicks", "early_active_days",
    ]
    df = df[keep_cols]
    df.to_csv(OUT / "processed_student_data.csv", index=False)

    bias = bias_audit(df)
    (OUT / "bias_audit.json").write_text(json.dumps(bias, indent=2))

    qc = quality_checks(df)
    (OUT / "quality_checks.json").write_text(json.dumps(qc, indent=2))

    print(f"Processed dataset: {df.shape[0]} rows, {df.shape[1]} columns")
    print(f"Withdrawal rate: {df['withdrawn'].mean() * 100:.2f}%")
    print("Wrote:", OUT / "processed_student_data.csv")
    print("Wrote:", OUT / "data_quality_report.json")
    print("Wrote:", OUT / "bias_audit.json")
    print("Wrote:", OUT / "quality_checks.json")


if __name__ == "__main__":
    main()
