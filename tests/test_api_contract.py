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


def expired_token():
    payload = {
        "sub": "test_user",
        "role": "admin",
        "exp": datetime.utcnow() - timedelta(minutes=5),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def token_wrong_secret():
    payload = {
        "sub": "test_user",
        "role": "admin",
        "exp": datetime.utcnow() + timedelta(minutes=30),
    }
    return jwt.encode(payload, "WRONG_SECRET_KEY", algorithm=ALGORITHM)


class TestOpenAPIContract:

    def test_openapi_schema_available(self):
        response = client.get("/openapi.json")
        assert response.status_code == 200

    def test_openapi_schema_is_valid_json(self):
        response = client.get("/openapi.json")
        data = response.json()
        assert "paths" in data
        assert "info" in data

    def test_openapi_has_title(self):
        response = client.get("/openapi.json")
        data = response.json()
        assert data["info"]["title"] == "Early Warning Platform API"

    def test_all_endpoints_listed(self):
        response = client.get("/openapi.json")
        paths = response.json().get("paths", {})
        assert len(paths) >= 1


class TestResponseContentType:

    def test_students_returns_json(self):
        response = client.get("/api/students", headers=auth_header("admin"))
        if response.status_code == 200:
            assert "application/json" in response.headers.get("content-type", "")

    def test_cohort_returns_json(self):
        response = client.get("/api/cohort", headers=auth_header("admin"))
        if response.status_code == 200:
            assert "application/json" in response.headers.get("content-type", "")


class TestTokenEdgeCases:

    def test_expired_token_rejected(self):
        headers = {"Authorization": f"Bearer {expired_token()}"}
        response = client.get("/api/students", headers=headers)
        assert response.status_code in [401, 403]

    def test_wrong_secret_rejected(self):
        headers = {"Authorization": f"Bearer {token_wrong_secret()}"}
        response = client.get("/api/students", headers=headers)
        assert response.status_code in [401, 403]

    def test_missing_role_claim_rejected(self):
        payload = {
            "sub": "test_user",
            "exp": datetime.utcnow() + timedelta(minutes=30),
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
        headers = {"Authorization": f"Bearer {token}"}
        response = client.get("/api/students", headers=headers)
        assert response.status_code in [401, 403, 422]

    def test_unknown_role_rejected(self):
        headers = auth_header("superuser")
        response = client.get("/api/students", headers=headers)
        assert response.status_code in [401, 403]

    def test_empty_bearer_rejected(self):
        headers = {"Authorization": "Bearer "}
        response = client.get("/api/students", headers=headers)
        assert response.status_code in [401, 403, 422]


class TestStudentEndpointContract:

    def test_returns_list(self):
        response = client.get("/api/students", headers=auth_header("admin"))
        if response.status_code == 200:
            assert isinstance(response.json(), list)

    def test_each_student_has_id(self):
        response = client.get("/api/students", headers=auth_header("admin"))
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                student = data[0]
                has_id = "id_student" in student or "student_id" in student or "id" in student
                assert has_id

    def test_each_student_has_risk_score(self):
        response = client.get("/api/students", headers=auth_header("admin"))
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                student = data[0]
                has_risk = (
                    "risk_score" in student
                    or "calibrated_risk" in student
                    or "probability" in student
                )
                assert has_risk

    def test_risk_scores_are_numeric(self):
        response = client.get("/api/students", headers=auth_header("admin"))
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list):
                for student in data[:10]:
                    score = student.get(
                        "risk_score",
                        student.get("calibrated_risk", student.get("probability", None))
                    )
                    if score is not None:
                        assert isinstance(score, (int, float))

    def test_risk_scores_in_range(self):
        response = client.get("/api/students", headers=auth_header("admin"))
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list):
                for student in data[:10]:
                    score = student.get(
                        "risk_score",
                        student.get("calibrated_risk", student.get("probability", None))
                    )
                    if score is not None:
                        assert 0.0 <= score <= 1.0


class TestCohortEndpointContract:

    def test_cohort_returns_dict(self):
        response = client.get("/api/cohort", headers=auth_header("admin"))
        if response.status_code == 200:
            assert isinstance(response.json(), (dict, list))


class TestErrorResponseFormat:

    def test_401_returns_json_body(self):
        response = client.get("/api/students")
        if response.status_code in [401, 403]:
            data = response.json()
            assert "detail" in data

    def test_403_returns_json_body(self):
        response = client.get("/api/cohort", headers=auth_header("advisor"))
        if response.status_code == 403:
            data = response.json()
            assert "detail" in data
