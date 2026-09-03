# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Voice-controlled robot system combining offline ASR (SenseVoice), LLM agent (Qwen2.5-3B via Ollama), and ROS2 to control a differential-drive robot in Gazebo simulation. Entirely offline - no cloud APIs.

**Data flow**: Microphone → VAD断句 → ASR → `/voice_text` → LLM Function Calling → `/robot_command` → `/cmd_vel` → Gazebo robot

## Build and Run Commands

### Build
```bash
cd /home/zy/Desktop/workplace/Jetson_llmAgent_ROS2
colcon build --packages-select my_package robot_description robot_agent voice_input state_query voice_output
source install/setup.bash
```

### Run (3 terminals)
```bash
# Terminal 1: Gazebo simulation with differential-drive robot + lidar
ros2 launch robot_description robot_bringup.launch.py

# Terminal 2: LLM agent + robot controller
ros2 launch robot_agent robot_agent_bringup.launch.py

# Terminal 3: Voice input (VAD + ASR)
ros2 run voice_input voice_input_node
```

### Test voice commands
- "向前走半米" → robot moves 0.5m forward
- "左转九十度" → robot turns 90° left  
- "停止" → immediate stop
- "前方有障碍物吗" → query lidar and answer (requires state_query node)

Text-only test: `ros2 topic pub --once /voice_text std_msgs/msg/String "data: '向前走半米'"`

## Architecture

### Two-Layer Contract Design
LLM layer outputs flexible JSON, ROS layer uses typed `RobotCommand.msg`. Conversion happens only at `llm_agent_node.py` - this isolation allows swapping models without changing downstream nodes.

### Core ROS2 Packages

**my_package** (`ament_cmake`): Message definitions
- `RobotCommand.msg`: action / distance / angle / sensor_type
- `QuerySensor.srv`: sensor query service

**robot_agent** (`ament_python`): Brain and muscle
- `llm_agent_node.py`: Subscribes `/voice_text`, calls LLMAgent.chat(), publishes `/robot_command`
- `robot_controller_node.py`: Subscribes `/robot_command`, publishes `/cmd_vel` at 20Hz
- `llm_core.py`: LLM agent with function calling, rejection rules, ASR correction, command caching

**voice_input** (`ament_python`): Ears
- `voice_input_node.py`: Silero VAD + SenseVoice ASR, publishes `/voice_text`

**robot_description** (`ament_cmake`): URDF + Gazebo launch
- Custom differential-drive robot with lidar (not turtlebot3)
- Launch: `robot_bringup.launch.py`

**state_query** (`ament_python`): Sensor queries
- `state_query_node.py`: Handles `/query_sensor` service, reads `/scan` (lidar) and `/odom`

**voice_output** (`ament_python`): Voice output
- Text-to-speech output node

## Critical Design Patterns

### Safety (Robot ≠ Pure Software)
1. **20Hz zero-velocity heartbeat**: Controller continuously publishes to `/cmd_vel` - prevents robot from running at last speed if controller dies
2. **Action completion**: Each movement auto-resets to zero speed
3. **stop highest priority**: Immediate stop command clears any active action
4. **Exit hook**: SIGINT/SIGTERM handler publishes zero speed before shutdown
5. **Parameter validation**: LLM output re-validated in controller (LLM schema is only hint)
6. **Rejection before LLM**: Dangerous commands intercepted before LLM call (zero token cost)

### Message Contract
Only `llm_agent_node.py` converts between LLM JSON output and ROS `RobotCommand.msg`. Downstream nodes only know typed messages - enables hot-swapping LLM models.

### LLM Agent Features (llm_core.py)
- **Rejection rules**: Pre-LLM filtering for dangerous commands ("飞到月球")
- **ASR correction**: Homophone fixes ("左传" → "左转")
- **Command caching**: LRU cache for repeated motion commands (zero latency)
- **Conversation history**: 20-turn limit for context + "再走远一点" references
- **Multi-round FC**: Two-stage for query_sensor (FC1 → real service → FC2 → answer)

## Configuration

### LLM Model
- Requires `ollama pull qwen2.5:3b` (or update `llm_config.json` model field)
- Config at `src/robot_agent/robot_agent/config/llm_config.json`
- Tools defined with JSON schema (move_forward, turn_left, turn_right, stop, query_sensor)

### ASR Models (230MB, not in repo)
Place in `models/asr/`:
- SenseVoice: `wget https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2`
- Silero VAD: `wget https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx`

## Common Development Tasks

### Adding new motion primitives
1. Update `llm_config.json` tool definitions
2. Update `RobotCommand.msg` if new parameters needed
3. Add handling in `robot_controller_node.py` on_cmd()
4. Add validation in `llm_core.py` validate_params()

### Adding new sensor queries
1. Add tool to `llm_config.json`
2. Implement service handler in `state_query_node.py`
3. Update `QuerySensor.srv` if new response fields needed

### Testing ASR without ROS
```bash
cd tools
python3 test_asr.py  # Direct VAD + ASR test
```

### Latency measurement
```bash
python3 tools/latency_recorder.py  # Subscribes /latency_diag + /cmd_vel
```

## Known Constraints

- Motion is open-loop (time-based: 0.2m/s × N seconds), ±10% error
- Use `--once` with `ros2 topic pub` to avoid 1Hz repeats
- Qwen2.5-3B偶尔丢required的type参数 - 已兜底为"all"
- Cache bypass words: "再", "又", "继续", "还", "刚才", "之前"

## Diagnostic Topics

- `/latency_diag` (JSON-in-String): FC latency, message latency, timestamps
- `/agent_answer` (String): LLM response text for sensor queries
