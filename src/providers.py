"""
🔌 MULTI-PROVIDER LLM ADAPTER (Google Gemini, OpenAI & Offline Mock)
Hỗ trợ Native Tool Calling và chuyển đổi linh hoạt qua biến môi trường LLM_PROVIDER.
"""

import os
import sys
import json
import re
from typing import Dict, Any, List, Optional

try:
    from dotenv import load_dotenv
except ImportError:

    def load_dotenv():
        """Cho phép chạy Mock Offline khi chưa cài python-dotenv."""
        return False


if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

load_dotenv()


class BaseLLMProvider:
    """Interface cơ sở cho các LLM Provider hỗ trợ Native Tool Calling"""

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        raise NotImplementedError

    def generate_with_tools(
        self,
        prompt: str,
        tools_schema: List[Dict[str, Any]],
        system_prompt: str = "",
        observations: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        raise NotImplementedError


def _prompt_with_observations(
    prompt: str, observations: Optional[List[Dict[str, Any]]]
) -> str:
    """Bổ sung các Observation để LLM quyết định bước ReAct tiếp theo."""
    if not observations:
        return prompt
    return (
        f"Yêu cầu ban đầu:\n{prompt}\n\n"
        "Các kết quả công cụ đã nhận:\n"
        f"{json.dumps(observations, ensure_ascii=False, indent=2)}\n\n"
        "Nếu đã đủ dữ liệu, hãy trả lời người dùng. Nếu còn thiếu một hành động "
        "để hoàn thành yêu cầu, hãy gọi đúng công cụ tiếp theo. Không gọi lại công "
        "cụ đã hoàn tất nếu không cần thiết."
    )


def _first_match(pattern: str, text: str) -> str:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _extract_medical_arguments(prompt: str) -> Dict[str, str]:
    """Trích xuất các trường của bộ test để Mock Provider chạy ngoại tuyến."""
    doctor_name = _first_match(
        r"bác sĩ\s+(.+?)(?=,\s*(?:chuyên khoa|trong ngày)|\s+(?:lúc|vào ngày|trong ngày)|$)",
        prompt,
    )
    specialty = _first_match(
        r"chuyên khoa\s+(.+?)(?=,|\s+(?:vào ngày|trong ngày)|$)", prompt
    )
    if not specialty:
        specialty = _first_match(r"đặt lịch khám\s+(.+?)\s+cho bệnh nhân", prompt)

    return {
        "doctor_name": doctor_name,
        "specialty": specialty,
        "appointment_date": _first_match(r"(\d{2}/\d{2}/\d{4})", prompt),
        "appointment_time": _first_match(r"(\d{2}:\d{2})", prompt),
        "patient_id": _first_match(r"\b(BN\d+)\b", prompt).upper(),
        "patient_name": _first_match(r"bệnh nhân\s+(.+?)(?=,\s*mã|\s+mã\s+|$)", prompt),
    }


def _format_tool_result(tool_name: str, result: Dict[str, Any]) -> str:
    """Tổng hợp Observation thành câu trả lời ngắn gọn, không bịa dữ liệu."""
    status = result.get("status")
    if status != "SUCCESS":
        return (
            result.get("message")
            or result.get("error")
            or json.dumps(result, ensure_ascii=False)
        )

    data = result.get("data", {})
    if tool_name == "doctor_schedule_query":
        slots = data.get("available_slots", [])
        if slots:
            return (
                f"Bác sĩ {data.get('doctor_name')} ({data.get('specialty')}) làm việc tại "
                f"{data.get('workplace')} ngày {data.get('appointment_date')}. "
                f"Các khung giờ còn trống: {', '.join(slots)}."
            )
        return result.get("message", "Bác sĩ không còn khung giờ trống.")
    if tool_name == "book_medical_appointment":
        return result.get("message", "Đặt lịch khám thành công.")
    return result.get("message") or json.dumps(result, ensure_ascii=False)


class MockOfflineProvider(BaseLLMProvider):
    """Offline Mock Provider dùng để chạy thử mà không tốn API Key"""

    def __init__(self):
        self.model_name = "Offline-Mock-Model-2026"

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        return (
            "[Mock Chatbot Response]: Tôi có thể hướng dẫn quy trình đặt lịch khám "
            "nhưng không có công cụ tra cứu lịch bác sĩ theo thời gian thực."
        )

    def generate_with_tools(
        self,
        prompt: str,
        tools_schema: List[Dict[str, Any]],
        system_prompt: str = "",
        observations: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        prompt_lower = prompt.lower()

        if observations:
            latest = observations[-1]
            tool_name = latest.get("tool_name", "")
            result = latest.get("result", {})

            # Chuỗi đa bước: tra cứu lịch -> chọn giờ sớm nhất -> đặt lịch.
            if (
                tool_name == "doctor_schedule_query"
                and result.get("status") == "SUCCESS"
                and "đặt" in prompt_lower
                and "sớm nhất" in prompt_lower
            ):
                data = result.get("data", {})
                slots = data.get("available_slots", [])
                extracted = _extract_medical_arguments(prompt)
                if not slots:
                    return {
                        "type": "text",
                        "content": result.get(
                            "message", "Không còn khung giờ trống để đặt lịch."
                        ),
                        "thought": "Không có khung giờ trống nên không thể thực hiện bước đặt lịch.",
                    }
                if not extracted["patient_id"] or not extracted["patient_name"]:
                    return {
                        "type": "text",
                        "content": "Vui lòng cung cấp đầy đủ mã và tên bệnh nhân để đặt lịch.",
                        "thought": "Thiếu thông tin bệnh nhân bắt buộc.",
                    }
                earliest_slot = min(slots)
                return {
                    "type": "tool_call",
                    "tool_name": "book_medical_appointment",
                    "arguments": {
                        "patient_id": extracted["patient_id"],
                        "patient_name": extracted["patient_name"],
                        "doctor_name": data.get("doctor_name", ""),
                        "specialty": data.get("specialty", ""),
                        "datetime_str": f"{earliest_slot} {data.get('appointment_date', '')}",
                    },
                    "thought": "Đã có lịch trống; chọn khung giờ sớm nhất và gọi công cụ đặt lịch.",
                }

            return {
                "type": "text",
                "content": _format_tool_result(tool_name, result),
                "thought": "Đã đủ dữ liệu từ công cụ để tổng hợp câu trả lời cuối cùng.",
            }

        extracted = _extract_medical_arguments(prompt)

        # Đặt lịch trực tiếp khi người dùng đã cung cấp giờ cụ thể.
        if "đặt lịch" in prompt_lower and extracted["appointment_time"]:
            return {
                "type": "tool_call",
                "tool_name": "book_medical_appointment",
                "arguments": {
                    "patient_id": extracted["patient_id"],
                    "patient_name": extracted["patient_name"],
                    "doctor_name": extracted["doctor_name"],
                    "specialty": extracted["specialty"],
                    "datetime_str": (
                        f"{extracted['appointment_time']} {extracted['appointment_date']}"
                    ),
                },
                "thought": "Người dùng đã cung cấp đủ thời gian; gọi công cụ đặt lịch khám.",
            }

        # Tra cứu riêng lẻ hoặc bước đầu của yêu cầu đặt giờ sớm nhất.
        if "lịch" in prompt_lower and "bác sĩ" in prompt_lower:
            return {
                "type": "tool_call",
                "tool_name": "doctor_schedule_query",
                "arguments": {
                    "doctor_name": extracted["doctor_name"],
                    "specialty": extracted["specialty"],
                    "appointment_date": extracted["appointment_date"],
                },
                "thought": "Cần tra cứu lịch bác sĩ và các khung giờ còn trống.",
            }

        return {
            "type": "text",
            "content": (
                "Quy trình đặt lịch khám Vinmec gồm: chọn chuyên khoa và bác sĩ, "
                "tra cứu khung giờ trống, cung cấp thông tin bệnh nhân, xác nhận thời "
                "gian và nhận mã đặt lịch. Nội dung này chỉ mang tính hướng dẫn, "
                "không phải chẩn đoán y khoa."
            ),
            "thought": "Đây là câu hỏi hướng dẫn chung nên không cần gọi công cụ.",
        }


class GeminiProvider(BaseLLMProvider):
    """Google Gemini Provider (Native Tool Calling với Google GenAI SDK)"""

    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model or os.getenv("LLM_MODEL") or "gemini-2.5-flash"

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        if not self.api_key or self.api_key == "your_gemini_api_key_here":
            return "[Gemini Error]: Chưa cấu hình GEMINI_API_KEY trong file .env! Đang sử dụng chế độ Mock."
        try:
            from google import genai

            client = genai.Client(api_key=self.api_key)
            contents = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
            response = client.models.generate_content(
                model=self.model_name, contents=contents
            )
            return response.text
        except Exception as e:
            return f"[Gemini Exception]: {str(e)}"

    def generate_with_tools(
        self,
        prompt: str,
        tools_schema: List[Dict[str, Any]],
        system_prompt: str = "",
        observations: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        if not self.api_key or self.api_key == "your_gemini_api_key_here":
            print(
                "ℹ️ [Gemini Provider]: Chưa tìm thấy GEMINI_API_KEY hợp lệ. Tự động chuyển sang Mock Offline."
            )
            return MockOfflineProvider().generate_with_tools(
                prompt, tools_schema, system_prompt, observations
            )

        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.api_key)

            # Chuẩn hóa function declarations cho Gemini SDK
            function_declarations = []
            for tool in tools_schema:
                # Bỏ qua các tool schema chưa được định nghĩa hoàn chỉnh
                if not tool.get("name") or not tool.get("parameters"):
                    continue
                function_declarations.append(
                    {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "parameters": tool.get("parameters", {}),
                    }
                )

            config = types.GenerateContentConfig(
                system_instruction=system_prompt if system_prompt else None,
                tools=(
                    [{"function_declarations": function_declarations}]
                    if function_declarations
                    else None
                ),
                temperature=0.2,
            )

            response = client.models.generate_content(
                model=self.model_name,
                contents=_prompt_with_observations(prompt, observations),
                config=config,
            )

            # Kiểm tra xem Gemini có trả về Tool Call không
            if response.function_calls:
                call = response.function_calls[0]
                args = dict(call.args) if hasattr(call, "args") and call.args else {}
                return {
                    "type": "tool_call",
                    "tool_name": call.name,
                    "arguments": args,
                    "thought": f"Gemini quyết định gọi công cụ '{call.name}' với tham số: {json.dumps(args, ensure_ascii=False)}",
                }
            else:
                return {
                    "type": "text",
                    "content": response.text or "",
                    "thought": "Gemini phản hồi trực tiếp bằng văn bản (không cần gọi công cụ).",
                }

        except Exception as e:
            print(
                f"⚠️ [Gemini API Warning]: Không thể kết nối live API ({str(e)}). Tự động fallback về Mock."
            )
            return MockOfflineProvider().generate_with_tools(
                prompt, tools_schema, system_prompt, observations
            )


class OpenAIProvider(BaseLLMProvider):
    """OpenAI Provider (Native Tool Calling với OpenAI SDK)"""

    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model_name = model or os.getenv("LLM_MODEL") or "gpt-4o-mini"

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        if not self.api_key or self.api_key == "your_openai_api_key_here":
            return "[OpenAI Error]: Chưa cấu hình OPENAI_API_KEY trong file .env! Đang sử dụng chế độ Mock."
        try:
            from openai import OpenAI

            client = OpenAI(api_key=self.api_key)
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            response = client.chat.completions.create(
                model=self.model_name, messages=messages
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            return f"[OpenAI Exception]: {str(e)}"

    def generate_with_tools(
        self,
        prompt: str,
        tools_schema: List[Dict[str, Any]],
        system_prompt: str = "",
        observations: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        if not self.api_key or self.api_key == "your_openai_api_key_here":
            print(
                "ℹ️ [OpenAI Provider]: Chưa tìm thấy OPENAI_API_KEY hợp lệ. Tự động chuyển sang Mock Offline."
            )
            return MockOfflineProvider().generate_with_tools(
                prompt, tools_schema, system_prompt, observations
            )

        try:
            from openai import OpenAI

            client = OpenAI(api_key=self.api_key)

            tools = []
            for tool in tools_schema:
                if not tool.get("name"):
                    continue
                tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": tool["name"],
                            "description": tool.get("description", ""),
                            "parameters": tool.get("parameters", {}),
                        },
                    }
                )

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append(
                {
                    "role": "user",
                    "content": _prompt_with_observations(prompt, observations),
                }
            )

            response = client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                tools=tools if tools else None,
                tool_choice="auto" if tools else None,
            )

            msg = response.choices[0].message
            if msg.tool_calls:
                call = msg.tool_calls[0]
                args = (
                    json.loads(call.function.arguments)
                    if call.function.arguments
                    else {}
                )
                return {
                    "type": "tool_call",
                    "tool_name": call.function.name,
                    "arguments": args,
                    "thought": f"OpenAI quyết định gọi công cụ '{call.function.name}' với tham số: {json.dumps(args, ensure_ascii=False)}",
                }
            else:
                return {
                    "type": "text",
                    "content": msg.content or "",
                    "thought": "OpenAI phản hồi trực tiếp bằng văn bản (không cần gọi công cụ).",
                }
        except Exception as e:
            print(
                f"⚠️ [OpenAI API Warning]: Không thể kết nối live API ({str(e)}). Tự động fallback về Mock."
            )
            return MockOfflineProvider().generate_with_tools(
                prompt, tools_schema, system_prompt, observations
            )


def get_llm_provider() -> BaseLLMProvider:
    """Factory function khởi tạo Provider theo LLM_PROVIDER env variable"""
    provider_type = os.getenv("LLM_PROVIDER", "gemini").lower()

    if provider_type == "gemini":
        key = os.getenv("GEMINI_API_KEY")
        if key and key != "your_gemini_api_key_here":
            return GeminiProvider()
        else:
            return MockOfflineProvider()
    elif provider_type == "openai":
        key = os.getenv("OPENAI_API_KEY")
        if key and key != "your_openai_api_key_here":
            return OpenAIProvider()
        else:
            return MockOfflineProvider()
    elif provider_type == "mock":
        return MockOfflineProvider()
    else:
        return MockOfflineProvider()
