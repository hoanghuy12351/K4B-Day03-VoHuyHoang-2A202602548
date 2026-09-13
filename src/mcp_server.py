"""
🔌 MODEL CONTEXT PROTOCOL (MCP) SERVER MODULE
Mô phỏng MCP Server cung cấp công cụ tra cứu và đặt lịch khám Vinmec.
"""

import json
import sys
from typing import Dict, Any, List
from tools import TOOLS_SCHEMA, dispatch_tool_call

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


class MCPAcademicServer:
    """
    Giả lập MCP Server cho trợ lý tư vấn sức khỏe.

    Tên lớp cũ được giữ lại để tương thích với cấu trúc bài lab.
    """

    def __init__(self, server_name: str = "vinmec-healthcare-mcp-server"):
        self.server_name = server_name
        self.version = "2026.1.0"

    def list_tools(self) -> List[Dict[str, Any]]:
        """Trả về danh sách các Tools chuẩn giao thức MCP"""
        return TOOLS_SCHEMA

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Thực thi request gọi Tool theo chuẩn MCP JSON-RPC
        """
        # 1. Gọi đúng tool
        result_json = dispatch_tool_call(tool_name, arguments)

        # 2. Chuyển chuỗi JSON thành Dict(từ điển Python)
        content = json.loads(result_json)

        # 3. Đóng gói kết quả
        return {
            "jsonrpc": "2.0",
            "server": self.server_name,
            "tool": tool_name,
            "result": content,
        }


if __name__ == "__main__":
    print("==========================================================")
    print("🔌 KIỂM THỬ ĐỘC LẬP MCP SERVER (vinmec-healthcare-mcp-server)")
    print("==========================================================")

    server = MCPAcademicServer()
    tools = server.list_tools()
    print(
        f"✅ Khởi tạo thành công MCP Server: {server.server_name} (Version: {server.version})"
    )
    print(f"📦 Số lượng Tools công bố: {len(tools)}")

    # Kiểm tra Tool Schema
    sched_tool = next(
        (t for t in tools if t.get("name") == "book_medical_appointment"), None
    )
    if sched_tool and not sched_tool.get("parameters", {}).get("properties"):
        print(
            "❌ Tool 'book_medical_appointment' chưa được định nghĩa properties trong 'src/tools.py'."
        )
    else:
        print("✅ Tool 'book_medical_appointment' đã có schema đầy đủ.")

    # Kiểm tra call_tool
    test_result = server.call_tool(
        "doctor_schedule_query",
        {
            "doctor_name": "Nguyễn Minh An",
            "specialty": "Tim mạch",
            "appointment_date": "20/09/2026",
        },
    )
    if not test_result:
        print("❌ Hàm call_tool() trả về kết quả rỗng.")
    else:
        print("✅ Test dispatch tool 'doctor_schedule_query' thành công:")
        print(f"   Phản hồi JSON-RPC: {json.dumps(test_result, ensure_ascii=False)}")
