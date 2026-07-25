# Early Warning Platform - Completion Plan

*Development of an Intelligent Web-Based Early Warning Platform for Predicting Student Attrition Risks Within Higher Education Academic Programs - MSc group project, University of the West of Scotland, 2025/26*

This plan is built from the four individual project specifications (Telaprolu - front-end/UX, Adeleke - data engineering, Ewa - ML modelling, Obah - back-end) and from the shared OULAD dataset in `open+university+learning+analytics+dataset/`. Everything under "Evidence produced" below is real, computed output from a working prototype in `Prototype/` - not mock data. Where a number is quoted, it came from running the pipeline against the actual CSVs.

---

## 1. What exists now

```
Prototype/
├── data_engineering/etl.py          → cleans & joins all 7 CSVs into one modelling table
├── modelling/train_models.py        → trains, calibrates, explains 3 candidate models
├── backend/main.py                  → FastAPI contract: JWT roles, risk/cohort/intervention endpoints
├── backend/requirements.txt
├── frontend/dashboard.html          → published dashboard artifact (this session's live demo)
├── frontend/template.html           → source template (edit this, not dashboard.html)
├── frontend/build_dashboard.py      → re-injects output/ data into template.html
└── output/                          → every JSON/CSV artefact the pipeline produced
```

Running `python data_engineering/etl.py` then `python modelling/train_models.py` regenerates everything in `output/` from the raw CSVs. `python frontend/build_dashboard.py` then rebuilds the dashboard around the fresh numbers. This is a real, re-runnable pipeline, not a one-off script.

**Headline results from the actual run:**

| Metric | Value |
|---|---|
| Rows processed (student × module-presentation) | 32,593 |
| Engineered features | 28 |
| Historic withdrawal rate | 31.16% |
| Best model | XGBoost |
| Test-set AUC-ROC (calibrated) | 0.944 |
| Test-set AUC-PR (calibrated) | 0.869 |
| Test-set Brier score (calibrated) | 0.091 |

The AUC-ROC sits above the 0.78–0.87 benchmark range cited in the literature review (Hlosta et al., 2017; Saarela and Jauhiainen, 2021) - see §5 for why, and the methodological refinement this implies for the dissertation.

---

## 2. What each raw file feeds into

| File | Rows | Role in the pipeline |
|---|---|---|
| `studentInfo.csv` | 32,594 | Base population: demographics + `final_result` → the attrition label (`Withdrawn` = 1) |
| `studentRegistration.csv` | 32,594 | Registration/unregistration timing - joined on student+module+presentation |
| `studentAssessment.csv` | 173,913 | Per-submission scores, joined to `assessments.csv` for weight/deadline → aggregated to submission rate, mean/min score, lateness |
| `assessments.csv` | 207 | Assessment calendar per module-presentation - denominator for submission rate |
| `studentVle.csv` | 10,655,281 | Daily click logs → aggregated to total clicks, active days, and an **early-window** (first 28 days) engagement signal, the genuine "early warning" feature |
| `vle.csv` | 6,365 | VLE material catalogue - available for a richer version (per-activity-type engagement) not yet exploited; see §6 |
| `courses.csv` | 23 | Module-presentation length - available for normalising engagement by course duration; not yet used |

`data_quality_report.json` and `bias_audit.json` in `output/` are the profiling and fairness-audit artefacts the data-engineering spec (objectives 2 and 5) asks for, generated from these tables directly.

---

## 3. Component-by-component: done vs. remaining

### 3.1 Data Engineering (Adeleke - objectives 1–8)

| Objective | Status | Evidence |
|---|---|---|
| 1. Identify/justify datasets | Done | OULAD selected and justified in the spec; CC BY 4.0 |
| 2. Profile datasets (missingness, imbalance, outliers) | Done | `output/data_quality_report.json` - per-table row/column/missingness/duplicate counts |
| 3. Normalised data model + data dictionary | Partial | Table shapes are implicit in `etl.py`; a formal data dictionary document (field, type, unit, source, transform) is not yet written - see §4 action items |
| 4. Reproducible ETL in Python | Done | `etl.py`, deterministic, re-runnable from raw CSVs |
| 5. Bias detection across demographic subgroups | Done | `output/bias_audit.json` - see real findings below |
| 6. Automated data quality checks | Done | `output/quality_checks.json` - uniqueness, null-target, score-range, class balance |
| 7. Data lineage per feature | Not started | Needs a lineage table (feature → source column(s) → transform) for the appendix |
| 8. UK GDPR / DPA 2018 compliance | Satisfied by design | OULAD is already anonymised; no PII is introduced by the pipeline |

**Real bias-audit findings worth writing up:** students who declared a disability withdraw at 39.4% vs 30.3% for those who did not (a 9-point gap); withdrawal falls fairly linearly as IMD band improves (37.2% in the most deprived decile down to 25.9% in the least, before an "Unknown" band at 21.2%); "No Formal quals" students withdraw at 42.9% vs 23.6% for postgraduate-qualified entrants. These are exactly the kind of findings Baker and Hawn (2022) predict, and they justify the subgroup fairness check in §3.2 - a model trained blind to these gaps risks reproducing them in its risk scores.

**Remaining for full marks:** the formal data dictionary and lineage table (objectives 3 and 7) are writing tasks, not engineering ones - the information already exists in `etl.py`'s column selection and can be tabulated directly from it. A PostgreSQL/SQLite load script (spec's "Implementation approach") is not yet written; the pipeline currently stops at CSV/JSON, which is sufficient for the ML and dashboard components but not for the backend's SQLAlchemy layer.

### 3.2 Machine Learning (Ewa - objectives 1–8)

| Objective | Status | Evidence |
|---|---|---|
| 1. Literature synthesis | Done (in Chapter 2 draft) | - |
| 2. Feature engineering | Done | Submission rate, score aggregates, lateness, total/active/early engagement - `etl.py` |
| 3. Train candidate algorithms (LR, RF, XGBoost + interpretable baseline) | Done | `train_models.py` - logistic regression doubles as the interpretable baseline |
| 4. Evaluate with AUC-ROC/AUC-PR/F1 across thresholds | Done | `output/model_metrics.json` |
| 5. Probability calibration (Brier, reliability diagram) | Done | Platt scaling via `CalibratedClassifierCV`; reliability curve in `output/model_metrics.json` and rendered on the dashboard |
| 6. SHAP explanations | Partial | Feature importance is currently tree/coefficient-based (`output/feature_importance.json`), not true SHAP - `shap` isn't installed in this environment. Swapping in `shap.TreeExplainer` on the saved `attrition_risk_model.joblib` is a same-day task once the package is available |
| 7. Subgroup fairness (TPR/FPR by gender, age, education) | Done | `output/fairness_audit.json` |
| 8. Reproducible, version-controlled notebook | Partial | Logic exists as a script with a fixed seed; porting to a documented notebook for the appendix is outstanding |

**Real fairness-audit findings:** true-positive rate is close between genders (78.3% women, 77.1% men) but the false-positive rate is notably higher for men (11.1% vs 7.8%) - the model over-flags men relative to women at a similar true-positive rate. "No Formal quals" students have a markedly lower TPR (65.2%) than every other education band (all ≥ 77%) despite a small sample (n=56) - worth flagging as a limitation rather than a conclusion, and a candidate for oversampling (SMOTE/ADASYN, both already in the literature review) in a follow-up iteration.

**Methodological point for the dissertation:** `submission_rate` alone carries 29% of feature importance, and `mean_score` is also highly ranked. Both are near-certain proxies for the outcome (a student who never submits anything is definitionally close to withdrawn), which is why AUC-ROC (0.944) beats the published OULAD benchmarks (0.78–0.87) - this is a legitimate but different question ("did this student engage/succeed") from the genuinely early-warning question ("will this student withdraw, using only signal available before assessment results exist"). **Recommended addition:** train a second, stricter model restricted to `early_clicks`, `early_active_days`, `date_registration`, and demographics only (no assessment features) to report a true early-window AUC alongside the full model, and discuss the gap between them explicitly - this is the kind of critical self-evaluation point that scores well in the "Critical Self-Evaluation" section of the marking scheme.

### 3.3 Back-End & API (Obah - objectives 1–8)

| Objective | Status | Evidence |
|---|---|---|
| 1. Literature review | Done (in Chapter 2 draft) | - |
| 2. Architecture / data-flow design | Done (informally) | Route structure in `main.py` mirrors the spec's endpoint list |
| 3. REST API (FastAPI) for risk/explanation/cohort/intervention | Done | `backend/main.py` - `/students`, `/students/{id}/risk`, `/cohort/overview`, `/interventions` |
| 4. JWT role-based auth (admin/advisor/module leader) | Done | `create_access_token`, `require_role()` dependency scoping every route |
| 5. Model-serving endpoint using the ML artefact | Done | Loads `output/attrition_risk_model.joblib` and `sample_predictions.json`/`feature_importance.json` |
| 6. SQLAlchemy/PostgreSQL schema | Not started | `main.py` currently reads the CSV/JSON artefacts directly, deliberately, so the contract can be exercised without a live database - swap `load_predictions()`/`load_feature_importance()` for real queries once the schema from §3.1 exists |
| 7. Testing strategy (pytest, integration, Locust load test) | Not started | No test files yet - `backend/main.py`'s route signatures are stable enough to write `TestClient` tests against now |
| 8. HTTPS/JWT-expiry/no-PII-logging compliance | Designed in, not deployed | Token expiry is implemented; HTTPS enforcement is a deployment concern (reverse proxy / Uvicorn TLS config), not yet configured |

**To actually run it:** `pip install -r backend/requirements.txt && uvicorn main:app --reload` from `backend/`, then open `/docs` for the generated OpenAPI spec - that auto-generated spec *is* the objective-3 API contract deliverable.

### 3.4 Front-End / UX (Telaprolu - objectives 1–8)

| Objective | Status | Evidence |
|---|---|---|
| 1. Systematic review of dashboard design patterns | Done (in Chapter 2 draft) | - |
| 2. Wireframes → high-fidelity prototype, role-based views | Done, as a working prototype | The published prototype is a genuine multi-page application - a persistent sidebar, a dashboard with drill-down buttons into each component, dedicated pages per component (each headed by the responsible student's name and Banner ID), an interactive API explorer that runs each backend route's logic client-side, and a searchable student register with individual profile pages reachable from anywhere via a global "trace student" search |
| 3. React implementation, WCAG 2.1 AA, responsive | Partial - see caveat below | Prototype is vanilla HTML/CSS/JS (an Artifact must be a single self-contained file); a real WCAG-audited React build is still required |
| 4. Role-based access control in the UI | Done, client-side simulation | Role switcher scopes cohort aggregates away from the Advisor role, matching the back-end's data-minimisation rule |
| 5. Interactive risk/trend/feature-breakdown visualisations | Done | Model comparison, reliability diagram, feature importance, fairness chart, per-student factor breakdown - all built from real model output, not placeholders |
| 6. Formal usability study (≥6 participants, SUS) | Not started | Requires ethics approval first - see §5 |
| 7. Iterate on usability findings | Blocked on 6 | - |
| 8. GDPR-safe client-side handling | Satisfied | No PII is stored client-side; student IDs shown are OULAD's anonymised identifiers |

**Important caveat to state plainly in the dissertation:** the published dashboard is a real, data-driven, interaction-complete prototype - useful for validating the information architecture and for early usability testing - but it is not the React/Tailwind/Recharts codebase the spec commits to, and it has not been through an axe-core WCAG audit. Treat it as the *validated design spec* to port into React, not as a substitute for objective 3. Porting is mostly mechanical (the component boundaries - cohort cards, student table, detail panel, four chart types - map directly onto React components) but should not be skipped or glossed over in the write-up.

---

## 4. Immediate next actions (this week)

1. **Adeleke** - write the data dictionary and lineage table from `etl.py`'s `keep_cols` list (objective 3/7); stand up the PostgreSQL/SQLite load script.
2. **Ewa** - `pip install shap` and replace the tree-importance proxy in `train_models.py` with real `shap.TreeExplainer` output; add the early-window-only model variant described in §3.2.
3. **Obah** - write `pytest` unit tests against `backend/main.py`'s existing routes; wire `load_predictions()`/`load_feature_importance()` to the database once Adeleke's schema lands.
4. **Telaprolu** - use `frontend/dashboard.html` as the approved design reference; scaffold the React + Tailwind + Recharts project and port section by section, starting with the student risk register and detail panel since those already have the clearest component boundaries; run axe-core against each page as it's built rather than at the end.
5. **All** - submit the ethics application (Week 8 in every individual work plan) - nothing in §3.4 objectives 6–7 can start before approval, so this is the actual critical-path item, not the modelling or engineering work.

## 5. What genuinely cannot be finished without further access

- **Ethics approval and the 6-participant usability study** - requires UWS Ethics Review Manager sign-off and real recruitment; cannot be simulated.
- **Live PostgreSQL deployment, HTTPS, and Locust load testing** - need a running server environment.
- **True SHAP explanations** - blocked only by `pip install shap` in whatever environment the modelling work continues in; trivial once available.
- **WCAG 2.1 AA conformance** - needs to be verified against the real React build with axe-core, not the prototype.

## 6. Nice-to-have extensions once the core is solid

- Use `vle.csv`'s `activity_type` to break engagement down by material type (forum vs. resource vs. quiz), not just raw click counts - a richer engagement feature than total clicks alone.
- Normalise engagement by `courses.csv`'s `module_presentation_length`, since modules run different lengths.
- Add SMOTE/ADASYN (already justified in the lit review) to the training pipeline and report whether it closes the "No Formal quals" TPR gap found in §3.2.

---

*All figures in this document were generated by running `Prototype/data_engineering/etl.py` and `Prototype/modelling/train_models.py` against the CSVs in `open+university+learning+analytics+dataset/` on 2026-07-24. Re-run both scripts any time the underlying code changes to keep these numbers current.*
