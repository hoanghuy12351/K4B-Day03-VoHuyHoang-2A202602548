"""Core persistence tests for the web MVP."""

import tempfile
import unittest
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from database import AppointmentDatabase  # noqa: E402


class AppointmentDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database = AppointmentDatabase(
            Path(self.temporary_directory.name) / "appointments.db"
        )
        self.database.initialize()

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_seeded_doctors_and_availability_are_readable(self):
        doctors = self.database.list_doctors()
        self.assertEqual(len(doctors), 2)

        availability = self.database.get_availability("BS001", "2026-09-20")
        self.assertIsNotNone(availability)
        self.assertEqual(
            availability["available_slots"], ["09:00", "10:30", "14:00"]
        )

    def test_booking_reserves_slot_and_cancellation_reopens_it(self):
        appointment = self.database.create_appointment(
            patient_id="BN2026001",
            patient_name="Nguyễn Văn Nam",
            phone="0901234567",
            email="nam@example.com",
            doctor_id="BS001",
            appointment_date="2026-09-20",
            appointment_time="09:00",
        )
        self.assertEqual(appointment["status"], "CONFIRMED")
        self.assertNotIn(
            "09:00",
            self.database.get_availability("BS001", "2026-09-20")[
                "available_slots"
            ],
        )

        with self.assertRaises(ValueError):
            self.database.create_appointment(
                patient_id="BN2026002",
                patient_name="Trần Thị Hoa",
                phone="0912345678",
                doctor_id="BS001",
                appointment_date="2026-09-20",
                appointment_time="09:00",
            )

        cancelled = self.database.cancel_appointment(
            appointment["booking_id"], "BN2026001"
        )
        self.assertEqual(cancelled["status"], "CANCELLED")
        self.assertIn(
            "09:00",
            self.database.get_availability("BS001", "2026-09-20")[
                "available_slots"
            ],
        )


if __name__ == "__main__":
    unittest.main()
