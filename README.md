# 语音大模型机器人控制系统（LLM Agent × ROS2）

> 说一句中文 → 离线语音识别 → LLM Function Calling → ROS2 → Gazebo 仿真车真的动起来
> 端侧全离线：ASR 与 LLM 均在本机推理，不依赖任何云 API

## 成果速览（截至 Day8，2026-08-26）

| 里程碑 | 内容 | 状态 |
| ------ | ---- | ---- |
| ★1 文字闭环 | 终端输入"向前走半米" → 车前进 0.5m | ✅ Day7 |
| ★2 语音闭环 | 说"左转九十度" → 车左转 90° | ✅ Day8 |
| 感知问答 ★3 | "前方有障碍物吗" 基于激光雷达回答 | ⬜ Day9（计划） |

**端到端实测延迟（说完→车动）**：**1.16 ± 0.05 s**（热态 7 条动作类指令）
= VAD 断句 0.50s + ASR 139ms + LLM FC 457ms + 控制 <50ms，分项模型与实测对账吻合。
拒绝类指令（"飞到月球"）在 LLM 调用前被规则拦截，**FC≈1ms、零 token 消耗**。

## 系统架构

```
 麦克风 ──▶ voice_input ──/voice_text──▶ llm_agent ──/robot_command──▶ robot_controller ──/cmd_vel──▶ Gazebo 差速车
            silero VAD 切段                │                                │                            (自写 URDF)
            SenseVoice 离线识别            │ Ollama Qwen2.5-3B              │ 20Hz 心跳发布               /scan /odom
            (sherpa-onnx int8)             │ Function Calling               │ 三条安全兜底
                                          └─ 拒绝规则前置（零 token）        └─ stop 最高优先级
            └────────── /latency_diag 诊断话题 ──────────┐
                                                        ▼
                                          tools/latency_recorder.py（延迟自动采集）
```

**核心设计（两层契约）**：LLM 层输出 JSON（灵活、可换模型），ROS 层用强类型 `RobotCommand.msg`（编译期检查、`ros2 interface show` 自文档）——转换边界只有 llm_agent 一个点。Day8 接入语音时下游**零改动**，这就是消息契约的价值。

## 技术栈

| 组件 | 选型 | 说明 |
| ---- | ---- | ---- |
| ROS2 | Humble（Ubuntu 22.04） | 全部 ament_python + 1 个 ament_cmake（消息生成） |
| 仿真 | Gazebo Fortress + 自写 URDF 差速车 | 2 轮差速 + 激光雷达，不依赖 turtlebot3 |
| LLM | Ollama + Qwen2.5-3B Int4 | 原生 Function Calling，多轮对话记忆 |
| ASR | sherpa-onnx + SenseVoice int8（~230MB） | 完全离线、CPU 实时、中文数字友好 |
| VAD | silero VAD（2MB） | 说话停顿 0.5s 自动断句 |
| 消息 | 自定义 `my_package/msg/RobotCommand` | action / distance(米) / angle(度) / sensor_type |

## 仓库结构

```
ROS2/
├── src/
│   ├── my_package/        # Day2 通讯基础 + RobotCommand.msg（消息定义，ament_cmake）
│   ├── action_demo/       # Day3 Action（Goal/Feedback/Result）
│   ├── robot_description/ # Day5 自写 URDF 差速车 + Gazebo 一键启动
│   ├── robot_agent/       # Day7 llm_agent（大脑）+ robot_controller（肌肉）+ llm_core
│   └── voice_input/       # Day8 语音输入节点（VAD + SenseVoice）
├── tools/
│   ├── latency_recorder.py      # 延迟自动采集器（订阅 /latency_diag + /cmd_vel，出表+CSV）
│   └── test_asr.py              # ASR 裸测脚本（无 ROS）
├── models/asr/            # ASR 模型（SenseVoice int8 + silero VAD，不入库）
├── results/               # 延迟 CSV 输出
├── DOC/                   # 每日实验手册 + 踩坑记录（experiment_4~8.md 等）
└── llm/                   # Day6 LLM Agent 原型与测试
```

## 快速开始

### 1. 依赖准备（一次性）

```bash
# Python 依赖（装进系统 python3）
python3 -m pip install sherpa-onnx sounddevice ollama numpy

# 系统库（sounddevice 需要）
sudo apt install libportaudio2

# LLM 模型
ollama pull qwen2.5:3b

# ASR 模型（~230MB，放 models/asr/）
mkdir -p models/asr && cd models/asr
wget https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2
tar xvf sherpa-onnx-sense-voice-*.tar.bz2 && mv sherpa-onnx-sense-voice-* sense-voice
wget https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx
```

### 2. 编译

```bash
cd /mnt/apfs/workplace/ROS2
colcon build --packages-select my_package robot_description robot_agent voice_input
source install/setup.bash
```

### 3. 启动（3 个终端，均先 `source install/setup.bash`）

```bash
# 终端1：Gazebo 仿真（差速车 + 激光雷达）
ros2 launch robot_description robot_bringup.launch.py

# 终端2：大脑 + 肌肉
ros2 launch robot_agent robot_agent_bringup.launch.py

# 终端3：耳朵（麦克风）
ros2 run voice_input voice_input_node
```

### 4. 说话测试

对着麦克风说（说完停顿半秒等断句）：

```
"左转九十度"   → 车左转 90°
"向前走一米"   → 车前进 1m
"再走远一点"   → 对话记忆生效，继续前进
"停下"        → 立即停车
"飞到月球"     → 拒绝，车不动（零 token）
```

无麦克风时可用文字替代：`ros2 topic pub --once /voice_text std_msgs/msg/String "data: '向前走半米'"`

### 5. 延迟数据采集（可选）

```bash
# 终端4
python3 tools/latency_recorder.py
# 热身（不记录）：ros2 topic pub --once /voice_text std_msgs/msg/String "data: '停止'"
# 说测试指令 → Ctrl+C 出 Markdown 表 + results/day8_latency.csv
```

## 性能实测（Day8，PC · Qwen2.5-3B · SenseVoice int8）

| 指标 | 实测值 |
| ---- | ------ |
| ASR 识别耗时 | 139 ms 均值（12 条热态） |
| LLM Function Calling | 457 ms 均值（10 条热态） |
| **端到端（动作类）** | **1.16 ± 0.05 s**（7 条） |
| 端到端（停止） | 1.01 ± 0.03 s（3 条） |
| 拒绝路径 FC | ≈1 ms（规则前置，零 token） |
| 冷启动 FC | 2.4 s（首条指令，热身后消除） |

完整 13 条原始数据：[DOC/experiment_8.md](DOC/experiment_8.md) Step8 / [results/](results/) CSV。

## 安全设计（机器人系统 ≠ 纯软件）

1. **动作完成发零速**：每个动作到期归零
2. **20Hz 零速心跳（看门狗）**：静止期持续发零速——Gazebo DiffDrive 会保持末速，控制器死掉车就永远跑
3. **stop 最高优先级**：立即清空当前动作
4. **退出钩子**：Ctrl+C / kill 前最后发一次零速（自定义信号处理器保证 context 存活时发出）
5. **LLM 输出参数校验**：schema 的 min/max 只是提示，controller 侧再验一遍；非法即丢弃
6. **拒绝规则前置**：危险指令在 LLM 调用前拦截——安全设计同时是成本设计

核心思想：**LLM 可以卡死，车不能停不下来**（fail-safe）。

## 设计决策（为什么这么做）

- **LLM 输出动作原语而非速度值**：意图层（可换模型）与执行层（可单测可回滚）解耦
- **ASR 选 SenseVoice 而非 Whisper**：离线 / CPU 实时 / 中文数字友好 / aarch64 wheel（Day11 Jetson 复用）
- **VAD 自动断句 + 手动录音双模式**：自动体验好，手动永远可兜底（演示现场保险）
- **模型与代码分离**：200MB+ 模型放 `models/`（不入包不入库），路径 ROS 参数注入
- **诊断通道 JSON-in-String**：dev-only 观测通道不为它建 msg（正式监控再升级）
- **延迟采集零侵入**：只订阅 /latency_diag + /cmd_vel，不改执行节点，采集器可随时启停

## 进度

- [x] Day1-3：ROS2 基础（话题/服务/Action/launch）
- [x] Day4：传感器数据流 + TF（Gazebo Fortress）
- [x] Day5：自写 URDF 差速车（2轮差速 + 激光雷达）
- [x] Day6：LLM Agent（FC + 拒绝 + 多轮记忆，10/10 用例通过）
- [x] Day7：★1 文字闭环（llm_agent + robot_controller + 三条安全兜底）
- [x] Day8：★2 语音闭环（SenseVoice + silero VAD + 延迟采集基建）
- [ ] Day9：★3 传感器感知问答（/query_sensor 服务 + 环境摘要回填 LLM）
- [ ] Day10：TTS 语音播报（sherpa-onnx VITS）
- [ ] Day11：分布式多机（ASR+LLM 拆 Jetson，DDS 跨机）
- [ ] Day12-14：打磨交付 + 文章 + 投递

每日详细手册与踩坑记录见 [DOC/](DOC/)。

## 已知限制

- 前进/转弯为**开环时间法**（0.2m/s × N 秒），实测误差 ±10%——闭环（订阅 /odom）留 Day9 后
- `ros2 topic pub` 不带 `--once` 会 1Hz 重复发布，测试务必带 `--once`
- ASR 热身指令要用"停止"（"热身"会被 LLM 执行成 move_forward 0.5m）
