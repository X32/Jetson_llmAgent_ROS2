#!/bin/bash
# 启动 llama.cpp 版本的 LLM Agent（支持文本模式 Function Calling）
# 解决 Python 版本不兼容和 ollama 依赖问题
#
# 特性：
# - 自动切换到 Python 3.10 环境
# - 支持文本模式 Function Calling
# - 使用 GGUF 格式模型

echo "🚀 启动 LLM Agent (llama.cpp + 文本模式 FC)"

# 激活 Python 3.10 conda 环境
source ~/miniconda3/etc/profile.d/conda.sh
conda activate ros2_env

# Source ROS2 环境
source install/setup.bash

# 检查 llama.cpp 服务器是否运行
if ! curl -s http://localhost:8000/v1/models > /dev/null 2>&1; then
    echo "❌ 错误: llama.cpp 服务器未运行"
    echo "请先启动服务器:"
    echo "  cd /path/to/llama.cpp"
    echo "  ./llama-server --model /path/to/qwen2.5-3b-instruct-q4_k_m.gguf --port 8000"
    exit 1
fi

echo "✅ 环境检查通过"
echo "📡 模型: Qwen2.5-Coder-3B-Instruct-Q4_K_M"
echo "🔄 Function Calling: 文本模式"
echo ""

# 启动 llama.cpp 版本的 llm_agent
LLAMACPP=1 ros2 run robot_agent llm_agent
