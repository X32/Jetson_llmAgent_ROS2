# LLM 后端切换指南

本项目支持两种 LLM 后端：Ollama（默认）和 llama.cpp 服务器。

## 1. Ollama（默认后端）

### 启动 Ollama 服务
```bash
# 确保 Ollama 服务正在运行
ollama serve

# 拉取模型
ollama pull qwen2.5:3b
```

### 启动机器人系统
```bash
# Terminal 1: Gazebo 仿真
source install/setup.bash
ros2 launch robot_description robot_bringup.launch.py

# Terminal 2: LLM agent + robot controller（默认使用 Ollama）
source install/setup.bash
ros2 launch robot_agent robot_agent_bringup.launch.py

# Terminal 3: 语音输入
source install/setup.bash
ros2 run voice_input voice_input_node
```

## 2. llama.cpp 服务器

### 启动 llama.cpp 服务器
```bash
# 启动 llama.cpp 服务器（示例命令，根据你的实际启动方式调整）
# 确保服务器监听在 http://localhost:8000
llama-server --model /path/to/your/model.gguf --port 8000
```

### 启动机器人系统（使用 llama.cpp 后端）
```bash
# Terminal 1: Gazebo 仿真
source install/setup.bash
ros2 launch robot_description robot_bringup.launch.py

# Terminal 2: LLM agent + robot controller（使用 llama.cpp 后端）
export LLAMACPP=1
source install/setup.bash
ros2 launch robot_agent robot_agent_bringup.launch.py

# Terminal 3: 语音输入
source install/setup.bash
ros2 run voice_input voice_input_node
```

## 配置文件

- **Ollama**: `src/robot_agent/robot_agent/config/llm_config.json`
- **llama.cpp**: `src/robot_agent/robot_agent/config/llm_config_llamacpp.json`

### llama.cpp 配置示例
```json
{
  "base_url": "http://localhost:8000",
  "model": "mlc-ai/Qwen2.5-3B-Instruct-q4f16_1-MLC",
  "options": {
    "temperature": 0.1,
    "max_tokens": 4096
  },
  "tools": [...]
}
```

## 测试连接

### 测试 Ollama
```bash
curl http://localhost:11434/api/chat -d '{
  "model":"qwen2.5:3b",
  "messages":[{"role":"user","content":"你好"}],
  "stream":false
}'
```

### 测试 llama.cpp
```bash
curl http://localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model":"mlc-ai/Qwen2.5-3B-Instruct-q4f16_1-MLC",
    "messages":[{"role":"user","content":"你好"}],
    "stream":false,
    "max_tokens":64
  }'
```

## 切换后端说明

- **默认行为**: 使用 Ollama 后端
- **启用 llama.cpp**: 设置环境变量 `export LLAMACPP=1`
- **配置文件**: 系统会根据环境变量自动选择对应的配置文件

## 故障排除

1. **连接失败**: 确保 LLM 服务正在运行并监听正确的端口
2. **模型错误**: 检查配置文件中的模型名称与实际部署的模型匹配
3. **超时问题**: 如果网络延迟较高，可以增加 `llm_core_llamacpp.py` 中的超时时间

## 性能对比

- **Ollama**: 开箱即用，支持多种模型格式，管理方便
- **llama.cpp**: 更轻量，支持更多量化选项，灵活性更高

选择合适的后端取决于你的具体需求和硬件配置。
