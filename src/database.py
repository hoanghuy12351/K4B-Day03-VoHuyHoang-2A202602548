"""SQLite persistence for the healthcare appointment MVP."""

from __future__ import annotations

import os
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "data" / "healthcare_mvp.db"


SEED_DOCTORS = (
    {
        "id": "BS001",
        "name": "Nguyễn Minh An",
        "specialty": "Tim mạch",
        "workplace": "Vinmec Times City",
        "experience_years": 12,
        "description": "Tư vấn và theo dõi các bệnh lý tim mạch ở người trưởng thành.",
        "slots": {
            "2026-09-20": ("09:00", "10:30", "14:00"),
            "2026-09-21": ("08:00", "09:30", "15:00"),
        },
    },
    {
        "id": "BS002",
        "name": "Trần Thu Hà",
        "specialty": "Nhi khoa",
        "workplace": "Vinmec Times City",
        "experience_years": 9,
        "description": "Khám tổng quát, tư vấn dinh dưỡng và theo dõi sức khỏe trẻ em.",
        "slots": {
            "2026-09-20": ("08:30", "10:00", "13:30"),
            "2026-09-21": ("09:00", "14:30"),
        },
    },
)


class AppointmentDatabase:
    """Small repository layer with one SQLite connection per operation."""

    def __init__(self, path: str | Path | None = None) -> None:
        configured_path = path or os.getenv("DATABASE_PATH") or DEFAULT_DATABASE_PATH
        self.path = Path(configured_path)
        if not self.path.is_absolute():
            self.path = PROJECT_ROOT / self.path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS doctors (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    specialty TEXT NOT NULL,
                    workplace TEXT NOT NULL,
                    experience_years INTEGER NOT NULL DEFAULT 0,
                    description TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS schedule_slots (
                    doctor_id TEXT NOT NULL,
                    appointment_date TEXT NOT NULL,
                    appointment_time TEXT NOT NULL,
                    is_available INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY (doctor_id, appointment_date, appointment_time),
                    FOREIGN KEY (doctor_id) REFERENCES doctors(id)
                );

                CREATE TABLE IF NOT EXISTS appointments (
                    booking_id TEXT PRIMARY KEY,
                    patient_id TEXT NOT NULL,
                    patient_name TEXT NOT NULL,
                    phone TEXT NOT NULL DEFAULT '',
                    email TEXT NOT NULL DEFAULT '',
                    doctor_id TEXT NOT NULL,
                    appointment_date TEXT NOT NULL,
                    appointment_time TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'CONFIRMED',
                    created_at TEXT NOT NULL,
                    cancelled_at TEXT,
                    FOREIGN KEY (doctor_id) REFERENCES doctors(id)
                );

                CREATE UNIQUE INDEX IF NOT EXISTS one_confirmed_appointment_per_slot
                ON appointments(doctor_id, appointment_date, appointment_time)
                WHERE status = 'CONFIRMED';
                """
            )

            for doctor in SEED_DOCTORS:
                connection.execute(
                    """
                    INSERT INTO doctors (
                        id, name, specialty, workplace, experience_years, description
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        name = excluded.name,
                        specialty = excluded.specialty,
                        workplace = excluded.workplace,
                        experience_years = excluded.experience_years,
                        description = excluded.description
                    """,
                    (
                        doctor["id"],
                        doctor["name"],
                        doctor["specialty"],
                        doctor["workplace"],
                        doctor["experience_years"],
                        doctor["description"],
                    ),
                )
                for appointment_date, slots in doctor["slots"].items():
                    for appointment_time in slots:
                        connection.execute(
                            """
                            INSERT OR IGNORE INTO schedule_slots (
                                doctor_id, appointment_date, appointment_time
                            ) VALUES (?, ?, ?)
                            """,
                            (doctor["id"], appointment_date, appointment_time),
                        )

    def list_doctors(self, specialty: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM doctors"
        parameters: tuple[Any, ...] = ()
        if specialty:
            query += " WHERE specialty = ? COLLATE NOCASE"
            parameters = (specialty.strip(),)
        query += " ORDER BY specialty, name"

        with self._connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [dict(row) for row in rows]

    def get_doctor(self, doctor_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM doctors WHERE id = ?", (doctor_id.strip().upper(),)
            ).fetchone()
        return dict(row) if row else None

    def find_doctor(self, doctor_name: str, specialty: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM doctors
                WHERE name = ? COLLATE NOCASE AND specialty = ? COLLATE NOCASE
                """,
                (doctor_name.strip(), specialty.strip()),
            ).fetchone()
        return dict(row) if row else None

    def get_availability(self, doctor_id: str, appointment_date: str) -> dict[str, Any] | None:
        doctor = self.get_doctor(doctor_id)
        if doctor is None:
            return None

        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT appointment_time FROM schedule_slots
                WHERE doctor_id = ? AND appointment_date = ? AND is_available = 1
                ORDER BY appointment_time
                """,
                (doctor["id"], appointment_date),
            ).fetchall()

        return {
            "doctor": doctor,
            "appointment_date": appointment_date,
            "available_slots": [row["appointment_time"] for row in rows],
        }

    def create_appointment(
        self,
        *,
        patient_id: str,
        patient_name: str,
        doctor_id: str,
        appointment_date: str,
        appointment_time: str,
        phone: str = "",
        email: str = "",
    ) -> dict[str, Any]:
        booking_id = f"VM-{appointment_date.replace('-', '')}-{secrets.token_hex(3).upper()}"
        created_at = datetime.now(timezone.utc).isoformat()

        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            doctor = connection.execute(
                "SELECT * FROM doctors WHERE id = ?", (doctor_id.strip().upper(),)
            ).fetchone()
            if doctor is None:
                raise LookupError("Không tìm thấy bác sĩ đã chọn.")

            updated = connection.execute(
                """
                UPDATE schedule_slots SET is_available = 0
                WHERE doctor_id = ? AND appointment_date = ?
                    AND appointment_time = ? AND is_available = 1
                """,
                (doctor["id"], appointment_date, appointment_time),
            ).rowcount
            if updated != 1:
                raise ValueError("Khung giờ này vừa được đặt hoặc không còn khả dụng.")

            connection.execute(
                """
                INSERT INTO appointments (
                    booking_id, patient_id, patient_name, phone, email, doctor_id,
                    appointment_date, appointment_time, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'CONFIRMED', ?)
                """,
                (
                    booking_id,
                    patient_id.strip().upper(),
                    patient_name.strip(),
                    phone.strip(),
                    email.strip().lower(),
                    doctor["id"],
                    appointment_date,
                    appointment_time,
                    created_at,
                ),
            )

        appointment = self.get_appointment(booking_id)
        if appointment is None:  # pragma: no cover - defensive database guard
            raise RuntimeError("Không thể đọc lại lịch hẹn vừa tạo.")
        return appointment

    def get_appointment(self, booking_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT
                    a.booking_id, a.patient_id, a.patient_name, a.phone, a.email,
                    a.appointment_date, a.appointment_time, a.status, a.created_at,
                    a.cancelled_at, d.id AS doctor_id, d.name AS doctor_name,
                    d.specialty, d.workplace
                FROM appointments a
                JOIN doctors d ON d.id = a.doctor_id
                WHERE a.booking_id = ?
                """,
                (booking_id.strip().upper(),),
            ).fetchone()
        return dict(row) if row else None

    def cancel_appointment(self, booking_id: str, patient_id: str) -> dict[str, Any]:
        cancelled_at = datetime.now(timezone.utc).isoformat()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            appointment = connection.execute(
                """
                SELECT * FROM appointments
                WHERE booking_id = ? AND patient_id = ?
                """,
                (booking_id.strip().upper(), patient_id.strip().upper()),
            ).fetchone()
            if appointment is None:
                raise LookupError("Không tìm thấy lịch hẹn phù hợp với mã bệnh nhân.")
            if appointment["status"] != "CONFIRMED":
                raise ValueError("Lịch hẹn này đã được hủy trước đó.")

            connection.execute(
                """
                UPDATE appointments
                SET status = 'CANCELLED', cancelled_at = ?
                WHERE booking_id = ?
                """,
                (cancelled_at, appointment["booking_id"]),
            )
            connection.execute(
                """
                UPDATE schedule_slots SET is_available = 1
                WHERE doctor_id = ? AND appointment_date = ? AND appointment_time = ?
                """,
                (
                    appointment["doctor_id"],
                    appointment["appointment_date"],
                    appointment["appointment_time"],
                ),
            )

        cancelled = self.get_appointment(booking_id)
        if cancelled is None:  # pragma: no cover
            raise RuntimeError("Không thể đọc lại lịch hẹn vừa hủy.")
        return cancelled


_database_lock = threading.Lock()
_database: AppointmentDatabase | None = None


def get_database(path: str | Path | None = None) -> AppointmentDatabase:
    """Return the process-level database repository and ensure its schema exists."""
    global _database
    with _database_lock:
        if _database is None or (path is not None and Path(path) != _database.path):
            _database = AppointmentDatabase(path)
            _database.initialize()
    return _database


def reset_database_instance() -> None:
    """Reset the singleton for isolated tests."""
    global _database
    with _database_lock:
        _database = None
