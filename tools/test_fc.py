#!/usr/bin/env python3
"""测试 OpenAI 客户端的 Function Calling 支持"""
from openai import OpenAI

# 初始化客户端
client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-needed"
)

# 测试基础 function calling
response = client.chat.completions.create(
    model="Qwen2.5-3B-Instruct-q4f16_1-MLC",
    messages=[
        {"role": "system", "content": """你是一个天气查询助手。当用户询问天气时，你必须调用相应的工具函数来获取真实数据，不要编造任何数值。

重要规则：
1. 对于天气查询，你必须调用 get_weather 工具，不要只回答文字
2. 如果无法理解查询或查询超出服务范围，可以解释但不调用工具
3. 拿到工具返回的数据后，用简短自然的中文回答（1-2句话），数值必须来自工具结果

可用工具：get_weather"""},
        {"role": "user", "content": "北京的天气怎么样？"}
    ],
    tools=[
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "获取指定城市的天气",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string", "description": "城市名称"}
                    },
                    "required": ["city"]
                }
            }
        }
    ]
)

print("=== Function Calling 测试结果 ===")
print(f"模型: {response.model}")
print(f"状态: {response.choices[0].finish_reason}")

message = response.choices[0].message

# 检查是否有工具调用
if hasattr(message, 'tool_calls') and message.tool_calls:
    print("✅ 检测到工具调用:")
    for tool_call in message.tool_calls:
        print(f"  工具: {tool_call.function.name}")
        print(f"  参数: {tool_call.function.arguments}")
elif message.content:
    # 检查文本模式 FC
    import json
    import re

    # 尝试从文本中提取 JSON
    text_content = message.content.strip()
    patterns = [
        r'```json\s*(\{.*?\})\s*```',
        r'```\s*(\{.*?\})\s*```',
        r'(\{[^{}]*"name"[^{}]*"arguments"[^{}]*\})',
        r'^(\{.*?\})$',  # 纯 JSON 格式
    ]

    fc_detected = False
    for pattern in patterns:
        match = re.search(pattern, text_content, re.DOTALL)
        if match:
            try:
                json_data = json.loads(match.group(1))
                print("✅ 检测到文本模式工具调用:")
                print(f"  工具: {json_data.get('name')}")
                print(f"  参数: {json_data.get('arguments')}")
                fc_detected = True
                break
            except json.JSONDecodeError:
                continue

    if not fc_detected:
        print("❌ 未检测到工具调用")
        print(f"内容: {text_content[:200]}")

print("\n=== 完整消息对象 ===")
print(message)
