"""HTTP contract tests for the FastAPI application."""

import os
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

_temporary_directory = tempfile.TemporaryDirectory()
os.environ["DATABASE_PATH"] = str(Path(_temporary_directory.name) / "web-api.db")
os.environ["LLM_PROVIDER"] = "mock"

from fastapi.testclient import TestClient  # noqa: E402
from database import reset_database_instance  # noqa: E402

reset_database_instance()
from web_app import app  # noqa: E402


class WebApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_context = TestClient(app)
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client_context.__exit__(None, None, None)

    def test_health_and_doctor_availability(self):
        health = self.client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["ai_mode"], "offline")

        response = self.client.get("/api/doctors/BS001/availability?date=2026-09-20")
        self.assertEqual(response.status_code, 200)
        self.assertIn("09:00", response.json()["data"]["available_slots"])

    def test_chat_works_without_external_ai_key(self):
        response = self.client.post(
            "/api/chat",
            json={"message": "Quy trình đặt lịch khám như thế nào?"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["ai_mode"], "offline")
        self.assertIn("chọn chuyên khoa", response.json()["answer"].lower())

    def test_appointment_create_lookup_and_cancel(self):
        created = self.client.post(
            "/api/appointments",
            json={
                "patient_id": "BN-API-01",
                "patient_name": "Nguyễn Văn Nam",
                "phone": "0901234567",
                "email": "nam@example.com",
                "doctor_id": "BS001",
                "appointment_date": "2026-09-20",
                "appointment_time": "10:30",
            },
        )
        self.assertEqual(created.status_code, 201)
        booking_id = created.json()["data"]["booking_id"]

        lookup = self.client.get(
            f"/api/appointments/{booking_id}?patient_id=BN-API-01"
        )
        self.assertEqual(lookup.status_code, 200)
        self.assertEqual(lookup.json()["data"]["status"], "CONFIRMED")

        cancelled = self.client.post(
            f"/api/appointments/{booking_id}/cancel",
            json={"patient_id": "BN-API-01"},
        )
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.json()["data"]["status"], "CANCELLED")


def tearDownModule():
    _temporary_directory.cleanup()


if __name__ == "__main__":
    unittest.main()
