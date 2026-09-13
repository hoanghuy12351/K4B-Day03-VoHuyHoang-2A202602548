# 📊 BÁO CÁO THU HOẠCH NGHIỆM THU BÀI LAB 3 (BƯỚC 3 — SUBMISSION ARTIFACT)

> **Họ và Tên Học viên:** Võ Huy Hoàng
> **Mã Sinh Viên / Mã Học viên:** 2A202602548
> **Chủ đề Lựa chọn:** Trợ lý Tư vấn Sức khỏe Vinmec: Tra cứu lịch làm việc bác sĩ chuyên khoa và đặt lịch khám bệnh.

---

## 1. BẢNG CHẤM ĐIỂM AGENTIC FIT SCORING MATRIX (ĐÁNH GIÁ CHỦ ĐỀ)

| Tiêu chí Đánh giá           | Mức độ (1 - 5) | Giải trình chi tiết lý do chọn điểm                                                                                                                                                                                                                |
| :-------------------------- | :------------: | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **1. Multi-step Reasoning** |     4 / 5      | Bài toán cần xác định chuyên khoa phù hợp từ nhu cầu người dùng, tra cứu bác sĩ, kiểm tra khung giờ trống, sau đó thu thập thông tin cần thiết để đặt lịch. Quy trình gồm nhiều bước liên tiếp nhưng chưa quá phức tạp.                            |
| **2. Tool Interaction**     |     5 / 5      | Hệ thống bắt buộc kết nối MCP Server(máy chủ giao thức ngữ cảnh mô hình) hoặc cơ sở dữ liệu để tra cứu lịch làm việc theo thời gian thực và tạo lịch khám. Chatbot(trình trò chuyện tự động) thông thường không thể tự thực hiện các thao tác này. |
| **3. Dynamic Decision**     |     4 / 5      | Bước tiếp theo phụ thuộc vào Observation(kết quả quan sát) trước đó. Nếu bác sĩ không có lịch, Agent phải đề xuất bác sĩ khác hoặc thời gian khác; nếu còn lịch, Agent mới tiến hành đặt khám.                                                     |
| **4. Long Horizon Goal**    |     4 / 5      | Agent phải duy trì mục tiêu đặt lịch xuyên suốt nhiều bước: ghi nhớ chuyên khoa, bác sĩ, thời gian và thông tin bệnh nhân cho đến khi nhận được xác nhận đặt lịch thành công.                                                                      |
| **TỔNG ĐIỂM AGENTIC FIT**   |  **17 / 20**   | Bài toán rất phù hợp triển khai Agentic System vì tổng điểm lớn hơn 12/20.                                                                                                                                                                          |

---

## 2. TRÍCH XUẤT KẾT QUẢ WATERFALL TRACE LOG (SAU KHI CHẠY TEST SUITE TRÊN API THẬT)

> ⚠️ **YÊU CẦU NGHIỆM THU:** Mở tệp `.env` điền `GEMINI_API_KEY` (hoặc `OPENAI_API_KEY`) để kết nối LLM thật trước khi thực thi `python src/app.py --all`. Bài nộp chỉ dùng Mock Offline Provider sẽ không đạt điểm nghiệm thực tế.

Dán 1 đoạn trích xuất log tiêu biểu từ file `docs/trace_waterfall.json` sinh ra từ phản hồi LLM API thật:

```json
[
  {
    "step": 1,
    "action_type": "TOOL_EXECUTION",
    "tool_name": "doctor_schedule_query",
    "arguments": {
      "specialty": "Tim mạch",
      "doctor_name": "Nguyễn Minh An",
      "appointment_date": "21/09/2026"
    },
    "observation": {
      "status": "SUCCESS",
      "data": {
        "doctor_name": "Nguyễn Minh An",
        "available_slots": ["08:00", "09:30", "15:00"]
      }
    },
    "latency_ms": 13452.44
  },
  {
    "step": 2,
    "action_type": "TOOL_EXECUTION",
    "tool_name": "book_medical_appointment",
    "arguments": {
      "patient_id": "BN2026002",
      "patient_name": "Trần Thị Hoa",
      "doctor_name": "Nguyễn Minh An",
      "specialty": "Tim mạch",
      "datetime_str": "08:00 21/09/2026"
    },
    "observation": {
      "status": "SUCCESS",
      "data": {
        "booking_id": "VM-21092026-0002"
      }
    },
    "latency_ms": 20209.4
  }
]
```

---

## 3. TỔNG KẾT KẾT QUẢ NGHIỆM THU & NỘP BÀI

- [x] Đã điền API Key thật trong `.env` và xác nhận Agent chạy thành công trên Gemini API thật.
- **Môi trường nghiệm thu:** Python 3.14.5 | Gemini 2.5 Flash.
- **Tổng số Test Cases đã chạy thành công:** 5 / 5 test cases.
- **Số lượt gọi Tool qua MCP Server chính xác:** 5 lượt.
- **Kết quả đẩy Repo nộp bài:** [ ] Đã Commit và Push mã nguồn thành công lên GitHub cá nhân.

---

> ✅ **HOÀN TẤT NỘP BÀI:** Sao chép đường link GitHub Repository cá nhân của bạn và dán vào ô nộp bài trên hệ thống LMS VLearn để hoàn tất Bài Lab 3!
