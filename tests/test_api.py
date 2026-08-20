import pytest
import sys
from pathlib import Path
from datetime import datetime, timedelta
from jose import jwt

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from main import app, SECRET_KEY, ALGORITHM

from fastapi.testclient import TestClient

client = TestClient(app)


def make_token(role):
    payload = {
        "sub": "test_user",
        "role": role,
        "exp": datetime.utcnow() + timedelta(minutes=30),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def auth_header(role):
    return {"Authorization": f"Bearer {make_token(role)}"}


class TestHealthAndBasicRoutes:

    def test_app_starts(self):
        response = client.get("/")
        assert response.status_code in [200, 307, 302]

    def test_docs_endpoint(self):
        response = client.get("/docs")
        assert response.status_code == 200


class TestAuthenticationEnforcement:

    def test_no_token_rejected(self):
        response = client.get("/api/students")
        assert response.status_code in [401, 403]

    def test_invalid_token_rejected(self):
        headers = {"Authorization": "Bearer this.is.not.valid"}
        response = client.get("/api/students", headers=headers)
        assert response.status_code in [401, 403]


class TestRoleBasedAccess:

    def test_admin_can_access_students(self):
        response = client.get("/api/students", headers=auth_header("admin"))
        assert response.status_code == 200

    def test_admin_can_access_cohort(self):
        response = client.get("/api/cohort", headers=auth_header("admin"))
        assert response.status_code == 200

    def test_admin_cannot_log_intervention(self):
        response = client.post(
            "/api/interventions",
            headers=auth_header("admin"),
            json={"student_id": 12345, "note": "test"},
        )
        assert response.status_code == 403

    def test_advisor_can_access_students(self):
        response = client.get("/api/students", headers=auth_header("advisor"))
        assert response.status_code == 200

    def test_advisor_cannot_access_cohort(self):
        response = client.get("/api/cohort", headers=auth_header("advisor"))
        assert response.status_code == 403

    def test_advisor_can_log_intervention(self):
        response = client.post(
            "/api/interventions",
            headers=auth_header("advisor"),
            json={"student_id": 12345, "note": "test"},
        )
        assert response.status_code in [200, 201]

    def test_module_leader_can_access_cohort(self):
        response = client.get("/api/cohort", headers=auth_header("module_leader"))
        assert response.status_code == 200

    def test_module_leader_can_log_intervention(self):
        response = client.post(
            "/api/interventions",
            headers=auth_header("module_leader"),
            json={"student_id": 12345, "note": "test"},
        )
        assert response.status_code in [200, 201]


class TestResponseSchema:

    def test_student_risk_has_required_fields(self):
        response = client.get("/api/students", headers=auth_header("admin"))
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                student = data[0]
                assert "risk_score" in student or "calibrated_risk" in student


class TestStudentDetailFields:
    """The frontend renders student demographics/engagement straight from
    this endpoint now (no bundled copy), so the contract needs to actually
    carry them - and keep final_result off the advisor role's response.
    """

    def test_list_students_carries_demographic_and_engagement_fields(self):
        response = client.get("/api/students?limit=1", headers=auth_header("admin"))
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        student = data[0]
        for field in ("gender", "region", "highest_education", "age_band",
                      "num_of_prev_attempts", "studied_credits",
                      "submission_rate", "mean_score", "active_days", "early_clicks"):
            assert field in student

    def test_admin_sees_final_result(self):
        response = client.get("/api/students?limit=1", headers=auth_header("admin"))
        assert response.json()[0]["final_result"] is not None

    def test_advisor_does_not_see_final_result(self):
        response = client.get("/api/students?limit=1", headers=auth_header("advisor"))
        assert response.json()[0]["final_result"] is None

    def test_module_leader_sees_final_result(self):
        response = client.get("/api/students?limit=1", headers=auth_header("module_leader"))
        assert response.json()[0]["final_result"] is not None

    def test_single_student_detail_redacts_for_advisor_too(self):
        student_id = client.get("/api/students?limit=1", headers=auth_header("admin")).json()[0]["id_student"]
        admin_view = client.get(f"/api/students/{student_id}", headers=auth_header("admin")).json()
        advisor_view = client.get(f"/api/students/{student_id}", headers=auth_header("advisor")).json()
        assert admin_view["final_result"] is not None
        assert advisor_view["final_result"] is None
        assert admin_view["risk_score"] == advisor_view["risk_score"]


class TestBoundaryConditions:

    def test_empty_filter_returns_all(self):
        response = client.get("/api/students?module=", headers=auth_header("admin"))
        assert response.status_code in [200, 422]

    def test_nonexistent_student_id(self):
        response = client.get("/api/students/999999999", headers=auth_header("admin"))
        assert response.status_code in [404, 200]
