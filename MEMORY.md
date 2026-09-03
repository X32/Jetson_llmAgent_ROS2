# Project Memory

## Environment Setup

### Python Environment Configuration
- **Problem**: System Python 3.13 (miniconda3) incompatible with ROS2 Humble (requires Python 3.10)
- **Solution**: Created dedicated conda environment `ros2_env` with Python 3.10.21
- **Required Dependencies**: empy==3.3.4, catkin_pkg, lark-parser

### LLM Backend Switch
- **Original Issue**: `ModuleNotFoundError: No module named 'ollama'`
- **Solution**: Switch to llama.cpp backend using existing `llm_core_llamacpp.py`
- **Activation**: Set `LLAMACPP=1` environment variable
- **Launch Script**: `./run_llamaccp_agent.sh`

### Build Commands
```bash
# Activate correct Python environment
source ~/miniconda3/etc/profile.d/conda.sh
conda activate ros2_env

# Build project
colcon build --packages-select my_package robot_agent

# Run llama.cpp version
source install/setup.bash
LLAMACPP=1 ros2 run robot_agent llm_agent
```

## Function Calling 解决方案 (2024-09-01)

### 问题发现
llama.cpp 服务器返回 **文本模式 FC** - JSON 在 `content` 字段而非 `tool_calls`：
```json
{
  "content": "```json\n{\"name\": \"move_forward\", \"arguments\": {\"distance\": 0.5}}\n```",
  "tool_calls": null
}
```

### 解决方案
修改 `llm_core_llamacpp.py` 添加 `_extract_json_from_text()` 方法，支持双模式 FC：
1. **文本模式 FC**: 从 `content` 提取 JSON（当前方式）
2. **标准 FC**: 从 `tool_calls` 提取（OpenAI 标准）

### 测试验证
所有指令正常工作：
- ✅ 向前走半米 → move_forward distance=0.5
- ✅ 左转九十度 → turn_left angle=90.0
- ✅ 停止 → stop

### 性能
- FC 延迟: 1000-1600ms
- 发布延迟: 0.2ms

## Architecture Notes

### Backend Architecture
- **Ollama Version**: `llm_core.py` - requires ollama Python package
- **llama.cpp Version**: `llm_core_llamacpp.py` - **supports text-mode FC**, uses OpenAI-compatible HTTP API
- **Switch Logic**: `llm_agent_node.py` checks `LLAMACPP` environment variable at import time

### Message Contract
- Only `llm_agent_node.py` converts between LLM JSON output and ROS `RobotCommand.msg`
- This isolation allows swapping LLM models without changing downstream nodes

### FC Implementation Details
**Text-Mode FC** (当前 llama.cpp 实现):
- 模型输出 JSON 格式工具调用
- 正则表达式提取: ````json {...}````, ```{...}```, 直接 JSON
- 自动处理多种输出格式
- 兼容不同模型的 FC 训练风格

**Standard FC** (OpenAI 格式):
- 结构化 `tool_calls` 字段
- 标准参数传递
- Ollama 和部分 llama.cpp 版本支持

## Important Paths

- **Config files**: `src/robot_agent/robot_agent/config/`
  - `llm_config.json` - Ollama configuration
  - `llm_config_llamacpp.json` - llama.cpp configuration
- **LLM Cores**: `src/robot_agent/robot_agent/`
  - `llm_core.py` - Ollama backend
  - `llm_core_llamacpp.py` - llama.cpp backend
- **Launch Script**: `run_llamaccp_agent.sh`
