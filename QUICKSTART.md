# 语音控制机器人 - 快速启动指南

## 环境准备

### 1. 激活 Python 3.10 环境
```bash
source ~/miniconda3/etc/profile.d/conda.sh
conda activate ros2_env
```

### 2. 确保 llama.cpp 服务器运行
```bash
# 检查服务器状态
curl http://localhost:8000/v1/models

# 如果未运行，启动服务器
cd /path/to/llama.cpp
./llama-server --model /home/zy/Desktop/workplace/models/qwen2.5-coder-3b-instruct-q4_k_m.gguf --port 8000
```

## 启动系统 (3个终端)

### 终端 1: Gazebo 仿真
```bash
source ~/miniconda3/etc/profile.d/conda.sh
conda activate ros2_env
source install/setup.bash
ros2 launch robot_description robot_bringup.launch.py
```

### 终端 2: LLM Agent + Robot Controller
```bash
# 使用启动脚本
./run_llamaccp_agent.sh

# 或者手动启动
source ~/miniconda3/etc/profile.d/conda.sh
conda activate ros2_env
source install/setup.bash
LLAMACPP=1 ros2 launch robot_agent robot_agent_bringup.launch.py
```

### 终端 3: 语音输入
```bash
source ~/miniconda3/etc/profile.d/conda.sh
conda activate ros2_env
source install/setup.bash
ros2 run voice_input voice_input_node
```

## 测试语音控制

### 文本指令测试
```bash
# 基础动作
ros2 topic pub --once /voice_text std_msgs/msg/String "data: '向前走半米'"
ros2 topic pub --once /voice_text std_msgs/msg/String "data: '左转九十度'"
ros2 topic pub --once /voice_text std_msgs/msg/String "data: '右转四十五度'"
ros2 topic pub --once /voice_text std_msgs/msg/String "data: '停止'"

# 传感器查询
ros2 topic pub --once /voice_text std_msgs/msg/String "data: '前方有障碍物吗'"
ros2 topic pub --once /voice_text std_msgs/msg/String "data: '走了多远'"
```

### 语音指令测试
直接对着麦克风说话：
- "向前走半米"
- "左转九十度"
- "停止"
- "前面有障碍物吗"

## 故障排除

### LLM Agent 不响应
```bash
# 检查环境
conda activate ros2_env
python --version  # 应该是 Python 3.10.x

# 检查服务器
curl http://localhost:8000/v1/models

# 重新构建
colcon build --packages-select robot_agent
source install/setup.bash
```

### Function Calling 失败
```bash
# 运行测试脚本
cd tools
python test_llm_server.py

# 检查日志
ros2 topic echo /robot_command
```

### 语音输入不工作
```bash
# 检查麦克风权限
# 检查 VAD + ASR 模型路径
ls models/asr/
```

## 性能指标

- **FC 延迟**: 1000-1600ms
- **消息发布**: 0.2ms
- **语音识别**: 200-500ms
- **总延迟**: ~2秒 (从语音到机器人动作)

## 支持的指令

### 动作指令
- "向前走X米" (0.05-10.0米)
- "左转X度" (1-360度)
- "右转X度" (1-360度)
- "停止"

### 查询指令
- "前方有障碍物吗" → 激光雷达数据
- "离墙多远" → 激光雷达数据
- "走了多远" → 里程计数据
- "现在什么情况" → 全部传感器数据

## 系统架构

```
麦克风 → VAD断句 → ASR → /voice_text → LLM Agent (FC) → /robot_command → Robot Controller → /cmd_vel → Gazebo 机器人
```

**核心特性**:
- 完全离线运行
- 支持 Function Calling
- 文本模式 FC 兼容
- Python 3.10 环境
- 3B 量化模型 (Q4_K_M)
