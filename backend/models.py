from datetime import datetime

from sqlalchemy import Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Student(Base):
    """Demographic dimension - one row per OULAD id_student.

    Field lineage: see data_engineering/DATA_LINEAGE.md §1 (all sourced from
    studentInfo.csv, unchanged).
    """

    __tablename__ = "students"

    id_student: Mapped[int] = mapped_column(Integer, primary_key=True)
    gender: Mapped[str] = mapped_column(String(1))
    region: Mapped[str] = mapped_column(String(64))
    highest_education: Mapped[str] = mapped_column(String(64))
    age_band: Mapped[str] = mapped_column(String(16))
    disability: Mapped[str] = mapped_column(String(1))
    imd_band: Mapped[str] = mapped_column(String(16), default="Unknown")

    enrolments: Mapped[list["Enrolment"]] = relationship(back_populates="student")
    interventions: Mapped[list["Intervention"]] = relationship(back_populates="student")


class ModulePresentation(Base):
    """One row per (code_module, code_presentation) course run."""

    __tablename__ = "module_presentations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code_module: Mapped[str] = mapped_column(String(8))
    code_presentation: Mapped[str] = mapped_column(String(8))

    enrolments: Mapped[list["Enrolment"]] = relationship(back_populates="module_presentation")

    __table_args__ = (
        UniqueConstraint("code_module", "code_presentation", name="uq_module_presentation"),
    )


class Enrolment(Base):
    """One row per (student, module, presentation) - the fact grain everything
    else (assessment summary, VLE engagement, risk prediction) hangs off.

    Sourced from studentInfo.csv joined to studentRegistration.csv on
    (code_module, code_presentation, id_student) - see DATA_LINEAGE.md §2-3.
    """

    __tablename__ = "enrolments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_student: Mapped[int] = mapped_column(ForeignKey("students.id_student"))
    module_presentation_id: Mapped[int] = mapped_column(ForeignKey("module_presentations.id"))

    num_of_prev_attempts: Mapped[int] = mapped_column(Integer)
    studied_credits: Mapped[int] = mapped_column(Integer)
    date_registration: Mapped[float] = mapped_column(Float, nullable=True)
    date_unregistration: Mapped[float] = mapped_column(Float, nullable=True)
    final_result: Mapped[str] = mapped_column(String(16))
    withdrawn: Mapped[int] = mapped_column(Integer)  # 1 if final_result == 'Withdrawn'

    student: Mapped["Student"] = relationship(back_populates="enrolments")
    module_presentation: Mapped["ModulePresentation"] = relationship(back_populates="enrolments")
    assessment_summary: Mapped["AssessmentSummary"] = relationship(
        back_populates="enrolment", uselist=False, cascade="all, delete-orphan"
    )
    vle_engagement: Mapped["VleEngagement"] = relationship(
        back_populates="enrolment", uselist=False, cascade="all, delete-orphan"
    )
    risk_predictions: Mapped[list["RiskPrediction"]] = relationship(
        back_populates="enrolment", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("id_student", "module_presentation_id", name="uq_student_module_presentation"),
        Index("ix_enrolments_student", "id_student"),
    )


class AssessmentSummary(Base):
    """Per-enrolment aggregate of studentAssessment.csv + assessments.csv.

    See DATA_LINEAGE.md §4 for the exact aggregation per column.
    """

    __tablename__ = "assessment_summaries"

    enrolment_id: Mapped[int] = mapped_column(ForeignKey("enrolments.id"), primary_key=True)
    n_assessments_submitted: Mapped[int] = mapped_column(Integer)
    n_assessments_expected: Mapped[int] = mapped_column(Integer)
    submission_rate: Mapped[float] = mapped_column(Float)
    mean_score: Mapped[float] = mapped_column(Float)
    min_score: Mapped[float] = mapped_column(Float)
    weighted_score: Mapped[float] = mapped_column(Float)
    mean_days_late: Mapped[float] = mapped_column(Float)
    pct_late: Mapped[float] = mapped_column(Float)

    enrolment: Mapped["Enrolment"] = relationship(back_populates="assessment_summary")


class VleEngagement(Base):
    """Per-enrolment aggregate of studentVle.csv clicks.

    See DATA_LINEAGE.md §5 for the exact aggregation per column.
    """

    __tablename__ = "vle_engagements"

    enrolment_id: Mapped[int] = mapped_column(ForeignKey("enrolments.id"), primary_key=True)
    total_clicks: Mapped[float] = mapped_column(Float)
    active_days: Mapped[int] = mapped_column(Integer)
    mean_clicks_per_active_day: Mapped[float] = mapped_column(Float)
    early_clicks: Mapped[float] = mapped_column(Float)
    early_active_days: Mapped[int] = mapped_column(Integer)

    enrolment: Mapped["Enrolment"] = relationship(back_populates="vle_engagement")


class RiskPrediction(Base):
    """One scored prediction run for an enrolment. Kept append-only (not
    updated in place) so risk-score history per student is preserved.
    """

    __tablename__ = "risk_predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enrolment_id: Mapped[int] = mapped_column(ForeignKey("enrolments.id"))
    risk_score: Mapped[float] = mapped_column(Float)
    risk_band: Mapped[str] = mapped_column(String(8))  # low | medium | high
    model_version: Mapped[str] = mapped_column(String(32), default="xgboost-v1")
    scored_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    enrolment: Mapped["Enrolment"] = relationship(back_populates="risk_predictions")
    factors: Mapped[list["FeatureAttribution"]] = relationship(
        back_populates="prediction", cascade="all, delete-orphan", order_by="FeatureAttribution.rank"
    )

    __table_args__ = (Index("ix_risk_predictions_enrolment", "enrolment_id"),)


class FeatureAttribution(Base):
    """One SHAP-signed contribution row within a RiskPrediction's top_factors."""

    __tablename__ = "feature_attributions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("risk_predictions.id"))
    feature: Mapped[str] = mapped_column(String(64))
    contribution: Mapped[float] = mapped_column(Float)
    rank: Mapped[int] = mapped_column(Integer)  # 0 = largest absolute contribution

    prediction: Mapped["RiskPrediction"] = relationship(back_populates="factors")


class Intervention(Base):
    """Outreach action logged against a student. Mirrors main.py's
    InterventionRecord/InterventionCreate Pydantic contract exactly, so
    swapping main.py's in-memory _INTERVENTIONS list for this table is a
    drop-in change once a live database is deployed.
    """

    __tablename__ = "interventions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_student: Mapped[int] = mapped_column(ForeignKey("students.id_student"))
    created_by: Mapped[str] = mapped_column(String(64))
    note: Mapped[str] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    student: Mapped["Student"] = relationship(back_populates="interventions")

    __table_args__ = (Index("ix_interventions_student", "id_student"),)
