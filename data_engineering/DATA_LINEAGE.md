# Data lineage — modelling features

Every column in `output/processed_student_data.csv` (the table `train_models.py`
trains on) traced back to its OULAD source file(s) and the transform applied in
`data_engineering/etl.py`. Grouped by stage; join keys are
`(code_module, code_presentation, id_student)` throughout.

## 1. Passed through unchanged from `studentInfo.csv`

| Feature | Source column | Transform |
|---|---|---|
| `code_module` | `studentInfo.code_module` | none |
| `code_presentation` | `studentInfo.code_presentation` | none |
| `id_student` | `studentInfo.id_student` | none |
| `gender` | `studentInfo.gender` | none |
| `region` | `studentInfo.region` | none |
| `highest_education` | `studentInfo.highest_education` | none |
| `age_band` | `studentInfo.age_band` | none |
| `num_of_prev_attempts` | `studentInfo.num_of_prev_attempts` | none |
| `studied_credits` | `studentInfo.studied_credits` | none |
| `disability` | `studentInfo.disability` | none |
| `final_result` | `studentInfo.final_result` | none — retained for evaluation/display, withheld from advisors before a presentation ends |
| `imd_band` | `studentInfo.imd_band` | `"?"` → `NaN` → filled with the literal string `"Unknown"` (`engineer_features`) |

## 2. Derived label

| Feature | Source column | Transform |
|---|---|---|
| `withdrawn` | `studentInfo.final_result` | `1` if `final_result == "Withdrawn"`, else `0` — this is the model's binary target |

## 3. Registration timing, from `studentRegistration.csv`

Joined to `studentInfo` on the three-part key (left join).

| Feature | Source column | Transform |
|---|---|---|
| `date_registration` | `studentRegistration.date_registration` | cast numeric; missing values filled with the column median |
| `date_unregistration` | `studentRegistration.date_unregistration` | `"?"` → `NaN` → cast numeric; left null when the student never unregistered (no fill — nullability is meaningful here) |

## 4. Assessment performance, from `studentAssessment.csv` + `assessments.csv`

`studentAssessment` (one row per submission) is joined to `assessments` (the
per-module-presentation assessment calendar) on `id_assessment`, then
aggregated to one row per `(code_module, code_presentation, id_student)`.

| Feature | Source column(s) | Transform |
|---|---|---|
| `n_assessments_submitted` | `studentAssessment.score` | `count()` of non-null submissions per student |
| `mean_score` | `studentAssessment.score` | `mean()` per student; missing (no submissions) filled with the column median |
| `min_score` | `studentAssessment.score` | `min()` per student; missing filled with the column median |
| `weighted_score` | `studentAssessment.score`, `assessments.weight` | weighted average of `score` using `assessments.weight` (`+1e-9` to avoid a zero-weight division); missing filled with the column median |
| `mean_days_late` | `studentAssessment.date_submitted`, `assessments.date` | `days_late = max(date_submitted - date, 0)` per submission, then `mean()` per student; missing filled with the column median |
| `pct_late` | same as above | fraction of a student's submissions where `days_late > 0` |
| `n_assessments_expected` | `assessments.id_assessment` | count of assessments defined for that `(code_module, code_presentation)`, independent of the student |
| `submission_rate` | `n_assessments_submitted`, `n_assessments_expected` | `n_assessments_submitted / n_assessments_expected`, clipped to `[0, 1]`; `0` where a student submitted nothing |

## 5. VLE engagement, from `studentVle.csv`

Daily per-student click logs (`sum_click`), aggregated per
`(code_module, code_presentation, id_student)`.

| Feature | Source column(s) | Transform |
|---|---|---|
| `total_clicks` | `studentVle.sum_click` | `sum()` per student across the whole presentation |
| `active_days` | `studentVle.date` | count of distinct `date` values with any click activity |
| `mean_clicks_per_active_day` | `studentVle.sum_click` | `mean()` of daily click sums |
| `early_clicks` | `studentVle.sum_click` where `date <= 28` | `sum()` restricted to the first 28 days of the presentation — the early-warning engagement signal |
| `early_active_days` | `studentVle.date` where `date <= 28` | distinct-day count restricted to the same 28-day window |

All five are `0`-filled where a student has no VLE log rows at all (they never
logged in), which is a genuine, meaningful value here rather than missing data.

## Not currently used (available for a future iteration)

- `vle.csv` (`activity_type`, material metadata) — would let engagement be
  broken down by material type (forum / resource / quiz) instead of raw click
  totals. See `COMPLETION_PLAN.md` §6.
- `courses.csv` (`module_presentation_length`) — would let `total_clicks` /
  `active_days` be normalised by how long the presentation actually runs,
  since modules vary in length.

## Provenance

Source: Open University Learning Analytics Dataset (Kuzilek, Hlosta & Zdrahal,
2017), CC BY 4.0. Every transform above is implemented in
`data_engineering/etl.py::engineer_features`; this table is a direct
description of that function, not a separate design document that could drift
from the code.
