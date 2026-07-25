"""
FastAPI backend contract for the Early Warning Platform.

Maps to Back-End component objectives 3-6: RESTful endpoints for risk scores,
SHAP-style explanations, cohort statistics, and intervention records; JWT
role-based auth scoping responses by role; SQLAlchemy-style data access
(here backed by the CSV/JSON artefacts produced by the data-engineering and
modelling stages so the contract can be exercised without standing up
Postgres). Swap `load_*` for real SQLAlchemy queries once the database is
provisioned - the route signatures and response models do not need to change.

Run: uvicorn main:app --reload
Docs: http://127.0.0.1:8000/docs
"""
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordBearer
from fastapi.staticfiles import StaticFiles
from jose import JWTError, jwt
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
FRONTEND_DIR = ROOT / "frontend"
# Set a real value via the SECRET_KEY environment variable in any deployment
# beyond a local demo - a hardcoded fallback is fine for `uvicorn --reload`
# on localhost only.
SECRET_KEY = os.environ.get("SECRET_KEY", "CHANGE_ME_IN_ENV")  # pragma: allowlist secret
ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = 30

app = FastAPI(
    title="Early Warning Platform API",
    version="0.1.0",
    description="Serves student attrition risk scores, explanations, cohort "
                 "statistics and intervention logs to the role-based front-end.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # demo-only - scope to the real front-end origin in production
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

Role = Literal["administrator", "advisor", "module_leader"]


# ---------------------------------------------------------------------------
# Schemas (Pydantic models -> OpenAPI / nested JSON contract, spec obj. 3 & 5)
# ---------------------------------------------------------------------------

class TokenData(BaseModel):
    sub: str
    role: Role


class FeatureAttribution(BaseModel):
    feature: str
    contribution: float


class StudentRisk(BaseModel):
    id_student: int
    code_module: str
    code_presentation: str
    risk_score: float
    risk_band: Literal["low", "medium", "high"]
    top_factors: List[FeatureAttribution]


class CohortOverview(BaseModel):
    code_module: Optional[str]
    n_students: int
    mean_risk: float
    pct_high_risk: float
    withdrawal_rate_historic: float


class InterventionRecord(BaseModel):
    id_student: int
    created_by: str
    note: str
    created_at: datetime


class InterventionCreate(BaseModel):
    id_student: int
    note: str


# ---------------------------------------------------------------------------
# Auth (JWT role-based access control, spec objective 4)
# ---------------------------------------------------------------------------

def create_access_token(subject: str, role: Role) -> str:
    expire = datetime.utcnow() + timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    payload = {"sub": subject, "role": role, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(token: str = Depends(oauth2_scheme)) -> TokenData:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return TokenData(sub=payload["sub"], role=payload["role"])
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Could not validate credentials")


def require_role(*allowed: Role):
    def checker(user: TokenData = Depends(get_current_user)) -> TokenData:
        if user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role for this resource")
        return user
    return checker


# ---------------------------------------------------------------------------
# Data access (swap for SQLAlchemy sessions against Postgres in production)
# ---------------------------------------------------------------------------

def load_predictions():
    path = OUT / "sample_predictions.json"
    if not path.exists():
        return []
    return json.loads(path.read_text())


def load_feature_importance():
    path = OUT / "feature_importance.json"
    if not path.exists():
        return []
    return json.loads(path.read_text())


def risk_band(score: float) -> str:
    if score >= 0.6:
        return "high"
    if score >= 0.3:
        return "medium"
    return "low"


_INTERVENTIONS: List[InterventionRecord] = []  # in-memory demo store


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.post("/auth/token", tags=["auth"])
def login(username: str, role: Role):
    """Demo login - real deploy validates against institutional SSO/IdP."""
    token = create_access_token(username, role)
    return {"access_token": token, "token_type": "bearer"}


@app.get("/students", response_model=List[StudentRisk], tags=["students"])
def list_students(
    code_module: Optional[str] = Query(None),
    min_risk: float = Query(0.0, ge=0, le=1),
    limit: int = Query(50, le=500),
    offset: int = 0,
    user: TokenData = Depends(require_role("administrator", "advisor", "module_leader")),
):
    """Paginated, filterable list of students with current risk score."""
    rows = load_predictions()
    fi = load_feature_importance()[:3]
    out = []
    for r in rows:
        if code_module and r["code_module"] != code_module:
            continue
        if r["risk_score"] < min_risk:
            continue
        out.append(StudentRisk(
            id_student=r["id_student"], code_module=r["code_module"],
            code_presentation=r["code_presentation"], risk_score=r["risk_score"],
            risk_band=risk_band(r["risk_score"]),
            top_factors=[FeatureAttribution(feature=f["feature"], contribution=f["importance"]) for f in fi],
        ))
    return out[offset: offset + limit]


@app.get("/students/{id_student}/risk", response_model=StudentRisk, tags=["students"])
def get_student_risk(
    id_student: int,
    user: TokenData = Depends(require_role("administrator", "advisor", "module_leader")),
):
    """Individual risk score + SHAP-style top contributing factors."""
    rows = load_predictions()
    match = next((r for r in rows if r["id_student"] == id_student), None)
    if not match:
        raise HTTPException(404, "Student not found in current scored cohort")
    fi = load_feature_importance()[:5]
    return StudentRisk(
        id_student=match["id_student"], code_module=match["code_module"],
        code_presentation=match["code_presentation"], risk_score=match["risk_score"],
        risk_band=risk_band(match["risk_score"]),
        top_factors=[FeatureAttribution(feature=f["feature"], contribution=f["importance"]) for f in fi],
    )


@app.get("/cohort/overview", response_model=List[CohortOverview], tags=["cohort"])
def cohort_overview(
    user: TokenData = Depends(require_role("administrator", "module_leader")),
):
    """Cohort-level aggregates - restricted from the advisor role (data minimisation)."""
    import pandas as pd
    rows = load_predictions()
    if not rows:
        return []
    df = pd.DataFrame(rows)
    out = []
    for module, g in df.groupby("code_module"):
        out.append(CohortOverview(
            code_module=module, n_students=len(g),
            mean_risk=round(float(g.risk_score.mean()), 3),
            pct_high_risk=round(float((g.risk_score >= 0.6).mean() * 100), 1),
            withdrawal_rate_historic=round(float(g.true_label.mean() * 100), 1),
        ))
    return out


@app.post("/interventions", response_model=InterventionRecord, tags=["interventions"])
def log_intervention(
    payload: InterventionCreate,
    user: TokenData = Depends(require_role("advisor", "module_leader")),
):
    """Record an outreach/intervention action taken for a flagged student."""
    record = InterventionRecord(
        id_student=payload.id_student, created_by=user.sub,
        note=payload.note, created_at=datetime.utcnow(),
    )
    _INTERVENTIONS.append(record)
    return record


@app.get("/interventions/{id_student}", response_model=List[InterventionRecord], tags=["interventions"])
def get_interventions(
    id_student: int,
    user: TokenData = Depends(require_role("administrator", "advisor", "module_leader")),
):
    return [r for r in _INTERVENTIONS if r.id_student == id_student]


@app.get("/health", tags=["ops"])
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Front-end - served by this same process so a deployment only needs one
# service on one port. Must be registered last: Starlette matches routes in
# the order they were added, so every /students, /health, etc. route above
# still wins over the catch-all static mount below.
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/dashboard.html")

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
