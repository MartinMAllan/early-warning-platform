"""Load test against the live API.

Run with a server already up (e.g. `uvicorn backend.main:app`):

    locust -f backend/locustfile.py --host http://127.0.0.1:8000

Each simulated user logs in once (as a randomly assigned role, matching the
three real roles main.py enforces) and then repeatedly calls the endpoints
that role is allowed to use, at roughly the traffic mix an advisor/module
leader dashboard session would produce: mostly reads of the student list and
individual profiles, occasional cohort look-ups, rare intervention writes.
"""

import random

from locust import HttpUser, between, task

ROLES = ["admin", "advisor", "module_leader"]


class DashboardUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        self.role = random.choice(ROLES)
        resp = self.client.post(
            "/auth/token",
            params={"username": f"loadtest_{self.role}", "role": self.role},
            name="/auth/token",
        )
        resp.raise_for_status()
        token = resp.json()["access_token"]
        self.auth_header = {"Authorization": f"Bearer {token}"}
        self.known_student_ids = []

    @task(6)
    def list_students(self):
        with self.client.get(
            "/api/students", params={"limit": 20}, headers=self.auth_header,
            name="/api/students", catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                self.known_student_ids = [row["id_student"] for row in resp.json()]
                resp.success()
            else:
                resp.failure(f"unexpected status {resp.status_code}")

    @task(5)
    def get_student_risk(self):
        if not self.known_student_ids:
            return
        student_id = random.choice(self.known_student_ids)
        self.client.get(
            f"/api/students/{student_id}", headers=self.auth_header,
            name="/api/students/[id]",
        )

    @task(2)
    def cohort_overview(self):
        # Real endpoint restriction (admin/module_leader only): an advisor
        # user here should consistently get 403, which is the behaviour
        # under test, not a failure - see the catch_response block below.
        with self.client.get(
            "/api/cohort", headers=self.auth_header, name="/api/cohort",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200 or (resp.status_code == 403 and self.role == "advisor"):
                resp.success()
            else:
                resp.failure(f"unexpected status {resp.status_code} for role {self.role}")

    @task(1)
    def log_intervention(self):
        if not self.known_student_ids or self.role not in ("advisor", "module_leader"):
            return
        student_id = random.choice(self.known_student_ids)
        self.client.post(
            "/api/interventions",
            json={"student_id": student_id, "note": "Load-test outreach note."},
            headers=self.auth_header,
            name="/api/interventions",
        )

    @task(1)
    def get_interventions(self):
        if not self.known_student_ids:
            return
        student_id = random.choice(self.known_student_ids)
        self.client.get(
            f"/api/interventions/{student_id}", headers=self.auth_header,
            name="/api/interventions/[id]",
        )
