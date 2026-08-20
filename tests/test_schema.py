import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from database import Base
import models  # noqa: F401 - registers model classes on Base.metadata


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return engine, Session()


def test_all_tables_created():
    engine, _ = make_session()
    tables = set(inspect(engine).get_table_names())
    expected = {
        "students", "module_presentations", "enrolments",
        "assessment_summaries", "vle_engagements",
        "risk_predictions", "feature_attributions", "interventions",
    }
    assert expected.issubset(tables)


def test_enrolment_round_trip_with_relationships():
    engine, session = make_session()

    student = models.Student(
        id_student=627690, gender="F", region="East Anglian Region",
        highest_education="A Level or Equivalent", age_band="0-35",
        disability="N", imd_band="Unknown",
    )
    module = models.ModulePresentation(code_module="DDD", code_presentation="2014B")
    session.add_all([student, module])
    session.flush()

    enrolment = models.Enrolment(
        id_student=student.id_student, module_presentation_id=module.id,
        num_of_prev_attempts=0, studied_credits=120,
        date_registration=-53, date_unregistration=None,
        final_result="Withdrawn", withdrawn=1,
    )
    session.add(enrolment)
    session.flush()

    enrolment.assessment_summary = models.AssessmentSummary(
        enrolment_id=enrolment.id, n_assessments_submitted=0, n_assessments_expected=6,
        submission_rate=0.0, mean_score=76.0, min_score=76.0, weighted_score=76.0,
        mean_days_late=0.0, pct_late=0.0,
    )
    enrolment.vle_engagement = models.VleEngagement(
        enrolment_id=enrolment.id, total_clicks=0, active_days=0,
        mean_clicks_per_active_day=0.0, early_clicks=0, early_active_days=0,
    )
    prediction = models.RiskPrediction(
        enrolment_id=enrolment.id, risk_score=0.9736, risk_band="high",
    )
    prediction.factors = [
        models.FeatureAttribution(feature="submission_rate", contribution=1.7299, rank=0),
        models.FeatureAttribution(feature="active_days", contribution=0.9498, rank=1),
    ]
    session.add(prediction)
    session.commit()

    fetched = session.get(models.Enrolment, enrolment.id)
    assert fetched.student.id_student == 627690
    assert fetched.assessment_summary.mean_score == 76.0
    assert fetched.vle_engagement.total_clicks == 0
    assert len(fetched.risk_predictions) == 1
    assert fetched.risk_predictions[0].factors[0].feature == "submission_rate"


def test_intervention_matches_api_contract_shape():
    engine, session = make_session()
    student = models.Student(
        id_student=1, gender="M", region="Scotland", highest_education="HE Qualification",
        age_band="35-55", disability="N", imd_band="Unknown",
    )
    session.add(student)
    session.flush()

    record = models.Intervention(id_student=1, created_by="advisor_demo", note="Reached out by email.")
    session.add(record)
    session.commit()

    fetched = session.query(models.Intervention).one()
    assert fetched.id_student == 1
    assert fetched.created_by == "advisor_demo"
    assert fetched.created_at is not None
