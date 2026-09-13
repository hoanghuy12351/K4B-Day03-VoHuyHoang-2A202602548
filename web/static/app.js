const state = {
  doctors: [],
  doctor: null,
  date: "2026-09-20",
  time: null,
  booking: null,
};

const elements = {
  status: document.querySelector("#system-status"),
  doctorSelect: document.querySelector("#doctor-select"),
  dateInput: document.querySelector("#date-input"),
  doctorCard: document.querySelector("#doctor-card"),
  slotGrid: document.querySelector("#slot-grid"),
  slotCount: document.querySelector("#slot-count"),
  selectionSummary: document.querySelector("#selection-summary"),
  bookingForm: document.querySelector("#booking-form"),
  bookingSubmit: document.querySelector("#booking-submit"),
  chatForm: document.querySelector("#chat-form"),
  chatInput: document.querySelector("#chat-input"),
  chatLog: document.querySelector("#chat-log"),
  lookupForm: document.querySelector("#lookup-form"),
  lookupResult: document.querySelector("#lookup-result"),
  dialog: document.querySelector("#confirmation-dialog"),
  confirmationCopy: document.querySelector("#confirmation-copy"),
  confirmationCode: document.querySelector("#confirmation-code"),
  toast: document.querySelector("#toast"),
};

function localToday() {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60_000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
}

function formatDate(isoDate) {
  const [year, month, day] = isoDate.split("-");
  return `${day}/${month}/${year}`;
}

function showToast(message) {
  elements.toast.textContent = message;
  elements.toast.classList.add("is-visible");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => elements.toast.classList.remove("is-visible"), 3200);
}

function getErrorMessage(payload, fallback) {
  if (typeof payload?.detail === "string") return payload.detail;
  if (Array.isArray(payload?.detail) && payload.detail[0]?.msg) return payload.detail[0].msg;
  return fallback;
}

async function apiRequest(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(getErrorMessage(payload, "Không thể kết nối hệ thống."));
  }
  return payload;
}

function setButtonBusy(button, busy, label) {
  button.disabled = busy;
  const text = button.querySelector("span") || button;
  if (!button.dataset.defaultLabel) button.dataset.defaultLabel = text.textContent;
  text.textContent = busy ? label : button.dataset.defaultLabel;
}

function renderDoctor() {
  const doctor = state.doctor;
  if (!doctor) return;
  const initials = doctor.name
    .split(" ")
    .slice(-2)
    .map((part) => part[0])
    .join("");
  elements.doctorCard.querySelector(".doctor-card__avatar").textContent = initials;
  elements.doctorCard.querySelector(".doctor-card__specialty").textContent = doctor.specialty;
  elements.doctorCard.querySelector("h3").textContent = `BS. ${doctor.name}`;
  elements.doctorCard.querySelector(".doctor-card__body p:last-child").textContent =
    `${doctor.workplace} · ${doctor.description}`;
  elements.doctorCard.querySelector(".doctor-card__meta strong").textContent = doctor.experience_years;
}

function updateSelection() {
  const summary = elements.selectionSummary;
  const title = summary.querySelector("strong");
  const detail = summary.querySelector(".selection-summary__icon + div > span");
  if (!state.doctor || !state.time) {
    title.textContent = "Chưa chọn khung giờ";
    detail.textContent = "Vui lòng hoàn tất bước 01";
    elements.bookingSubmit.disabled = true;
    return;
  }
  title.textContent = `${state.time} · ${formatDate(state.date)}`;
  detail.textContent = `BS. ${state.doctor.name} · ${state.doctor.specialty}`;
  elements.bookingSubmit.disabled = false;
}

function renderSlots(slots) {
  elements.slotGrid.replaceChildren();
  state.time = null;
  updateSelection();
  elements.slotCount.textContent = slots.length ? `${slots.length} giờ trống` : "Đã kín lịch";

  if (!slots.length) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "Bác sĩ chưa có lịch trống trong ngày này.";
    elements.slotGrid.append(empty);
    return;
  }

  slots.forEach((slot) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "slot-button";
    button.textContent = slot;
    button.setAttribute("aria-pressed", "false");
    button.addEventListener("click", () => {
      elements.slotGrid.querySelectorAll(".slot-button").forEach((item) => {
        item.classList.remove("is-selected");
        item.setAttribute("aria-pressed", "false");
      });
      button.classList.add("is-selected");
      button.setAttribute("aria-pressed", "true");
      state.time = slot;
      updateSelection();
    });
    elements.slotGrid.append(button);
  });
}

async function loadAvailability() {
  if (!state.doctor || !state.date) return;
  elements.slotGrid.replaceChildren();
  const loading = document.createElement("p");
  loading.className = "loading-state";
  loading.textContent = "Đang kiểm tra lịch trống…";
  elements.slotGrid.append(loading);
  elements.slotCount.textContent = "Đang tải";
  try {
    const payload = await apiRequest(
      `/api/doctors/${encodeURIComponent(state.doctor.id)}/availability?date=${encodeURIComponent(state.date)}`,
    );
    renderSlots(payload.data.available_slots);
  } catch (error) {
    renderSlots([]);
    showToast(error.message);
  }
}

async function loadDoctors() {
  const payload = await apiRequest("/api/doctors");
  state.doctors = payload.data;
  elements.doctorSelect.replaceChildren();
  state.doctors.forEach((doctor) => {
    const option = document.createElement("option");
    option.value = doctor.id;
    option.textContent = `${doctor.name} — ${doctor.specialty}`;
    elements.doctorSelect.append(option);
  });
  state.doctor = state.doctors[0] || null;
  renderDoctor();
  await loadAvailability();
}

function appendMessage(role, text) {
  const wrapper = document.createElement("div");
  wrapper.className = `message message--${role}`;
  const badge = document.createElement("span");
  badge.textContent = role === "user" ? "Bạn" : "AI";
  const content = document.createElement("p");
  content.textContent = text;
  wrapper.append(badge, content);
  elements.chatLog.append(wrapper);
  elements.chatLog.scrollTop = elements.chatLog.scrollHeight;
  return wrapper;
}

function renderLookup(appointment, patientId) {
  elements.lookupResult.replaceChildren();
  const title = document.createElement("strong");
  title.textContent = `${appointment.appointment_time} · ${formatDate(appointment.appointment_date)}`;
  const doctor = document.createElement("span");
  doctor.textContent = `BS. ${appointment.doctor_name} · ${appointment.specialty}`;
  const place = document.createElement("span");
  place.textContent = `${appointment.workplace} · ${appointment.status === "CONFIRMED" ? "Đã xác nhận" : "Đã hủy"}`;
  elements.lookupResult.append(title, doctor, place);

  if (appointment.status === "CONFIRMED") {
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "cancel-button";
    cancel.textContent = "Hủy lịch hẹn";
    cancel.addEventListener("click", async () => {
      if (!window.confirm("Bạn chắc chắn muốn hủy lịch hẹn này?")) return;
      cancel.disabled = true;
      try {
        const payload = await apiRequest(`/api/appointments/${encodeURIComponent(appointment.booking_id)}/cancel`, {
          method: "POST",
          body: JSON.stringify({ patient_id: patientId }),
        });
        renderLookup(payload.data, patientId);
        await loadAvailability();
        showToast("Đã hủy lịch hẹn.");
      } catch (error) {
        cancel.disabled = false;
        showToast(error.message);
      }
    });
    elements.lookupResult.append(cancel);
  }
}

elements.doctorSelect.addEventListener("change", async (event) => {
  state.doctor = state.doctors.find((doctor) => doctor.id === event.target.value) || null;
  renderDoctor();
  await loadAvailability();
});

elements.dateInput.addEventListener("change", async (event) => {
  state.date = event.target.value;
  await loadAvailability();
});

elements.bookingForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.doctor || !state.time || !elements.bookingForm.reportValidity()) return;
  const form = new FormData(elements.bookingForm);
  const payload = {
    patient_name: form.get("patient_name").trim(),
    patient_id: form.get("patient_id").trim(),
    phone: form.get("phone").trim(),
    email: form.get("email").trim(),
    doctor_id: state.doctor.id,
    appointment_date: state.date,
    appointment_time: state.time,
  };

  setButtonBusy(elements.bookingSubmit, true, "Đang xác nhận…");
  try {
    const response = await apiRequest("/api/appointments", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.booking = response.data;
    elements.confirmationCode.textContent = response.data.booking_id;
    elements.confirmationCopy.textContent =
      `${response.data.appointment_time} ngày ${formatDate(response.data.appointment_date)} với BS. ${response.data.doctor_name}.`;
    elements.dialog.showModal();
    elements.bookingForm.reset();
    await loadAvailability();
  } catch (error) {
    showToast(error.message);
  } finally {
    setButtonBusy(elements.bookingSubmit, false, "");
    updateSelection();
  }
});

elements.lookupForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!elements.lookupForm.reportValidity()) return;
  const form = new FormData(elements.lookupForm);
  const bookingId = form.get("booking_id").trim().toUpperCase();
  const patientId = form.get("patient_id").trim().toUpperCase();
  const button = elements.lookupForm.querySelector("button");
  button.disabled = true;
  try {
    const response = await apiRequest(
      `/api/appointments/${encodeURIComponent(bookingId)}?patient_id=${encodeURIComponent(patientId)}`,
    );
    renderLookup(response.data, patientId);
  } catch (error) {
    elements.lookupResult.replaceChildren();
    showToast(error.message);
  } finally {
    button.disabled = false;
  }
});

elements.chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = elements.chatInput.value.trim();
  if (message.length < 2) return;
  appendMessage("user", message);
  elements.chatInput.value = "";
  const button = elements.chatForm.querySelector("button");
  button.disabled = true;
  const waiting = appendMessage("assistant", "Đang kiểm tra thông tin…");
  try {
    const response = await apiRequest("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message }),
    });
    waiting.querySelector("p").textContent = response.answer;
  } catch (error) {
    waiting.querySelector("p").textContent = error.message;
  } finally {
    button.disabled = false;
    elements.chatInput.focus();
  }
});

document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => {
    elements.chatInput.value = button.dataset.prompt;
    elements.chatInput.focus();
  });
});

document.querySelector("#close-dialog").addEventListener("click", () => elements.dialog.close());
document.querySelector("#copy-code").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(elements.confirmationCode.textContent);
    showToast("Đã sao chép mã xác nhận.");
  } catch {
    showToast("Vui lòng sao chép mã thủ công.");
  }
});

async function initialize() {
  elements.dateInput.min = localToday();
  state.date = elements.dateInput.value;
  try {
    const health = await apiRequest("/api/health");
    elements.status.classList.add("is-online");
    elements.status.querySelector("span:last-child").textContent =
      health.ai_mode === "live" ? "AI trực tuyến" : "Chế độ mô phỏng";
    await loadDoctors();
  } catch (error) {
    elements.status.querySelector("span:last-child").textContent = "Mất kết nối";
    showToast(error.message);
  }
}

initialize();
