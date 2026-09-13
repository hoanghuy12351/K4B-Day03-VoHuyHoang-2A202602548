"""
🚀 CORE AGENT APPLICATION (DAY 03: CHATBOT VS REACT AGENT)
Thực thi so sánh giữa Chatbot Baseline (Cấp 2) và ReAct Agent kết nối MCP Server (Cấp 3).
"""

import json
import os
import sys
import tempfile
import time

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv():
        """Cho phép chạy Mock Offline khi chưa cài python-dotenv."""
        return False

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from mcp_server import MCPAcademicServer
from prompts import (
    CHATBOT_BASELINE_PROMPT,
    REACT_AGENT_SYSTEM_PROMPT,
    MAX_ITERATIONS
)
from providers import get_llm_provider

load_dotenv()

def load_test_cases():
    """Tải danh sách 5 test cases từ config/test_cases.json hoặc config/test_cases.example.json"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, "config", "test_cases.json")
    if not os.path.exists(config_path):
        example_path = os.path.join(base_dir, "config", "test_cases.example.json")
        if os.path.exists(example_path):
            print("⚠️ [CONFIG NOTICE]: Chưa thấy file 'config/test_cases.json'. Đang dùng mẫu 'config/test_cases.example.json'.")
            print("👉 Hãy chạy: copy config/test_cases.example.json config/test_cases.json và viết test cases theo đề tài của bạn!\n")
            config_path = example_path
        else:
            config_path = "test_cases.json"
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_waterfall_trace(trace_data: list, filename: str = "trace_waterfall.json"):
    """Ghi Waterfall Trace ra file JSON trong thư mục docs."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    docs_dir = os.path.join(base_dir, "docs")
    os.makedirs(docs_dir, exist_ok=True)
    trace_path = os.path.join(docs_dir, filename)
    with open(trace_path, "w", encoding="utf-8") as f:
        json.dump(trace_data, f, ensure_ascii=False, indent=2)
    print(f"📊 [OBSERVABILITY]: Đã lưu {len(trace_data)} sự kiện Waterfall Trace tại '{trace_path}'!")


def run_baseline_chatbot(user_query: str, provider):
    """Chạy Chatbot gốc (Cấp 2) không có công cụ gọi Tool"""
    print(f"\n💬 [CHATBOT BASELINE] Câu hỏi: {user_query}")
    response = provider.generate(user_query, system_prompt=CHATBOT_BASELINE_PROMPT)
    print(f"🤖 Chatbot phản hồi:\n{response}")


def run_react_agent(
    user_query: str,
    provider,
    mcp_server: MCPAcademicServer,
    verbose: bool = True,
) -> list:
    """
    [REACT AGENT LOOP] Thực thi vòng lặp Thought -> Action -> Observation với MCP Server
    Trả về danh sách trace log của phiên thực thi.
    """
    emit = print if verbose else lambda *args, **kwargs: None
    emit(f"\n🤖 [REACT AGENT] Câu hỏi: {user_query}")
    
    trace_logs = []
    tools_list = mcp_server.list_tools()
    observations = []

    for step in range(1, MAX_ITERATIONS + 1):
        step_start_time = time.time()
        emit(f"\n--- 🔄 Vòng lặp ReAct Loop (Step {step}/{MAX_ITERATIONS}) ---")

        # Gọi LLM với Native Tool Calling Specs
        llm_response = provider.generate_with_tools(
            user_query,
            tools_list,
            system_prompt=REACT_AGENT_SYSTEM_PROMPT,
            observations=observations,
        )
        latency_ms = round((time.time() - step_start_time) * 1000, 2)

        thought = llm_response.get("thought", "Đang suy luận...")
        emit(f"🧠 [Thought]: {thought}")

        # Trường hợp 1: LLM quyết định trả lời bằng văn bản trực tiếp
        if llm_response.get("type") == "text":
            final_content = llm_response.get("content", "")
            emit(f"🏁 [Final Answer]: {final_content}")
            trace_logs.append({
                "step": step,
                "query": user_query,
                "action_type": "FINAL_ANSWER",
                "thought": thought,
                "output": final_content,
                "latency_ms": latency_ms
            })
            return trace_logs

        # Trường hợp 2: LLM đề xuất gọi Tool (Action)
        if llm_response.get("type") == "tool_call":
            tool_name = llm_response.get("tool_name")
            arguments = llm_response.get("arguments", {})

            emit(f"🛠️ [Action Proposed]: {tool_name}({arguments})")

            # Thực thi Tool qua MCP Server
            mcp_result = mcp_server.call_tool(tool_name, arguments)
            obs_data = mcp_result.get("result", {})

            emit(
                "👁️ [Observation từ MCP Server]: "
                f"{json.dumps(obs_data, ensure_ascii=False)}"
            )

            trace_logs.append({
                "step": step,
                "query": user_query,
                "action_type": "TOOL_EXECUTION",
                "tool_name": tool_name,
                "arguments": arguments,
                "observation": obs_data,
                "latency_ms": latency_ms
            })
            observations.append({
                "tool_name": tool_name,
                "arguments": arguments,
                "result": obs_data,
            })

            # Không dừng tại đây: Observation được đưa lại cho LLM ở vòng kế tiếp.
            continue

        final_content = "Mô hình trả về kiểu phản hồi không hợp lệ."
        emit(f"🏁 [Final Answer]: {final_content}")
        trace_logs.append({
            "step": step,
            "query": user_query,
            "action_type": "ERROR",
            "thought": thought,
            "output": final_content,
            "latency_ms": latency_ms,
        })
        return trace_logs

    # Chốt an toàn nếu mô hình liên tục gọi Tool vượt giới hạn.
    latest_result = observations[-1]["result"] if observations else {}
    final_content = (
        latest_result.get("message")
        or latest_result.get("error")
        or "Agent đã đạt giới hạn số vòng xử lý mà chưa có câu trả lời cuối cùng."
    )
    emit(f"🏁 [Final Answer]: {final_content}")
    trace_logs.append({
        "step": MAX_ITERATIONS + 1,
        "query": user_query,
        "action_type": "FINAL_ANSWER",
        "thought": "Dừng an toàn do đạt giới hạn số vòng ReAct.",
        "output": final_content,
        "latency_ms": 0.0,
    })

    return trace_logs


if __name__ == "__main__":
    # Chế độ nghiệm thu luôn dùng database tạm để không chiếm lịch thật.
    test_database_directory = None
    if "--all" in sys.argv:
        test_database_directory = tempfile.TemporaryDirectory()
        os.environ["DATABASE_PATH"] = os.path.join(
            test_database_directory.name, "test_suite.db"
        )

    print("==========================================================")
    print("🏥 VINMEC HEALTHCARE ASSISTANT - CHATBOT VS REACT AGENT")
    print("==========================================================")
    
    provider = get_llm_provider()
    mcp_server = MCPAcademicServer()
    
    print(f"🔌 LLM Provider: {provider.__class__.__name__}")
    print(f"🌐 MCP Server: {mcp_server.server_name}\n")
    
    tests = load_test_cases()
    print(f"✅ Đã tải thành công {len(tests)} Test Cases thử nghiệm.\n")
    
    if "--interactive" in sys.argv:
        print("🎮 [INTERACTIVE MODE] Trò chuyện trực tiếp với ReAct Agent:")
        print("💡 Gợi ý câu hỏi thử nghiệm:")
        print("   - Câu hỏi chung: 'Quy trình đặt lịch khám tại Vinmec như thế nào?'")
        print("   - Tra cứu: 'Tra cứu lịch bác sĩ Nguyễn Minh An, chuyên khoa Tim mạch, ngày 20/09/2026'")
        print("   - Đặt lịch: 'Đặt lịch cho bệnh nhân Nguyễn Văn Nam, mã BN2026001, với bác sĩ Nguyễn Minh An lúc 09:00 ngày 20/09/2026'")
        print("   - Gõ 'exit' hoặc 'quit' để kết thúc phiên trò chuyện.\n")
        while True:
            try:
                user_input = input("👤 Người dùng hỏi: ").strip()
                if not user_input or user_input.lower() in ["exit", "quit"]:
                    print("👋 Tạm biệt! Kết thúc phiên trò chuyện.")
                    break
                logs = run_react_agent(user_input, provider, mcp_server)
                # Không ghi đè trace nghiệm thu được tạo bởi chế độ --all.
                save_waterfall_trace(logs, "trace_interactive.json")
            except (KeyboardInterrupt, EOFError):
                print("\n👋 Đã thoát phiên tương tác.")
                break
    elif "--all" in sys.argv:
        print("🚀 [TEST SUITE MODE] Kiểm tra 5 Test Cases:")
        completed_count = 0
        todo_count = 0
        all_traces = []
        
        for tc in tests:
            print(f"\n==================================================")
            print(f"🧪 [{tc['id']}] Loại test: {tc['type']} (Độ phức tạp: {tc['complexity']})")
            print(f"📌 Kỳ vọng: {tc['expected_behavior']}")
            
            if tc["question"].strip().startswith("TODO"):
                print(f"⏸️ [CHƯA KÍCH HOẠT - ĐANG LÀ TODO]:")
                print(f"   {tc['question']}")
                print(f"   👉 Hãy mở file 'config/test_cases.json' để viết câu hỏi thực tế cho Test Case này!")
                todo_count += 1
            else:
                logs = run_react_agent(tc["question"], provider, mcp_server)
                all_traces.extend(logs)
                completed_count += 1
                
        print(f"\n==================================================")
        print(f"📊 [KẾT QUẢ TEST SUITE]: Đã thực thi {completed_count}/{len(tests)} Test Cases | {todo_count} Test Cases đang chờ điền câu hỏi (TODO)")
        if all_traces:
            save_waterfall_trace(all_traces)
        print(f"💡 Để trò chuyện trực tiếp từng câu: Chạy 'python src/app.py --interactive'")
    else:
        # Chế độ mặc định khi chỉ gõ 'python src/app.py'
        print("ℹ️ HƯỚNG DẪN SỬ DỤNG CHƯƠNG TRÌNH:")
        print("  1. Chat trực tiếp liên tục:   python src/app.py --interactive")
        print("  2. Chạy toàn bộ Test Cases:    python src/app.py --all\n")
        
        sample_query = tests[1]["question"]
        print("--- 🏁 DEMO CHẠY THỬ 1 TEST CASE MẪU (TC02: Tra cứu lịch bác sĩ) ---")
        logs = run_react_agent(sample_query, provider, mcp_server)
        save_waterfall_trace(logs)
        print("\n💡 Hãy thử ngay lệnh: python src/app.py --interactive để chat trực tiếp!")
