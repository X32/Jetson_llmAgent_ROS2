#!/usr/bin/env python3
"""测试 llama.cpp 服务器的 Python 脚本 - 支持文本模式 FC"""
import requests
import json
import re

def extract_json_from_text(text):
    """从文本中提取 JSON 工具调用（支持文本模式 FC）"""
    if not text:
        return None

    patterns = [
        r'```json\s*(\{.*?\})\s*```',  # ```json {...}```
        r'```\s*(\{.*?\})\s*```',      # ``` {...}```
        r'(\{[^{}]*"name"[^{}]*"arguments"[^{}]*\})',  # 直接的 JSON
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                json_str = match.group(1)
                return json.loads(json_str)
            except json.JSONDecodeError:
                continue

    return None

def test_function_calling(base_url, model, user_content, tools, test_name="FC 测试"):
    """测试 Function Calling（支持文本模式和标准模式）"""
    print(f"\n--- {test_name}: {user_content} ---")

    fc_payload = {
        "model": model,
        "messages": [{"role": "user", "content": user_content}],
        "tools": tools,
        "stream": False
    }

    try:
        response = requests.post(
            f"{base_url}/v1/chat/completions",
            headers={"Content-Type": "application/json"},
            json=fc_payload,
            timeout=30
        )

        print(f"状态码: {response.status_code}")

        if response.status_code != 200:
            print(f"❌ 错误响应: {response.text[:200]}")
            return False

        result = response.json()
        message = result["choices"][0]["message"]
        text_content = message.get("content", "").strip()

        # === 优先检查文本模式 FC ===
        json_fc = extract_json_from_text(text_content) if text_content else None
        if json_fc and "name" in json_fc and "arguments" in json_fc:
            print(f"✅ 文本模式 Function Calling 成功!")
            func_name = json_fc["name"]
            func_args = json_fc["arguments"]
            print(f"   🔧 工具: {func_name}")
            print(f"   📋 参数: {json.dumps(func_args, ensure_ascii=False)}")
            return True

        # === 检查标准模式 FC ===
        elif "tool_calls" in message and message["tool_calls"]:
            print(f"✅ 标准 Function Calling 成功!")
            tool_calls = message["tool_calls"]
            if isinstance(tool_calls, list):
                for tool_call in tool_calls:
                    func_name = tool_call["function"]["name"]
                    func_args = tool_call["function"]["arguments"]
                    if isinstance(func_args, str):
                        func_args = json.loads(func_args)
                    print(f"   🔧 工具: {func_name}")
                    print(f"   📋 参数: {json.dumps(func_args, ensure_ascii=False)}")
            return True

        # === 无 Function Calling ===
        else:
            print(f"❌ 没有触发 Function Calling")
            print(f"   📝 回答: {text_content[:200]}")
            return False

    except Exception as e:
        print(f"❌ 请求失败: {e}")
        return False

def test_llm_server():
    """测试 llama.cpp 服务器的聊天 API"""

    # 服务器配置
    base_url = "http://localhost:8000"
    model = "mlc-ai/Qwen2.5-3B-Instruct-q4f16_1-MLC"  # 或者使用实际模型路径

    print(f"🧪 测试 llama.cpp 服务器: {base_url}")
    print(f"📝 模型: {model}")

    # 测试 1: 健康检查
    print("\n=== 测试 1: 健康检查 ===")
    try:
        response = requests.get(f"{base_url}/health", timeout=5)
        print(f"✅ 健康检查: {response.status_code}")
    except Exception as e:
        print(f"❌ 健康检查失败: {e}")
        return

    # 测试 2: 获取模型列表
    print("\n=== 测试 2: 获取模型列表 ===")
    try:
        response = requests.get(f"{base_url}/v1/models", timeout=5)
        models = response.json()
        print(f"✅ 可用模型:")
        for model_info in models.get("data", []):
            print(f"   - {model_info['id']}")

        # 使用第一个可用的模型
        if models.get("data"):
            model = models["data"][0]["id"]
            print(f"\n🔄 使用模型: {model}")
    except Exception as e:
        print(f"❌ 获取模型列表失败: {e}")
        return

    # 测试 3: 简单对话（无 Function Calling）
    print("\n=== 测试 3: 简单对话测试 ===")
    test_messages = [
        {"role": "user", "content": "你好"},
        {"role": "user", "content": "向前走半米"},
    ]

    for i, message in enumerate(test_messages, 1):
        print(f"\n--- 测试 {i}: {message['content']} ---")
        payload = {
            "model": model,
            "messages": [message],
            "stream": False,
            "max_tokens": 64
        }

        try:
            response = requests.post(
                f"{base_url}/v1/chat/completions",
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=30
            )

            print(f"状态码: {response.status_code}")

            if response.status_code == 200:
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                print(f"✅ 回答: {content}")
            else:
                print(f"❌ 错误响应: {response.text}")

        except Exception as e:
            print(f"❌ 请求失败: {e}")

    # 测试 4: Function Calling 综合测试
    print("\n=== 测试 4: Function Calling 综合测试 ===")

    tools = [
        {
            "type": "function",
            "function": {
                "name": "move_forward",
                "description": "控制机器人向前移动指定距离",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "distance": {
                            "type": "number",
                            "description": "移动距离（米），范围 0.05~10.0"
                        }
                    },
                    "required": ["distance"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "turn_left",
                "description": "控制机器人向左旋转指定角度",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "angle": {
                            "type": "number",
                            "description": "旋转角度（度），范围 1~360"
                        }
                    },
                    "required": ["angle"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "stop",
                "description": "停止机器人运动",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        }
    ]

    # 测试不同的指令
    test_cases = [
        ("向前走半米", "基础移动指令"),
        ("左转九十度", "旋转指令"),
        ("停止", "停止指令"),
        ("向前走1.5米", "浮点数参数"),
    ]

    fc_results = []
    for user_content, description in test_cases:
        success = test_function_calling(base_url, model, user_content, tools, description)
        fc_results.append((user_content, success))

    # 测试结果统计
    print("\n=== 测试结果统计 ===")
    passed = sum(1 for _, success in fc_results if success)
    total = len(fc_results)

    print(f"✅ 通过: {passed}/{total}")
    for user_content, success in fc_results:
        status = "✅" if success else "❌"
        print(f"   {status} {user_content}")

    print("\n=== 测试完成 ===")

if __name__ == "__main__":
    test_llm_server()
