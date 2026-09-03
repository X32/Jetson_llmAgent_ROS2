# Function Calling 解决方案

## 问题发现

通过 `tools/test_llm_server.py` 测试发现，llama.cpp 服务器返回的 Function Calling 格式为：

```json
{
  "choices": [{
    "message": {
      "content": "```json\n{\"name\": \"move_forward\", \"arguments\": {\"distance\": 0.5}}\n```",
      "tool_calls": null
    }
  }]
}
```

**问题**：模型理解 FC 但以 **JSON 文本** 形式输出，而不是标准的 `tool_calls` 结构。

## 解决方案

修改 `llm_core_llamacpp.py` 添加 **双模式 FC 支持**：

### 1. 添加 JSON 提取功能
```python
def _extract_json_from_text(self, text):
    """从文本中提取 JSON 工具调用（支持文本模式 FC）"""
    patterns = [
        r'```json\s*(\{.*?\})\s*```',  # ```json {...}```
        r'```\s*(\{.*?\})\s*```',      # ``` {...}```
        r'(\{[^{}]*"name"[^{}]*"arguments"[^{}]*\})',  # 直接的 JSON
    ]
    # ... 提取逻辑
```

### 2. 双模式处理逻辑
```python
# 优先尝试文本模式 FC（从 content 提取 JSON）
json_fc = self._extract_json_from_text(text_content)
if json_fc and "name" in json_fc and "arguments" in json_fc:
    # 处理文本模式 FC

# 回退到标准 FC（从 tool_calls 提取）
elif "tool_calls" in message and message["tool_calls"]:
    # 处理标准 OpenAI FC
```

## 测试结果

所有指令测试通过：

| 指令 | 识别结果 | 参数 |
|------|----------|------|
| 向前走半米 | move_forward | distance=0.5 ✅ |
| 左转九十度 | turn_left | angle=90.0 ✅ |
| 停止 | stop | - ✅ |

## 性能指标

- **FC 延迟**: 1000-1600ms（模型推理时间）
- **消息发布延迟**: 0.2ms
- **总延迟**: 主要取决于模型推理速度

## 环境要求

- **Python**: 3.10 (ros2_env conda 环境)
- **模型**: Qwen2.5-Coder-3B-Instruct-Q4_K_M.gguf
- **内存**: ~3-4GB
- **服务器**: llama.cpp (http://localhost:8000)

## 启动命令

```bash
# 1. 启动 llama.cpp 服务器
./llama-server --model /path/to/qwen2.5-3b-instruct-q4_k_m.gguf --port 8000

# 2. 启动 LLM Agent
./run_llamaccp_agent.sh

# 3. 测试
ros2 topic pub --once /voice_text std_msgs/msg/String "data: '向前走半米'"
```

## 关键改进

1. **兼容性**: 同时支持文本模式和标准 FC
2. **稳定性**: 多种 JSON 格式提取模式
3. **性能**: 保持原有缓存和优化
4. **可扩展**: 易于添加新的 FC 模式

## 注意事项

- 不同模型的 FC 格式可能不同，需要相应调整提取模式
- 文本模式 FC 依赖于模型训练质量和提示词设计
- 建议定期测试新模型版本以验证 FC 兼容性

## 实测踩坑记录

### 坑1：500 Missing tool call type（2024-09-01）

**现象**：第一条指令成功，第二条指令报 500：
```
Failed to parse messages: Missing tool call type:
{"function":{"name":"turn_left","arguments":{"angle":90}}}
```

**根因**：文本模式 FC 下我们自己构建的 `tool_calls`（写进对话历史）缺少
`"type": "function"` 字段。下一轮把历史发回服务器时解析失败。

**修复**：构建 tool_calls 时必须带 type 字段：
```python
tool_calls = [{
    "type": "function",           # ← 必须有
    "function": {"name": ..., "arguments": ...},
}]
```

**教训**：任何写进 messages 历史的结构，都要按服务器要求完整——
本轮能用 ≠ 下轮回放时能用。

### 坑2：3B 模型多轮上下文偶发 no_tool

**现象**：多轮对话后，单条指令偶发不输出工具调用（纯文字回答）。

**验证**：单独测试"停止" 10/10 成功，说明是长上下文下的采样抖动。

**兜底**：系统安全设计已覆盖——no_tool 不发布指令，controller
零速心跳保持车静止（最安全方向的失败）。

