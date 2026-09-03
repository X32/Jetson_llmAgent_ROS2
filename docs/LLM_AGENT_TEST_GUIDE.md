# LLM Agent 节点测试指南

## 概述

本文档提供了 `llm_agent_node.py` 节点的完整测试方案，包括多种测试方法和故障排查指南。

## 测试环境准备

### 前置条件
1. ✅ llama.cpp 服务器运行中 (http://localhost:8000)
2. ✅ Python 3.10 环境 (ros2_env)
3. ✅ ROS2 工作空间已构建

### 环境检查
```bash
# 检查 LLM 服务器
curl http://localhost:8000/v1/models

# 激活 Python 环境
source ~/miniconda3/etc/profile.d/conda.sh
conda activate ros2_env
python --version  # 应显示 Python 3.10.x

# Source ROS2
source install/setup.bash
```

## 测试方法

### 方法1：直接运行节点（最简单）

#### 步骤
```bash
# 启动节点
LLAMACPP=1 ros2 run robot_agent llm_agent
```

#### 预期输出
```
[INFO] [llm_agent]: llm_agent 就绪（后端=llama.cpp，模型=...），等待 /voice_text ...
```

### 方法2：手动 ROS2 命令测试

#### 终端1：启动节点
```bash
source ~/miniconda3/etc/profile.d/conda.sh
conda activate ros2_env
source install/setup.bash
LLAMACPP=1 ros2 run robot_agent llm_agent
```

#### 终端2：发送测试指令
```bash
source ~/miniconda3/etc/profile.d/conda.sh
conda activate ros2_env
source install/setup.bash

# 测试1: 向前走
ros2 topic pub --once /voice_text std_msgs/msg/String "data: '向前走半米'"

# 测试2: 左转
ros2 topic pub --once /voice_text std_msgs/msg/String "data: '左转九十度'"

# 测试3: 停止
ros2 topic pub --once /voice_text std_msgs/msg/String "data: '停止'"

# 测试4: 右转
ros2 topic pub --once /voice_text std_msgs/msg/String "data: '右转四十五度'"
```

#### 终端3：监听输出
```bash
ros2 topic echo /robot_command
```

#### 预期输出示例
```
action: move_forward
distance: 0.5
angle: 0.0
sensor_type: ''
---
action: turn_left
distance: 0.0
angle: 90.0
sensor_type: ''
---
action: stop
distance: 0.0
angle: 0.0
sensor_type: ''
```

### 方法3：Python 自动化测试脚本

#### 使用测试脚本
```bash
cd tools
python test_llm_agent_node.py
```

#### 测试脚本功能
- 自动发送预定义测试指令
- 监听 `/robot_command` 输出
- 统计测试结果
- 实时显示测试进度

#### 预期输出
```
=== LLM Agent 节点测试 ===

--- 测试 1/5: 向前走半米 ---
📤 发送测试指令 #1: 向前走半米
✅ 收到机器人指令 #1: action=move_forward distance=0.5 angle=0.0

--- 测试 2/5: 左转九十度 ---
📤 发送测试指令 #2: 左转九十度
✅ 收到机器人指令 #2: action=turn_left distance=0.0 angle=90.0

=== 测试完成 ===
发送: 5 条指令
接收: 3 条机器人指令
```

### 方法4：交互式测试脚本

#### 使用交互式脚本
```bash
cd tools
./test_llm_agent.sh
```

#### 测试模式选择
1. **基础功能测试** - 不需要其他节点
2. **完整功能测试** - 需要 state_query_node
3. **性能压力测试** - 连续指令测试
4. **交互式测试** - 手动输入指令

## 传感器查询测试

### 准备工作
```bash
# 启动 state_query_node
ros2 run state_query state_query_node
```

### 测试指令
```bash
# 激光雷达查询
ros2 topic pub --once /voice_text std_msgs/msg/String "data: '前方有障碍物吗'"

# 里程查询
ros2 topic pub --once /voice_text std_msgs/msg/String "data: '走了多远'"

# 全部传感器
ros2 topic pub --once /voice_text std_msgs/msg/String "data: '现在什么情况'"
```

### 监听查询答案
```bash
ros2 topic echo /agent_answer
```

## 监控和调试工具

### 节点状态检查
```bash
# 查看运行中的节点
ros2 node list | grep llm_agent

# 查看节点详细信息
ros2 node info /llm_agent

# 查看节点参数
ros2 param list /llm_agent
```

### 话题连接检查
```bash
# 查看话题信息
ros2 topic info /voice_text
ros2 topic info /robot_command
ros2 topic info /agent_answer

# 查看话题发布者/订阅者
ros2 topic info /voice_text --verbose
```

### 实时监控
```bash
# 监听输入话题
ros2 topic echo /voice_text

# 监听输出话题
ros2 topic echo /robot_command

# 监听查询答案
ros2 topic echo /agent_answer

# 监听延迟诊断
ros2 topic echo /latency_diag
```

### 性能分析
```bash
# 查看 TF 变换
ros2 run tf2_tools view_frames

# 查看话题频率
ros2 topic hz /robot_command

# 查看带宽使用
ros2 topic bw /robot_command
```

## 延迟诊断

### 延迟指标
- **FC 延迟**: Function Calling 处理时间 (1000-1600ms)
- **消息延迟**: ROS2 消息发布时间 (~0.2ms)
- **总延迟**: 从语音输入到机器人动作的总时间

### 延迟监控
```bash
# 实时延迟监控
ros2 topic echo /latency_diag
```

### 延迟数据分析
```json
{
  "stage": "llm",
  "text": "向前走半米",
  "status": "success",
  "action": "move_forward",
  "fc_ms": 1270,
  "msg_ms": 0.2,
  "done_at": 1788244419.007
}
```

## 故障排查

### 节点无响应

#### 检查节点状态
```bash
ros2 node list | grep llm_agent
```

#### 检查环境变量
```bash
echo $LLAMACPP  # 应该为 1
python --version  # 应该为 3.10.x
```

#### 检查 LLM 服务器
```bash
cd tools
python test_llm_server.py
```

### Function Calling 失败

#### 测试 LLM 服务器
```bash
cd tools
python test_llm_server.py

# 或使用 OpenAI 客户端测试
python test_fc.py
```

#### 检查配置文件
```bash
cat install/robot_agent/lib/python3.10/site-packages/robot_agent/config/llm_config_llamacpp.json
```

#### 查看详细日志
```bash
# 启动时增加日志级别
LLAMACPP=1 ros2 run robot_agent llm_agent --ros-args --log-level debug
```

### 传感器查询失败

#### 检查服务可用性
```bash
ros2 service list | grep query_sensor
ros2 service type /query_sensor
```

#### 手动调用服务
```bash
ros2 service call /query_sensor my_package/srv/QuerySensor "{type: lidar}"
```

#### 检查 state_query_node
```bash
ros2 node list | grep state_query
ros2 node info /state_query
```

### 性能问题

#### 检查系统资源
```bash
# CPU 使用
top -p $(pgrep -f llm_agent)

# 内存使用
free -h

# GPU 使用 (Jetson)
tegrastats
```

#### 检查话题队列
```bash
# 检查消息队列深度
ros2 topic info /voice_text --verbose
```

## 测试用例集

### 基础动作测试
```python
test_cases = [
    ("向前走半米", "move_forward", 0.5),
    ("向前走1米", "move_forward", 1.0),
    ("左转九十度", "turn_left", 90.0),
    ("右转四十五度", "turn_right", 45.0),
    ("停止", "stop", 0.0),
]
```

### 边界值测试
```python
boundary_tests = [
    ("向前走0.05米", "move_forward", 0.05),  # 最小值
    ("向前走10米", "move_forward", 10.0),     # 最大值
    ("左转1度", "turn_left", 1.0),           # 最小角度
    ("左转360度", "turn_left", 360.0),       # 最大角度
]
```

### 传感器查询测试
```python
sensor_tests = [
    ("前方有障碍物吗", "lidar"),
    ("离墙多远", "lidar"),
    ("走了多远", "odom"),
    ("现在什么情况", "all"),
]
```

## 自动化测试套件

### 完整自动化测试
```bash
cd tools
python test_llm_agent_node.py
```

### 压力测试
```bash
# 发送100个连续指令
for i in {1..100}; do
    ros2 topic pub --once /voice_text std_msgs/msg/String "data: '向前走0.5米'"
    sleep 0.1
done
```

### 回归测试
```bash
# 使用测试脚本
./test_llm_agent.sh
# 选择模式1进行基础功能测试
```

## 性能基准

### 预期性能指标
| 指标 | 预期值 | 说明 |
|------|--------|------|
| FC 延迟 | 1000-1600ms | Function Calling 处理时间 |
| 消息延迟 | <1ms | ROS2 消息发布时间 |
| 话题频率 | 按需 | 根据语音输入频率 |
| 内存占用 | <500MB | 节点进程内存使用 |
| CPU 占用 | <10% | 空闲时 CPU 占用 |

### 性能优化建议
1. 使用指令缓存减少重复 FC 调用
2. 调整上下文长度限制 (max_turns=20)
3. 优化 LLM 模型量化级别
4. 调整话题队列深度

## 集成测试

### 完整系统测试
```bash
# 终端1: Gazebo 仿真
ros2 launch robot_description robot_bringup.launch.py

# 终端2: LLM Agent + Controller
ros2 launch robot_agent robot_agent_bringup.launch.py

# 终端3: 语音输入
ros2 run voice_input voice_input_node

# 终端4: 测试
./tools/test_llm_agent.sh
```

### 端到端测试
1. 启动完整系统
2. 使用语音输入测试
3. 观察 Gazebo 中的机器人动作
4. 验证传感器查询功能

## 测试报告模板

```markdown
# LLM Agent 测试报告

## 测试环境
- 日期: YYYY-MM-DD
- 测试人员:
- 硬件配置: Jetson Orin
- 软件版本: ROS2 Humble, Python 3.10

## 测试结果
- 基础动作测试: ✅ 5/5 通过
- 传感器查询测试: ✅ 4/4 通过
- 边界值测试: ✅ 8/8 通过
- 性能测试: ✅ 符合预期

## 问题记录
- 问题描述:
- 解决方案:

## 性能数据
- 平均 FC 延迟: 1200ms
- 平均消息延迟: 0.2ms
- 内存占用: 450MB
```

## 参考文档

- [QUICKSTART.md](../QUICKSTART.md) - 快速启动指南
- [LLM_BACKEND_GUIDE.md](./LLM_BACKEND_GUIDE.md) - LLM 后端指南
- [LLAMACPP_FC_SOLUTION.md](./LLAMACPP_FC_SOLUTION.md) - FC 解决方案

## 常用命令速查

```bash
# 启动节点
LLAMACPP=1 ros2 run robot_agent llm_agent

# 发送测试指令
ros2 topic pub --once /voice_text std_msgs/msg/String "data: '测试指令'"

# 监听输出
ros2 topic echo /robot_command

# 运行测试脚本
cd tools && python test_llm_agent_node.py

# 检查节点状态
ros2 node info /llm_agent

# 查看延迟
ros2 topic echo /latency_diag
```

---

**最后更新**: 2024-09-01
**维护者**: Claude Code Assistant
