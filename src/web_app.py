"""FastAPI web application for the healthcare assistant MVP."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import run_react_agent
from database import get_database
from mcp_server import MCPAcademicServer
from providers import get_llm_provider


PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = PROJECT_ROOT / "web" / "static"
PATIENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9-]{4,24}$")
PHONE_PATTERN = re.compile(r"^[0-9+().\s-]{8,20}$")
TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
logger = logging.getLogger(__name__)


class AppointmentCreate(BaseModel):
    patient_id: str = Field(min_length=4, max_length=24)
    patient_name: str = Field(min_length=2, max_length=100)
    phone: str = Field(min_length=8, max_length=20)
    email: str = Field(default="", max_length=160)
    doctor_id: str = Field(min_length=3, max_length=20)
    appointment_date: date
    appointment_time: str = Field(min_length=5, max_length=5)


class AppointmentLookup(BaseModel):
    patient_id: str = Field(min_length=4, max_length=24)


class ChatRequest(BaseModel):
    message: str = Field(min_length=2, max_length=2000)


class SlidingWindowLimiter:
    """A small in-process guard against accidental request bursts."""

    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self.requests: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        events = self.requests[key]
        while events and events[0] <= now - self.window_seconds:
            events.popleft()
        if len(events) >= self.limit:
            return False
        events.append(now)
        return True


chat_limiter = SlidingWindowLimiter(limit=20, window_seconds=60)
write_limiter = SlidingWindowLimiter(limit=12, window_seconds=60)


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _require_rate_limit(limiter: SlidingWindowLimiter, request: Request) -> None:
    if not limiter.allow(_client_key(request)):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Bạn thao tác quá nhanh. Vui lòng thử lại sau một phút.",
        )


def _validate_patient_fields(payload: AppointmentCreate) -> None:
    if not PATIENT_ID_PATTERN.fullmatch(payload.patient_id.strip()):
        raise HTTPException(status_code=422, detail="Mã bệnh nhân không hợp lệ.")
    if not PHONE_PATTERN.fullmatch(payload.phone.strip()):
        raise HTTPException(status_code=422, detail="Số điện thoại không hợp lệ.")
    if payload.email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", payload.email):
        raise HTTPException(status_code=422, detail="Email không hợp lệ.")
    if not TIME_PATTERN.fullmatch(payload.appointment_time):
        raise HTTPException(status_code=422, detail="Giờ khám không hợp lệ.")


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_database().initialize()
    yield


app = FastAPI(
    title="Vinmec Care AI MVP",
    description="API tra cứu lịch bác sĩ, đặt lịch và trợ lý AI.",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url=None,
    lifespan=lifespan,
)

allowed = os.getenv("CORS_ORIGINS", "").strip()
if allowed:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in allowed.split(",") if origin.strip()],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self'; "
        "script-src 'self'; connect-src 'self'; frame-ancestors 'none'"
    )
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, error: Exception):
    logger.exception("Unhandled web request error", exc_info=error)
    return JSONResponse(
        status_code=500,
        content={"detail": "Hệ thống đang bận. Vui lòng thử lại sau."},
    )


@app.get("/", include_in_schema=False)
async def homepage():
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/api/health")
async def health_check():
    provider_name = get_llm_provider().__class__.__name__
    return {
        "status": "ok",
        "service": "healthcare-assistant",
        "ai_mode": "offline" if provider_name == "MockOfflineProvider" else "live",
    }


@app.get("/api/doctors")
async def list_doctors(specialty: str | None = Query(default=None, max_length=80)):
    return {"data": get_database().list_doctors(specialty)}


@app.get("/api/doctors/{doctor_id}/availability")
async def doctor_availability(doctor_id: str, appointment_date: date = Query(alias="date")):
    result = get_database().get_availability(doctor_id, appointment_date.isoformat())
    if result is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy bác sĩ.")
    return {"data": result}


@app.post("/api/appointments", status_code=status.HTTP_201_CREATED)
async def create_appointment(payload: AppointmentCreate, request: Request):
    _require_rate_limit(write_limiter, request)
    _validate_patient_fields(payload)
    try:
        appointment = get_database().create_appointment(
            patient_id=payload.patient_id,
            patient_name=payload.patient_name,
            phone=payload.phone,
            email=payload.email,
            doctor_id=payload.doctor_id,
            appointment_date=payload.appointment_date.isoformat(),
            appointment_time=payload.appointment_time,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"message": "Đặt lịch thành công.", "data": appointment}


@app.get("/api/appointments/{booking_id}")
async def get_appointment(
    booking_id: str,
    patient_id: str = Query(min_length=4, max_length=24),
):
    appointment = get_database().get_appointment(booking_id)
    if appointment is None or appointment["patient_id"] != patient_id.strip().upper():
        raise HTTPException(status_code=404, detail="Không tìm thấy lịch hẹn.")
    return {"data": appointment}


@app.post("/api/appointments/{booking_id}/cancel")
async def cancel_appointment(booking_id: str, payload: AppointmentLookup, request: Request):
    _require_rate_limit(write_limiter, request)
    try:
        appointment = get_database().cancel_appointment(booking_id, payload.patient_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"message": "Đã hủy lịch hẹn.", "data": appointment}


@app.post("/api/chat")
async def chat(payload: ChatRequest, request: Request):
    _require_rate_limit(chat_limiter, request)
    provider = get_llm_provider()
    server = MCPAcademicServer()
    traces = await asyncio.to_thread(
        run_react_agent, payload.message.strip(), provider, server, False
    )

    final_event = next(
        (event for event in reversed(traces) if event.get("action_type") == "FINAL_ANSWER"),
        None,
    )
    answer = (final_event or {}).get("output") or "Tôi chưa thể xử lý yêu cầu này."
    public_steps = [
        {
            "type": event.get("action_type"),
            "tool": event.get("tool_name"),
            "latency_ms": event.get("latency_ms", 0),
        }
        for event in traces
    ]
    return {
        "answer": answer,
        "steps": public_steps,
        "ai_mode": "offline" if provider.__class__.__name__ == "MockOfflineProvider" else "live",
    }


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "web_app:app",
        host=os.getenv("APP_HOST", "127.0.0.1"),
        port=int(os.getenv("APP_PORT", "8000")),
        reload=os.getenv("APP_RELOAD", "false").lower() == "true",
    )
