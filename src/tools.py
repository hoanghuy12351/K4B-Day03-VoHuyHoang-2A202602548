"""
Tool schemas và lớp thực thi cho Trợ lý Tư vấn Sức khỏe Vinmec.

Đề tài cung cấp hai khả năng:
1. Tra cứu lịch làm việc và khung giờ trống của bác sĩ.
2. Đặt lịch khám cho bệnh nhân vào một khung giờ còn trống.
"""

import json
from datetime import datetime
from typing import Any, Dict

from database import get_database

# ==============================================================================
# 1. TOOL SCHEMAS (JSON Schema)
# ==============================================================================

TOOLS_SCHEMA = [
    {
        "name": "doctor_schedule_query",
        "description": (
            "Tra cứu lịch làm việc và các khung giờ còn trống của bác sĩ Vinmec "
            "theo tên bác sĩ, chuyên khoa và ngày khám."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "doctor_name": {
                    "type": "string",
                    "description": "Họ tên bác sĩ, ví dụ: 'Nguyễn Minh An'.",
                },
                "specialty": {
                    "type": "string",
                    "description": "Tên chuyên khoa, ví dụ: 'Tim mạch'.",
                },
                "appointment_date": {
                    "type": "string",
                    "description": "Ngày cần tra cứu theo định dạng DD/MM/YYYY, ví dụ: '20/09/2026'.",
                },
            },
            "required": ["doctor_name", "specialty", "appointment_date"],
        },
    },
    {
        "name": "book_medical_appointment",
        "description": (
            "Đặt lịch khám tại Vinmec cho bệnh nhân sau khi đã xác định bác sĩ "
            "và khung giờ còn trống."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "patient_id": {
                    "type": "string",
                    "description": "Mã bệnh nhân, ví dụ: 'BN2026001'.",
                },
                "patient_name": {
                    "type": "string",
                    "description": "Họ tên đầy đủ của bệnh nhân.",
                },
                "doctor_name": {
                    "type": "string",
                    "description": "Họ tên bác sĩ được chọn.",
                },
                "specialty": {
                    "type": "string",
                    "description": "Chuyên khoa cần khám, ví dụ: 'Tim mạch'.",
                },
                "datetime_str": {
                    "type": "string",
                    "description": (
                        "Thời gian khám theo định dạng HH:MM DD/MM/YYYY, "
                        "ví dụ: '09:00 20/09/2026'."
                    ),
                },
                "phone": {
                    "type": "string",
                    "description": "Số điện thoại liên hệ, không bắt buộc.",
                },
                "email": {
                    "type": "string",
                    "description": "Email nhận xác nhận, không bắt buộc.",
                },
            },
            "required": [
                "patient_id",
                "patient_name",
                "doctor_name",
                "specialty",
                "datetime_str",
            ],
        },
    },
]


# ==============================================================================
# 2. SQLITE DATABASE VÀ EXECUTION LAYER
# ==============================================================================


def _json_response(payload: Dict[str, Any]) -> str:
    """Chuyển kết quả tool thành chuỗi JSON Unicode."""
    return json.dumps(payload, ensure_ascii=False)


def _normalize_date(date_str: str) -> str:
    """Chuẩn hóa ngày DD/MM/YYYY; chấp nhận thêm định dạng YYYY-MM-DD."""
    value = date_str.strip()
    for date_format in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, date_format).strftime("%d/%m/%Y")
        except ValueError:
            continue
    raise ValueError("Ngày khám phải có định dạng DD/MM/YYYY, ví dụ 20/09/2026.")


def _normalize_datetime(datetime_str: str) -> tuple[str, str]:
    """Tách và chuẩn hóa giờ, ngày từ chuỗi HH:MM DD/MM/YYYY."""
    value = datetime_str.strip()
    for date_format in ("%H:%M %d/%m/%Y", "%H:%M %Y-%m-%d"):
        try:
            parsed = datetime.strptime(value, date_format)
            return parsed.strftime("%H:%M"), parsed.strftime("%d/%m/%Y")
        except ValueError:
            continue
    raise ValueError(
        "Thời gian khám phải có định dạng HH:MM DD/MM/YYYY, ví dụ 09:00 20/09/2026."
    )


def execute_doctor_schedule_query(
    doctor_name: str,
    specialty: str,
    appointment_date: str,
) -> str:
    """Tra cứu lịch và các khung giờ còn trống của bác sĩ."""
    try:
        normalized_date = _normalize_date(appointment_date)
    except ValueError as error:
        return _json_response({"status": "INVALID_INPUT", "message": str(error)})

    database = get_database()
    doctor = database.find_doctor(doctor_name, specialty)
    if doctor is None:
        return _json_response(
            {
                "status": "NOT_FOUND",
                "message": (
                    f"Không tìm thấy bác sĩ '{doctor_name}' thuộc chuyên khoa "
                    f"'{specialty}'."
                ),
            }
        )

    iso_date = datetime.strptime(normalized_date, "%d/%m/%Y").strftime("%Y-%m-%d")
    availability = database.get_availability(doctor["id"], iso_date)
    available_slots = availability["available_slots"] if availability else []
    return _json_response(
        {
            "status": "SUCCESS",
            "data": {
                "doctor_id": doctor["id"],
                "doctor_name": doctor["name"],
                "specialty": doctor["specialty"],
                "workplace": doctor["workplace"],
                "appointment_date": normalized_date,
                "available_slots": available_slots,
            },
            "message": (
                f"Có {len(available_slots)} khung giờ trống trong ngày {normalized_date}."
                if available_slots
                else f"Bác sĩ không còn lịch trống trong ngày {normalized_date}."
            ),
        }
    )


def book_medical_appointment(
    patient_id: str,
    patient_name: str,
    doctor_name: str,
    specialty: str,
    datetime_str: str,
    phone: str = "",
    email: str = "",
) -> str:
    """Đặt lịch khám nếu bác sĩ tồn tại và khung giờ vẫn còn trống."""
    patient_id = patient_id.strip().upper()
    patient_name = patient_name.strip()
    if not patient_id or not patient_name:
        return _json_response(
            {
                "status": "INVALID_INPUT",
                "message": "Mã và tên bệnh nhân không được để trống.",
            }
        )

    try:
        appointment_time, appointment_date = _normalize_datetime(datetime_str)
    except ValueError as error:
        return _json_response({"status": "INVALID_INPUT", "message": str(error)})

    database = get_database()
    doctor = database.find_doctor(doctor_name, specialty)
    if doctor is None:
        return _json_response(
            {
                "status": "NOT_FOUND",
                "message": (
                    f"Không tìm thấy bác sĩ '{doctor_name}' thuộc chuyên khoa "
                    f"'{specialty}'."
                ),
            }
        )

    iso_date = datetime.strptime(appointment_date, "%d/%m/%Y").strftime("%Y-%m-%d")
    try:
        stored_appointment = database.create_appointment(
            patient_id=patient_id,
            patient_name=patient_name,
            doctor_id=doctor["id"],
            appointment_date=iso_date,
            appointment_time=appointment_time,
            phone=phone,
            email=email,
        )
    except ValueError as error:
        availability = database.get_availability(doctor["id"], iso_date)
        return _json_response(
            {
                "status": "SLOT_UNAVAILABLE",
                "message": str(error),
                "available_slots": availability["available_slots"] if availability else [],
            }
        )

    booking_id = stored_appointment["booking_id"]
    appointment = {
        "booking_id": booking_id,
        "patient_id": stored_appointment["patient_id"],
        "patient_name": stored_appointment["patient_name"],
        "doctor_id": stored_appointment["doctor_id"],
        "doctor_name": stored_appointment["doctor_name"],
        "specialty": stored_appointment["specialty"],
        "workplace": stored_appointment["workplace"],
        "datetime": f"{appointment_time} {appointment_date}",
    }

    return _json_response(
        {
            "status": "SUCCESS",
            "data": appointment,
            "message": (
                f"Đặt lịch thành công. Mã xác nhận {booking_id}: bệnh nhân "
                f"{patient_name} khám với bác sĩ {doctor['name']} lúc "
                f"{appointment_time} ngày {appointment_date}."
            ),
        }
    )


# Router ánh xạ tên tool với hàm thực thi tương ứng.
TOOL_ROUTER = {
    "doctor_schedule_query": execute_doctor_schedule_query,
    "book_medical_appointment": book_medical_appointment,
}


def dispatch_tool_call(tool_name: str, arguments: Dict[str, Any]) -> str:
    """Kiểm tra và chuyển yêu cầu từ MCP server đến đúng tool."""
    tool_function = TOOL_ROUTER.get(tool_name)
    if tool_function is None:
        return _json_response(
            {"status": "UNKNOWN_TOOL", "error": f"Tool '{tool_name}' không tồn tại."}
        )

    try:
        return tool_function(**arguments)
    except TypeError as error:
        return _json_response({"status": "INVALID_ARGUMENTS", "error": str(error)})
    except Exception as error:
        return _json_response({"status": "EXECUTION_ERROR", "error": str(error)})
